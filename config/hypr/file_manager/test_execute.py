import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import execute


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        original = Path.exists
        self.addCleanup(patch.stopall)
        patch.object(Path, 'exists', lambda p: True if str(p) == '/dev/fuse' else original(p)).start()

    def script(self, name="installer's $(literal); #.sh", content=b'#!/bin/bash\nexit 0\n'):
        path = self.root/name
        path.write_bytes(content); path.chmod(0o644)
        return path

    def appimage(self, dynamic=True, machine=62):
        path = self.root/'My application.AppImage'
        count = 2 if dynamic else 1
        marker = b'libfuse.so.2\0' if dynamic else b'static FUSE runtime\0'
        size = 64+count*56+len(marker)
        header = bytearray(64)
        header[:6] = b'\x7fELF\x02\x01'; header[8:11] = b'AI\x02'
        struct.pack_into('<H', header, 18, machine)
        struct.pack_into('<Q', header, 32, 64)
        struct.pack_into('<HH', header, 54, 56, count)
        data = header+struct.pack('<IIQQQQQQ', 1, 5, 0, 0, 0, size, size, 4096)
        if dynamic: data += struct.pack('<IIQQQQQQ', 3, 0, 0, 0, 0, 0, 0, 1)
        path.write_bytes(data+marker); path.chmod(0o755)
        return path

    @patch.object(execute, 'library_available', return_value=False)
    @patch.object(execute.shutil, 'which', return_value=None)
    def test_legacy_appimage_lists_fuse2_without_executing_it(self, *_):
        plan = execute.inspect(self.appimage())
        self.assertEqual(plan['packages'], ['fuse2'])
        self.assertTrue(execute.needs_setup(plan))

    @patch.object(execute, 'library_available', return_value=True)
    @patch.object(execute.shutil, 'which', return_value='/usr/bin/fusermount')
    def test_ready_appimage_needs_no_setup(self, *_):
        plan = execute.inspect(self.appimage())
        self.assertFalse(execute.needs_setup(plan))

    @patch.object(execute, 'library_available', return_value=False)
    @patch.object(execute.shutil, 'which', side_effect=lambda name: '/usr/bin/fusermount3' if name == 'fusermount3' else None)
    def test_static_appimage_does_not_require_fuse2(self, which, library):
        plan = execute.inspect(self.appimage(dynamic=False))
        self.assertFalse(execute.needs_setup(plan))
        library.assert_not_called()

    @patch.object(execute.shutil, 'which', return_value=None)
    def test_static_runtime_without_mount_helper_offers_fuse3(self, _):
        self.assertEqual(execute.inspect(self.appimage(dynamic=False))['packages'], ['fuse3'])

    def test_corrupt_or_wrong_architecture_appimage_stops_before_setup(self):
        path = self.appimage(machine=183)
        with patch.object(execute.platform, 'machine', return_value='x86_64'):
            with self.assertRaisesRegex(ValueError, 'processor'): execute.inspect(path)
        path.write_bytes(b'not an appimage')
        with self.assertRaisesRegex(ValueError, 'complete AppImage'): execute.inspect(path)

    def test_oversized_runtime_header_is_rejected(self):
        path = self.appimage()
        data = bytearray(path.read_bytes()); struct.pack_into('<Q', data, 64+32, 64*1024*1024)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'incomplete or too large'): execute.inspect(path)

    def test_script_permissions_require_confirmation(self):
        path = self.script()
        plan = execute.inspect(path)
        self.assertEqual(plan['packages'], [])
        self.assertFalse(plan['executable'])
        with patch.object(execute, 'dialog', return_value=False), patch.object(execute.subprocess, 'Popen') as start:
            self.assertEqual(execute.main(['--', str(path)]), 0)
            start.assert_not_called()
        self.assertFalse(os.access(path, os.X_OK))

    def test_requirements_dialog_opens_and_cancels_with_the_real_theme(self):
        code = '''from PyQt6.QtWidgets import QApplication,QMessageBox
from PyQt6.QtCore import QTimer,Qt
import execute
app=QApplication([])
seen=[]
def cancel():
    box=next(w for w in app.topLevelWidgets() if w.objectName()=='executionRequirements')
    assert box.textFormat()==Qt.TextFormat.PlainText
    assert '<b>installer</b>' in box.text()
    seen.append(True)
    box.button(QMessageBox.StandardButton.Cancel).click()
QTimer.singleShot(100,cancel)
assert execute.dialog('Run <b>installer</b>?',question=True) is False
assert seen
'''
        result = subprocess.run([execute.sys.executable, '-c', code], cwd=Path(execute.__file__).parent,
                                env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME=''),
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_permission_setup_uses_only_chmod_under_sudo(self):
        path = self.script(); approved = execute.inspect(path)
        def run(command, check):
            self.assertTrue(check)
            self.assertEqual(command, ['sudo', 'chmod', '+x', '--', str(path)])
            path.chmod(0o755)
        ready = execute.prepare(approved, runner=run)
        self.assertTrue(ready['executable'])
        self.assertEqual(execute.target_command(ready), [str(path)])

    def test_failed_setup_does_not_run_the_file(self):
        path = self.script(); approved = execute.inspect(path)
        runner = Mock(side_effect=subprocess.CalledProcessError(1, ['sudo', 'chmod']))
        with self.assertRaises(subprocess.CalledProcessError): execute.prepare(approved, runner=runner)
        self.assertFalse(os.access(path, os.X_OK))

    def test_changed_file_cannot_use_previous_confirmation(self):
        path = self.script(); approved = execute.inspect(path)
        path.write_text('echo changed\n')
        runner = Mock()
        with self.assertRaisesRegex(ValueError, 'changed after confirmation'): execute.prepare(approved, runner=runner)
        runner.assert_not_called()

    def test_new_requirements_need_new_confirmation(self):
        approved = execute.inspect(self.script())
        current = copy.deepcopy(approved); current['packages'] = ['fuse2']
        runner = Mock()
        with patch.object(execute, 'inspect', return_value=current):
            with self.assertRaisesRegex(ValueError, 'requirements changed'): execute.prepare(approved, runner=runner)
        runner.assert_not_called()

    def test_installation_and_kernel_setup_precede_permissions(self):
        path = self.script(); approved = execute.inspect(path)
        approved.update(packages=['fuse2'], load_fuse=True)
        ready = dict(approved, packages=[], load_fuse=False, executable=True)
        runner = Mock()
        with patch.object(execute, 'inspect', side_effect=[approved, ready]), \
             patch.object(execute.platform, 'freedesktop_os_release', return_value={'ID': 'arch'}):
            self.assertEqual(execute.prepare(approved, runner=runner), ready)
        self.assertEqual([call.args[0] for call in runner.call_args_list], [
            ['sudo', 'pacman', '-S', '--needed', '--noconfirm', '--', 'fuse2'],
            ['sudo', 'modprobe', 'fuse'], ['sudo', 'chmod', '+x', '--', str(path)]])

    def test_shell_characters_are_arguments_in_the_terminal_command(self):
        path = self.script(); plan = execute.inspect(path)
        command = execute.terminal_command(plan, setup=True)
        self.assertEqual(command[-2:], ['--', str(path)])
        self.assertEqual(json.loads(command[command.index('--approved')+1]), plan)
        self.assertNotIn('-c', command)
        self.assertNotIn('sudo', command)

    def test_ready_run_file_honors_its_interpreter_as_normal_user(self):
        path = self.script('installer.run', b'#!/usr/bin/python3\nraise SystemExit(7)\n')
        path.chmod(0o755); plan = execute.inspect(path)
        result = execute.main(['--terminal', '--approved', json.dumps(plan), '--', str(path)])
        self.assertEqual(result, 7)

    def test_shell_script_without_shebang_uses_bash(self):
        path = self.script(content=b'echo hello\n'); plan = execute.inspect(path)
        self.assertEqual(execute.target_command(plan), ['bash', str(path)])

    def test_named_script_symlink_keeps_its_type_and_identity(self):
        target = self.script('actual-content')
        link = self.root/'run-this.sh'; link.symlink_to(target)
        plan = execute.inspect(link)
        self.assertEqual(plan['kind'], 'script')
        self.assertEqual(plan['path'], str(link))
        self.assertEqual(plan['identity'], execute.identity(target))

    def test_warm_panel_request_keeps_the_selected_file(self):
        sys_path = list(execute.sys.path)
        execute.sys.path.insert(0, str(execute.ROOT))
        self.addCleanup(lambda: execute.sys.path.__setitem__(slice(None), sys_path))
        from session_ui import client
        path = "/tmp/package's $(literal).deb"
        with patch.object(execute.sys, 'argv', ['client.py', 'panel', '--section', 'deb', '--deb-file', path]), \
             patch.object(client, 'contact', return_value=True) as contact:
            self.assertEqual(client.main(), 0)
        contact.assert_called_once_with('.xpanel.sock', {'section': 'deb', 'preload': False, 'deb_file': path})

    def test_missing_known_interpreter_is_offered_as_requirement(self):
        path = self.script(content=b'#!/usr/bin/env zsh\necho hello\n')
        with patch.object(execute.shutil, 'which', return_value=None):
            self.assertEqual(execute.inspect(path)['packages'], ['zsh'])

    def test_deb_opens_panel_with_selected_path_without_installing(self):
        path = self.script('application package.deb')
        with patch.object(execute.os, 'execv', side_effect=RuntimeError('exec handoff')) as launch:
            with self.assertRaisesRegex(RuntimeError, 'exec handoff'): execute.main(['--', str(path)])
        command = launch.call_args.args[1]
        self.assertEqual(command[-5:], ['panel', '--section', 'deb', '--deb-file', str(path)])

    def test_appimage_does_not_inherit_host_qt_plugins(self):
        with patch.dict(os.environ, {'QT_PLUGIN_PATH': '/host/qt', 'QT_QPA_PLATFORMTHEME': 'xetal'}):
            self.assertNotIn('QT_PLUGIN_PATH', execute.launch_environment({'kind': 'appimage'}))
            self.assertNotIn('QT_QPA_PLATFORMTHEME', execute.launch_environment({'kind': 'appimage'}))
            self.assertEqual(execute.launch_environment({'kind': 'script'})['QT_PLUGIN_PATH'], '/host/qt')

    def test_arch_package_transaction_is_limited_to_missing_packages(self):
        self.assertEqual(execute.install_command(['fuse2'], {'ID': 'cachyos', 'ID_LIKE': 'arch'}),
                         ['sudo', 'pacman', '-S', '--needed', '--noconfirm', '--', 'fuse2'])
        self.assertNotIn('-Sy', execute.install_command(['fuse2'], {'ID': 'arch'}))


if __name__ == '__main__': unittest.main()
