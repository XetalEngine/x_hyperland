"""Distribution and package preflight tests never change the host packages."""
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'installer'))
import dependencies as deps
import install
import runtime_install as runtime
import update


class DistributionTests(unittest.TestCase):
    def host(self, ident='arch', like='', machine='x86_64', compositor='Version mismatch'):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(deps,'distribution',return_value={'ID':ident,'ID_LIKE':like,'PRETTY_NAME':ident}))
        stack.enter_context(patch.object(deps.platform,'system',return_value='Linux'))
        stack.enter_context(patch.object(deps.platform,'machine',return_value=machine))
        stack.enter_context(patch.object(deps.shutil,'which',side_effect=lambda name:'/usr/bin/'+name))
        stack.enter_context(patch.object(deps.Path,'exists',return_value=False))
        stack.enter_context(patch.object(runtime.policy,'problem',return_value=compositor))
        return stack

    def test_distribution_families_use_os_release_identity_and_ancestry(self):
        cases=[('arch','','arch'),('cachyos','arch','arch'),('endeavouros','arch','arch'),
               ('manjaro','arch','arch'),('garuda','arch','arch'),('ubuntu','debian','debian'),
               ('linuxmint','ubuntu debian','debian'),('fedora','','fedora'),
               ('opensuse-tumbleweed','suse',None),('nixos','',None)]
        for ident,like,expected in cases:
            with self.subTest(ident=ident):
                self.assertEqual(deps.distro({'ID':ident,'ID_LIKE':like}),expected)

    def test_other_distributions_need_native_compositor_without_arch_install(self):
        for ident in ('fedora','ubuntu','opensuse-tumbleweed'):
            with self.subTest(ident=ident),self.host(ident),patch.object(deps.subprocess,'run') as run:
                with self.assertRaises(RuntimeError):deps.preflight()
                run.assert_not_called()
        for family in ('fedora','debian'):
            self.assertNotIn('hyprland',deps.PACKAGES[family])

    def test_matching_manual_compositor_allows_other_dependency_recipes(self):
        with self.host('fedora',compositor=None),patch.object(deps.subprocess,'run') as run:
            deps.preflight();run.assert_not_called()

    def test_wrong_cpu_and_missing_package_tools_fail_before_resolution(self):
        with self.host(machine='aarch64'),patch.object(deps.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'x86-64'):deps.preflight()
            run.assert_not_called()
        with self.host(),patch.object(deps.shutil,'which',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'pacman-key'):deps.preflight()

    def test_package_resolution_is_read_only_and_checks_repository_versions(self):
        output='waybar 0.15.0-2\nkitty 1:0.49.1-1.1\nhyprpaper 0.8.0-1\n'
        with self.host('cachyos','arch'),patch.object(deps.subprocess,'run',return_value=subprocess.CompletedProcess([],0,output,'')) as run:
            deps.preflight()
            args=run.call_args.args[0]
            self.assertEqual(args[:2],['pacman','-Sp'])
            self.assertNotIn('--needed',args)
            self.assertEqual(args[-len(deps.PACKAGES['arch']):],deps.PACKAGES['arch'])
        self.assertTrue(deps.package_version_problems(output.replace('0.15.0','0.14.0')))
        self.assertTrue(deps.package_version_problems('kitty 0.49.0\n'))

    def test_missing_repository_package_has_an_actionable_error(self):
        with self.host('manjaro','arch'),patch.object(deps.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','error: target not found: kitty')):
            with self.assertRaisesRegex(RuntimeError,'target not found: kitty'):deps.preflight()

    def test_compositor_abi_resolution_keeps_dependency_checks_enabled(self):
        with patch.object(runtime.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','unsatisfied libaquamarine.so dependency')) as run:
            with self.assertRaisesRegex(RuntimeError,'has not been changed'):runtime.check_transaction(Path('/tmp/package'))
            self.assertEqual(run.call_args.args[0],['pacman','-Up','--noconfirm','--print-format','%n %v','/tmp/package'])

    def test_incompatible_compositor_does_not_request_administrator_or_backup(self):
        with self.host(),patch.object(runtime,'download',return_value=Path('/tmp/package')), \
             patch.object(runtime,'check_transaction',side_effect=RuntimeError('ABI mismatch')), \
             patch.object(runtime,'administrator') as administrator,patch.object(runtime,'previous_package') as backup:
            with self.assertRaisesRegex(RuntimeError,'ABI mismatch'):runtime.ensure(yes=True)
            administrator.assert_not_called();backup.assert_not_called()

    def test_install_and_foreground_update_preflight_before_any_package_changes(self):
        actions=[]
        def preflight():
            actions.append('resolve')
            raise RuntimeError('Repository mismatch')
        with tempfile.TemporaryDirectory(prefix='xetal-distro-test-') as temporary, \
             patch.object(install.os,'geteuid',return_value=1000), \
             patch.object(install.Path,'home',return_value=Path(temporary)), \
             patch.object(install,'source_revision',return_value='a'*40), \
             patch.object(deps,'check',return_value=[]), \
             patch.object(runtime.policy,'problem',return_value='Version mismatch'), \
             patch.object(deps,'prepare_repositories',side_effect=lambda:actions.append('refresh')), \
             patch.object(deps,'preflight',side_effect=preflight), \
             patch.object(runtime,'ensure') as ensure,patch.object(deps,'install') as packages:
            with patch.object(sys,'argv',['install.py','--yes']):
                with self.assertRaisesRegex(RuntimeError,'Repository mismatch'):install.main()
            with self.assertRaisesRegex(RuntimeError,'Repository mismatch'):
                update.prepare(Path(temporary),'a'*40,automatic=False,allow_runtime=True)
            ensure.assert_not_called();packages.assert_not_called()
            self.assertEqual(actions,['refresh','resolve','refresh','resolve'])
            self.assertFalse((Path(temporary)/'.config').exists())

    def test_refresh_failure_stops_foreground_setup_before_any_package_changes(self):
        with tempfile.TemporaryDirectory(prefix='xetal-distro-test-') as temporary, \
             patch.object(install.os,'geteuid',return_value=1000), \
             patch.object(install.Path,'home',return_value=Path(temporary)), \
             patch.object(install,'source_revision',return_value='a'*40), \
             patch.object(deps,'check',return_value=[]), \
             patch.object(runtime.policy,'problem',return_value='Version mismatch'), \
             patch.object(deps,'prepare_repositories',side_effect=RuntimeError('Repository refresh failed')), \
             patch.object(deps,'preflight') as preflight, patch.object(runtime,'ensure') as ensure, \
             patch.object(deps,'install') as packages:
            with patch.object(sys,'argv',['install.py','--yes']):
                with self.assertRaisesRegex(RuntimeError,'Repository refresh failed'):install.main()
            with self.assertRaisesRegex(RuntimeError,'Repository refresh failed'):
                update.prepare(Path(temporary),'a'*40,automatic=False,allow_runtime=True)
            preflight.assert_not_called();ensure.assert_not_called();packages.assert_not_called()
            self.assertFalse((Path(temporary)/'.config').exists())


if __name__=='__main__':unittest.main()
