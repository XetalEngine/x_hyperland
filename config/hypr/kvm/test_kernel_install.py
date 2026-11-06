"""Exact-kernel install orchestration, with all host mutations mocked."""
from contextlib import ExitStack
import fcntl
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import kernel_install as kernel


def image(release):
    data = bytearray(4096)
    data[0x202:0x206] = b'HdrS';data[0x20e:0x210] = (0x200).to_bytes(2, 'little')
    text = (release+' (builder@fixture)\0').encode();data[0x400:0x400+len(text)] = text
    return bytes(data)


def package(directory, name, target, *, embedded=None, header=None, version=None):
    path = directory/f'{name}-{target.version}-x86_64.pkg.tar.zst'
    is_headers = name.endswith('-headers')
    metadata = f'pkgname = {name}\npkgver = {version or target.version}\narch = x86_64\nsize = 4096\npkgdesc = Fixture\n'
    files = {'.PKGINFO':metadata.encode(),
             'usr/lib/modules/'+target.release+('/build/include/config/kernel.release' if is_headers else '/vmlinuz'):
                 ((header or target.release)+'\n').encode() if is_headers else image(embedded or target.release)}
    # libarchive detects compression from bytes; no compression needed here.
    with tarfile.open(path, 'w') as archive:
        for name, body in files.items():
            item = tarfile.TarInfo(name);item.size = len(body);archive.addfile(item, io.BytesIO(body))
    path.with_name(path.name+'.sig').write_bytes(b'fixture signature, never used by real pacman')
    return path


class KernelInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root = Path(temp.name);self.target = kernel.Target.parse('7.2.11-arch1-1')
        self.runner = kernel.Installer(self.target, state=self.root/'state')

    def test_mapping_requires_complete_arch_release_and_arch_family(self):
        self.assertEqual(self.target.version, '7.2.11.arch1-1')
        for release in ('7.2.11', '7.2.11-cachyos', '7.2.11-arch1-1;reboot', '../linux'):
            with self.assertRaises(RuntimeError):kernel.Target.parse(release)
        for family in ('arch', 'manjaro', 'cachyos'):
            self.assertFalse(kernel.platform_problem({'ID':family}, 'x86_64'))
        for family in ('debian', 'fedora'):
            self.assertTrue(kernel.platform_problem({'ID':family}, 'x86_64'))
        self.assertTrue(kernel.platform_problem({'ID':'arch'}, 'aarch64'))

    def test_payload_checks_kernel_bytes_and_matching_headers_not_just_names(self):
        first = package(self.root, 'linux', self.target)
        second = package(self.root, 'linux-headers', self.target)
        self.assertEqual(len(kernel.validate_pair([first, second], self.target, self.runner.run)), 2)
        package(self.root, 'linux', self.target, embedded='7.2.11-some-other-build')
        with self.assertRaisesRegex(RuntimeError, 'different release'):
            kernel.validate_pair([first, second], self.target, self.runner.run)
        package(self.root, 'linux', self.target)
        package(self.root, 'linux-headers', self.target, header='7.2.14-arch1-1')
        with self.assertRaisesRegex(RuntimeError, 'headers belong'):
            kernel.validate_pair([first, second], self.target, self.runner.run)

    def test_installed_check_verifies_image_and_headers(self):
        folder = self.root/'usr/lib/modules'/self.target.release;folder.mkdir(parents=True)
        (folder/'vmlinuz').write_bytes(image(self.target.release))
        self.assertTrue(kernel.installed(self.target, self.root));self.assertFalse(kernel.complete(self.target, self.root))
        header = folder/'build/include/config/kernel.release';header.parent.mkdir(parents=True);header.write_text(self.target.release)
        self.assertTrue(kernel.complete(self.target, self.root))
        (folder/'vmlinuz').write_bytes(image('7.2.14-arch1-1'))
        self.assertFalse(kernel.complete(self.target, self.root))

    def test_exact_cached_package_does_not_download_or_install_helpers(self):
        cache = self.root/'cache';cache.mkdir();source = package(cache, 'linux', self.target)
        dest = self.root/'dest';dest.mkdir()
        with patch.object(self.runner, 'caches', return_value=[cache]), \
             patch.object(self.runner, 'run', return_value=(0, 'linux\t7.2.14.arch1-1\thttps://mirror.invalid/new.zst')), \
             patch.object(self.runner, 'download') as download:
            result = self.runner.official_package('linux', self.target.version, dest)
        self.assertEqual(result.read_bytes(), source.read_bytes());download.assert_not_called()

    def install_fixture(self, *, available=True, signature=True):
        stack = ExitStack();self.addCleanup(stack.close)
        first = package(self.root, 'linux', self.target);second = package(self.root, 'linux-headers', self.target)
        metadata = [dict(pkgname=['linux'], pkgver=[self.target.version]), dict(pkgname=['linux-headers'], pkgver=[self.target.version])]
        stack.enter_context(patch.object(kernel, 'platform_problem', return_value=''))
        stack.enter_context(patch.object(kernel, 'complete', side_effect=[False, available]))
        stack.enter_context(patch.object(kernel.os, 'geteuid', return_value=1000))
        stack.enter_context(patch.object(kernel.shutil, 'which', return_value='/fixture/tool'))
        stack.enter_context(patch.object(kernel, 'validate_pair', return_value=metadata))
        stack.enter_context(patch.object(self.runner, 'official_package', side_effect=[first, second]))
        stack.enter_context(patch.object(self.runner, 'dependencies'))
        backup = stack.enter_context(patch.object(self.runner, 'backup_previous'))
        def run(args, **kwargs):
            if args[0] == 'pacman-key' and not signature:raise RuntimeError('Invalid signature')
            return ''
        commands = stack.enter_context(patch.object(self.runner, 'run', side_effect=run))
        return commands, backup

    def test_failed_signature_blocks_installation_and_aur_fallback(self):
        commands, backup = self.install_fixture(signature=False)
        with patch.object(self.runner, 'aur_pair') as aur:
            with self.assertRaisesRegex(RuntimeError, 'Invalid signature'):self.runner.install()
            aur.assert_not_called()
        backup.assert_not_called()
        self.assertFalse(any(c.args[0][0] == 'pacman' for c in commands.call_args_list))

    def test_success_preserves_checks_saves_record_and_requires_reboot(self):
        commands, backup = self.install_fixture()
        message = self.runner.install();backup.assert_called_once()
        self.assertIn('installed', message)
        self.assertTrue((self.runner.directory/'install.json').is_file())
        call = next(c for c in commands.call_args_list if c.args[0][0] == 'pacman')
        self.assertEqual(call.args[0][:3], ['pacman', '-U', '--noconfirm'])
        self.assertTrue(call.kwargs['admin'])
        self.assertNotIn('--nodeps', call.args[0]);self.assertNotIn('--overwrite', call.args[0])
        self.assertFalse(any('reboot' in c.args[0] for c in commands.call_args_list))

    def test_failed_post_install_verification_reports_failure(self):
        self.install_fixture(available=False)
        with self.assertRaisesRegex(RuntimeError, 'could not be verified'):self.runner.install()

    def test_missing_rollback_package_stops_before_replacing_kernel(self):
        self.runner.directory = self.root
        with patch.object(self.runner, 'run', return_value=(0, 'linux 7.2.14.arch1-1\n')), \
             patch.object(self.runner, 'official_package', side_effect=RuntimeError('Recovery package unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'Recovery package unavailable'):
                self.runner.backup_previous([dict(pkgname=['linux'], pkgver=[self.target.version])])

    def test_helper_fallback_attempts_both_and_keeps_working_one(self):
        self.runner.directory = self.root
        installed = set();calls = []
        def run(args, **kwargs):
            calls.append((args, kwargs))
            if args[:2] == ['pacman', '-Si']:return 0, 'in repo'
            if args[:2] == ['pacman', '-Syu']:
                if args[-1] == 'yay':raise RuntimeError('yay repository failure')
                installed.add(args[-1]);return ''
            return 0, 'version'
        with patch.object(self.runner, 'run', side_effect=run), \
             patch.object(self.runner, 'backup_standard_kernel'), \
             patch.object(kernel.shutil, 'which', side_effect=lambda name:'/bin/'+name if name in installed else None):
            self.assertEqual(self.runner.helpers(), ['/bin/paru'])
        self.assertEqual([a[-1] for a,k in calls if a[:2] == ['pacman','-Syu']], ['yay', 'paru'])

    def test_aur_does_not_substitute_a_kernel_with_only_matching_upstream_version(self):
        with patch.object(self.runner, 'helpers', return_value=['/bin/yay','/bin/paru']), \
             patch.object(self.runner, 'run', return_value=(0, 'aur/linux-other 7.2.11-1\n')) as run, \
             patch.object(self.runner, 'source_build') as build:
            with self.assertRaisesRegex(RuntimeError, 'exact release'):self.runner.aur_pair()
        self.assertEqual(run.call_count, 2);build.assert_not_called()

    def test_missing_dependencies_back_up_kernel_before_any_system_update(self):
        events = []
        def run(args, **kwargs):
            events.append(args[1]);return (127, 'git\n') if args[1] == '-T' else ''
        with patch.object(self.runner, 'run', side_effect=run), \
             patch.object(self.runner, 'backup_standard_kernel', side_effect=lambda:events.append('backup')):
            self.runner.dependencies(['git'])
        self.assertEqual(events, ['-T', 'backup', '-Syu'])

    def test_recovery_retains_original_packages_after_a_dependency_update(self):
        self.runner.directory = self.root
        metadata = [dict(pkgname=['linux'], pkgver=[self.target.version])]
        old = self.root/'original-kernel.pkg.tar.zst';old.write_bytes(b'fixture')
        def run(args, **kwargs):
            return (0, 'linux 7.2.14.arch1-1\n') if args[0] == 'pacman' else ''
        with patch.object(self.runner, 'run', side_effect=run) as calls, \
             patch.object(self.runner, 'official_package', return_value=old) as fetch:
            self.runner.backup_previous(metadata)
            self.runner.backup_previous(metadata)
        fetch.assert_called_once()
        self.assertEqual(sum(c.args[0][0] == 'pacman' for c in calls.call_args_list), 1)
        self.assertIn(str(old), (self.root/'restore.txt').read_text())

    def test_pacman_zero_exit_with_failed_boot_hook_is_still_a_failure(self):
        sys.path.insert(0, str(kernel.ROOT/'backend/lib'));self.addCleanup(sys.path.pop, 0)
        import uiutil
        script = 'print("error: command failed to execute correctly")'
        with patch.object(uiutil, 'sudo_command', return_value=([sys.executable,'-c',script], dict(os.environ), True)):
            with self.assertRaisesRegex(kernel.PackageTransactionError, 'Do not reboot'):
                self.runner.run(['pacman', '-U', '--', 'fixture-only'], admin=True)

    def test_helper_setup_does_not_continue_after_a_failed_system_transaction(self):
        self.runner.directory = self.root
        with patch.object(kernel.shutil, 'which', return_value=None), \
             patch.object(self.runner, 'backup_standard_kernel'), \
             patch.object(self.runner, 'run', side_effect=[(0, 'in repo'), kernel.PackageTransactionError('failed boot hook')]) as run:
            with self.assertRaisesRegex(kernel.PackageTransactionError, 'failed boot hook'):self.runner.helpers()
        self.assertEqual(run.call_count, 2)

    def test_cancel_prevents_commands_and_active_lock_is_detected(self):
        self.runner.cancel.set()
        with patch.object(kernel.subprocess, 'Popen') as popen:
            with self.assertRaises(kernel.Cancelled):self.runner.run(['pacman', '-U'], admin=True)
            popen.assert_not_called()
        self.runner.state.mkdir()
        with (self.runner.state/'install.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertTrue(kernel.active(self.runner.state))
        self.assertFalse(kernel.active(self.runner.state))

    def test_cancel_waits_for_started_package_operation_then_stops_next_step(self):
        sys.path.insert(0, str(kernel.ROOT/'backend/lib'));self.addCleanup(sys.path.pop, 0)
        import uiutil
        script = 'import time;time.sleep(.1);print("transaction finished")'
        def phase(text):
            if text.startswith('Installing packages'):self.runner.cancel.set()
        self.runner.phase = phase
        with patch.object(uiutil, 'sudo_command', return_value=([sys.executable,'-c',script], dict(os.environ), True)):
            self.assertIn('transaction finished', self.runner.run(['fixture-package-manager'], admin=True))
        with self.assertRaises(kernel.Cancelled):self.runner.checkpoint()


if __name__ == '__main__':unittest.main()
