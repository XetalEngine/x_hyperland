"""Control Panel bridge tests never open listeners or touch real preferences."""
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from . import remote_cli as cli


class RemoteCliTests(unittest.TestCase):
    def test_refresh_reads_without_starting_sharing(self):
        with patch.object(cli, 'remote') as remote, patch.object(cli, 'monitors', return_value=[{'name': 'DP-1'}]):
            remote.status.return_value = dict(running=False, process=None, log='')
            remote.preferences.return_value = dict(protocol='vnc')
            remote.addresses.return_value = ['127.0.0.1']
            remote.executable.return_value = '/usr/bin/fixture'
            result = cli.execute('refresh', {})
            self.assertEqual(result['monitors'], [{'name': 'DP-1'}])
            self.assertFalse(result['status']['running'])
            remote.start.assert_not_called(); remote.stop.assert_not_called(); remote.save.assert_not_called()

    def test_start_saves_before_launch_and_status_does_not_return_preferences(self):
        with patch.object(cli, 'remote') as remote:
            remote.status.return_value = dict(running=True)
            result = cli.execute('start', dict(values={'protocol': 'rdp'}, password='test-secret-1234'))
            calls = remote.method_calls
            self.assertEqual(calls[0][0], 'save'); self.assertEqual(calls[1][0], 'start')
            remote.save.assert_called_once_with({'protocol': 'rdp'}, 'test-secret-1234')
            self.assertNotIn('preferences', result)
            remote.preferences.assert_not_called()

    def test_invalid_requests_cannot_run_commands(self):
        with patch.object(cli, 'remote') as remote, patch.object(cli, 'install_packages') as install, patch.object(cli.subprocess, 'run') as build:
            for action, value in [('unknown', {}), ('start', []), ('save', {'values': []}), ('install', {'protocol': 'sh'})]:
                with self.subTest(action=action), self.assertRaises(ValueError): cli.execute(action, value)
            remote.save.assert_not_called(); remote.start.assert_not_called(); install.assert_not_called(); build.assert_not_called()

    def test_install_uses_fixed_component_and_never_starts_server(self):
        with patch.object(cli, 'remote') as remote, patch.object(cli, 'install_packages') as install, patch.object(cli.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as build:
            cli.execute('install', {'protocol': 'vnc'})
            install.assert_called_once_with(['wayvnc'])
            cli.execute('install', {'protocol': 'rdp'})
            self.assertEqual(build.call_args.args[0][-1], 'hypr-rdp')
            self.assertEqual(build.call_args.kwargs['stdout'], cli.subprocess.DEVNULL)
            remote.start.assert_not_called()

    def test_cli_redacts_new_and_saved_secrets_even_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); (directory/'password').write_text('old-secret-1234')
            stream = SimpleNamespace(buffer=BytesIO(json.dumps({'password': 'new-secret-5678'}).encode()))
            output = StringIO()
            with patch.object(cli.remote, 'DIRECTORY', directory), patch.object(cli.sys, 'argv', ['remote_cli.py', 'start']), \
                    patch.object(cli.sys, 'stdin', stream), patch.object(cli.sys, 'stdout', output), \
                    patch.object(cli, 'execute', side_effect=RuntimeError('new-secret-5678')), \
                    patch.object(cli, 'snapshot', return_value={'status': {'log': 'old-secret-1234'}}):
                self.assertEqual(cli.main(), 1)
            result = json.loads(output.getvalue())
            self.assertFalse(result['ok']); self.assertEqual(result['error'], '[hidden]')
            self.assertEqual(result['status']['log'], '[hidden]')

    def test_oversized_input_never_dispatches(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cli.remote, 'DIRECTORY', Path(folder)), \
                patch.object(cli.sys, 'argv', ['remote_cli.py', 'save']), \
                patch.object(cli.sys, 'stdin', SimpleNamespace(buffer=BytesIO(b'x'*(cli.MAX_REQUEST+1)))), \
                patch.object(cli.sys, 'stdout', StringIO()), patch.object(cli, 'execute') as execute, \
                patch.object(cli, 'snapshot', return_value={}):
            self.assertEqual(cli.main(), 1); execute.assert_not_called()


if __name__ == '__main__': unittest.main()
