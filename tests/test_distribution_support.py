"""Distribution and package preflight tests never change the host packages."""
from contextlib import ExitStack
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'installer'))
import dependencies as deps
import install
import runtime_install as runtime
import arch_runtime as arch
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
        with self.host('cachyos','arch'),patch.object(arch,'preflight') as preflight:
            deps.preflight()
            preflight.assert_called_once_with(deps.PACKAGES['arch'])
        self.assertTrue(deps.package_version_problems(output.replace('0.15.0','0.14.0')))
        self.assertTrue(deps.package_version_problems('kitty 0.49.0\n'))

    def test_missing_repository_package_has_an_actionable_error(self):
        with self.host('manjaro','arch'),patch.object(arch,'preflight',side_effect=RuntimeError('error: target not found: kitty')):
            with self.assertRaisesRegex(RuntimeError,'target not found: kitty'):deps.preflight()

    def test_compositor_abi_resolution_keeps_dependency_checks_enabled(self):
        with patch.object(runtime.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','unsatisfied libaquamarine.so dependency')) as run:
            with self.assertRaisesRegex(RuntimeError,'has not been changed'):runtime.check_transaction(Path('/tmp/package'))
            self.assertEqual(run.call_args.args[0],['pacman','-Up','--noconfirm','--print-format','%n %v','/tmp/package'])

    def test_package_failures_keep_the_conflict_details_and_error_summary(self):
        detail=":: installing fixture-lib (2.0-1) breaks dependency 'fixture-lib=1.0' required by fixture-app"
        summary='error: failed to prepare transaction (could not satisfy dependencies)'
        for stdout,stderr in ((detail,summary),(summary,detail),('',detail),(detail,'')):
            with self.subTest(stdout=stdout,stderr=stderr),self.host(), \
                 patch.object(runtime.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stdout,stderr)), \
                 patch.object(runtime,'administrator') as administrator:
                for check in (lambda:arch.resolve(Path('/tmp/config'), []),lambda:runtime.check_transaction(Path('/tmp/package'))):
                    with self.assertRaises(RuntimeError) as raised:check()
                    self.assertIn(detail,str(raised.exception))
                    if summary in stdout+stderr:self.assertIn(summary,str(raised.exception))
                administrator.assert_not_called()

    @unittest.skipUnless(shutil.which('pacman'),'A real pacman is needed for the isolated repository fixture')
    def test_real_pacman_dependency_details_reach_setup_without_changing_packages(self):
        # Reproduce a partially updated library with a reverse dependency. All
        # databases, repositories, root and cache are disposable; no sudo or -Sy.
        with tempfile.TemporaryDirectory(prefix='xetal-pacman-conflict-') as temporary:
            root=Path(temporary)
            for directory in ('db/local','db/sync','cache','root'):(root/directory).mkdir(parents=True)
            (root/'db/local/ALPM_DB_VERSION').write_text('9\n')
            def desc(name,version,depends=()):
                fields={'NAME':name,'VERSION':version,'ARCH':'x86_64','DESC':'Fixture',
                        'FILENAME':name+'-'+version+'-x86_64.pkg.tar.zst'}
                text=''.join('%'+key+'%\n'+value+'\n\n' for key,value in fields.items())
                if depends:text+='%DEPENDS%\n'+'\n'.join(depends)+'\n\n'
                return text
            for name,depends in (('fixture-lib',()),('fixture-app',('fixture-lib=1.0',))):
                entry=root/'db/local'/(name+'-1.0-1');entry.mkdir()
                (entry/'desc').write_text(desc(name,'1.0-1',depends))
                (entry/'files').write_text('%FILES%\n\n')
            data=desc('fixture-lib','2.0-1').encode()
            with tarfile.open(root/'db/sync/fixture.db','w:gz') as archive:
                info=tarfile.TarInfo('fixture-lib-2.0-1/desc');info.size=len(data)
                archive.addfile(info,io.BytesIO(data))
            config=root/'pacman.conf'
            config.write_text('[options]\nArchitecture = x86_64\nSigLevel = Never\n\n[fixture]\nServer = file://'+str(root/'empty-repository')+'\n')
            original={str(p.relative_to(root/'db')):p.read_bytes() for p in (root/'db').rglob('*') if p.is_file()}
            execute=subprocess.run
            results=[]
            def resolve(argv,**kwargs):
                self.assertEqual(argv[:2],['pacman','--config'])
                result=execute([argv[0],'--config',str(config),'--dbpath',str(root/'db'),
                                '--root',str(root/'root'),'--cachedir',str(root/'cache'),
                                '--logfile',str(root/'pacman.log'),*argv[3:]], **kwargs)
                results.append(result)
                return result
            with self.host(),patch.dict(deps.PACKAGES,{'arch':['fixture-lib']}), \
                 patch.object(arch,'package_args',return_value=['fixture-lib']), \
                 patch.object(deps.subprocess,'run',side_effect=resolve):
                with self.assertRaises(RuntimeError) as raised:arch.resolve(config, ['fixture-lib'])
            self.assertIn("required by fixture-app",results[0].stdout)
            self.assertIn('could not satisfy dependencies',results[0].stderr)
            self.assertIn("required by fixture-app",str(raised.exception))
            self.assertIn('could not satisfy dependencies',str(raised.exception))
            self.assertEqual({str(p.relative_to(root/'db')):p.read_bytes() for p in (root/'db').rglob('*') if p.is_file()},original)
            self.assertEqual(list((root/'root').iterdir()),[])
            self.assertEqual(list((root/'cache').iterdir()),[])

    def test_incompatible_combined_runtime_does_not_request_administrator_or_backup(self):
        with self.host(),patch.object(arch,'preflight',side_effect=RuntimeError('ABI mismatch')), \
             patch.object(runtime,'administrator') as administrator,patch.object(runtime,'previous_package') as backup:
            with self.assertRaisesRegex(RuntimeError,'ABI mismatch'):deps.preflight()
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
