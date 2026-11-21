"""Opt-in administrator boundary and reversible system configuration."""
from pathlib import Path
import json
import os
import sys
import tempfile
import subprocess
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'installer'))
import login_setup
import system_login
import install
import update
import service


class ChoiceTests(unittest.TestCase):
    def test_keyring_hooks_preserve_system_pam_and_complete_partial_configuration(self):
        original = '# auth optional pam_gnome_keyring.so\nauth include system-local-login\naccount include system-local-login\nsession optional pam_gnome_keyring.so # existing hook\n'
        content = system_login.keyring_pam(original, 'pam_kwallet5.so')
        self.assertIn('auth include system-local-login', content)
        self.assertIn('account include system-local-login', content)
        self.assertIn('\nauth optional pam_gnome_keyring.so\n', content)
        self.assertIn('session optional pam_gnome_keyring.so auto_start # existing hook', content)
        self.assertIn('session optional pam_kwallet5.so auto_start', content)
        self.assertEqual(system_login.keyring_pam(content, 'pam_kwallet5.so'), content)

    def test_default_and_unselected_options_never_request_admin_or_touch_system(self):
        with patch.object(login_setup, 'enabled', return_value=False), \
             patch.object(login_setup.runtime_install, 'administrator', side_effect=AssertionError('default must not authenticate')), \
             patch.object(login_setup.subprocess, 'run', side_effect=AssertionError('default must not run commands')):
            login_setup.apply(None, Path('/profile'))
            login_setup.apply(False, Path('/profile'))

    def test_explicit_choice_routes_to_privileged_helper_and_disable_restores(self):
        with patch.object(login_setup.runtime_install, 'administrator', return_value=['sudo']), \
             patch.object(login_setup, 'enabled', return_value=True), \
             patch.object(login_setup.subprocess, 'run') as run:
            login_setup.apply(True, Path('/profile'), skip_packages=True)
            command = run.call_args.args[0]
            self.assertIn('--source', command); self.assertIn('/profile', command)
            self.assertIn('--skip-packages', command)
            login_setup.apply(False, Path('/profile'))
            self.assertEqual(run.call_args.args[0][-2:], ['--restore', 'original'])

    def test_existing_greeter_migrates_without_requiring_a_new_opt_in(self):
        identity={'version':'0.57.2','adapter_sha256':'new'}
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'installation.json'
            for previous in ({}, {'version':'0.56.2'}, {'version':'0.57.2','adapter_sha256':'old'}):
                with self.subTest(previous=previous):
                    state.write_text(json.dumps({'enabled':True,'runtime':previous}))
                    with patch.object(login_setup,'STATE',state), \
                         patch.object(system_login,'runtime_identity',return_value=identity), \
                         patch.object(login_setup.runtime_install,'administrator',return_value=['sudo']), \
                         patch.object(login_setup.subprocess,'run') as run:
                        login_setup.apply(None,Path('/profile'))
                    self.assertEqual(run.call_args.args[0][-3:],['--refresh-runtime','--source','/profile'])
                    self.assertNotIn('--user',run.call_args.args[0])

    def test_matching_enabled_greeter_does_not_request_admin_again(self):
        identity={'version':'0.57.2','adapter_sha256':'same'}
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'installation.json'
            state.write_text(json.dumps({'enabled':True,'runtime':identity}))
            with patch.object(login_setup,'STATE',state), \
                 patch.object(system_login,'runtime_identity',return_value=identity), \
                 patch.object(login_setup.runtime_install,'administrator',side_effect=AssertionError('already matching')), \
                 patch.object(login_setup.subprocess,'run',side_effect=AssertionError('already matching')):
                login_setup.apply(None,Path('/profile'))

    def test_greeter_never_autologs_into_a_persons_desktop(self):
        configs = system_login.configuration()
        config = tomllib.loads(configs[Path('/etc/xetal-fusion-login/greetd.toml')])
        self.assertNotIn('initial_session', config)
        self.assertEqual(config['default_session']['user'], 'fusion-greeter')
        self.assertIn('--config /etc/xetal-fusion-login/hyprland.conf', config['default_session']['command'])
        compositor = configs[Path('/etc/xetal-fusion-login/hyprland.conf')]
        self.assertNotIn('startup-scene', compositor)
        self.assertNotIn('bind =', compositor)
        self.assertIn('disable_hyprland_guiutils_check = true', compositor)
        self.assertIn('plugin = /usr/local/lib/xetal-fusion-login/xetal-startup-notices.so', compositor)
        self.assertNotIn('suppress_errors', compositor)

    def test_power_policy_is_local_active_greeter_only_and_is_backed_up(self):
        self.assertIn(system_login.POWER_POLICY, system_login.SYSTEM_PATHS)
        policy = system_login.configuration()[system_login.POWER_POLICY]
        self.assertIn('subject.user === "fusion-greeter"', policy)
        self.assertIn('subject.local && subject.active', policy)
        self.assertIn('action.id === "org.freedesktop.login1.power-off"', policy)
        self.assertIn('action.id === "org.freedesktop.login1.reboot"', policy)
        self.assertNotIn('ignore-inhibit', policy)
        self.assertNotIn('multiple-sessions', policy)

    def test_modern_greeter_uses_lua_and_correct_session_exit_without_desktop_bindings(self):
        configs=system_login.configuration(modern=True)
        command=tomllib.loads(configs[system_login.CONFIG/'greetd.toml'])['default_session']['command']
        self.assertTrue(command.endswith('/hyprland.lua'))
        lua=configs[system_login.CONFIG/'hyprland.lua']
        self.assertIn('hl.plugin.load(',lua)
        self.assertIn('hl.on("hyprland.start"',lua)
        self.assertIn('greeter-session.sh',lua)
        self.assertNotIn('hl.bind(',lua)
        self.assertNotIn('startup-scene',lua)
        self.assertIn("dispatch 'hl.dsp.exit()'",system_login.session_script(True))
        self.assertIn('dispatch exit ',system_login.session_script(False))


class RuntimeRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.base=self.root/'state';self.base.mkdir()
        self.code=self.root/'code';self.code.mkdir()
        self.config=self.root/'config';self.config.mkdir()
        self.state=self.base/'installation.json'
        self.previous={'enabled':True,'user':'xetal','original_backup':'original','latest_backup':'old'}
        self.state.write_text(json.dumps(self.previous))
        self.legacy=system_login.configuration()[system_login.CONFIG/'hyprland.conf']+'\ninput {\nkb_layout = br\nkb_variant = abnt2\n}\n'
        (self.config/'hyprland.conf').write_text(self.legacy)
        (self.config/'greetd.toml').write_text('[default_session]\nuser="fusion-greeter"\ncommand="start-hyprland -- --config '+str(self.config/'hyprland.conf')+'"\n')
        (self.code/'xetal-startup-notices.so').write_bytes(b'old-plugin')
        (self.code/'app.py').write_text('existing greeter UI')
        self.source=self.root/'source'
        notices=self.source/'runtime/notices/.build';notices.mkdir(parents=True)
        (notices/'xetal-startup-notices.so').write_bytes(b'matching-plugin')
        self.identity={'version':'0.57.2','commit':'a'*40,'configuration':'lua','adapter_sha256':'checksum'}
        self.enterContext(patch.object(system_login.pwd,'getpwnam',return_value=system_login.pwd.getpwuid(os.getuid())))
        self.chown=self.enterContext(patch.object(system_login.os,'chown'))
        for name,value in (('BASE',self.base),('CODE',self.code),('CONFIG',self.config),('STATE',self.state)):
            patcher=patch.object(system_login,name,value);patcher.start();self.addCleanup(patcher.stop)

    def test_enabled_greeter_refresh_preserves_choices_and_replaces_only_runtime_files(self):
        with patch.object(system_login,'runtime_identity',return_value=self.identity), \
             patch.object(system_login,'run',return_value=subprocess.CompletedProcess([],0,'config ok','')) as run:
            backup=system_login.refresh_runtime(self.source)
        current=json.loads(self.state.read_text())
        self.assertEqual(current['original_backup'],'original')
        self.assertEqual(current['runtime'],self.identity)
        self.assertEqual(current['latest_backup'],str(backup))
        self.assertEqual((self.config/'hyprland.conf').read_text(),self.legacy)
        self.assertIn('["input.kb_layout"]="br"',(self.config/'hyprland.lua').read_text())
        self.assertIn('["input.kb_variant"]="abnt2"',(self.config/'hyprland.lua').read_text())
        self.assertIn('hyprland.lua',(self.config/'greetd.toml').read_text())
        self.assertEqual((self.code/'app.py').read_text(),'existing greeter UI')
        self.assertEqual((self.code/'xetal-startup-notices.so').read_bytes(),b'matching-plugin')
        self.assertEqual(len(run.call_args_list),1)
        self.assertIn('--verify-config',run.call_args.args[0])
        self.assertNotIn('systemctl',run.call_args.args[0])
        runtime=next(value.split('=',1)[1] for value in run.call_args.args[0] if value.startswith('XDG_RUNTIME_DIR='))
        self.assertFalse(Path(runtime).exists())
        self.chown.assert_any_call(runtime,os.getuid(),os.getgid())

    def test_failed_validation_restores_plugin_config_and_state(self):
        original=(self.config/'greetd.toml').read_text()
        with patch.object(system_login,'runtime_identity',return_value=self.identity), \
             patch.object(system_login,'run',side_effect=subprocess.CalledProcessError(1,['Hyprland'],
                          output='checking greeter\n',stderr='the actual configuration error')):
            with self.assertRaisesRegex(RuntimeError,'the actual configuration error'):system_login.refresh_runtime(self.source)
        self.assertEqual(json.loads(self.state.read_text()),self.previous)
        self.assertEqual((self.config/'greetd.toml').read_text(),original)
        self.assertEqual((self.code/'xetal-startup-notices.so').read_bytes(),b'old-plugin')
        self.assertFalse((self.config/'hyprland.lua').exists())

    def test_runtime_refresh_never_enables_a_disabled_greeter(self):
        self.state.write_text(json.dumps({'enabled':False}))
        with patch.object(system_login,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'will not enable'):system_login.refresh_runtime(self.source)
        run.assert_not_called()
        self.assertFalse((self.base/'backups').exists())


