import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import guest
import lab


class LabTests(unittest.TestCase):
    def test_local_login_refuses_host_before_writing_guest_service_override(self):
        with patch.object(guest, 'guard', side_effect=RuntimeError('not a lab guest')), patch.object(guest, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'not a lab guest'):
                guest.local_login('example')
            run.assert_not_called()

    def test_local_login_checks_the_actual_active_seat_owner(self):
        def invoke(args, **kwargs):
            output = ''
            if args[:2] == ['loginctl', 'show-seat']: output = '7\n'
            if args[:2] == ['loginctl', 'show-session']: output = str(guest.os.getuid())+'\n'
            return subprocess.CompletedProcess(args, 0, output)
        with patch.object(guest, 'guard') as guard, patch.object(guest, 'run', side_effect=invoke) as run:
            result = guest.local_login('example')
        guard.assert_called_once_with('example')
        self.assertEqual(result['uid'], guest.os.getuid())
        self.assertEqual(result['session'], '7')
        self.assertIn(['loginctl', 'show-session', '7', '--property=User', '--value'], [call.args[0] for call in run.call_args_list])

    def test_poweroff_transport_disconnect_still_waits_for_guest_exit(self):
        instance = object.__new__(lab.Lab)
        with tempfile.TemporaryDirectory() as directory:
            instance.current = Path(directory)
            pid = instance.current/'qemu.pid'; pid.write_text('123')
            with patch.object(instance, 'ssh', side_effect=subprocess.CalledProcessError(255, ['ssh'])), \
                 patch.object(lab.time, 'sleep', side_effect=lambda _:pid.unlink()) as sleep:
                instance.stop(graceful=True)
            sleep.assert_called_once_with(0.5)
            self.assertIsNone(instance.current)

    def test_sandboxed_window_can_be_identified_without_disabling_its_sandbox(self):
        responses = [
            subprocess.CompletedProcess([], 0, '_NET_WM_PID(CARDINAL) = 123\nWM_CLASS(STRING) = "app"'),
            subprocess.CompletedProcess([], 0, '/opt/app/application\n'),
            subprocess.CompletedProcess([], 0, 'Width: 800\nHeight: 600\nMap State: IsViewable'),
            subprocess.CompletedProcess([], 0, 'application\n')]
        with patch.object(guest.os, 'readlink', side_effect=PermissionError), patch.object(guest.subprocess, 'run', side_effect=responses) as run:
            self.assertEqual(guest.window_info('0x123')['package'], 'application')
            self.assertEqual(run.call_args_list[1].args[0], ['sudo', '-n', 'readlink', '--', '/proc/123/exe'])

    def test_guest_refuses_host_before_privileged_commands(self):
        with patch.object(guest, 'Path') as path, patch.object(guest, 'run') as run:
            path.return_value.is_file.return_value = False
            with self.assertRaisesRegex(RuntimeError, 'disposable guest'):
                guest.guard('example')
            run.assert_not_called()

    def test_ambiguous_release_is_not_selected(self):
        releases = [{'tag_name': '1.0', 'draft': False, 'prerelease': False, 'assets': [
            {'name': 'a-amd64.deb'}, {'name': 'b-amd64.deb'}]}]
        with patch.object(lab, 'fetch', return_value=json.dumps(releases).encode()):
            with self.assertRaisesRegex(RuntimeError, 'unambiguous'):
                lab.resolve_app({'github': 'example/app', 'asset': r'.*amd64\.deb$'})

    def test_prerelease_and_arm_assets_are_not_selected(self):
        releases = [
            {'tag_name': '2.0', 'prerelease': True, 'draft': False, 'assets': [{'name': 'a-amd64.deb'}]},
            {'tag_name': '1.0', 'prerelease': False, 'draft': False, 'assets': [
                {'name': 'a-arm64.deb', 'browser_download_url': 'https://example.org/wrong.deb'},
                {'name': 'a-amd64.deb', 'browser_download_url': 'https://example.org/right.deb'}]}]
        with patch.object(lab, 'fetch', return_value=json.dumps(releases).encode()):
            self.assertEqual(lab.resolve_app({'github': 'example/app', 'asset': r'.*\.deb$'}),
                             ('https://example.org/right.deb', None))

    def test_download_requires_https(self):
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            lab.download('http://example.org/package.deb', Path('/not-created'))

    def test_boot_rejects_paths_outside_lab(self):
        instance = object.__new__(lab.Lab)
        with tempfile.TemporaryDirectory() as directory:
            instance.data = Path(directory)/'storage'; instance.data.mkdir()
            instance.current = None
            wrong = Path(directory)/'outside.qcow2'; wrong.touch()
            with self.assertRaisesRegex(RuntimeError, 'inside lab storage'):
                instance.boot(wrong, Path(directory)/'vm')

    def test_guest_has_localhost_ssh_without_host_filesystem_shares(self):
        instance = object.__new__(lab.Lab)
        with tempfile.TemporaryDirectory() as directory:
            instance.state = instance.data = Path(directory)
            instance.identity = Path(directory)/'key'
            instance.current = None; instance.runtime = {}; instance.config = {'uuid': 'example'}
            disk = Path(directory)/'disk.qcow2'; disk.touch()
            with patch.object(lab, 'command') as command, patch.object(lab.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), patch.object(lab.socket, 'socket') as socket:
                socket.return_value.__enter__.return_value.getsockname.return_value = ('127.0.0.1', 22222)
                instance.boot(disk, Path(directory)/'boot')
                args = command.call_args.args[0]
                self.assertEqual(args[args.index('-display')+1], 'none')
                self.assertIn('hostfwd=tcp:127.0.0.1:', args[args.index('-netdev')+1])
                self.assertFalse(set(args) & {'-virtfs', '-fsdev', '-spice', '-vnc'})
                self.assertFalse(any('/dev/nvme' in str(value) for value in args))


if __name__ == '__main__':
    unittest.main()
