"""Exercise the private authentication terminal without host PAM or passwords."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'installer'))
import debian_su as auth
import debian_administrator as account
import runtime_install as runtime


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='xetal-auth-terminal-')))
        self.marker = b'XETAL_ROOT_READY_0123456789abcdef0123456789abcdef'
        self.output = io.BytesIO()
        self.secret = bytearray(b'test-only: $() `quotes` and spaces')
        self.prompt = Mock(return_value=self.secret)

    def child(self, script):
        path = self.root/'pam-fixture.py'
        path.write_text('import os,sys,time,termios\nmarker='+repr(self.marker)+'\n'+script)
        return [sys.executable, str(path)]

    def exchange(self, script, timeout=3):
        return auth.exchange(self.child(script), self.marker, self.prompt, self.output.write, timeout)

    def password_script(self, tail):
        return '''attributes=termios.tcgetattr(0)
attributes[3] &= ~termios.ECHO
termios.tcsetattr(0,termios.TCSANOW,attributes)
os.write(1,b'Pass');time.sleep(.02);os.write(1,b'word: ')
password=sys.stdin.buffer.readline().rstrip(b'\\n')
if password != b'test-only: $() `quotes` and spaces': sys.exit(1)
'''+tail

    def test_password_is_private_erased_and_command_errors_are_preserved(self):
        code = self.exchange(self.password_script(
            "os.write(1,marker[:15]);time.sleep(.02);os.write(1,marker[15:]+b'\\nAPT output\\n');sys.exit(100)\n"))
        self.assertEqual(code, 100)
        self.assertEqual(self.prompt.call_count, 1)
        self.assertEqual(self.secret, bytearray())
        self.assertEqual(self.output.getvalue(), b'\nAPT output\n')
        self.assertNotIn(b'Password', self.output.getvalue())

    def test_wrong_password_does_not_run_command_or_leak_terminal_output(self):
        self.prompt.return_value = bytearray(b'wrong test password')
        with self.assertRaisesRegex(auth.AuthenticationError, 'root password'):
            self.exchange(self.password_script("os.write(1,marker+b'\\nshould not run')\n"))
        self.assertEqual(self.output.getvalue(), b'')
        self.assertEqual(self.prompt.call_count, 1)

    def test_cancel_terminates_the_waiting_authentication_process(self):
        self.prompt.side_effect = auth.AuthenticationCancelled('cancelled')
        with patch.object(auth, 'stop', wraps=auth.stop) as stop:
            with self.assertRaises(auth.AuthenticationCancelled):
                self.exchange(self.password_script("os.write(1,marker)\n"))
            stop.assert_called_once()
        self.assertEqual(self.output.getvalue(), b'')

    def test_echoing_terminal_cannot_receive_a_password(self):
        with self.assertRaisesRegex(auth.AuthenticationError, 'not private'):
            self.exchange("os.write(1,b'Password: ');sys.stdin.buffer.readline()\n")
        self.prompt.assert_not_called()
        self.assertEqual(self.output.getvalue(), b'')

    def test_unrecognized_prompt_times_out_without_hanging_or_reading_password(self):
        with self.assertRaisesRegex(auth.AuthenticationError, 'timed out'):
            self.exchange("os.write(1,b'Unsupported PAM challenge: ');sys.stdin.buffer.readline()\n", timeout=.15)
        self.prompt.assert_not_called()

    def test_already_authenticated_process_does_not_prompt_and_preserves_exit_one(self):
        self.assertEqual(self.exchange("os.write(1,marker+b'\\nBuild failed\\n');sys.exit(1)\n"), 1)
        self.prompt.assert_not_called()
        self.assertEqual(self.output.getvalue(), b'\nBuild failed\n')


class RunnerTests(unittest.TestCase):
    def test_root_command_arguments_are_shell_quoted_and_never_contain_passwords(self):
        command = ['/usr/bin/python3', '/tmp/path with spaces/helper.py', '$(touch /should-not-exist)', "a'`literal`"]
        with patch.object(runtime.policy, 'debian_host', return_value=True), \
             patch.object(account, 'desktop_account', return_value=SimpleNamespace(pw_uid=1000)), \
             patch.object(auth, 'exchange', return_value=0) as exchange:
            self.assertEqual(auth.run(command), 0)
        arguments, marker, _, _ = exchange.call_args.args
        payload = shlex.split(arguments[arguments.index('--command')+1])
        self.assertEqual(payload[2:5], ['--exec', '1000', marker.decode()])
        self.assertEqual(payload[5:], command)
        self.assertIn('--login', arguments)
        self.assertEqual(arguments[-1], 'root')

    def test_privileged_runner_checks_authority_and_uses_a_clean_environment(self):
        marker = 'XETAL_ROOT_READY_'+'a'*32
        with patch.object(runtime.policy, 'debian_host', return_value=True), \
             patch.object(auth.os, 'geteuid', return_value=1000), patch.object(auth.os, 'execvpe') as execute:
            with self.assertRaisesRegex(RuntimeError, 'authentication is required'):
                auth.execute('1000', marker, ['true'])
            execute.assert_not_called()
        with patch.object(runtime.policy, 'debian_host', return_value=True), \
             patch.object(auth.os, 'geteuid', return_value=0), \
             patch.object(account, 'desktop_account', return_value=SimpleNamespace(pw_uid=1000)), \
             patch.object(auth.os, 'execvpe') as execute, redirect_stdout(io.StringIO()) as output:
            auth.execute('1000', marker, ['/usr/bin/id', '-u'])
            self.assertEqual(output.getvalue(), marker+'\n')
            env = execute.call_args.args[2]
            self.assertEqual(env['XETAL_SETUP_SU_UID'], '1000')
            self.assertEqual(env['DEBIAN_FRONTEND'], 'noninteractive')
            self.assertNotIn('SUDO_UID', env)
            self.assertNotIn('PYTHONPATH', env)
            self.assertNotIn('LD_PRELOAD', env)

    def test_root_dialog_cancellation_does_not_return_a_password(self):
        with patch.object(auth.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'')) as run:
            with self.assertRaises(auth.AuthenticationCancelled):
                auth.root_password()
            self.assertEqual(run.call_args.args[0][-1], '--root')


if __name__ == '__main__':
    unittest.main()