class BackupTests(unittest.TestCase):
    def test_runtime_adapter_replacement_does_not_overwrite_a_mapped_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'adapter.so'; path.write_bytes(b'old loaded adapter')
            with path.open('rb') as loaded:
                system_login.write(path, b'new adapter')
                self.assertEqual(loaded.read(), b'old loaded adapter')
            self.assertEqual(path.read_bytes(), b'new adapter')
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_upgrading_an_old_greeter_restores_newly_managed_files_to_their_original_state(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base/'root'; root.mkdir()
            backups = base/'state/backups'; backups.mkdir(parents=True)
            original = backups/'original'; original.mkdir()
            initial = system_login.Backup(original, root)
            initial.save(Path('/usr/local/lib/xetal-fusion-login'))
            initial.finish({})
            policy = system_login.POWER_POLICY; relative = str(policy).lstrip('/')
            for preexisting in (False, True):
                actual = root/relative; actual.parent.mkdir(parents=True, exist_ok=True)
                if preexisting: actual.write_text('administrator policy before Fusion')
                latest = backups/str(preexisting); latest.mkdir()
                upgraded = system_login.Backup(latest, root); upgraded.save(policy); upgraded.finish({})
                previous = {'original_backup': str(original)}
                with patch.object(system_login, 'BASE', base/'state'):
                    additions = system_login.original_additions(previous, latest)
                    self.assertEqual(additions, {relative: str(latest)})
                    later = {**previous, 'original_additions': additions}
                    self.assertEqual(system_login.original_additions(later, original), additions)
                    actual.write_text('Fusion policy')
                    state = base/'installation.json'; state.write_text(json.dumps(later))
                    real_restore = system_login.Backup.restore
                    def restore_test(path, **kwargs): return real_restore(path, root=root, **kwargs)
                    with patch.object(system_login, 'STATE', state), \
                         patch.object(system_login, 'run'), \
                         patch.object(system_login.Backup, 'restore', side_effect=restore_test):
                        system_login.restore('original')
                if preexisting: self.assertEqual(actual.read_text(), 'administrator policy before Fusion')
                else: self.assertFalse(actual.exists())

    def test_restore_retains_content_modes_symlinks_and_originally_absent_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base/'root'; root.mkdir()
            folder = root/'etc/systemd/system'; folder.mkdir(parents=True)
            original = folder/'example.service'; original.write_text('original\n'); original.chmod(0o640)
            link = folder/'display-manager.service'; link.symlink_to('/usr/lib/systemd/system/sddm.service')
            missing = folder/'fusion.service'
            saved = base/'backup'; saved.mkdir()
            backup = system_login.Backup(saved, root)
            for path in (original, link, missing): backup.save(Path('/')/path.relative_to(root))
            backup.finish({'previous_target': 'graphical.target'})
            original.write_text('changed'); original.chmod(0o644)
            link.unlink(); link.symlink_to('/etc/systemd/system/fusion.service')
            missing.write_text('new file')
            system_login.Backup.restore(saved, root)
            self.assertEqual(original.read_text(), 'original\n')
            self.assertEqual(original.stat().st_mode & 0o777, 0o640)
            self.assertEqual(os.readlink(link), '/usr/lib/systemd/system/sddm.service')
            self.assertFalse(missing.exists())

    def test_failed_setup_can_restore_entire_previous_code_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base/'root'; folder = root/'usr/local/lib/greeter'
            folder.mkdir(parents=True); (folder/'app.py').write_text('old version')
            saved = base/'backup'; saved.mkdir()
            backup = system_login.Backup(saved, root); backup.save(Path('/usr/local/lib/greeter')); backup.finish({})
            (folder/'app.py').write_text('bad version'); (folder/'added.py').write_text('new')
            system_login.Backup.restore(saved, root)
            self.assertEqual((folder/'app.py').read_text(), 'old version')
            self.assertFalse((folder/'added.py').exists())


class InstallRecoveryTests(unittest.TestCase):
    def test_login_failure_restores_desktop_before_outer_runtime_recovery(self):
        self.exercise_login_failure(True)

    def test_login_failure_after_waiver_keeps_desktop_matching_new_packages(self):
        self.exercise_login_failure(False)

    def exercise_login_failure(self, can_rollback):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)/'recipient'; target = home/'.config/hypr'
            target.mkdir(parents=True); (target/'hyprland.conf').write_text('original desktop')
            (target/'runtime').mkdir(); (target/'runtime/manifest.json').write_text('{}')
            def render(stage, *_):
                stage.mkdir(parents=True); (stage/'hyprland.conf').write_text('new desktop')
                return target
            with patch.object(Path, 'home', return_value=home), \
                 patch.object(install.os, 'geteuid', return_value=1000), \
                 patch.object(sys, 'argv', ['install.py', '--yes', '--skip-packages', '--fusion-login']), \
                 patch.object(install.dependencies, 'check', return_value=[]), \
                 patch.object(install, 'source_revision', return_value='a'*40), \
                 patch.object(install, 'connected_monitors', return_value=[]), \
                 patch.object(install, 'render', side_effect=render), \
                 patch.object(install, 'register_updates'), patch.object(install, 'validate_config'), \
                 patch.object(install, 'build'), patch.object(install, 'validate'), \
                 patch.object(install.runtime_install.policy, 'require') as require, \
                 patch.object(install.runtime_install, 'complete') as complete, \
                 patch.object(install.runtime_install, 'rollback_available', return_value=can_rollback), \
                 patch.object(install.commands, 'install'), \
                 patch.object(install.login_setup, 'apply', side_effect=RuntimeError('test login failure')):
                with self.assertRaisesRegex(RuntimeError, 'test login failure'): install.main()
            self.assertEqual((target/'hyprland.conf').read_text(), 'original desktop' if can_rollback else 'new desktop')
            if not can_rollback:
                saved = list((home/'.local/state/xetal-hyprland/backups').glob('*/hypr/hyprland.conf'))
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0].read_text(), 'original desktop')
            self.assertEqual(require.call_count, 1)
            complete.assert_not_called()


