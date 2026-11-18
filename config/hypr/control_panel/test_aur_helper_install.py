"""Helper bootstrap uses reviewed, unprivileged builds and verifies installation."""
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import aur_helper_install as helper


class AurHelperTests(unittest.TestCase):
    def setUp(self):
        self.present=set();self.commands=[];self.install_result=True
        def execute(args, **kwargs):
            self.commands.append(list(map(str,args)))
            if args[0]=='git':
                source=Path(args[-1]);source.mkdir()
                (source/'PKGBUILD').write_text('pkgname=yay\n')
                (source/'.SRCINFO').write_text('pkgbase = yay\n')
            if self.install_result and args[0] == 'makepkg':
                self.present.add(Path(kwargs['cwd']).name)
            elif self.install_result and str(args[0]).endswith(('/paru', '/yay')):
                self.present.add(args[-1])
        for mock in (patch.object(helper.os,'geteuid',return_value=1000),
                     patch.object(helper.shutil,'which',side_effect=lambda name:'/usr/bin/'+name if name in self.present else None),
                     patch.object(helper,'run',side_effect=execute),
                     patch('builtins.input',return_value='y')):
            mock.start();self.addCleanup(mock.stop)
        self.output=io.StringIO()
        redirect=contextlib.redirect_stdout(self.output);redirect.__enter__();self.addCleanup(redirect.__exit__,None,None,None)

    def test_bootstrap_reviews_build_files_and_builds_as_desktop_user(self):
        helper.install('yay')
        self.assertEqual(self.commands[0],['sudo','pacman','-Syu','--needed','base-devel','git'])
        self.assertEqual(self.commands[1][0:4],['git','-c','core.hooksPath=/dev/null','clone'])
        self.assertEqual(self.commands[-1],['makepkg','-si'])
        self.assertIn('pkgname=yay',self.output.getvalue())
        self.assertIn('Yay is installed',self.output.getvalue())

    def test_declining_review_stops_before_building(self):
        with patch('builtins.input',return_value='n'),self.assertRaisesRegex(RuntimeError,'cancelled'):
            helper.install('yay')
        self.assertFalse(any(cmd[0]=='makepkg' for cmd in self.commands))

    def test_existing_helper_is_reused_and_declined_transaction_is_not_success(self):
        self.present={'paru'};self.install_result=False
        with self.assertRaisesRegex(RuntimeError,'was not installed'):
            helper.install('yay')
        self.assertEqual(self.commands,[['/usr/bin/paru','-S','--needed','--','yay']])
        self.assertNotIn('Yay is installed',self.output.getvalue())

    def test_existing_binary_needs_no_action_and_root_cannot_build(self):
        self.present={'yay'};helper.install('yay')
        self.assertEqual(self.commands,[])
        with patch.object(helper.os,'geteuid',return_value=0),self.assertRaisesRegex(RuntimeError,'without sudo'):
            helper.install('yay')
        self.assertEqual(self.commands,[])

    def test_both_are_installed_sequentially_and_existing_helpers_are_kept(self):
        self.assertEqual(helper.main(['both']), 0)
        self.assertEqual(self.present, {'yay', 'paru'})
        self.assertEqual(self.commands[-2:], [['makepkg', '-si'], ['/usr/bin/yay', '-S', '--needed', '--', 'paru']])
        self.commands.clear()
        self.assertEqual(helper.main(['both']), 0)
        self.assertEqual(self.commands, [])

    def test_cancelled_first_helper_never_starts_the_second(self):
        with patch('builtins.input', return_value='n'):
            self.assertEqual(helper.main(['both']), 1)
        self.assertFalse(self.present)
        self.assertFalse(any(cmd[0] == 'makepkg' or str(cmd[0]).endswith(('/yay', '/paru')) for cmd in self.commands))

    def test_deb_continues_only_after_both_helpers_succeed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(helper, 'install_deb') as deb:
            path = Path(directory)/"app's $(literal).deb"; path.write_bytes(b'fixture')
            self.assertEqual(helper.main(['--deb', str(path), 'both']), 0)
            self.assertEqual(self.present, {'yay', 'paru'})
            deb.assert_called_once_with(path)
            deb.reset_mock(); self.present.clear()
            original = helper.run
            def fail_second(args, **kwargs):
                if str(args[0]).endswith('/yay'):
                    raise subprocess.CalledProcessError(1, args)
                return original(args, **kwargs)
            with patch.object(helper, 'run', side_effect=fail_second):
                self.assertEqual(helper.main(['--deb', str(path), 'both']), 1)
            self.assertEqual(self.present, {'yay'}); deb.assert_not_called()

    def test_missing_deb_and_incomplete_setup_do_not_start_conversion(self):
        with patch.object(helper, 'install_deb') as deb:
            self.assertEqual(helper.main(['--deb', '/nonexistent/fixture.deb', 'both']), 1)
            self.assertEqual(self.commands, []); deb.assert_not_called()
            with tempfile.TemporaryDirectory() as directory, patch.object(helper, 'install'):
                path = Path(directory)/'fixture.deb'; path.write_bytes(b'fixture')
                self.assertEqual(helper.main(['--deb', str(path), 'both']), 1)
                deb.assert_not_called()

    def test_reinstall_does_not_remove_working_helper_or_use_needed(self):
        self.present = {'yay'}
        self.assertEqual(helper.main(['--reinstall', 'yay']), 0)
        self.assertEqual(self.commands, [['/usr/bin/yay', '-S', '--', 'yay']])


if __name__=='__main__':unittest.main()
