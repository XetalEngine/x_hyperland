"""Minimal-system authentication selection, quoting and identity preservation."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'installer'))
import dependencies
import root_auth as auth
import runtime_install as runtime


class RootAuthenticationTests(unittest.TestCase):
    def test_missing_sudo_uses_root_auth_and_keeps_it_after_packages_arrive(self):
        for gui in ('0', '1'):
            with self.subTest(gui=gui), patch.dict(os.environ, {'XETAL_SETUP_GUI':gui}, clear=True), \
                 patch.object(runtime.policy, 'debian_host', return_value=False), \
                 patch.object(runtime.shutil, 'which', side_effect=lambda name:'/usr/bin/su' if name == 'su' else None):
                expected = ['/usr/bin/python3', str(runtime.ROOT/'installer/root_auth.py')]
                self.assertEqual(runtime.administrator(), expected)
                self.assertEqual(os.environ['XETAL_SETUP_AUTH_SU'], '1')
                with patch.object(runtime.shutil, 'which', side_effect=lambda name:'/usr/bin/'+name):
                    self.assertEqual(runtime.administrator(), expected)

    def test_existing_graphical_pkexec_works_without_sudo_and_remains_selected(self):
        with patch.dict(os.environ, {'XETAL_SETUP_GUI':'1'}, clear=True), \
             patch.object(runtime.policy, 'debian_host', return_value=False), \
             patch.object(runtime.shutil, 'which', side_effect=lambda name:None if name == 'sudo' else '/usr/bin/'+name):
            self.assertEqual(runtime.administrator(), ['pkexec', '--disable-internal-agent'])
            with patch.object(runtime.shutil, 'which', side_effect=lambda name:'/usr/bin/'+name):
                self.assertEqual(runtime.administrator(), ['pkexec', '--disable-internal-agent'])

    def test_arch_preflight_accepts_su_when_sudo_is_not_installed(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(dependencies, 'distribution', return_value={'ID':'arch'}), \
             patch.object(dependencies.platform, 'system', return_value='Linux'), \
             patch.object(dependencies.platform, 'machine', return_value='x86_64'), \
             patch.object(dependencies.Path, 'exists', return_value=False), \
             patch.object(runtime.shutil, 'which', side_effect=lambda name:None if name in ('sudo', 'pkexec') else '/usr/bin/'+name):
            self.assertEqual(dependencies.platform_problems(), [])

    def test_su_payload_preserves_literal_arguments(self):
        values = ['/usr/bin/python3', '/tmp/path with spaces/tool.py', '$(touch /no)', "a'`literal`"]
        with patch.object(auth, 'desktop', return_value=SimpleNamespace(pw_uid=1000)), \
             patch.object(auth.conversation, 'exchange', return_value=0) as exchange:
            self.assertEqual(auth.run(values), 0)
        arguments, marker, _, _ = exchange.call_args.args
        payload = shlex.split(arguments[arguments.index('--command')+1])
        self.assertEqual(payload[2:5], ['--exec', '1000', marker.decode()])
        self.assertEqual(payload[5:], values)

    def test_root_runner_requires_auth_and_clears_untrusted_environment(self):
        marker = 'XETAL_ROOT_READY_'+'a'*32
        with patch.object(auth.os, 'geteuid', return_value=1000), patch.object(auth.os, 'execvpe') as execute:
            with self.assertRaisesRegex(RuntimeError, 'authentication is required'):
                auth.execute('1000', marker, ['true'])
            execute.assert_not_called()
        with patch.object(auth.os, 'geteuid', return_value=0), \
             patch.object(auth, 'desktop', return_value=SimpleNamespace(pw_uid=1000)), \
             patch.object(auth.os, 'execvpe') as execute, redirect_stdout(io.StringIO()) as output:
            auth.execute('1000', marker, ['/usr/bin/id', '-u'])
            self.assertEqual(output.getvalue(), marker+'\n')
            env = execute.call_args.args[2]
            self.assertEqual(env['XETAL_SETUP_SU_UID'], '1000')
            self.assertNotIn('SUDO_UID', env)
            self.assertNotIn('LD_PRELOAD', env)
            self.assertNotIn('PYTHONPATH', env)

    def test_terminal_auth_requires_private_tty(self):
        with patch.dict(os.environ, {}, clear=True), patch('builtins.open', side_effect=OSError('no tty')), \
             patch.object(auth.getpass, 'getpass') as prompt:
            with self.assertRaises(OSError):
                auth.password()
            prompt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