class UpdateRecoveryTests(unittest.TestCase):
    """Exercise actual profile activation and rollback around greeter failure."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.home=Path(temporary.name)/'recipient'
        self.live=self.home/'.config/hypr';self.live.mkdir(parents=True)
        self.state=self.home/'.local/state/xetal-hyprland/updates'
        self.stage=self.state/'prepared'
        (self.live/'code.py').write_text('old desktop')
        (self.live/'personal.txt').write_text('personal settings')
        engine=update.engine
        engine.write_json(self.live/engine.META,engine.metadata(self.live,'1'*40))
        self.before={path.name:path.read_bytes() for path in self.live.iterdir()}
        upstream=Path(temporary.name)/'upstream';upstream.mkdir()
        (upstream/'code.py').write_text('new desktop')
        expected=engine.merge_profile(self.live,upstream,self.stage,'2'*40)
        plan=engine.prepare_plan(self.live,self.stage,expected,'2'*40,automatic=False)
        engine.write_json(self.stage/'plan.json',plan)
        engine.write_json(self.state/'pending.json',{'revision':'2'*40,'stage':str(self.stage),'automatic':False})
        compatibility=SimpleNamespace(candidate=lambda *args:self.stage/'hyprland.conf')
        self.enterContext(patch.dict(sys.modules,{'hypr_compat':compatibility}))
        self.enterContext(patch.object(service,'ROOT',self.live))
        self.enterContext(patch.object(service.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'config ok','')))
        self.enterContext(patch.object(install.commands,'install'))
        self.complete=self.enterContext(patch.object(install.runtime_install,'complete'))

    def test_greeter_failure_restores_profile_before_runtime_recovery(self):
        def fail(choice, root):
            self.assertIsNone(choice)
            self.assertEqual((root/'code.py').read_text(),'new desktop')
            self.complete.assert_not_called()
            raise RuntimeError('greeter validation failed')
        with patch.object(login_setup,'apply',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'greeter validation failed'):
                update.activate(self.home)
        self.assertEqual({path.name:path.read_bytes() for path in self.live.iterdir()},self.before)
        self.assertEqual(update.engine.installed(self.live)['revision'],'1'*40)
        self.assertFalse((self.state/'pending.json').exists())
        self.complete.assert_not_called()
        self.assertEqual(update.engine.json_file(self.state/'status.json')['phase'],'attention')

    def test_success_keeps_recovery_active_until_greeter_is_ready(self):
        def finish(choice,root):
            self.assertIsNone(choice)
            self.assertEqual((root/'code.py').read_text(),'new desktop')
            self.complete.assert_not_called()
        with patch.object(login_setup,'apply',side_effect=finish) as apply:
            update.activate(self.home)
        apply.assert_called_once_with(None,self.live)
        self.complete.assert_called_once_with()
        self.assertEqual(update.engine.installed(self.live)['revision'],'2'*40)

    def test_greeter_failure_after_waiver_keeps_matching_new_profile_and_backup(self):
        (self.live/'notes.txt').write_text('personal settings')
        with patch.object(login_setup, 'apply', side_effect=RuntimeError('greeter validation failed')), \
             patch.object(install.runtime_install, 'rollback_available', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'greeter validation failed'):
                update.activate(self.home)
        self.assertEqual((self.live/'code.py').read_text(), 'new desktop')
        self.assertEqual((self.live/'notes.txt').read_text(), 'personal settings')
        self.assertEqual(update.engine.installed(self.live)['revision'], '2'*40)
        backup = Path(update.engine.json_file(self.state/'last-backup.json')['backup'])
        self.assertEqual((backup/'files/code.py').read_text(), 'old desktop')
        status = update.engine.json_file(self.state/'status.json')
        self.assertEqual(status['phase'], 'attention')
        self.assertIn('matching new desktop was kept', status['message'])
        self.complete.assert_not_called()

    def test_failed_activation_never_changes_greeter_or_commits_recovery(self):
        with patch.object(service,'activate',return_value=False),patch.object(login_setup,'apply') as apply:
            with self.assertRaisesRegex(RuntimeError,'could not be activated'):update.activate(self.home)
        apply.assert_not_called();self.complete.assert_not_called()
        self.assertEqual({path.name:path.read_bytes() for path in self.live.iterdir()},self.before)


if __name__ == '__main__': unittest.main()
