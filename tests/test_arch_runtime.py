"""Matched Arch ABI packages, transaction recovery and older-system upgrades."""
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import arch_runtime as arch
import dependencies
import runtime_install as runtime
import system_arch_runtime as system


class ArchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='fusion-arch-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_release_contains_the_complete_verified_runtime_offline(self):
        with patch.object(arch, 'urlopen', side_effect=AssertionError('Unexpected network download')):
            packages = arch.packages(cache=self.root/'cache')
        self.assertEqual(len(packages), 12)
        self.assertLess(sum(p['bytes'] for p, _, _ in packages), 100_000_000)
        for item, package, signature in packages:
            self.assertEqual(arch.digest(package), item['sha256'])
            self.assertEqual(arch.digest(signature), item['signature_sha256'])
        for name in ('hyprland', 'aquamarine', 'hyprgraphics', 'hyprtoolkit', 'hyprlock'):
            self.assertIn(name, arch.expected())

    def test_missing_library_is_fetched_and_verified_with_its_signature(self):
        package, signature = b'library package', b'library signature'
        item = dict(name='aquamarine', file='aquamarine-1-1-x86_64.pkg.tar.zst',
                    sha256=hashlib.sha256(package).hexdigest(), signature_sha256=hashlib.sha256(signature).hexdigest())
        def fetch(url, **kwargs):
            self.assertTrue(url.startswith('https://archive.archlinux.org/packages/a/aquamarine/'))
            return io.BytesIO(signature if url.endswith('.sig') else package)
        with patch.object(runtime, 'BUNDLED', self.root/'absent'), patch.object(runtime, 'package_caches', return_value=[]), \
             patch.object(arch, 'urlopen', side_effect=fetch):
            [(_, saved, sig)] = arch.packages(self.root/'cache', {'packages':[item]})
        self.assertEqual(saved.read_bytes(), package)
        self.assertEqual(sig.read_bytes(), signature)

    def test_corrupt_download_never_becomes_an_installable_package(self):
        item = dict(name='aquamarine', file='aquamarine-1-1-x86_64.pkg.tar.zst',
                    sha256='a'*64, signature_sha256='b'*64)
        with patch.object(runtime, 'BUNDLED', self.root/'absent'), patch.object(runtime, 'package_caches', return_value=[]), \
             patch.object(arch, 'urlopen', return_value=io.BytesIO(b'corrupt')):
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                arch.packages(self.root/'cache', {'packages':[item]})
        self.assertFalse(list((self.root/'cache').iterdir()))

    def test_resolution_combines_full_upgrade_runtime_and_desktop(self):
        values = {**arch.expected(), 'kitty':'0.49.0-1', 'waybar':'0.15.0-1'}
        output = '\n'.join(name+' '+version for name, version in values.items())
        with patch.object(arch.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')) as run:
            result = arch.resolve(self.root/'conf', dependencies.PACKAGES['arch'])
        argv = run.call_args.args[0]
        self.assertIn('-Sup', argv)
        self.assertIn('xetal-fusion-runtime/aquamarine', argv)
        self.assertIn('xetal-fusion-runtime/hyprlock', argv)
        self.assertNotIn('hyprlock', argv)
        self.assertIn('dolphin', argv)
        self.assertNotIn('--nodeps', argv)
        self.assertEqual(result['hyprland'], arch.expected()['hyprland'])

    def test_private_repository_preserves_distribution_repositories_and_signature_checks(self):
        original = '[options]\nIgnorePkg = linux\nSigLevel = Required DatabaseOptional\n[manjaro]\nServer = https://example.invalid\n'
        changed = arch.configuration(original, self.root)
        self.assertLess(changed.index('[xetal-fusion-runtime]'), changed.index('[manjaro]'))
        self.assertIn('IgnorePkg = linux', changed)
        self.assertIn('PackageRequired DatabaseNever', changed)
        self.assertTrue(changed.endswith('[manjaro]\nServer = https://example.invalid\n'))
        with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
            arch.configuration(changed, self.root)

    def test_hold_protects_libraries_as_well_as_the_compositor(self):
        pin = self.root/'pin'
        pin.write_text(arch.hold_text())
        with patch.object(runtime, 'PIN', pin), patch.object(runtime, 'pacman_config', return_value=list(arch.expected())):
            self.assertTrue(arch.pinned())
            pin.write_text(runtime.pin_text(runtime.policy.manifest()))
            self.assertFalse(arch.pinned())

    def test_dependency_install_always_repairs_even_when_runtime_already_matches(self):
        with patch.object(dependencies, 'distro', return_value='arch'), patch.object(arch, 'ensure') as ensure:
            dependencies.install(True)
        ensure.assert_called_once_with(True, force=True)

    def test_old_system_keyring_refresh_keeps_distro_identity_and_signature_checks(self):
        with patch.object(runtime.policy, 'arch_versions', return_value={'archlinux-keyring':'old', 'manjaro-keyring':'old'}), \
             patch.object(system, 'run') as run:
            system.refresh_keyrings()
        args = run.call_args.args[0]
        self.assertEqual(args[-2:], ['archlinux-keyring', 'manjaro-keyring'])
        self.assertNotIn('--nodeps', args)
        self.assertNotIn('cachyos-keyring', args)
        self.assertNotIn('hyprland', args)

    def test_pacman_stock_config_upgrade_is_distinguished_from_external_edits(self):
        conf = self.root/'pacman.conf';conf.write_text('[options]\nnew default\n')
        db = self.root/'db';entry = db/'local/pacman-7.1-1';entry.mkdir(parents=True)
        checksum = hashlib.md5(conf.read_bytes()).hexdigest()
        (entry/'files').write_text('%BACKUP%\netc/pacman.conf\t'+checksum+'\n\n')
        real_path = Path
        with patch.object(system, 'Path', side_effect=lambda value:conf if str(value)=='/etc/pacman.conf' else real_path(value)), \
             patch.object(runtime, 'pacman_config', return_value=[str(db)]), \
             patch.object(runtime.policy, 'arch_versions', return_value={'pacman':'7.1-1'}):
            self.assertTrue(system.package_managed_config(conf))
            conf.write_text(conf.read_text()+'# a later user edit\n')
            self.assertFalse(system.package_managed_config(conf))

    def fixture_recovery(self):
        state = self.root/'state';state.mkdir()
        backup = state/'backup';backup.mkdir()
        (backup/'previous').mkdir()
        conf = self.root/'pacman.conf';conf.write_text('[options]\nIgnorePkg = linux\n')
        pin = self.root/'hold.conf';pin.write_text('new hold\n')
        (backup/'pacman.conf').write_text(conf.read_text())
        before = {'hyprland':'0.57.1-1', 'aquamarine':'0.16.0-1', 'hyprgraphics':'0.6.0-1'}
        expected = {name:arch.expected()[name] for name in before}
        record = dict(before=before, expected=expected, had_pin=False, new_hold='new hold\n', previous={})
        for name in before:
            package = backup/'previous'/(name+'.pkg.tar.zst');package.write_bytes(name.encode())
            Path(str(package)+'.sig').write_bytes(b'signature')
            record['previous'][name] = dict(file=package.name, sha256=arch.digest(package),
                                          signature_sha256=arch.digest(Path(str(package)+'.sig')))
        (backup/'record.json').write_text(json.dumps(record))
        return state, backup, conf, pin, record

    def test_recovery_restores_changed_libraries_and_compositor_in_one_transaction(self):
        state, backup, conf, pin, record = self.fixture_recovery()
        current = record['expected'].copy()
        def run(argv, **kwargs):
            if '-U' in argv:
                self.assertEqual(len([p for p in argv if str(p).endswith('.pkg.tar.zst')]), 3)
                current.update(record['before'])
            return subprocess.CompletedProcess(argv, 0, '', '')
        with patch.object(runtime.policy, 'arch_versions', side_effect=lambda _:current.copy()), \
             patch.object(system, 'run', side_effect=run) as calls, patch.object(system, 'verify'):
            system.restore(backup, state, conf, pin)
            system.restore(backup, state, conf, pin)  # Idempotent recovery.
        self.assertEqual(current, record['before'])
        self.assertEqual(sum('-U' in c.args[0] for c in calls.call_args_list), 1)
        self.assertIn('IgnorePkg = linux', conf.read_text())
        self.assertFalse(pin.exists())

    def test_external_library_change_stops_recovery_without_overwriting_it(self):
        state, backup, conf, pin, record = self.fixture_recovery()
        changed = {**record['expected'], 'aquamarine':'999.0-1'}
        with patch.object(runtime.policy, 'arch_versions', return_value=changed), patch.object(system, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'outside Setup'):
                system.restore(backup, state, conf, pin)
        run.assert_not_called()
        self.assertEqual(pin.read_text(), 'new hold\n')

    def test_corrupt_library_backup_is_rejected_before_any_package_change(self):
        state, backup, conf, pin, record = self.fixture_recovery()
        (backup/'previous/aquamarine.pkg.tar.zst').write_bytes(b'wrong')
        with patch.object(runtime.policy, 'arch_versions', return_value=record['expected']), \
             patch.object(system, 'verify'), patch.object(system, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'recovery package changed'):
                system.restore(backup, state, conf, pin)
        run.assert_not_called()

    def test_external_hold_change_blocks_recovery_before_package_changes(self):
        state, backup, conf, pin, record = self.fixture_recovery()
        pin.write_text('a later user hold\n')
        with patch.object(system, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'edited externally'):
                system.restore(backup, state, conf, pin)
        run.assert_not_called()
        self.assertEqual(pin.read_text(), 'a later user hold\n')

    def test_arch_bundle_recovery_routes_to_its_own_helper(self):
        self.addCleanup(runtime.complete)
        with patch.object(runtime, 'TRANSACTION', self.root/'backup'), patch.object(runtime, 'TRANSACTION_BACKEND', 'arch-bundle'), \
             patch.object(runtime, 'administrator', return_value=['sudo']), patch.object(runtime.subprocess, 'run') as run:
            runtime.rollback()
        self.assertIn(str(ROOT/'installer/system_arch_runtime.py'), run.call_args.args[0])

    def test_python_upgrade_restarts_worker_with_its_arguments_and_recovery(self):
        record = Path('/var/lib/xetal-hyprland/arch-runtime/test-recovery')
        with patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '9.99\n', '')), \
             patch.object(runtime, 'TRANSACTION', record), patch.object(runtime, 'TRANSACTION_BACKEND', 'arch-bundle'), \
             patch.object(sys, 'argv', ['installer/install.py', '--yes', '--cancel-file', '/tmp/cancel']), \
             patch.object(runtime.os, 'execve') as restart:
            runtime.restart_after_python_upgrade()
        binary, args, environment = restart.call_args.args
        self.assertEqual(binary, '/usr/bin/python3')
        self.assertEqual(args[1:], ['installer/install.py', '--yes', '--cancel-file', '/tmp/cancel'])
        self.assertEqual(json.loads(environment['XETAL_SETUP_PACKAGE_RECOVERY']),
                         dict(backend='arch-bundle', path=str(record)))

    def test_unchanged_python_does_not_restart_setup(self):
        version = '%d.%d' % sys.version_info[:2]
        with patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, version+'\n', '')), \
             patch.object(runtime.os, 'execve') as restart:
            runtime.restart_after_python_upgrade()
        restart.assert_not_called()


if __name__ == '__main__':
    unittest.main()
