"""Verify the elevation wrapper with mock commands; never call real sudo/xhost."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import time
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('xsudo.sh')
spec = importlib.util.spec_from_file_location('gui_admin', SCRIPT.with_name('gui-admin.py'))
admin = importlib.util.module_from_spec(spec); spec.loader.exec_module(admin)


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xetal-xsudo-test-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        for name in ('xhost', 'sudo'):
            command = self.root/name
            command.write_text('''#!/usr/bin/python3
import json, os, sys, time
from pathlib import Path
name=Path(sys.argv[0]).name
with Path(os.environ['TEST_LOG']).open('a') as f:
 f.write(json.dumps([name,sys.argv[1:],os.environ.get('SUDO_ASKPASS')])+'\\n')
if name=='xhost' and len(sys.argv)==1:
 print('access control enabled')
 if os.environ.get('ROOT_ALREADY_ALLOWED'):print('SI:localuser:root')
if name=='sudo':
 time.sleep(float(os.environ.get('SUDO_DELAY', '0')))
 sys.exit(int(os.environ.get('SUDO_EXIT','0')))
''')
            command.chmod(0o755)
        self.log = self.root/'calls.jsonl'
        self.env = {**os.environ, 'PATH': str(self.root)+':/usr/bin', 'HOME': str(self.root),
                    'DISPLAY': ':99', 'HYPRLAND_INSTANCE_SIGNATURE': '', 'TEST_LOG': str(self.log),
                    'XDG_RUNTIME_DIR': str(self.root)}
    def run_wrapper(self, **changes):
        result = subprocess.run(['bash', str(SCRIPT), '/program with spaces', 'literal $(command)'],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, env={**self.env, **changes})
        return result, [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_literal_arguments_and_cleanup_on_failure(self):
        result, calls = self.run_wrapper(SUDO_EXIT='7')
        self.assertEqual(result.returncode, 7)
        sudo = next(call for call in calls if call[0]=='sudo')
        self.assertEqual(sudo[1][-2:], ['/program with spaces', 'literal $(command)'])
        self.assertEqual(sudo[1][:2], ['--preserve-env=DISPLAY,XAUTHORITY', '--'])
        self.assertIn('QT_QPA_PLATFORM=xcb', sudo[1])
        self.assertIn('QT_PLUGIN_PATH', sudo[1])
        self.assertEqual(calls[-1][1], ['-SI:localuser:root'])

    def test_existing_root_access_is_never_revoked(self):
        result, calls = self.run_wrapper(ROOT_ALREADY_ALLOWED='1')
        self.assertEqual(result.returncode, 0)
        self.assertEqual([call[1] for call in calls if call[0]=='xhost'], [[]])

    def test_no_display_does_not_change_x_access(self):
        result, calls = self.run_wrapper(DISPLAY='')
        self.assertEqual(result.returncode, 0)
        self.assertEqual([call[0] for call in calls], ['sudo'])

    def test_graphical_authentication_is_asked_by_helper_without_shell(self):
        with patch.dict(os.environ, {**self.env, 'HYPRLAND_INSTANCE_SIGNATURE': 'test'}), \
             patch.object(admin.sys.stdin, 'isatty', return_value=False):
            argv = admin.command(['/program with spaces', '$(literal)'])
            self.assertEqual(argv[:2], ['sudo', '--askpass'])
            self.assertEqual(os.environ['SUDO_ASKPASS'], str(SCRIPT.with_name('sudo-askpass.sh')))
            self.assertEqual(argv[-2:], ['/program with spaces', '$(literal)'])

    def test_concurrent_launches_keep_access_until_last_app_exits(self):
        def launch(delay):
            return subprocess.Popen(['bash', str(SCRIPT), '/fixture'], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env={**self.env, 'SUDO_DELAY': str(delay)})
        first = launch(.6)
        deadline = time.monotonic()+3
        while not self.log.exists() or 'sudo' not in self.log.read_text():
            self.assertLess(time.monotonic(), deadline); time.sleep(.01)
        second = launch(1.2)
        self.addCleanup(lambda: second.poll() is None and second.terminate())
        self.assertEqual(first.communicate(timeout=4)[1], b'')
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertNotIn(['-SI:localuser:root'], [call[1] for call in calls])
        self.assertEqual(second.communicate(timeout=4)[1], b'')
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(sum(call[1] == ['-SI:localuser:root'] for call in calls), 1)

    def test_stale_lease_is_cleaned_and_preexisting_access_is_preserved(self):
        with patch.dict(os.environ, self.env), patch.object(admin, 'xhost') as host:
            host.return_value = 'access control enabled\n'
            lease = admin.DisplayLease(self.root/'lease')
            lease.write({'owned': True, 'clients': [[999999999, '0']]})
            with lease:
                self.assertEqual(lease.read()['clients'], [lease.token])
            self.assertFalse(lease.path.exists())
            host.assert_called_with('-SI:localuser:root')

    def test_insecure_runtime_directory_is_rejected(self):
        path = self.root/'insecure'; path.mkdir(); path.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError, 'not private'):
            admin.DisplayLease(path)


if __name__ == '__main__': unittest.main()
