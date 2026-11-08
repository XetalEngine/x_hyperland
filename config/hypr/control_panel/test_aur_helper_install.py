"""Helper bootstrap uses reviewed, unprivileged builds and verifies installation."""
import contextlib
import io
from pathlib import Path
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
            if self.install_result and (args[0]=='makepkg' or args[0].endswith('/paru')):
                self.present.add('yay')
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


if __name__=='__main__':unittest.main()
