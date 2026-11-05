"""Appearance fixtures: no host boot writes, authentication or mounted drives."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grub_appearance as appearance
import grub_editor as grub


CONFIG = '''set default=1
set timeout=7
set theme=/old-theme/theme.txt
menuentry 'Linux' --id=linux {
  search --fs-uuid --set=root 1234-abcd
  linux /vmlinuz root=UUID=1234-abcd quiet
  initrd /initramfs.img
}
menuentry 'Firmware' { fwsetup; }
'''


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-grub-appearance-')
        self.addCleanup(temporary.cleanup); self.root = Path(temporary.name)
        (self.root/'boot/grub').mkdir(parents=True); (self.root/'etc/grub.d').mkdir(parents=True)
        self.config = self.root/'boot/grub/grub.cfg'; self.config.write_text(CONFIG)
        self.store = appearance.AppearanceStore(self.root, shutil.which('grub-script-check') or '/bin/true')
        self.options = appearance.presets()[0]['options']
        self.real_command = grub.command

    def command(self, args, **kwargs):
        if Path(args[0]).name in ('grub-probe', 'grub2-probe'): return b'1234-abcd\n'
        if Path(args[0]).name in ('grub-mkrelpath', 'grub2-mkrelpath'):
            return ('/'+str(Path(args[-1]).relative_to(self.root))+'\n').encode()
        return self.real_command(args, **kwargs)

    def apply(self, **overrides):
        with self.store.locked(), patch.object(grub, 'command', side_effect=self.command):
            return self.store.apply({**self.options, **overrides}, self.store.revision(),
                grub.digest(self.config.read_bytes()), prepare_fn=appearance.prepare)

    def test_presets_and_custom_options_render_without_touching_boot_files(self):
        for preset in appearance.presets():
            with self.subTest(theme=preset['id']):
                value = appearance.preview(preset['options'], ['My system', 'Firmware settings'])
                self.assertTrue(base64.b64decode(value['image']).startswith(b'\x89PNG'))
                self.assertTrue(value['background_sha'])
        self.assertEqual(self.config.read_text(), CONFIG)
        self.assertFalse(self.store.state.exists())
        for position in ('left', 'center', 'right'):
            value = appearance.preview({**self.options, 'background': '', 'layout': position,
                                        'heading': 'A "quoted" title', 'hints': False})
            self.assertEqual(value['background_sha'], '')
            text = appearance.theme_text({**self.options, 'layout': position, 'heading': 'A "quoted" title'})
            self.assertIn('A \\"quoted\\" title', text)

    def test_apply_preserves_every_boot_entry_and_survives_generator_use(self):
        self.apply(heading='My boot screen')
        current = self.config.read_text()
        self.assertEqual(appearance.replace_appearance(current, ''), CONFIG)
        self.assertEqual([(e['name'], e['commands']) for e in grub.menu_entries(current)],
                         [(e['name'], e['commands']) for e in grub.menu_entries(CONFIG)])
        block = current[len(CONFIG):]
        self.assertNotIn('--set=root', block); self.assertNotIn('set default=', block); self.assertNotIn('set timeout=', block)
        self.assertIn('--set=fusion_theme_device', block)
        self.assertEqual(subprocess.check_output([str(self.store.generator)]).decode(), block)
        state = self.store.status(); self.assertTrue(state['active']); self.assertTrue(state['can_undo'])
        source = Path(state['options']['background']); self.assertTrue(source.is_file())
        self.assertTrue((source.parent/'theme.txt').is_file())
        self.assertIn('My boot screen', (source.parent/'theme.txt').read_text())
        self.assertFalse((self.root/'etc/default/grub').exists())

    def test_reapply_then_undo_retains_old_design_assets(self):
        self.apply(); first = self.config.read_bytes(); original_source = self.store.status()['options']['background']
        self.apply(layout='right', size=28)
        self.assertEqual(self.config.read_text().count(appearance.BEGIN), 1)
        with self.store.locked(): self.store.undo(self.store.revision())
        self.assertEqual(self.config.read_bytes(), first); self.assertTrue(Path(original_source).is_file())
        self.assertEqual(self.store.status()['options']['layout'], 'left')

    def test_system_appearance_and_undo_keep_original_theme(self):
        self.apply(); applied = self.config.read_bytes()
        with self.store.locked():
            self.store.system_appearance(self.store.revision(), grub.digest(applied))
        self.assertEqual(self.config.read_text(), CONFIG); self.assertFalse(self.store.generator.exists())
        with self.store.locked(): self.store.undo(self.store.revision())
        self.assertEqual(self.config.read_bytes(), applied); self.assertTrue(self.store.generator.exists())

    def test_external_menu_change_rejected_before_assets_are_prepared(self):
        revision = self.store.revision(); old = grub.digest(self.config.read_bytes())
        self.config.write_text(CONFIG+'# kernel update\n')
        with self.store.locked(), patch.object(appearance, 'prepare') as prepare:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                self.store.apply(self.options, revision, old, prepare_fn=prepare)
            prepare.assert_not_called()
        self.assertFalse(self.store.assets.exists())

    def test_undo_does_not_overwrite_an_entry_edit(self):
        self.apply(); self.config.write_text(self.config.read_text()+'# another editor\n')
        current = self.config.read_bytes()
        with self.store.locked(), self.assertRaisesRegex(RuntimeError, 'Another tool'):
            self.store.undo(self.store.revision())
        self.assertEqual(self.config.read_bytes(), current)

    def test_failed_validation_and_publication_leave_original_menu(self):
        original = self.config.read_bytes()
        calls = 0
        checker = self.store.check
        def fail_candidate(text):
            nonlocal calls
            calls += 1
            if calls == 2: raise RuntimeError('candidate rejected')
            checker(text)
        with patch.object(self.store, 'check', side_effect=fail_candidate), self.assertRaisesRegex(RuntimeError, 'candidate'):
            self.apply()
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse(self.store.generator.exists())
        self.assertEqual(list(self.store.assets.iterdir()), [])
        atomic = grub.atomic
        def fail_config(path, data, mode=0o600):
            if path == self.config and appearance.BEGIN.encode() in data: raise OSError('write failed')
            return atomic(path, data, mode)
        with patch.object(grub, 'atomic', side_effect=fail_config), self.assertRaisesRegex(OSError, 'write failed'):
            self.apply()
        self.assertEqual(self.config.read_bytes(), original); self.assertFalse(self.store.generator.exists())
        self.assertFalse((self.store.state/'pending.json').exists())

    def test_interrupted_transaction_is_recovered(self):
        with self.store.locked():
            targets = self.store.unchanged_targets(); targets['config'] = ((CONFIG+'# pending\n').encode(), 0o644)
            targets['generator'] = (b'#!/bin/sh\n# pending\n', 0o755)
            record = self.store.snapshot(targets)
            grub.atomic(self.store.state/'pending.json', grub.encoded(record))
            grub.atomic(self.store.generator, targets['generator'][0], 0o755)
        with self.store.locked(): pass
        self.assertEqual(self.config.read_text(), CONFIG); self.assertFalse(self.store.generator.exists())

    def test_incomplete_assets_unknown_settings_and_changed_image_are_rejected(self):
        for value in ({'size': 200}, {'accent': 'red"; set root=bad'}, {'heading': 'bad\ntext'}, {'background': 'relative.png'}):
            with self.assertRaises(ValueError): appearance.normalize({**self.options, **value})
        with self.assertRaisesRegex(ValueError, 'changed'): appearance.prepare(self.options, 'wrong-image-hash')
        with self.store.locked(), self.assertRaisesRegex(ValueError, 'incomplete'):
            self.store.apply(self.options, self.store.revision(), grub.digest(self.config.read_bytes()),
                prepare_fn=lambda *_: {'files': {}})
        self.assertEqual(self.config.read_text(), CONFIG)

    def test_forwarding_config_and_symlink_destination_rejected(self):
        self.config.write_text('configfile /real/menu/grub.cfg\n')
        with self.assertRaisesRegex(RuntimeError, 'forwarding'): self.apply()
        self.config.write_text(CONFIG)
        self.store.assets.parent.mkdir(); self.store.assets.symlink_to(self.root/'elsewhere')
        with self.assertRaisesRegex(RuntimeError, 'symbolic link'): self.apply()

    def test_damaged_or_nested_markers_are_not_silently_rewritten(self):
        with self.assertRaises(ValueError): appearance.replace_appearance(CONFIG+appearance.BEGIN+'\n', '')
        with self.assertRaises(ValueError): appearance.appearance_block('bad;halt', '/boot/themes/theme')
        with self.assertRaises(ValueError): appearance.appearance_block('1234-abcd', '/boot/$(evil)')

    def test_picture_preparation_drops_root_privileges(self):
        result = subprocess.CompletedProcess([], 0, b'{"files": {}}', b'')
        uid = os.getuid()
        if uid == 0: self.skipTest('This fixture expects the desktop test user.')
        with patch.object(os, 'geteuid', return_value=0), patch.dict(os.environ, {'PKEXEC_UID': str(uid)}), \
             patch.object(subprocess, 'run', return_value=result) as child:
            appearance.prepared_as_user(self.options, 'sha')
        self.assertEqual(child.call_args.kwargs['user'], uid)
        self.assertIn('group', child.call_args.kwargs)
        self.assertIn('extra_groups', child.call_args.kwargs)
        self.assertEqual(child.call_args.args[0][1], '-I')
        with patch.object(os, 'geteuid', return_value=0), patch.dict(os.environ, {'PKEXEC_UID': '0'}):
            with self.assertRaisesRegex(RuntimeError, 'desktop user'): appearance.prepared_as_user(self.options, '')


if __name__ == '__main__': unittest.main()
