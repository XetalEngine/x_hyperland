"""Real disposable files plus injected I/O failures for local transfer safety."""
from contextlib import suppress
import errno
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from transfer_worker import Transfer, Undo, Control, Cancelled, Counter
from transfer_io import FileOps
from transfer_authority import send, receive, serve


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fusion-native-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base/'source'; self.source.mkdir()
        self.target = self.base/'target'; self.target.mkdir()
        self.events = []
        self.control = Control(self.events.append)
        self.sequence = 0

    def request(self, sources=None, operation='copy', destination=None):
        self.sequence += 1
        return dict(sources=[str(p) for p in (sources or [self.source])],
                    destination=str(destination or self.target), operation=operation,
                    journal=str(self.base/f'journal-{self.sequence}.sqlite'))

    def transfer(self, request=None, cls=Transfer):
        transfer = cls(request or self.request(), self.control, self.events.append)
        self.addCleanup(transfer.close)
        return transfer

    def write(self, name, value=b'original'):
        path = self.source/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
        return path

    def force_cross_device(self, transfer):
        execute = transfer.ops.execute
        def run(action, args):
            if action == 'rename': raise OSError(errno.EXDEV, 'Cross-device link')
            return execute(action, args)
        transfer.ops.execute = run

    def test_copy_starts_without_waiting_for_counter_and_handles_names(self):
        self.write("a;$(touch nope)\n# 100% café.txt", b'contents')
        self.write('folder/empty', b'')
        (self.source/'empty-dir').mkdir()
        def count(counter): counter.stop.wait(5)
        with patch.object(Counter, 'run', count):
            transfer = self.transfer(); self.assertTrue(transfer.run()['ok'])
        self.assertEqual((self.target/'source'/"a;$(touch nope)\n# 100% café.txt").read_bytes(), b'contents')
        self.assertTrue((self.target/'source'/'empty-dir').is_dir())
        self.assertTrue(any(e.get('totalsKnown') is False for e in self.events))
        self.assertEqual(self.events[-1]['processedFiles'], 2)
        self.assertTrue(self.events[-1]['totalsKnown'])

    def test_same_filesystem_move_is_rename_and_undo_restores_inode(self):
        item = self.write('a')
        before = item.stat().st_ino
        transfer = self.transfer(self.request(operation='move'))
        with patch.object(transfer, 'copy_file', side_effect=AssertionError('must rename')):
            self.assertTrue(transfer.run()['ok'])
        self.assertFalse(self.source.exists())
        self.assertEqual((self.target/'source'/'a').stat().st_ino, before)
        undo = self.transfer(dict(operation='undo', undoJournal=transfer.journal,
                                  journal=str(self.base/'undo.sqlite')), Undo)
        self.assertTrue(undo.run()['ok'])
        self.assertEqual(item.stat().st_ino, before)

    def test_move_copies_everything_before_verification_or_deletion(self):
        first = self.write('a', b'A'*32); second = self.write('nested/b', b'B'*128)
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        verify = transfer.verify
        def observed():
            self.assertTrue(first.exists()); self.assertTrue(second.exists())
            self.assertEqual((self.target/'source'/'nested'/'b').read_bytes(), b'B'*128)
            verify()
        transfer.verify = observed
        self.assertTrue(transfer.run()['ok'])
        self.assertFalse(self.source.exists())
        undo = self.transfer(dict(operation='undo', undoJournal=transfer.journal,
                                  journal=str(self.base/'undo.sqlite')), Undo)
        self.assertTrue(undo.run()['ok'])
        self.assertEqual(first.read_bytes(), b'A'*32); self.assertEqual(second.read_bytes(), b'B'*128)
        self.assertFalse((self.target/'source').exists())

    def test_failure_on_later_file_keeps_all_cross_device_originals(self):
        self.write('a'); self.write('b')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        copy = transfer.copy_file; copied = []
        def fail_later(*args):
            if copied: raise OSError(errno.ENOSPC, 'No space left')
            copy(*args); copied.append(args[0])
        transfer.copy_file = fail_later
        with self.assertRaises(OSError): transfer.run()
        self.assertTrue((self.source/'a').exists()); self.assertTrue((self.source/'b').exists())
        self.assertEqual(len(list((self.target/'source').iterdir())), 1)

    def test_corruption_during_verification_keeps_all_originals(self):
        self.write('a'); self.write('b')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        verify = transfer.verify
        def corrupt():
            (self.target/'source'/'b').write_bytes(b'corrupted')
            verify()
        transfer.verify = corrupt
        with self.assertRaises(OSError): transfer.run()
        self.assertEqual((self.source/'a').read_bytes(), b'original')
        self.assertEqual((self.source/'b').read_bytes(), b'original')

    def test_source_or_destination_change_after_verification_prevents_cleanup(self):
        for side in ('source', 'target'):
            with self.subTest(side=side):
                self.write('a'); self.write('b')
                target = self.base/('target-'+side); target.mkdir()
                transfer = self.transfer(self.request(operation='move', destination=target)); self.force_cross_device(transfer)
                verify = transfer.verify
                def modify():
                    verify()
                    ((self.source if side == 'source' else target/'source')/'b').write_bytes(b'changed')
                transfer.verify = modify
                with self.assertRaises(OSError): transfer.run()
                self.assertTrue((self.source/'a').exists()); self.assertTrue((self.source/'b').exists())

    def test_partial_overwrite_failure_keeps_destination_and_cleans_temp(self):
        item = self.write('a', b'new data')
        old = self.target/'a'; old.write_bytes(b'old data')
        transfer = self.transfer(self.request([item])); self.control.question = lambda *args: 'replace'
        def fail(source, target, size):
            os.write(target, b'partial'); raise OSError(errno.ENOSPC, 'No space left')
        with patch('transfer_worker.fcntl.ioctl', side_effect=OSError(errno.EOPNOTSUPP, 'not supported')):
            transfer.copy_data = fail
            with self.assertRaises(OSError): transfer.run()
        self.assertEqual(old.read_bytes(), b'old data')
        self.assertEqual(item.read_bytes(), b'new data')
        self.assertEqual(list(self.target.iterdir()), [old])

    def test_cancel_mid_file_keeps_original_and_previous_destination(self):
        item = self.write('a', b'new data')
        old = self.target/'a'; old.write_bytes(b'old data')
        transfer = self.transfer(self.request([item], operation='move')); self.control.question = lambda *args: 'replace'
        def cancel(source, target, size):
            os.write(target, b'partial'); self.control.cancelled = True; self.control.check()
        with patch('transfer_worker.fcntl.ioctl', side_effect=OSError(errno.EOPNOTSUPP, 'not supported')):
            transfer.copy_data = cancel
            with self.assertRaises(Cancelled): transfer.run()
        self.assertEqual(old.read_bytes(), b'old data'); self.assertEqual(item.read_bytes(), b'new data')
        self.assertFalse(list(self.target.glob('.fusion-*')))

    def test_skip_merges_new_children_and_keeps_skipped_move_originals(self):
        self.write('folder/a'); self.write('folder/new', b'new')
        target = self.target/'source'/'folder'; target.mkdir(parents=True); (target/'a').write_bytes(b'keep')
        self.control.question = lambda *args: 'skip'
        transfer = self.transfer(self.request(operation='move')); self.assertTrue(transfer.run()['ok'])
        self.assertEqual((target/'a').read_bytes(), b'keep'); self.assertEqual((target/'new').read_bytes(), b'new')
        self.assertTrue((self.source/'folder'/'a').exists()); self.assertFalse((self.source/'folder'/'new').exists())
        self.assertEqual(transfer.skipped, 1)

    def test_symlinks_are_not_followed_and_self_copy_is_numbered(self):
        self.write('sub/a')
        (self.source/'loop').symlink_to(self.source, target_is_directory=True)
        (self.source/'dangling').symlink_to('not-there')
        self.write('backup.tar.gz')
        transfer = self.transfer(self.request([self.source/'backup.tar.gz'], destination=self.source)); transfer.run()
        self.assertTrue((self.source/'backup_copy1.tar.gz').exists())
        transfer = self.transfer(); transfer.run()
        self.assertTrue((self.target/'source'/'loop').is_symlink())
        self.assertEqual(os.readlink(self.target/'source'/'dangling'), 'not-there')
        self.assertEqual((self.target/'source'/'sub'/'a').read_bytes(), b'original')

    def test_copy_into_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'into itself'):
            self.transfer(self.request(destination=self.source)).run()

    def test_sparse_copy_fallback_and_short_kernel_copies(self):
        item = self.source/'sparse'
        with item.open('wb') as stream:
            stream.write(b'head'); stream.seek(32*1024*1024); stream.write(b'tail')
        real = os.copy_file_range
        def short(source, target, count): return real(source, target, min(count, 1024))
        with patch('transfer_worker.fcntl.ioctl', side_effect=OSError(errno.EOPNOTSUPP, 'not supported')):
            with patch('transfer_worker.os.copy_file_range', side_effect=short): self.transfer().run()
        result = self.target/'source'/'sparse'
        self.assertEqual(result.stat().st_size, item.stat().st_size)
        self.assertLess(result.stat().st_blocks*512, result.stat().st_size//2)
        with result.open('rb') as stream:
            self.assertEqual(stream.read(4), b'head'); stream.seek(-4, 2); self.assertEqual(stream.read(), b'tail')

    def test_mode_timestamp_and_user_attributes_survive(self):
        item = self.write('script', b'#!/bin/sh\n')
        item.chmod(0o751); os.utime(item, ns=(1234567890000000000, 1234567890123456789))
        os.setxattr(item, 'user.fusion-test', b'attribute')
        self.transfer().run()
        result = self.target/'source'/'script'
        self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o751)
        self.assertEqual(result.stat().st_mtime_ns, item.stat().st_mtime_ns)
        self.assertEqual(os.getxattr(result, 'user.fusion-test'), b'attribute')

    def test_moving_multiple_hardlinks_does_not_mistake_our_unlink_for_an_edit(self):
        first = self.write('first', b'shared')
        os.link(first, self.source/'second')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        self.assertTrue(transfer.run()['ok'])
        self.assertFalse(self.source.exists())
        for name in ('first', 'second'): self.assertEqual((self.target/'source'/name).read_bytes(), b'shared')

    def test_short_reads_do_not_falsely_fail_content_verification(self):
        self.write('a', b'abcdefgh'*4096)
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        read = os.read
        with patch('transfer_worker.os.read', side_effect=lambda fd, size: read(fd, min(123, size))):
            self.assertTrue(transfer.run()['ok'])

    def test_new_source_child_during_verification_is_kept_and_reported(self):
        self.write('a')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        verify = transfer.verify
        def added():
            verify(); self.write('created-later', b'keep me')
        transfer.verify = added
        result = transfer.run()
        self.assertTrue(result['ok']); self.assertTrue(result['warnings'])
        self.assertEqual((self.source/'created-later').read_bytes(), b'keep me')
        self.assertFalse((self.source/'a').exists())

    def test_permission_refusal_keeps_completed_copies_and_all_move_originals(self):
        self.write('a'); self.write('private')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        execute = transfer.ops.execute
        def denied(action, args):
            if action == 'read' and args['path'].endswith('/private'): raise PermissionError(errno.EACCES, 'Denied')
            return execute(action, args)
        transfer.ops.execute = denied
        with patch.object(transfer.access, 'authorize', side_effect=PermissionError('Authentication declined')):
            with self.assertRaises(PermissionError): transfer.run()
        self.assertEqual((self.source/'a').read_bytes(), b'original')
        self.assertEqual((self.source/'private').read_bytes(), b'original')

    def test_undo_copy_preserves_existing_directories_and_changed_files(self):
        self.write('a'); (self.target/'source').mkdir(); (self.target/'source'/'keep').write_bytes(b'keep')
        transfer = self.transfer(); transfer.run()
        (self.target/'source'/'a').write_bytes(b'edited')
        undo = self.transfer(dict(operation='undo', undoJournal=transfer.journal,
                                  journal=str(self.base/'undo.sqlite')), Undo)
        with self.assertRaises(OSError): undo.run()
        self.assertEqual((self.target/'source'/'a').read_bytes(), b'edited')
        self.assertEqual((self.target/'source'/'keep').read_bytes(), b'keep')

    def test_authority_scope_rejects_parent_traversal_and_directory_symlinks(self):
        item = self.write('a'); (self.target/'escape').symlink_to(self.source, target_is_directory=True)
        ops = FileOps([str(item)], str(self.target))
        for path in (str(self.base/'outside'), str(self.target/'..'/'outside')):
            with self.assertRaises(ValueError): ops.execute('read', {'path': path})
        with self.assertRaises(OSError): ops.execute('temporary', {'path': str(self.target/'escape'/'new')})
        with self.assertRaises(ValueError): ops.execute('remove', {'path': str(item), 'expected': {}})

    def test_file_descriptor_transport_and_helper_eof(self):
        item = self.write('a', b'passed descriptor')
        ops = FileOps([str(item)], str(self.target))
        client, server = socket.socketpair()
        def worker():
            with server: serve(server, ops)
        thread = threading.Thread(target=worker); thread.start()
        with client:
            send(client, {'action': 'read', 'args': {'path': str(item)}})
            result, fd = receive(client)
            try: self.assertTrue(result['ok']); self.assertEqual(os.read(fd, 100), b'passed descriptor')
            finally: os.close(fd)
            send(client, {'action': 'read', 'args': {'path': str(self.base/'outside')}})
            result, fd = receive(client); self.assertFalse(result['ok']); self.assertIsNone(fd)
        thread.join(2); self.assertFalse(thread.is_alive())


if __name__ == '__main__': unittest.main()
