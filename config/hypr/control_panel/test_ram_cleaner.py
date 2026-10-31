"""Exercise the privileged operation against mocks, never the host's caches."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, mock_open, patch

import ram_cleaner as cleaner


class MemoryTests(unittest.TestCase):
    def test_shared_memory_is_not_advertised_as_reclaimable_cache(self):
        data = ('MemTotal: 10000 kB\nMemAvailable: 6000 kB\nMemFree: 1000 kB\n'
                'Cached: 4000 kB\nShmem: 1500 kB\nBuffers: 200 kB\n'
                'SReclaimable: 300 kB\nSwapTotal: 2000 kB\nSwapFree: 500 kB\n')
        with patch.object(Path, 'read_text', return_value=data):
            snapshot = cleaner.memory_snapshot()
        self.assertEqual(snapshot['file_cache'], 2700 * 1024)
        self.assertEqual(snapshot['metadata_cache'], 300 * 1024)
        self.assertEqual(snapshot['available'], 6000 * 1024)
        self.assertEqual(snapshot['swap_used'], 1500 * 1024)

    def test_invalid_statistics_fail_instead_of_showing_zero_capacity(self):
        for data in ('', 'MemTotal: 10 kB\n', 'MemTotal: 0 kB\nMemAvailable: 0 kB\n'):
            with patch.object(Path, 'read_text', return_value=data), self.assertRaises(ValueError):
                cleaner.memory_snapshot()

    def test_status_never_requests_privileges(self):
        with patch.object(cleaner, 'memory_snapshot', return_value={'total': 1024}), \
             patch.object(cleaner.os, 'execv') as execute, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(cleaner.main(['status']), 0)
            execute.assert_not_called()
            self.assertEqual(json.loads(output.getvalue()), {'total': 1024})

    def test_invalid_modes_cannot_reach_authentication_or_kernel_writes(self):
        with patch.object(cleaner.os, 'execv') as execute, patch.object(cleaner, 'apply') as apply, \
             patch('sys.stdout', new_callable=io.StringIO):
            for args in (['clean', '3'], ['clean', 'normal;reboot'], ['--apply', 'swapoff'], ['clean', 'normal', 'extra']):
                self.assertEqual(cleaner.main(args), 1)
            execute.assert_not_called()
            apply.assert_not_called()

    def test_authentication_uses_exact_arguments_without_a_shell(self):
        with patch.object(cleaner.os, 'execv') as execute, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(cleaner.main(['clean', 'aggressive']), 0)
        command, args = execute.call_args.args
        self.assertEqual(command, '/usr/bin/pkexec')
        self.assertEqual(args, ['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/python3',
                                '-I', str(Path(cleaner.__file__).resolve()), '--apply', 'aggressive'])


class CleanupTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.uid = stack.enter_context(patch.object(cleaner.os, 'geteuid', return_value=0))
        self.lock_open = stack.enter_context(patch.object(cleaner.os, 'open', return_value=123))
        stack.enter_context(patch.object(cleaner.os, 'fdopen', return_value=MagicMock()))
        self.lock = stack.enter_context(patch.object(cleaner.fcntl, 'flock'))
        self.client = stack.enter_context(patch.object(cleaner, 'check_client'))
        self.snapshots = stack.enter_context(patch.object(cleaner, 'memory_snapshot', side_effect=[{'available': 10}, {'available': 8}]))
        stack.enter_context(patch.object(cleaner, 'emit'))
        self.events = []
        self.sync = stack.enter_context(patch.object(cleaner.os, 'sync', side_effect=lambda: self.events.append('sync')))
        self.writer = mock_open()
        def open_target(path, mode):
            self.assertEqual(path, '/proc/sys/vm/drop_caches')
            self.assertEqual(mode, 'w')
            self.events.append('write')
            return self.writer(path, mode)
        self.open = stack.enter_context(patch('builtins.open', side_effect=open_target))

    def test_normal_only_drops_clean_file_cache_after_sync(self):
        result = cleaner.apply('normal')
        self.assertEqual(self.events, ['sync', 'write'])
        self.writer().write.assert_called_once_with('1\n')
        self.assertEqual(result['before']['available'], 10)
        self.assertEqual(result['after']['available'], 8)  # Do not invent a gain.
        self.assertTrue(result['ok'])

    def test_aggressive_adds_metadata_without_other_kernel_operations(self):
        cleaner.apply('aggressive')
        self.assertEqual(self.events, ['sync', 'write'])
        self.open.assert_called_once()
        self.writer().write.assert_called_once_with('3\n')

    def test_unprivileged_or_invalid_requests_do_nothing(self):
        self.uid.return_value = 1000
        with self.assertRaises(PermissionError): cleaner.apply('normal')
        with self.assertRaises(ValueError): cleaner.apply('compact')
        self.lock_open.assert_not_called()
        self.sync.assert_not_called()
        self.open.assert_not_called()

    def test_sync_failure_never_proceeds_to_reclamation(self):
        self.sync.side_effect = OSError('disk error')
        with self.assertRaises(OSError): cleaner.apply('normal')
        self.open.assert_not_called()

    def test_another_cleanup_blocks_work(self):
        self.lock.side_effect = BlockingIOError()
        with self.assertRaisesRegex(RuntimeError, 'already running'): cleaner.apply('aggressive')
        self.sync.assert_not_called()
        self.open.assert_not_called()

    def test_closing_panel_during_sync_prevents_reclamation(self):
        self.client.side_effect = [None, RuntimeError('panel closed')]
        with self.assertRaisesRegex(RuntimeError, 'panel closed'): cleaner.apply('normal')
        self.sync.assert_called_once()
        self.open.assert_not_called()


if __name__ == '__main__':
    unittest.main()
