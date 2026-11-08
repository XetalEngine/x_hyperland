"""Windows timing handoff with fake sysfs and a real local QMP fixture.

No guest, kernel module, SSH service or real module parameter is changed.
"""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import guest_timing
import module_state
import module_tool
import vm_memory
import vm_session
from test_module_image import elf


class TimingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='kvm-timing-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sysfs = self.root/'modules'
        self.receipt = self.root/'receipt.json'
        self.boot = self.root/'boot-id'
        self.boot.write_text('fixture-boot\n')
        self.versions = {'kvm': 'A'*24, 'kvm_amd': 'B'*24}
        for name, version in self.versions.items():
            directory = self.sysfs/name
            directory.mkdir(parents=True)
            (directory/'srcversion').write_text(version+'\n')
        self.param = self.sysfs/'kvm_amd/parameters/intercept_cpuid'
        self.param.parent.mkdir()
        self.param.write_text('Y\n')
        # Only the receipt's owner is simulated; permissions and symlinks still
        # go through the actual open/fstat checks on our disposable filesystem.
        fstat = os.fstat
        def root_stat(fd):
            fields = list(fstat(fd)); fields[4] = 0
            return os.stat_result(fields)
        for target, name, value in (
                (module_state, 'RECEIPT', self.receipt),
                (module_state, 'SYS_MODULE', self.sysfs),
                (module_state, 'BOOT_ID', self.boot)):
            mock = patch.object(target, name, value); mock.start(); self.addCleanup(mock.stop)
        for mock in (patch.object(module_state.platform, 'release', return_value='fixture-kernel'),
                     patch.object(os, 'geteuid', return_value=0),
                     patch.object(os, 'fstat', side_effect=root_stat)):
            mock.start(); self.addCleanup(mock.stop)
        module_state.record_loaded('fixture-kernel', self.versions)

    @contextmanager
    def qmp(self, *, name='win10', enabled=True, state='running', running=True, oversized=False):
        path = self.root/'qmp.sock'
        errors = []; commands = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path)); listener.listen(1); listener.settimeout(3)
            def serve():
                try:
                    with listener.accept()[0] as client:
                        client.settimeout(3)
                        client.sendall((b'x'*65537+b'\n') if oversized else b'{"QMP": {}}\n')
                        if oversized:
                            return
                        with client.makefile('rb') as stream:
                            for line in stream:
                                request = json.loads(line); command = request['execute']
                                commands.append(command)
                                value = {'qmp_capabilities': {}, 'query-name': {'name': name},
                                         'query-kvm': {'enabled': enabled},
                                         'query-status': {'status': state, 'running': running}}[command]
                                client.sendall(b'{"event": "RESUME"}\n')
                                client.sendall(json.dumps({'return': value, 'id': request['id']}).encode()+b'\n')
                except Exception as error:
                    errors.append(error)
            thread = threading.Thread(target=serve, daemon=True); thread.start()
            try:
                yield path, commands
            finally:
                thread.join(4)
                path.unlink(missing_ok=True)
                self.assertFalse(thread.is_alive(), 'QMP fixture did not exit')
                if errors:
                    raise errors[0]

    def test_authenticated_load_receipt_contains_only_public_identity(self):
        record = module_state.verified()
        self.assertEqual(record['srcversions'], self.versions)
        self.assertEqual(set(record), {'schema', 'kernel', 'boot_id', 'srcversions'})
        self.assertEqual(self.receipt.stat().st_mode & 0o777, 0o644)
        (self.sysfs/'kvm/srcversion').write_text('C'*24)
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            module_state.verified()

    def test_stale_or_missing_record_never_changes_the_parameter(self):
        for change in ('boot', 'kernel', 'missing', 'permission', 'owner', 'symlink'):
            with self.subTest(change=change):
                self.boot.write_text('fixture-boot\n')
                self.receipt.unlink(missing_ok=True)
                module_state.record_loaded('fixture-kernel', self.versions)
                if change == 'boot': self.boot.write_text('other-boot')
                elif change == 'kernel':
                    data = json.loads(self.receipt.read_text()); data['kernel'] = 'other'
                    self.receipt.write_text(json.dumps(data))
                elif change == 'missing': self.receipt.unlink()
                elif change == 'permission': self.receipt.chmod(0o666)
                elif change == 'symlink':
                    other = self.root/'other.json'; other.write_bytes(self.receipt.read_bytes())
                    self.receipt.unlink(); self.receipt.symlink_to(other)
                with patch.object(guest_timing, 'guest_state') as query:
                    if change == 'owner':
                        info = list(os.stat(self.receipt)); info[4] = 1234
                        with patch.object(os, 'fstat', return_value=os.stat_result(info)), self.assertRaises(RuntimeError):
                            guest_timing.apply('off', self.root/'qmp.sock', 'win10')
                    else:
                        with self.assertRaises(RuntimeError):
                            guest_timing.apply('off', self.root/'qmp.sock', 'win10')
                    query.assert_not_called()
                    self.assertEqual(self.param.read_text(), 'Y\n')

    def test_running_named_guest_enables_timing_and_on_restores_boot_setting(self):
        with self.qmp() as (path, commands), patch('sys.stdout', new_callable=io.StringIO) as output:
            guest_timing.apply('off', path, 'win10')
            self.assertEqual(self.param.read_text(), '0\n')
            self.assertIn('CPUID interception is OFF', output.getvalue())
        self.assertEqual(commands, ['qmp_capabilities', 'query-name', 'query-kvm', 'query-status'])
        with patch.object(guest_timing, 'guest_state', side_effect=AssertionError('on needs no guest')):
            guest_timing.apply('on', path, 'win10')
        self.assertEqual(self.param.read_text(), '1\n')

    def test_wrong_guest_paused_guest_and_software_emulation_never_write(self):
        for kwargs in ({'name': 'other'}, {'state': 'paused'}, {'enabled': False}, {'running': False}, {'oversized': True}):
            with self.subTest(kwargs=kwargs), self.qmp(**kwargs) as (path, _):
                with self.assertRaises((ValueError, RuntimeError)):
                    guest_timing.apply('off', path, 'win10')
                self.assertEqual(self.param.read_text(), 'Y\n')
        with self.assertRaisesRegex(RuntimeError, 'shut off'):
            guest_timing.apply('off', self.root/'absent.sock', 'win10')

    def test_failed_readback_and_unprivileged_call_are_reported(self):
        with patch.object(guest_timing, 'guest_state', return_value='running'), \
             patch.object(Path, 'write_text', return_value=2):
            with self.assertRaisesRegex(RuntimeError, 'did not retain'):
                guest_timing.apply('off', self.root/'qmp.sock', 'win10')
        with patch.object(os, 'geteuid', return_value=1000), \
             patch.object(module_state, 'verified') as verified:
            with self.assertRaisesRegex(RuntimeError, 'sudo'):
                guest_timing.apply('off', self.root/'qmp.sock', 'win10')
            verified.assert_not_called()

    def test_module_loader_records_identity_only_after_success_and_closes_fds(self):
        component = self.root/'component'; component.mkdir()
        (component/'.component.json').write_text(json.dumps({'kernel': 'fixture-kernel', 'runtime': {'component': 'kvm-amd'}}))
        for code in (0, 1):
            descriptors = []
            def receive(_path, name):
                fd = os.memfd_create('fixture', os.MFD_CLOEXEC)
                os.write(fd, elf(srcversion=(self.versions['kvm' if name == 'kvm.ko' else 'kvm_amd']).encode()))
                descriptors.append(fd)
                return fd
            def load(command, **kwargs):
                self.assertEqual(kwargs['pass_fds'], descriptors)
                self.assertEqual(kwargs['env']['XETAL_KVM_MEMORY_MODULES'], '1')
                self.assertEqual(command, ['/usr/bin/bash', str(component/'load-kvm.sh')])
                return subprocess.CompletedProcess(command, code)
            with patch.object(sys, 'argv', ['module-tool']), \
                 patch.object(module_tool, 'root', return_value=self.root), \
                 patch.object(module_tool, 'check', return_value=component), \
                 patch.object(vm_session, 'receive_image', side_effect=receive), \
                 patch.object(vm_memory, 'private_memory'), \
                 patch.object(subprocess, 'run', side_effect=load), \
                 patch.object(module_state, 'record_loaded', wraps=module_state.record_loaded) as record, \
                 patch.dict(os.environ, {}), self.assertRaises(SystemExit) as exit:
                module_tool.main()
            self.assertEqual(exit.exception.code, code)
            self.assertEqual(record.call_count, int(code == 0))
            for fd in descriptors:
                with self.assertRaises(OSError): os.fstat(fd)


if __name__ == '__main__':
    unittest.main()
