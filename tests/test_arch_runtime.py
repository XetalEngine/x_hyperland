"""Matched Arch ABI packages, transaction recovery and older-system upgrades."""
from contextlib import ExitStack, redirect_stdout
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

    def test_local_build_with_repository_name_is_preserved_but_runtime_is_mandatory(self):
        database=self.root/'db'
        for name, validation in (('discord','none'),('curl','pgp'),('hyprland','none'),('aquamarine','none')):
            entry=database/'local'/(name+'-1-1');entry.mkdir(parents=True)
            (entry/'desc').write_text('%NAME%\n'+name+'\n\n%VERSION%\n1-1\n\n%VALIDATION%\n'+validation+'\n\n')
        preserve=arch.local_packages(database)
        self.assertEqual(preserve, {'discord'})
        original='[options]\nSigLevel = Required DatabaseOptional\n[extra]\nServer = https://example.invalid\n'
        config=arch.configuration(original,self.root/'runtime',preserve)
        self.assertLess(config.index('IgnorePkg = discord'), config.index('[extra]'))
        self.assertIn('SigLevel = Required DatabaseOptional',config)
        self.assertIn('PackageRequired DatabaseNever',config)
        self.assertNotIn('discord',arch.package_args(['discord','hyprland'],preserve=preserve))
        self.assertIn('xetal-fusion-runtime/hyprland',arch.package_args(['discord','hyprland'],preserve=preserve))
        self.assertNotIn('discord',arch.hold_text())  # No permanent local-app hold.

    def test_preserved_local_build_still_requires_a_valid_complete_dependency_graph(self):
        failed=subprocess.CompletedProcess([],1,'installing openssl breaks dependency required by local-app','failed')
        with patch.object(arch.subprocess,'run',return_value=failed) as run:
            with self.assertRaisesRegex(RuntimeError,'local-app'):
                arch.resolve(self.root/'conf',['local-app'],preserve={'local-app'})
        args=run.call_args.args[0]
        self.assertIn('-Sup',args)
        self.assertNotIn('--nodeps',args)
        self.assertNotIn('local-app',args)

    def test_recovery_prepares_all_system_libraries_in_an_isolated_database(self):
        backup = self.root/'backup'; backup.mkdir()
        database = self.root/'database'
        for name in ('local', 'sync'):
            (database/name).mkdir(parents=True)
            (database/name/'sentinel').write_text('original')
        before = {'hyprland':'old', 'openssl':'3', 'libjxl':'0.12', 'replaced-package':'1'}
        expected = {'hyprland':'new', 'openssl':'4', 'libjxl':'0.13', 'new-helper':'1'}
        previous = {name:{'file':name+'.pkg.tar.zst'} for name in before}
        base = '[options]\nSigLevel = Required DatabaseOptional\n[core]\nServer = https://example.invalid\n'
        with patch.object(system, 'inventory', side_effect=[before, expected, before, before]), \
             patch.object(system, 'save_previous', return_value=previous) as save, \
             patch.object(system.recovery, 'replay') as replay, \
             patch.object(system, 'run') as calls:
            actual = system.prepare_recovery(backup, ['pacman'], ['hyprland'], database, base)
        self.assertEqual(actual, (before, expected, previous))
        save.assert_called_once_with(backup, before, expected)
        for call in calls.call_args_list:
            args = call.args[0]
            self.assertIn('--dbonly', args)
            self.assertIn('--noscriptlet', args)
            self.assertEqual(args[args.index('--dbpath')+1], backup/'projection/db')
            self.assertEqual(args[args.index('--root')+1], backup/'projection/root')
            self.assertNotIn('--nodeps', args)
        rollback = replay.call_args.args[2]
        for name in ('openssl', 'libjxl', 'replaced-package'):
            self.assertIn(dict(path=str(backup/'previous'/(name+'.pkg.tar.zst')),name=name,version=before[name]), rollback)
        self.assertEqual(replay.call_args.args[3],[dict(name='new-helper',version='1')])
        self.assertTrue(replay.call_args.kwargs['database_only'])
        self.assertNotIn('[core]', (backup/'recovery.conf').read_text())
        self.assertEqual((database/'local/sentinel').read_text(), 'original')

    def test_incompatible_recovery_stops_before_any_live_package_transaction(self):
        backup = self.root/'backup'; backup.mkdir()
        database = self.root/'database'
        for name in ('local', 'sync'): (database/name).mkdir(parents=True)
        before, after = {'openssl':'3'}, {'openssl':'4', 'new-helper':'1'}
        def run(args, **kwargs):self.assertIn('--dbonly', args)
        with patch.object(system, 'inventory', side_effect=[before, after]), \
             patch.object(system, 'save_previous', return_value={'openssl':{'file':'openssl.pkg.tar.zst'}}), \
             patch.object(system.recovery, 'replay',side_effect=subprocess.CalledProcessError(1,['arch-recovery'])), \
             patch.object(system, 'run', side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                system.prepare_recovery(backup, ['pacman'], ['hyprland'], database, '[options]\n')
        self.assertFalse((backup/'record.json').exists())

    def test_reused_recovery_archives_are_verified_again_for_the_exact_installed_version(self):
        backup=self.root/'new-attempt';backup.mkdir()
        old=self.root/'old-attempt/previous';old.mkdir(parents=True)
        file='appstream-1.2.2-1-x86_64.pkg.tar.zst'
        (old/file).write_bytes(b'cached archive');(old/(file+'.sig')).write_bytes(b'cached signature')
        def queries(args,**kwargs):
            if args[:2]==['pacman','-Q']:value='appstream 1.2.2-1\n'
            elif args[:2]==['pacman','-Qi']:value='Name : appstream\nArchitecture : x86_64\n'
            else:raise AssertionError('Unexpected package command: '+repr(args))
            return subprocess.CompletedProcess(args,0,value,'')
        with patch.object(runtime.subprocess,'run',side_effect=queries), \
             patch.object(runtime,'package_caches',return_value=[]), \
             patch.object(runtime,'urlopen',side_effect=AssertionError('Cached archive attempted download')), \
             patch.object(system,'verify') as verify:
            saved=system.save_previous(backup,{'appstream':'1.2.2-1'},{'appstream':'1.2.3-1'})
        verify.assert_called_once_with(backup/'previous'/file,'appstream 1.2.2-1')
        self.assertEqual(saved['appstream']['sha256'],hashlib.sha256(b'cached archive').hexdigest())
        self.assertEqual(saved['appstream']['signature_sha256'],hashlib.sha256(b'cached signature').hexdigest())

    def test_reused_recovery_archive_with_bad_signature_still_stops_preparation(self):
        backup=self.root/'new-attempt';backup.mkdir()
        def saved(directory,name,**kwargs):
            path=directory/'untrusted.pkg.tar.zst';path.write_bytes(b'untrusted');return path
        with patch.object(runtime,'previous_package',side_effect=saved), \
             patch.object(system,'verify',side_effect=subprocess.CalledProcessError(1,['pacman-key','--verify'])):
            with self.assertRaises(subprocess.CalledProcessError):
                system.save_previous(backup,{'appstream':'1.2.2-1'},{'appstream':'1.2.3-1'})
        self.assertFalse((backup/'record.json').exists())

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
        before = {'hyprland':'0.56.2-4', 'aquamarine':'0.15.1-1', 'hyprgraphics':'0.5.1-4'}
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

    def test_full_recovery_removes_new_compatibility_packages_with_old_libraries(self):
        state, backup, conf, pin, record = self.fixture_recovery()
        record['schema']=3
        record['expected']['compat-library']='1-1'
        (backup/'record.json').write_text(json.dumps(record))
        (backup/'recovery.conf').write_text('[options]\n')
        current=record['expected'].copy()
        def replay(saved, base, additions, removals, inventory):
            self.assertEqual(saved,backup)
            self.assertEqual(inventory,current)
            self.assertEqual({item['name'] for item in additions},set(record['before']))
            self.assertEqual(removals,[dict(name='compat-library',version='1-1')])
            current.clear();current.update(record['before'])
        with patch.object(runtime.policy,'arch_versions',side_effect=lambda _:current.copy()), \
             patch.object(system,'inventory',side_effect=lambda:current.copy()), \
             patch.object(system,'verify'),patch.object(system.recovery,'replay',side_effect=replay) as transaction:
            system.restore(backup,state,conf,pin)
        transaction.assert_called_once()
        self.assertTrue(json.loads((backup/'record.json').read_text())['restored'])
        self.assertEqual(current,record['before'])

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

    def test_non_utf8_signer_does_not_interrupt_runtime_output_or_lose_recovery(self):
        record=self.root/'recovery'
        output=b'gpg: Good signature from "Test Jos\xf3"\nXETAL_RUNTIME_TRANSACTION '+str(record).encode()+b'\n'
        child=[sys.executable,'-c','import os;os.write(1,'+repr(output)+')']
        log=io.StringIO()
        with patch.object(arch,'packages'),patch.object(arch,'pinned',return_value=True), \
             patch.object(runtime,'administrator',return_value=child), \
             patch.object(runtime,'TRANSACTION',None),patch.object(runtime,'TRANSACTION_BACKEND','arch'), \
             patch.object(runtime.policy,'require'),patch.object(runtime.policy,'arch_versions',return_value=arch.expected()), \
             redirect_stdout(log):
            self.assertTrue(arch.ensure(yes=True,force=True))
            self.assertEqual(runtime.TRANSACTION,record)
            self.assertEqual(runtime.TRANSACTION_BACKEND,'arch-bundle')
        self.assertIn('Good signature',log.getvalue())
        self.assertIn('\ufffd',log.getvalue())

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
                         dict(backend='arch-bundle', path=str(record), rollback_available=True))

    def test_unchanged_python_does_not_restart_setup(self):
        version = '%d.%d' % sys.version_info[:2]
        with patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, version+'\n', '')), \
             patch.object(runtime.os, 'execve') as restart:
            runtime.restart_after_python_upgrade()
        restart.assert_not_called()


if __name__ == '__main__':
    unittest.main()
