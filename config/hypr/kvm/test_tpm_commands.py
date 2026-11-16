"""TPM command regressions; fixtures never boot a guest or change TPM keys."""
import copy
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/lib')]
import launcher
from model import VMConfig
import portable
from tabs_paths import PathsTab
from tabs_tpm import TpmTab
import tpm_actions


def arguments(argv, flag):
    return [argv[i + 1] for i, item in enumerate(argv[:-1]) if item == flag]


class Field:
    def __init__(self, value=''):
        self.value = value

    def text(self):
        return self.value

    def setText(self, value):
        self.value = value


class Radio:
    def __init__(self):
        self.checked = False
        self.other = None

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked
        if checked and self.other:
            self.other.checked = False


def tab_for(cfg):
    tab = SimpleNamespace(cfg=cfg, pt_path=Field('/dev/tpm0'), pt_cancel=Field('/dev/null'),
                          state_dir=Field(), widgets={}, rb_emulated=Radio(), rb_passthrough=Radio(),
                          _sync_backend_ui=Mock(), changed=Mock(), check_attestation=Mock())
    tab.rb_emulated.other = tab.rb_passthrough
    tab.rb_passthrough.other = tab.rb_emulated
    tab.rb_emulated.setChecked(True)
    tab._apply_backend = lambda emit=True: TpmTab._apply_backend(tab, emit)
    tab._chardev = lambda cid: next((c for c in cfg.data.get('chardevs', []) if c.get('id') == cid), None)
    return tab


class TPMCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='kvm-tpm-command-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {'XETAL_KVM_DATA': str(self.root)})
        env.start(); self.addCleanup(env.stop)
        self.socket = {'_positional': ['socket'], 'id': 'chrtpm', 'path': str(self.root / 'tpm.sock')}
        self.choice = dict(mode='emulator', label='Fixture TPM', binary='/fixture/swtpm',
                           state=str(self.root / 'private-state'))

    def config(self, chars=None, recorded=False):
        return VMConfig({'_meta': {'binary': 'qemu-system-x86_64'},
                         'simple': {'tpmdev': 'emulator,id=tpm-tpm0,chardev=chrtpm'},
                         'order': ([['chardev', 0]] if recorded else []) + [['tpmdev', None]],
                         'chardevs': copy.deepcopy(chars if chars is not None else [self.socket])},
                        root=str(self.root))

    def expected(self, path=None):
        return 'socket,id=chrtpm,path=' + (path or self.socket['path']).replace(',', ',,')

    def test_recorded_and_appended_structured_sockets_emit_complete_arguments(self):
        for recorded in (False, True):
            for raw in (None, '', '   '):
                with self.subTest(recorded=recorded, raw=raw):
                    entry = dict(self.socket)
                    if raw is not None: entry['_raw'] = raw
                    cfg = self.config([entry], recorded)
                    before = copy.deepcopy(cfg.data['chardevs'])
                    self.assertEqual(arguments(cfg.to_argv(), '-chardev'), [self.expected()])
                    self.assertEqual(cfg.data['chardevs'], before)

    def test_raw_imports_remain_authoritative(self):
        raw = 'socket,id=imported,path=/fixture/original.sock,reconnect-ms=500'
        entry = dict(self.socket, _raw=raw, path='/fixture/structured-is-not-authoritative.sock')
        for recorded in (False, True):
            self.assertEqual(arguments(self.config([entry], recorded).to_argv(), '-chardev'), [raw])

    def test_structured_values_escape_commas_and_boolean_switches(self):
        entry = dict(self.socket, path='/fixture/with,comma.sock', server=True, wait=False)
        self.assertEqual(arguments(self.config([entry]).to_argv(), '-chardev'),
                         ['socket,id=chrtpm,path=/fixture/with,,comma.sock,server=on,wait=off'])

    def test_missing_backend_or_id_is_rejected_before_command_generation(self):
        for entry in ({}, {'id': 'chrtpm'}, {'_positional': ['socket']},
                      {'_positional': [''], 'id': 'chrtpm'},
                      {'_positional': ['socket'], 'id': ''}):
            for recorded in (False, True):
                with self.subTest(entry=entry, recorded=recorded):
                    with self.assertRaises(ValueError): self.config([entry], recorded).to_argv()

    def test_invalid_disabled_socket_is_not_emitted_or_validated(self):
        cfg = self.config([{'_disabled': True}])
        self.assertEqual(arguments(cfg.to_argv(), '-chardev'), [])
        self.assertFalse(any('chardev' in message.lower() for _, message in cfg.validate()))

    def test_structured_socket_survives_json_save_reload(self):
        cfg = self.config(recorded=True)
        path = self.root / 'session.json'
        cfg.save(path)
        loaded = VMConfig.load(path, root=str(self.root))
        self.assertEqual(arguments(loaded.to_argv(), '-chardev'), [self.expected()])

    def test_activation_builds_a_complete_socket_and_reuses_it(self):
        cfg = self.config([])
        tab = tab_for(cfg)
        for _ in range(3): tpm_actions.activate(tab, self.choice)
        path = str(self.root / 'run/swtpm.sock')
        self.assertEqual(arguments(cfg.to_argv(), '-chardev'), [self.expected(path)])
        self.assertEqual(cfg.data['chardevs'][0]['_raw'], self.expected(path))
        self.assertEqual(len(cfg.devices), 1)

    def test_backend_round_trip_preserves_socket_without_duplicates(self):
        cfg = self.config()
        tab = tab_for(cfg)
        for _ in range(3):
            tpm_actions.activate(tab, dict(mode='passthrough', label='Physical TPM', device='/dev/tpm0'))
            self.assertEqual(arguments(cfg.to_argv(), '-chardev'), [])
            self.assertTrue(cfg.simple['tpmdev'].startswith('passthrough,'))
            tpm_actions.activate(tab, self.choice)
            self.assertEqual(arguments(cfg.to_argv(), '-chardev'), [self.expected()])
        self.assertEqual(len(cfg.data['chardevs']), 1)

    def test_save_in_physical_mode_keeps_custom_socket_for_advanced_toggle(self):
        entry = dict(self.socket, path=str(self.root / 'custom.sock'),
                     _raw='socket,id=chrtpm,path=' + str(self.root / 'custom.sock') + ',reconnect-ms=500')
        cfg = self.config([entry], recorded=True)
        cfg.devices.append({'driver': 'tpm-crb', 'id': 'tpm0', 'tpmdev': 'tpm-tpm0'})
        tab = tab_for(cfg)
        tab.rb_passthrough.setChecked(True); tab._apply_backend(emit=False)
        cfg.compact()  # checkpoint.save compacts before writing the saved profile.
        path = self.root / 'session.json'; cfg.save(path)
        reopened = VMConfig.load(path, root=str(self.root))
        self.assertEqual(arguments(reopened.to_argv(), '-chardev'), [])
        tab = tab_for(reopened); tab._apply_backend(emit=False)
        self.assertEqual(arguments(reopened.to_argv(), '-chardev'), [entry['_raw']])
        self.assertEqual(reopened.devices[0]['driver'], 'tpm-crb')

    def test_advanced_emulator_toggle_restores_socket_missing_from_old_saved_profile(self):
        cfg = self.config([])
        cfg.simple['tpmdev'] = 'passthrough,id=tpm-tpm0,path=/dev/tpm0,cancel-path=/dev/null'
        cfg.data['tpm_chardev'] = 'remembered-tpm'
        tab_for(cfg)._apply_backend(emit=False)
        self.assertEqual(arguments(cfg.to_argv(), '-chardev'),
                         ['socket,id=remembered-tpm,path=' + str(self.root / 'run/swtpm.sock')])
        self.assertIn('chardev=remembered-tpm', cfg.simple['tpmdev'])

    def test_path_edit_builds_missing_raw_and_preserves_other_options(self):
        for raw in (None, '', 'socket,id=chrtpm,path=/fixture/old,,name.sock,reconnect-ms=500'):
            with self.subTest(raw=raw):
                entry = dict(self.socket)
                if raw is not None: entry['_raw'] = raw
                cfg = self.config([entry]); tab = tab_for(cfg)
                value = r'/fixture/new,dir/back\slash.sock'
                PathsTab._chardev_path_set(tab, 'chrtpm', value)
                emitted = arguments(cfg.to_argv(), '-chardev')[0]
                self.assertTrue(emitted.startswith(self.expected(value)))
                if raw: self.assertTrue(emitted.endswith(',reconnect-ms=500'))
                self.assertEqual(cfg.data['chardevs'][0]['path'], value)

    def test_path_edit_does_not_replace_path_text_inside_another_value(self):
        entry = dict(self.socket, _raw='socket,id=chrtpm,logfile=/fixture/a,,path=keep,path=/old')
        cfg = self.config([entry]); tab = tab_for(cfg)
        PathsTab._chardev_path_set(tab, 'chrtpm', '/new,')
        self.assertEqual(arguments(cfg.to_argv(), '-chardev'),
                         ['socket,id=chrtpm,logfile=/fixture/a,,path=keep,path=/new,,'])

    def test_preflight_reports_invalid_socket_before_any_argv_consumer(self):
        cfg = self.config([{'id': 'broken'}])
        with patch.object(cfg, 'to_argv', side_effect=AssertionError('Invalid chardev reached argv')):
            checks = launcher.preflight(cfg, {'vcpupin': [{'vcpu': 0, 'cpuset': '0'}]})
        self.assertTrue(any(severity == 'error' and 'chardev' in message.lower() for severity, message in checks))

    def test_preflight_checks_structured_socket_path(self):
        cfg = VMConfig(portable.configuration('windows'), root=str(self.root))
        cfg.data['chardevs'].append(dict(_positional=['socket'], id='other', path=str(self.root / 'missing.sock')))
        checks = launcher.preflight(cfg, {})
        self.assertTrue(any(severity == 'error' and 'chardev other connects to' in message for severity, message in checks))

    def test_generated_launch_script_contains_complete_tpm_and_valid_bash(self):
        cfg = VMConfig(portable.configuration('windows'), root=str(self.root))
        for char in cfg.data['chardevs']: char.pop('_raw', None)
        script = launcher.build_script(cfg, {}, reboot_after=False)
        self.assertNotIn("-chardev ''", script)
        self.assertIn('-chardev socket,id=chrtpm,path=', script)
        self.assertIn('$(uname -n)', script)
        subprocess.run(['bash', '-n'], input=script, text=True, check=True)


class TPMPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.application = QApplication.instance() or QApplication([])

    def test_real_refresh_replaces_old_command_and_clears_invalid_preview(self):
        from PyQt6.QtWidgets import QPlainTextEdit
        from vmstart2 import VMStart2
        cfg = VMConfig({'_meta': {'binary': 'qemu-system-x86_64'}, 'chardevs': [
            {'_positional': ['socket'], 'id': 'chrtpm', 'path': '/fixture/new.sock'}]})
        preview = QPlainTextEdit(); preview.setPlainText('old command')
        window = SimpleNamespace(cfg=cfg, preview=preview, chk_standalone=SimpleNamespace(isChecked=lambda: True),
                                 _fill_features=Mock(), _fill_smbios=Mock(), _update_modified=Mock(), _refresh_sections=Mock())
        VMStart2._refresh_all(window)
        self.assertEqual(arguments(shlex.split(preview.toPlainText()), '-chardev'),
                         ['socket,id=chrtpm,path=/fixture/new.sock'])
        cfg.data['chardevs'][0].pop('_positional')
        VMStart2._refresh_all(window)
        self.assertIn('Command unavailable', preview.toPlainText())
        self.assertNotIn('qemu-system-x86_64', preview.toPlainText())
        preview.deleteLater()


if __name__ == '__main__':
    unittest.main()
