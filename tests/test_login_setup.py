"""Opt-in administrator boundary and reversible system configuration."""
from pathlib import Path
import json
import os
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'installer'))
import login_setup
import system_login
import install


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
                 patch.object(install.commands, 'install'), \
                 patch.object(install.login_setup, 'apply', side_effect=RuntimeError('test login failure')):
                with self.assertRaisesRegex(RuntimeError, 'test login failure'): install.main()
            self.assertEqual((target/'hyprland.conf').read_text(), 'original desktop')
            self.assertEqual(require.call_count, 1)
            complete.assert_not_called()


if __name__ == '__main__': unittest.main()
