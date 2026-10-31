"""Compositor verification across administrator backends, without a live session."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'config/hypr/runtime'))
import runtime_policy as policy


class RuntimeProbeTests(unittest.TestCase):
    def setUp(self):
        self.target = policy.manifest()
        self.account = SimpleNamespace(pw_uid=1000, pw_gid=1001, pw_name='desktop', pw_dir='/home/desktop')
        self.output = 'Hyprland '+self.target['hyprland']+' built from branch v0.56.2 at commit '+self.target['commit']+'\n'

    def test_each_administrator_backend_probes_as_the_authenticated_desktop_user(self):
        for key in ('SUDO_UID', 'PKEXEC_UID', 'XETAL_SETUP_SU_UID'):
            with self.subTest(backend=key), patch.dict(os.environ, {key: '1000', 'HOME': '/root'}, clear=True), \
                 patch.object(policy.os, 'geteuid', return_value=0), \
                 patch.object(policy.pwd, 'getpwuid', return_value=self.account) as lookup, \
                 patch.object(policy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, self.output, '')) as run:
                self.assertEqual(policy.installed(), {'version': self.target['hyprland'], 'commit': self.target['commit']})
                lookup.assert_called_once_with(1000)
                self.assertEqual(run.call_args.args[0], ['/usr/bin/Hyprland', '--version'])
                options = run.call_args.kwargs
                self.assertEqual((options['user'], options['group'], options['extra_groups']), (1000, 1001, []))
                self.assertEqual(options['env']['XDG_RUNTIME_DIR'], '/run/user/1000')
                self.assertEqual(options['env']['HOME'], '/home/desktop')
                self.assertEqual(options['env']['USER'], 'desktop')
                self.assertEqual(options['env']['LOGNAME'], 'desktop')

    def test_missing_invalid_root_or_conflicting_identities_never_launch_a_root_probe(self):
        environments = [{}, {'SUDO_UID': '0'}, {'PKEXEC_UID': '-1'}, {'XETAL_SETUP_SU_UID': 'desktop'},
                        {'XETAL_SETUP_SU_UID': '１０００'}, {'SUDO_UID': '1000', 'PKEXEC_UID': '1002'}]
        for environment in environments:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), \
                 patch.object(policy.os, 'geteuid', return_value=0), patch.object(policy.subprocess, 'run') as run:
                error = policy.problem()
                self.assertIn('Could not verify Hyprland', error)
                self.assertIn('authenticated desktop user', error)
                self.assertNotIn('found not installed', error)
                run.assert_not_called()

    def test_matching_identity_markers_are_not_a_conflict(self):
        with patch.dict(os.environ, {'SUDO_UID': '1000', 'PKEXEC_UID': '1000'}, clear=True), \
             patch.object(policy.os, 'geteuid', return_value=0), \
             patch.object(policy.pwd, 'getpwuid', return_value=self.account), \
             patch.object(policy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, self.output, '')) as run:
            self.assertEqual(policy.installed()['commit'], self.target['commit'])
            self.assertEqual(run.call_args.kwargs['user'], 1000)

    def test_removed_desktop_account_reports_verification_failure(self):
        with patch.dict(os.environ, {'XETAL_SETUP_SU_UID': '1000'}, clear=True), \
             patch.object(policy.os, 'geteuid', return_value=0), \
             patch.object(policy.pwd, 'getpwuid', side_effect=KeyError(1000)), patch.object(policy.subprocess, 'run') as run:
            self.assertIn('desktop account no longer exists', policy.problem())
            run.assert_not_called()

    def test_normal_user_probe_keeps_its_session_and_custom_binary(self):
        with patch.dict(os.environ, {'PKEXEC_UID': '2000', 'XDG_RUNTIME_DIR': '/run/user/1000'}, clear=True), \
             patch.object(policy.os, 'geteuid', return_value=1000), \
             patch.object(policy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, self.output, '')) as run:
            self.assertEqual(policy.installed('/test/Hyprland')['version'], self.target['hyprland'])
            self.assertEqual(run.call_args.args[0], ['/test/Hyprland', '--version'])
            self.assertNotIn('user', run.call_args.kwargs)
            self.assertNotIn('env', run.call_args.kwargs)

    def test_absent_binary_is_still_reported_as_not_installed(self):
        with patch.object(policy.os, 'geteuid', return_value=1000), \
             patch.object(policy.subprocess, 'run', side_effect=FileNotFoundError('Hyprland')):
            self.assertIn('found not installed', policy.problem())

    def test_launch_errors_and_timeouts_are_not_reported_as_missing_packages(self):
        for error in (PermissionError('Access denied'), subprocess.TimeoutExpired('Hyprland', 10)):
            with self.subTest(error=error), patch.object(policy.os, 'geteuid', return_value=1000), \
                 patch.object(policy.subprocess, 'run', side_effect=error):
                message = policy.problem()
                self.assertIn('Could not verify Hyprland', message)
                self.assertNotIn('found not installed', message)

    def test_failed_probe_includes_diagnostic_and_cannot_match_even_if_it_prints_version(self):
        with patch.object(policy.os, 'geteuid', return_value=1000), \
             patch.object(policy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, self.output, 'missing runtime library')):
            message = policy.problem()
            self.assertIn('exit 1', message)
            self.assertIn('missing runtime library', message)
            self.assertFalse(policy.matches_requirement(self.target))


if __name__ == '__main__': unittest.main()
