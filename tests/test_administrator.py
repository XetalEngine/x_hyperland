"""Authentication selection and diagnostics, without prompting or changing permissions."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'installer'))
import runtime_install as runtime
import debian_runtime as debian
import dependencies


class AdministratorTests(unittest.TestCase):
    def test_debian_gui_uses_system_authentication_without_sudo_or_askpass(self):
        with patch.dict(os.environ, {'XETAL_SETUP_GUI': '1'}, clear=True), \
             patch.object(runtime.policy, 'debian_host', return_value=True), \
             patch.object(runtime.shutil, 'which', side_effect=lambda name: '/usr/bin/pkexec' if name == 'pkexec' else None), \
             patch.object(runtime.subprocess, 'run') as run:
            self.assertEqual(runtime.administrator(), ['pkexec', '--disable-internal-agent'])
            self.assertNotIn('SUDO_ASKPASS', os.environ)
            run.assert_not_called()  # Selection never requests a password itself.

    def test_terminal_and_other_distribution_authentication_stay_with_sudo(self):
        for gui, debian_host, expected in (('0', True, ['sudo']), ('1', False, ['sudo', '-A'])):
            with self.subTest(gui=gui, debian=debian_host), patch.dict(os.environ, {'XETAL_SETUP_GUI': gui}, clear=True), \
                 patch.object(runtime.policy, 'debian_host', return_value=debian_host), \
                 patch.object(runtime.shutil, 'which', side_effect=lambda name: '/usr/bin/'+name):
                self.assertEqual(runtime.administrator(), expected)
                self.assertEqual('SUDO_ASKPASS' in os.environ, gui == '1')

    def test_debian_falls_back_to_sudo_when_system_authentication_is_unavailable(self):
        with patch.dict(os.environ, {'XETAL_SETUP_GUI': '1'}, clear=True), \
             patch.object(runtime.policy, 'debian_host', return_value=True), \
             patch.object(runtime.shutil, 'which', side_effect=lambda name: '/usr/bin/sudo' if name == 'sudo' else None):
            self.assertEqual(runtime.administrator(), ['sudo', '-A'])
        with patch.object(runtime.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'desktop user'):
                runtime.administrator()

    def test_graphical_debian_platform_check_accepts_pkexec_without_sudo(self):
        data = dict(ID='debian', VERSION_ID='13')
        with patch.dict(os.environ, {'XETAL_SETUP_GUI': '1'}), \
             patch.object(dependencies, 'distribution', return_value=data), \
             patch.object(dependencies.platform, 'machine', return_value='x86_64'), \
             patch.object(dependencies.platform, 'system', return_value='Linux'), \
             patch.object(dependencies.Path, 'exists', return_value=False), \
             patch.object(runtime.shutil, 'which', side_effect=lambda name: None if name == 'sudo' else '/usr/bin/'+name):
            self.assertEqual(dependencies.platform_problems(), [])

    def test_refresh_distinguishes_denied_cancelled_and_repository_failures(self):
        cases = [(['sudo', '-A'], 1, 'xetal is not in the sudoers file.\n', 'not authorized to use sudo'),
                 (['sudo', '-A'], 1, 'sudo: no password was provided\n', 'authentication failed or was cancelled'),
                 (['pkexec', '--disable-internal-agent'], 126, '', 'authentication was cancelled'),
                 (['pkexec', '--disable-internal-agent'], 127, 'Not authorized\n', 'access was not granted'),
                 (['pkexec', '--disable-internal-agent'], 100, 'E: Failed to fetch mirror\n', 'repository errors')]
        for prefix, code, stderr, message in cases:
            with self.subTest(prefix=prefix, code=code), \
                 patch.object(runtime, 'administrator', return_value=prefix), \
                 patch.object(debian.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, None, stderr)) as run:
                with self.assertRaisesRegex(RuntimeError, message):
                    debian.refresh()
                self.assertEqual(run.call_count, 1)  # Never rerun an unsuccessful APT operation.
                self.assertEqual(run.call_args.args[0][-1], 'update')
                self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C')

    def test_package_failures_are_not_misreported_as_authentication(self):
        runtime.check_administrator_result(['sudo'], 1, 'Dependency resolution failed')
        runtime.check_administrator_result(['pkexec'], 1, 'Dependency resolution failed')
        runtime.check_administrator_result(['sudo'], 0, 'not in the sudoers file')


if __name__ == '__main__':
    unittest.main()
