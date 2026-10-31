"""Compositor selection, package holds and recovery use disposable fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'installer'))
import runtime_install as runtime
import system_runtime as system


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='xetal-runtime-test-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.conf = self.root/'pacman.conf'; self.pin = self.root/'hold.conf'
        self.state = self.root/'records'
        self.original = '[options]\nIgnorePkg = linux\n[extra]\nServer = https://example.invalid\n'
        self.conf.write_text(self.original)
        self.target = runtime.policy.manifest()

    def test_exact_version_and_source_commit_are_both_required(self):
        for version, commit, accepted in [('0.56.2',self.target['commit'],True),
                                         ('0.57.0','a'*40,False),('0.56.2','b'*40,False)]:
            with self.subTest(version=version,commit=commit), patch.object(runtime.policy,'installed',return_value={'version':version,'commit':commit}):
                self.assertEqual(not runtime.policy.problem(), accepted)

    def test_package_hold_is_in_options_idempotent_and_preserves_other_holds(self):
        text = system.config_with_hold(self.original, str(self.pin))
        self.assertEqual(system.config_with_hold(text,str(self.pin)),text)
        self.assertLess(text.index(str(self.pin)),text.index('[extra]'))
        self.assertIn('IgnorePkg = linux',text)
        self.pin.write_text(runtime.pin_text(self.target)); self.conf.write_text(text)
        result = subprocess.run(['pacman-conf','--config',str(self.conf),'IgnorePkg'],capture_output=True,text=True,check=True)
        self.assertEqual(set(result.stdout.split()),{'linux','hyprland'})
        with self.assertRaisesRegex(RuntimeError,'options'): system.config_with_hold('[extra]\n',str(self.pin))

    def test_administrator_probe_drops_privileges_and_restores_runtime_directory(self):
        import os
        uid=os.getuid()
        output='Hyprland 0.56.2 built from branch v0.56.2 at commit '+self.target['commit']
        with patch.object(runtime.policy.os,'geteuid',return_value=0), \
             patch.dict(os.environ,{'SUDO_UID':str(uid)}), \
             patch.object(runtime.policy.subprocess,'run',return_value=subprocess.CompletedProcess([],0,output,'')) as run:
            self.assertEqual(runtime.policy.installed()['commit'],self.target['commit'])
        self.assertEqual(run.call_args.kwargs['user'],uid)
        self.assertEqual(run.call_args.kwargs['env']['XDG_RUNTIME_DIR'],'/run/user/'+str(uid))
        self.assertEqual(run.call_args.args[0],['/usr/bin/Hyprland','--version'])

    def test_gui_rerun_preserves_an_existing_registered_desktop(self):
        import launcher
        from types import SimpleNamespace
        from unittest.mock import Mock
        start=Mock(return_value=0)
        with patch.object(launcher.Path,'home',return_value=self.root), \
             patch.object(sys,'argv',['x_hyperinstall.sh','--gui']), \
             patch.object(launcher.ctypes,'CDLL'),patch.dict(sys.modules,{'wizard':SimpleNamespace(main=start)}):
            launcher.main();start.assert_called_with(update=False)
            profile=self.root/'.config/hypr';profile.mkdir(parents=True)
            (profile/'.xetal-update.json').write_text('{}')
            launcher.main();start.assert_called_with(update=True)

    def test_bad_download_never_replaces_a_verified_package(self):
        import io
        with patch.object(runtime,'urlopen',return_value=io.BytesIO(b'wrong bytes')):
            # Use a synthetic version to avoid the host's package cache.
            target={**self.target,'arch_package':'0.56.2-99'}
            with self.assertRaisesRegex(RuntimeError,'checksum'): runtime.download(target,self.root/'cache')
        self.assertFalse(list((self.root/'cache').glob('*.part')))
        self.assertFalse(list((self.root/'cache').glob('*.zst')))

    def test_package_pin_failure_restores_existing_configuration(self):
        self.pin.write_text('existing hold\n')
        def run(argv,**kwargs):
            if argv[0].endswith('pacman-conf'): raise subprocess.CalledProcessError(1,argv)
            return subprocess.CompletedProcess(argv,0,'hyprland '+self.target['arch_package']+'\n','')
        with patch.object(system.subprocess,'run',side_effect=run),patch.object(runtime.policy,'require'):
            with self.assertRaises(subprocess.CalledProcessError):
                system.install(conf=self.conf,pin=self.pin,state=self.state)
        self.assertEqual(self.conf.read_text(),self.original)
        self.assertEqual(self.pin.read_text(),'existing hold\n')

    def test_background_update_requests_setup_without_touching_packages_or_profile(self):
        import update as updater
        home=self.root/'recipient';home.mkdir()
        commit='a'*40
        with patch.object(updater.install,'source_revision',return_value=commit), \
             patch.object(runtime.policy,'installed',return_value={'version':'0.57.0','commit':'b'*40}), \
             patch.object(runtime,'ensure') as ensure,patch.object(updater.install,'build') as build:
            with self.assertRaisesRegex(RuntimeError,'requires Hyprland 0.56.2'):
                updater.prepare(home,commit)
        ensure.assert_not_called();build.assert_not_called()
        self.assertFalse((home/'.config/hypr').exists())
        record=json.loads((home/'.local/state/xetal-hyprland/updates/runtime-required.json').read_text())
        self.assertEqual(record['revision'],commit)

    def test_corrupted_package_is_rejected_before_pacman_or_hold_changes(self):
        package=self.root/'package.zst';package.write_bytes(b'corrupt');Path(str(package)+'.sig').write_bytes(b'bad sig')
        with patch.object(system.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','')) as run:
            with self.assertRaisesRegex(RuntimeError,'verification'):
                system.install(package,conf=self.conf,pin=self.pin,state=self.state)
        self.assertFalse(any('-U' in call.args[0] for call in run.call_args_list))
        self.assertEqual(self.conf.read_text(),self.original);self.assertFalse(self.pin.exists())

    def test_recovery_restores_previous_package_and_preserves_later_unrelated_config(self):
        self.state.mkdir(); backup=self.state/'fixture';backup.mkdir()
        previous=b'previous signed compositor';(backup/'previous.pkg.tar.zst').write_bytes(previous)
        (backup/'previous.pkg.tar.zst.sig').write_bytes(b'fixture signature')
        (backup/'pacman.conf').write_text(self.original)
        (backup/'record.json').write_text(json.dumps({'previous':'hyprland 0.57.0-1','required':self.target,
            'had_pin':False,'previous_sha256':hashlib.sha256(previous).hexdigest()}))
        self.conf.write_text(system.config_with_hold(self.original,str(self.pin))+'# later setting\n')
        self.pin.write_text(runtime.pin_text(self.target))
        with patch.object(system.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'hyprland '+self.target['arch_package'],'') ) as run:
            system.restore(backup,self.conf,self.pin,self.state)
        self.assertTrue(any('-U' in call.args[0] for call in run.call_args_list))
        self.assertEqual(self.conf.read_text(),self.original+'# later setting\n');self.assertFalse(self.pin.exists())
        with self.assertRaisesRegex(RuntimeError,'Invalid compositor recovery'):
            system.restore(self.root,self.conf,self.pin,self.state)

    def test_hold_only_recovery_does_not_require_or_reinstall_a_package(self):
        installed='hyprland '+self.target['arch_package']
        with patch.object(system.subprocess,'run',return_value=subprocess.CompletedProcess([],0,installed,'')) as run, \
             patch.object(runtime.policy,'require'):
            system.install(conf=self.conf,pin=self.pin,state=self.state)
            backup=next(path for path in self.state.iterdir() if path.is_dir())
            system.restore(backup,self.conf,self.pin,self.state)
        self.assertFalse(any('-U' in call.args[0] for call in run.call_args_list))
        self.assertEqual(self.conf.read_text(),self.original)
        self.assertFalse(self.pin.exists())

    def test_failed_postinstall_probe_restores_previous_package_before_returning(self):
        package=self.root/'new.pkg.tar.zst';package.write_bytes(b'tested package')
        Path(str(package)+'.sig').write_bytes(b'tested signature')
        previous=self.root/'old.pkg.tar.zst';previous.write_bytes(b'previous package')
        Path(str(previous)+'.sig').write_bytes(b'previous signature')
        target={**self.target,'package_sha256':hashlib.sha256(package.read_bytes()).hexdigest(),
                'signature_sha256':hashlib.sha256(Path(str(package)+'.sig').read_bytes()).hexdigest()}
        installed='hyprland 0.57.0-1';transactions=[]
        def run(argv,**kwargs):
            nonlocal installed
            if '-U' in argv:
                installed='hyprland 0.57.0-1' if Path(argv[-1]).name=='previous.pkg.tar.zst' else 'hyprland '+target['arch_package']
                transactions.append(installed)
            value='hyprland 0.57.0-1' if '-Qp' in argv else installed
            return subprocess.CompletedProcess(argv,0,value,'')
        with patch.object(runtime.policy,'manifest',return_value=target), \
             patch.object(runtime.policy,'require',side_effect=RuntimeError('Post-install probe failed')), \
             patch.object(system.subprocess,'run',side_effect=run):
            with self.assertRaisesRegex(RuntimeError,'Post-install probe failed'):
                system.install(package,previous,self.conf,self.pin,self.state)
        self.assertEqual(transactions,['hyprland '+target['arch_package'],'hyprland 0.57.0-1'])
        self.assertEqual(self.conf.read_text(),self.original);self.assertFalse(self.pin.exists())

    def test_failed_helper_still_returns_its_recovery_record_to_the_caller(self):
        import dependencies
        original_popen=subprocess.Popen
        backup=self.root/'recovery'
        def helper(*args,**kwargs):
            return original_popen([sys.executable,'-c',
                'print('+repr('XETAL_RUNTIME_TRANSACTION '+str(backup))+'); raise SystemExit(1)'],**kwargs)
        self.addCleanup(runtime.complete)
        with patch.object(runtime.policy,'problem',return_value='Version mismatch'), \
             patch.object(dependencies,'distro',return_value='arch'), \
             patch.object(runtime,'download',return_value=self.root/'package'), \
             patch.object(runtime,'previous_package',return_value=None), \
             patch.object(runtime,'administrator',return_value=[]),patch.object(runtime.subprocess,'Popen',side_effect=helper):
            with self.assertRaisesRegex(RuntimeError,'package setup failed'):runtime.ensure(yes=True)
        self.assertEqual(runtime.TRANSACTION,backup)


if __name__ == '__main__': unittest.main()
