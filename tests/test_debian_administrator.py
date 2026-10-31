"""Debian enrollment authorization and installer ordering; no host account writes."""
from contextlib import ExitStack, redirect_stdout
import grp
import io
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'installer'))
import debian_administrator as admin
import dependencies
import install
import runtime_install as runtime
import update

prepare_account = dependencies.prepare_account


class DebianAdministratorTests(unittest.TestCase):
    def setUp(self):
        self.account = pwd.struct_passwd(('desktop', 'x', 1000, 1000, '', '/home/desktop', '/bin/bash'))
        self.group = grp.struct_group(('sudo', 'x', 27, []))
        stack = self.enterContext(ExitStack())
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(patch.dict(os.environ, {'PKEXEC_UID': '1000'}, clear=True))
        stack.enter_context(patch.object(runtime.policy, 'debian_host', return_value=True))
        stack.enter_context(patch.object(admin.os, 'geteuid', return_value=0))
        stack.enter_context(patch.object(admin.os, 'getuid', return_value=1000))
        self.lookup = stack.enter_context(patch.object(admin.pwd, 'getpwuid', return_value=self.account))
        stack.enter_context(patch.object(admin.Path, 'read_text', return_value='desktop:x:1000:1000::/home/desktop:/bin/bash\n'))
        self.groups = stack.enter_context(patch.object(admin.grp, 'getgrnam', side_effect=lambda name: self.group))
        self.run = stack.enter_context(patch.object(admin.subprocess, 'run'))

    def enroll(self, *args, **kwargs):
        self.group.gr_mem.append('desktop')
        return subprocess.CompletedProcess(args[0], 0, '', '')

    def test_authenticated_user_is_enrolled_with_existing_groups_preserved(self):
        self.run.side_effect = self.enroll
        for variable in ('PKEXEC_UID', 'SUDO_UID'):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: '1000', 'USER': 'root'}, clear=True):
                self.group.gr_mem.clear()
                self.assertTrue(admin.enable())
                self.lookup.assert_called_with(1000)
                self.assertEqual(self.run.call_args.args[0],
                                 ['/usr/sbin/usermod', '--append', '--groups', 'sudo', '--', 'desktop'])
                self.assertEqual(self.run.call_args.kwargs['env']['LC_ALL'], 'C')

    def test_existing_membership_never_prompts_or_changes_groups(self):
        self.group.gr_mem.append('desktop')
        self.assertFalse(admin.enable())
        with patch.object(runtime, 'administrator') as authenticate:
            self.assertFalse(admin.prepare())
            authenticate.assert_not_called()
        self.run.assert_not_called()
        self.group = grp.struct_group(('sudo', 'x', 1000, []))
        self.assertTrue(admin.sudo_member(self.account))

    def test_non_debian_and_unprivileged_helpers_are_rejected_before_changes(self):
        with patch.object(admin.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(RuntimeError, 'only available'):
                admin.enable()
        with patch.object(runtime.policy, 'debian_host', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'only available'):
                admin.enable()
            self.assertFalse(admin.prepare())
        self.run.assert_not_called()

    def test_untrusted_or_missing_invoking_identity_is_rejected(self):
        for value in ('', 'root', '-1', '1000 other', '0', '998', '65534', '1001'):
            with self.subTest(uid=value), patch.dict(os.environ, {'PKEXEC_UID': value}, clear=True):
                with self.assertRaises(RuntimeError):
                    admin.enable()
        with patch.dict(os.environ, {'USER': 'desktop', 'LOGNAME': 'desktop'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'authenticated installing user'):
                admin.enable()
        with patch.dict(os.environ, {'PKEXEC_UID': '1000', 'SUDO_UID': '1001'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'authenticated installing user'):
                admin.enable()
        with patch.object(admin.pwd, 'getpwuid', side_effect=KeyError):
            with self.assertRaisesRegex(RuntimeError, 'no longer exists'):
                admin.enable()
        self.run.assert_not_called()

    def test_missing_group_or_failed_change_does_not_claim_success(self):
        with patch.object(admin.grp, 'getgrnam', side_effect=KeyError):
            with self.assertRaisesRegex(RuntimeError, 'sudo group is missing'):
                admin.enable()
        self.run.assert_not_called()
        self.run.return_value = subprocess.CompletedProcess([], 1, '', 'Cannot lock /etc/group')
        with self.assertRaisesRegex(RuntimeError, 'Cannot lock'):
            admin.enable()
        self.run.return_value = subprocess.CompletedProcess([], 0, '', '')
        with self.assertRaisesRegex(RuntimeError, 'could not be verified'):
            admin.enable()

    def test_prepare_requests_authentication_without_an_arbitrary_account_argument(self):
        self.run.side_effect = self.enroll
        with patch.object(runtime, 'administrator', return_value=['pkexec', '--disable-internal-agent']):
            self.assertTrue(admin.prepare())
        self.assertEqual(self.run.call_args.args[0],
                         ['pkexec', '--disable-internal-agent', '/usr/bin/python3', str(Path(admin.__file__).resolve())])
        self.assertEqual(self.run.call_count, 1)

    def test_authentication_denial_and_cancellation_never_retry_or_report_success(self):
        for code, message in ((126, 'cancelled'), (127, 'not granted'), (1, 'did not finish')):
            with self.subTest(code=code), patch.object(runtime, 'administrator', return_value=['pkexec']):
                self.run.reset_mock()
                self.run.return_value = subprocess.CompletedProcess([], code, '', '')
                with self.assertRaisesRegex(RuntimeError, message):
                    admin.prepare()
                self.assertEqual(self.run.call_count, 1)
                self.assertFalse(admin.sudo_member(self.account))


class InstallerAccountTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='xetal-account-test-')))
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(install.os, 'geteuid', return_value=1000))
        self.enterContext(patch.object(install.Path, 'home', return_value=self.home))
        self.enterContext(patch.object(install, 'source_revision', return_value='a'*40))
        self.enterContext(patch.object(install, 'connected_monitors', return_value=[]))
        self.enterContext(patch.object(runtime.policy, 'problem', return_value=None))
        self.enterContext(patch.object(runtime.policy, 'require'))
        self.refresh = self.enterContext(patch.object(dependencies, 'prepare_repositories'))
        self.resolve = self.enterContext(patch.object(dependencies, 'preflight'))
        self.runtime = self.enterContext(patch.object(runtime, 'ensure'))
        self.packages = self.enterContext(patch.object(dependencies, 'install'))
        self.check = self.enterContext(patch.object(dependencies, 'check', return_value=[]))
        self.account = self.enterContext(patch.object(dependencies, 'prepare_account', side_effect=RuntimeError('account-step')))
        self.render = self.enterContext(patch.object(install, 'render', side_effect=RuntimeError('render-step')))

    def test_install_and_foreground_update_prepare_account_after_dependencies(self):
        for mode in ('install', 'update'):
            with self.subTest(mode=mode):
                actions = []
                self.refresh.side_effect = lambda: actions.append('refresh')
                self.resolve.side_effect = lambda: actions.append('resolve')
                self.runtime.side_effect = lambda *args, **kwargs: actions.append('runtime')
                self.packages.side_effect = lambda *args, **kwargs: actions.append('packages')
                self.check.side_effect = [['missing'], ['missing'], []] if mode == 'install' else [['missing'], []]
                def account():
                    actions.append('account')
                    raise RuntimeError('account-step')
                self.account.side_effect = account
                with self.assertRaisesRegex(RuntimeError, 'account-step'):
                    if mode == 'install':
                        with patch.object(sys, 'argv', ['install.py', '--yes']):
                            install.main()
                    else:
                        update.prepare(self.home, 'a'*40, automatic=False, allow_runtime=True)
                self.assertEqual(actions, ['refresh', 'resolve', 'runtime', 'packages', 'account'])
                self.render.assert_not_called()

    def test_checks_review_builds_and_skip_packages_do_not_enroll(self):
        for args in (['--check'], ['--dry-run'], ['--prepare', str(self.home/'review')], ['--skip-packages']):
            with self.subTest(args=args), patch.object(sys, 'argv', ['install.py', '--yes', *args]):
                if args[0] in ('--check', '--dry-run'):
                    self.assertEqual(install.main(), 0)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'render-step'):
                        install.main()
                self.account.assert_not_called()

    def test_background_update_never_requests_account_setup(self):
        with patch.object(update.engine, 'recover'), self.assertRaisesRegex(RuntimeError, 'render-step'):
            update.prepare(self.home, 'a'*40)
        self.account.assert_not_called()
        self.refresh.assert_not_called()

    def test_other_distros_do_not_enroll_even_when_dependencies_use_debian_family(self):
        for data in (dict(ID='arch'), dict(ID='cachyos', ID_LIKE='arch'), dict(ID='fedora', VERSION_ID='44'),
                     dict(ID='ubuntu', ID_LIKE='debian', VERSION_ID='26.04'), dict(ID='debian', VERSION_ID='12')):
            with self.subTest(data=data), patch.object(dependencies, 'distribution', return_value=data), \
                 patch.object(admin, 'prepare') as enroll:
                prepare_account()
                enroll.assert_not_called()
        with patch.object(dependencies, 'distribution', return_value=dict(ID='debian', VERSION_ID='13')), \
             patch.object(admin, 'prepare') as enroll:
            prepare_account()
            enroll.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
