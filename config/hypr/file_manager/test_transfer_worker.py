"""Real disposable files plus injected I/O failures for local transfer safety."""
from contextlib import suppress
import errno
import json
import io
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
from transfer_pending import export_report


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fusion-native-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base/'source'; self.source.mkdir()
        self.target = self.base/'target'; self.target.mkdir()
        self.events = []
        self.control = Control(self.events.append)
        self.on_issue = None
        self.on_event = None
        self.sequence = 0

    def request(self, sources=None, operation='copy', destination=None):
        self.sequence += 1
        return dict(sources=[str(p) for p in (sources or [self.source])],
                    destination=str(destination or self.target), operation=operation,
                    journal=str(self.base/f'journal-{self.sequence}.sqlite'))

    def transfer(self, request=None, cls=Transfer):
        transfer = cls(request or self.request(), self.control, self.observe)
        self.addCleanup(transfer.close)
        return transfer

    def decide(self, event, choice='skip', all_similar=False):
        self.control.decisions.append(dict(ids=[event['id']], versions={str(event['id']): event['version']}, choice=choice, all=all_similar))

    def observe(self, event):
        self.events.append(event)
        if self.on_event: self.on_event(event)
        if event.get('event') != 'issue' or event.get('status') != 'pending': return
        if self.on_issue: self.on_issue(event)
        elif ':conflict:' in event['category']:
            self.decide(event, self.control.question(event['source'], event['destination'], event['replace_allowed']))
        else: self.control.cancelled = True

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
        with self.assertRaises(Cancelled): transfer.run()
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
        with self.assertRaises(Cancelled): transfer.run()
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
                with self.assertRaises(Cancelled): transfer.run()
                self.assertTrue((self.source/'a').exists()); self.assertTrue((self.source/'b').exists())

    def test_partial_overwrite_failure_keeps_destination_and_cleans_temp(self):
        item = self.write('a', b'new data')
        old = self.target/'a'; old.write_bytes(b'old data')
        transfer = self.transfer(self.request([item])); self.control.question = lambda *args: 'replace'
        def fail(source, target, size):
            os.write(target, b'partial'); raise OSError(errno.ENOSPC, 'No space left')
        with patch('transfer_worker.fcntl.ioctl', side_effect=OSError(errno.EOPNOTSUPP, 'not supported')):
            transfer.copy_data = fail
            with self.assertRaises(Cancelled): transfer.run()
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
            with self.assertRaises(Cancelled): transfer.run()
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

    def test_sockets_are_ignored_while_other_unsupported_types_still_need_a_choice(self):
        endpoints = []
        for name in ('control-a.sock', 'control-b.sock'):
            endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(self.source/name)); endpoints.append(endpoint)
            self.addCleanup(endpoint.close)
        os.mkfifo(self.source/'pipe')
        self.write('nested/good', b'copy immediately')
        self.on_issue = lambda event: None
        passes = []
        def waiting(event):
            if event.get('phase') != 'Waiting for queued items': return
            self.assertEqual((self.target/'source/nested/good').read_bytes(), b'copy immediately')
            issues = [e for e in self.events if e.get('event') == 'issue' and e['status'] == 'pending']
            self.assertEqual(len(issues), 1)
            self.assertEqual(event['pendingIssues'], 1)
            self.assertTrue(issues[0]['category'].endswith(':named pipe'))
            self.decide(issues[0])
            passes.append(True)
        self.on_event = waiting
        transfer = self.transfer(); result = transfer.run()
        self.assertTrue(result['ok']); self.assertEqual(transfer.files, 1); self.assertEqual(transfer.skipped, 1)
        self.assertEqual(result['ignoredSockets'], 2)
        self.assertTrue(result['warnings']); self.assertEqual(len(passes), 1)
        self.assertEqual(transfer.db.execute("SELECT count(*) FROM issues WHERE status='skipped'").fetchone()[0], 1)
        self.assertEqual(self.events[-1]['totalFiles'], 2)
        self.assertFalse((self.target/'source/control-a.sock').exists())
        self.assertTrue(stat.S_ISSOCK((self.source/'control-a.sock').stat().st_mode))

    def test_move_ignores_socket_without_queue_and_undo_restores_copied_files(self):
        endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(self.source/'vm.sock')); self.addCleanup(endpoint.close)
        item = self.write('nested/data', b'safe data')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        self.assertTrue(transfer.run()['ok']); self.assertFalse(item.exists())
        self.assertEqual(transfer.ignored_sockets, 1); self.assertEqual(transfer.skipped, 0)
        self.assertFalse(any(e.get('event') in ('issue', 'authenticate') for e in self.events))
        self.assertEqual(self.events[-1]['processedFiles'], 1); self.assertEqual(self.events[-1]['totalFiles'], 1)
        self.assertTrue((self.source/'vm.sock').exists())
        undo = self.transfer(dict(operation='undo', undoJournal=transfer.journal, journal=str(self.base/'undo-queued.sqlite')), Undo)
        self.assertTrue(undo.run()['ok']); self.assertEqual(item.read_bytes(), b'safe data')
        self.assertTrue((self.source/'vm.sock').exists()); self.assertFalse((self.target/'source').exists())

    def test_successful_retry_stays_successful_after_skipping_an_unrelated_item(self):
        protected = self.write('win10.xml', b'<domain/>')
        self.write('other.txt', b'copied while waiting')
        endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(self.source/'vm.sock')); self.addCleanup(endpoint.close)
        os.mkfifo(self.source/'pipe')
        transfer = self.transfer(); copy_file = transfer.copy_file; attempts = []
        def permission_once(source, *args):
            if source == str(protected) and not attempts:
                attempts.append(True); raise PermissionError(errno.EACCES, 'Permission denied')
            return copy_file(source, *args)
        transfer.copy_file = permission_once
        self.on_issue = lambda event: self.decide(event, 'retry') if event['category'].endswith(':permission') else None
        def waiting(event):
            if event.get('phase') != 'Waiting for queued items': return
            successes = [e for e in self.events if e.get('resolution') == 'Copied successfully']
            self.assertEqual(len(successes), 1)
            self.assertEqual(successes[0]['source'], str(protected))
            self.assertEqual((self.target/'source/win10.xml').read_bytes(), b'<domain/>')
            self.assertEqual((self.target/'source/other.txt').read_bytes(), b'copied while waiting')
            pending = next(e for e in self.events if e.get('status') == 'pending' and e['category'].endswith(':named pipe'))
            self.assertFalse(pending['retry_allowed'])
            transfer.pending.choose(pending['id'], 'retry')
            self.assertEqual(transfer.db.execute('SELECT status FROM issues WHERE id=?', (pending['id'],)).fetchone()[0], 'pending')
            self.decide(pending, 'skip', True)
        self.on_event = waiting
        self.assertTrue(transfer.run()['ok']); self.assertEqual(transfer.files, 2); self.assertEqual(transfer.skipped, 1)
        self.assertTrue(protected.exists()); self.assertTrue((self.source/'vm.sock').exists())
        states = transfer.db.execute('SELECT source,status FROM issues').fetchall()
        self.assertIn((str(protected), 'resolved'), states)
        self.assertIn((str(self.source/'pipe'), 'skipped'), states)
        self.assertNotIn(str(self.source/'vm.sock'), [source for source, _ in states])
        report = io.StringIO(); export_report(transfer.journal, report)
        self.assertIn('Status: Copied successfully', report.getvalue())
        self.assertIn('Original issue: Permission denied', report.getvalue())
        self.assertIn('Runtime socket ignored automatically', report.getvalue())

    def test_actual_socket_types_are_excluded_but_names_directories_and_links_transfer(self):
        for name in ('vnc.sock', 'bus_100', 'looks-like-data.txt'):
            endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(self.source/name)); self.addCleanup(endpoint.close)
        self.write('regular.sock', b'this is ordinary data')
        self.write('folder.sock/data', b'inside a directory')
        os.symlink('vnc.sock', self.source/'socket-link')
        os.symlink('missing.sock', self.source/'dangling-link')
        transfer = self.transfer()
        for privileged in (False, True):
            counter = Counter([str(self.source)], transfer.access); counter.scan(privileged)
            self.assertTrue(counter.complete); self.assertEqual(counter.files, 4)
            self.assertEqual(counter.bytes, len(b'this is ordinary datainside a directory'))
        result = transfer.run()
        self.assertTrue(result['ok']); self.assertEqual(result['warnings'], [])
        self.assertEqual(result['ignoredSockets'], 3); self.assertEqual(result['skippedFiles'], 0)
        self.assertFalse(any(e.get('event') in ('issue', 'authenticate', 'question') for e in self.events))
        self.assertEqual(self.events[-1]['totalFiles'], 4); self.assertEqual(self.events[-1]['processedFiles'], 4)
        self.assertEqual((self.target/'source/regular.sock').read_bytes(), b'this is ordinary data')
        self.assertEqual((self.target/'source/folder.sock/data').read_bytes(), b'inside a directory')
        self.assertEqual(os.readlink(self.target/'source/socket-link'), 'vnc.sock')
        self.assertEqual(os.readlink(self.target/'source/dangling-link'), 'missing.sock')
        for name in ('vnc.sock', 'bus_100', 'looks-like-data.txt'):
            self.assertTrue(stat.S_ISSOCK((self.source/name).lstat().st_mode))
            self.assertFalse((self.target/'source'/name).exists())
        self.assertEqual(transfer.db.execute('SELECT count(*) FROM issues').fetchone()[0], 0)

    def test_selected_socket_does_not_conflict_with_or_replace_existing_destination(self):
        path = self.source/'endpoint'; endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(path)); self.addCleanup(endpoint.close)
        existing = self.target/path.name; existing.write_bytes(b'keep this file')
        transfer = self.transfer(self.request([path]))
        for privileged in (False, True):
            counter = Counter([str(path)], transfer.access); counter.scan(privileged)
            self.assertTrue(counter.complete); self.assertEqual((counter.files, counter.bytes), (0, 0))
        self.assertTrue(transfer.run()['ok'])
        self.assertEqual(existing.read_bytes(), b'keep this file')
        self.assertFalse(any(e.get('event') in ('issue', 'authenticate') for e in self.events))
        self.assertEqual(self.events[-1]['totalFiles'], 0); self.assertEqual(self.events[-1]['processedFiles'], 0)
        self.assertEqual(transfer.ignored_sockets, 1); self.assertEqual(transfer.skipped, 0)

    def test_socket_count_observation_does_not_hide_a_replacement_regular_file(self):
        path = self.source/'changing.sock'; endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(path)); self.addCleanup(endpoint.close)
        transfer = self.transfer(); get = transfer.get; changed = threading.Event()
        def count(counter):
            counter.scan(False)
            endpoint.close(); path.unlink(); path.write_bytes(b'now ordinary data'); changed.set()
        def after_counter(source):
            if source == str(path): self.assertTrue(changed.wait(2))
            return get(source)
        transfer.get = after_counter
        with patch.object(Counter, 'run', count): self.assertTrue(transfer.run()['ok'])
        self.assertEqual((self.target/'source/changing.sock').read_bytes(), b'now ordinary data')
        self.assertEqual(transfer.ignored_sockets, 0)
        self.assertEqual(self.events[-1]['totalFiles'], 1); self.assertEqual(self.events[-1]['processedFiles'], 1)

    def test_socket_found_after_permission_retry_is_not_claimed_as_copied(self):
        path = self.source/'private.sock'; endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(path)); self.addCleanup(endpoint.close)
        transfer = self.transfer(); get = transfer.get; failures = []
        def inaccessible(source):
            if source == str(path) and not failures:
                failures.append(True); raise PermissionError(errno.EACCES, 'Cannot inspect item')
            return get(source)
        transfer.get = inaccessible
        self.on_issue = lambda event: self.decide(event, 'retry')
        self.assertTrue(transfer.run()['ok'])
        resolved = [e for e in self.events if e.get('status') == 'resolved']
        self.assertTrue(resolved); self.assertTrue(all(e['resolution'] == 'Runtime socket ignored' for e in resolved))
        self.assertEqual(transfer.files, 0); self.assertEqual(transfer.skipped, 0)
        self.assertEqual(self.events[-1]['totalFiles'], 0)

    def test_ignored_socket_journal_deduplicates_rescans_and_old_reports_still_work(self):
        path = self.source/'runtime'; endpoint = socket.socket(socket.AF_UNIX); endpoint.bind(str(path)); self.addCleanup(endpoint.close)
        transfer = self.transfer(); target = str(self.target/path.name)
        transfer.walk(str(path), target); transfer.walk(str(path), target, rescan=True); transfer.db.commit()
        self.assertEqual(transfer.ignored_sockets, 1); self.assertEqual(transfer.pending.total, 0)
        report = io.StringIO(); export_report(transfer.journal, report)
        self.assertEqual(report.getvalue().count('Status: ignored / original kept'), 1)
        transfer.db.execute('DROP TABLE ignored_sockets'); transfer.db.commit()
        report = io.StringIO(); export_report(transfer.journal, report)
        self.assertIn('Fusion Files transfer report', report.getvalue())

    def test_move_retry_only_claims_moved_after_verified_original_removal(self):
        for keep_original in (False, True):
            with self.subTest(keep_original=keep_original):
                item = self.write(f'move-{keep_original}.txt')
                transfer = self.transfer(self.request([item], operation='move')); self.force_cross_device(transfer)
                copy_file = transfer.copy_file; attempts = []
                def fail_once(source, *args):
                    if not attempts:
                        attempts.append(True); raise OSError(errno.EIO, 'Temporary read failure')
                    return copy_file(source, *args)
                transfer.copy_file = fail_once
                if keep_original:
                    execute = transfer.ops.execute
                    def fail_remove(action, args):
                        if action == 'remove': raise PermissionError(errno.EACCES, 'Cannot remove original')
                        return execute(action, args)
                    transfer.ops.execute = fail_remove
                self.on_issue = lambda event: self.decide(event, 'skip' if event['stage'] == 'remove' else 'retry')
                self.assertTrue(transfer.run()['ok'])
                outcomes = [e['resolution'] for e in self.events if e.get('source') == str(item) and
                            e.get('status') == 'resolved' and e['stage'] != 'remove']
                self.assertEqual(outcomes, ['Copied; move pending', 'Copied; original kept' if keep_original else 'Moved successfully'])
                self.assertEqual(item.exists(), keep_original)
                self.assertEqual((self.target/item.name).read_bytes(), b'original')

    def test_folder_attribute_pass_reports_progress_without_changing_copy_counts(self):
        for n in range(4): self.write(f'folder-{n}/data')
        transfer = self.transfer(); apply_directory = transfer.apply_directory
        def observed(*args):
            apply_directory(*args)
            transfer.last_progress = 0  # Observe each step without timing-dependent sleeps.
        transfer.apply_directory = observed
        self.assertTrue(transfer.run()['ok'])
        progress = [e for e in self.events if e.get('phase') == 'Saving folder attributes']
        self.assertEqual(progress[0]['processedFolderAttributes'], 0)
        self.assertEqual(progress[-1]['processedFolderAttributes'], 5)
        self.assertTrue(all(e['totalFolderAttributes'] == 5 and e['processedFiles'] == 4 for e in progress))
        self.assertTrue(any(e['currentFile'] for e in progress))
        self.assertEqual(self.events[-1]['currentFile'], '')

    def test_failed_retry_returns_to_queue_with_an_explicit_failure(self):
        item = self.write('bad'); self.write('good')
        transfer = self.transfer(); copy_file = transfer.copy_file
        def fail(source, *args):
            if source == str(item): raise OSError(errno.EIO, 'Read failure')
            return copy_file(source, *args)
        transfer.copy_file = fail
        self.on_issue = lambda event: self.decide(event, 'retry' if event['version'] == 1 else 'skip')
        self.assertTrue(transfer.run()['ok'])
        failures = [e for e in self.events if e.get('status') == 'pending']
        self.assertEqual(len(failures), 2)
        self.assertEqual(failures[-1]['detail'], 'Retry failed: Read failure')
        self.assertEqual(item.read_bytes(), b'original')
        self.assertEqual((self.target/'source/good').read_bytes(), b'original')

    def test_partial_disk_full_error_retries_after_unrelated_files_and_counts_once(self):
        bad = self.write('blocked', b'new contents'); good = self.write('other', b'other contents')
        transfer = self.transfer(self.request([bad, good]))
        copy_data = transfer.copy_data; attempts = []
        def fail_once(source, target, size):
            if not attempts:
                attempts.append(True); os.write(target, b'par'); transfer.processed += 3
                raise OSError(errno.ENOSPC, 'No space left on device')
            copy_data(source, target, size)
        transfer.copy_data = fail_once; self.on_issue = lambda event: None
        def waiting(event):
            if event.get('phase') != 'Waiting for queued items': return
            self.assertEqual((self.target/'other').read_bytes(), b'other contents')
            self.assertEqual(event['processedBytes'], len(b'other contents'))
            self.assertFalse((self.target/'blocked').exists()); self.assertFalse(list(self.target.glob('.fusion-*')))
            self.decide(next(e for e in self.events if e.get('event') == 'issue'), 'retry')
        self.on_event = waiting
        with patch('transfer_worker.fcntl.ioctl', side_effect=OSError(errno.EOPNOTSUPP, 'not supported')):
            self.assertTrue(transfer.run()['ok'])
        self.assertEqual((self.target/'blocked').read_bytes(), b'new contents')
        self.assertEqual(transfer.files, 2); self.assertEqual(transfer.processed, len(b'other contentsnew contents'))

    def test_conflicts_do_not_block_and_delayed_replace_checks_destination_again(self):
        item = self.write('conflict', b'new'); good = self.write('good', b'good')
        destination = self.target/'conflict'; destination.write_bytes(b'old')
        self.on_issue = lambda event: None
        decisions = []
        def waiting(event):
            if event.get('phase') != 'Waiting for queued items': return
            self.assertEqual((self.target/'good').read_bytes(), b'good')
            issue = next(e for e in reversed(self.events) if e.get('event') == 'issue' and e['status'] == 'pending')
            if not decisions:
                destination.write_bytes(b'edited while queued')
                self.decide(issue, 'replace')
            else:
                self.decide(dict(issue, version=issue['version']-1), 'replace')  # Stale answer is rejected.
                self.decide(issue, 'skip')
            decisions.append(True)
        self.on_event = waiting
        transfer = self.transfer(self.request([item, good])); self.assertTrue(transfer.run()['ok'])
        self.assertEqual(destination.read_bytes(), b'edited while queued'); self.assertEqual(len(decisions), 2)

    def test_authorization_starts_during_copy_without_blocking_other_files(self):
        private = self.write('private/secret'); good = self.write('good')
        transfer = self.transfer(self.request([private.parent, good])); execute = transfer.ops.execute
        authenticated = []
        prompted, continue_auth = threading.Event(), threading.Event()
        def guarded(action, args):
            if action == 'list' and args['path'].endswith('/private') and not authenticated:
                raise PermissionError(errno.EACCES, 'Private folder')
            return execute(action, args)
        transfer.ops.execute = guarded
        def authorize():
            prompted.set()
            if not continue_auth.wait(3): raise PermissionError('Test prompt was not released')
            authenticated.append(True)
        transfer.access.authorize = authorize
        copy = transfer.copy_file
        def copying(source, *args):
            if source == str(good):
                transfer.progress(True)
                self.assertTrue(prompted.wait(2), 'Authentication waited until the end of the copy pass')
                self.assertFalse(authenticated, 'The fixture prompt should still be open')
            copy(source, *args)
            if source == str(good): continue_auth.set()
        transfer.copy_file = copying
        self.addCleanup(continue_auth.set)
        self.on_issue = lambda event: self.decide(event, 'authorize')
        self.assertTrue(transfer.run()['ok']); self.assertEqual(authenticated, [True])
        self.assertEqual((self.target/'private/secret').read_bytes(), b'original')
        self.assertIn('authorizing', [e.get('status') for e in self.events])

    def test_cancelled_authentication_returns_rows_to_choices_and_can_retry(self):
        private = self.write('private'); good = self.write('good')
        transfer = self.transfer(self.request([private, good])); execute = transfer.ops.execute
        authenticated, attempts = [], []
        def guarded(action, args):
            if action == 'read' and args['path'] == str(private) and not authenticated:
                raise PermissionError(errno.EACCES, 'Private file')
            return execute(action, args)
        transfer.ops.execute = guarded
        def authorize():
            attempts.append(True)
            if len(attempts) == 1: raise PermissionError('Authentication cancelled')
            authenticated.append(True)
        transfer.access.authorize = authorize
        self.on_issue = lambda event: self.decide(event, 'authorize')
        self.assertTrue(transfer.run()['ok'])
        choices = [e for e in self.events if e.get('status') == 'pending']
        self.assertEqual([e['version'] for e in choices], [1, 2])
        self.assertIn('Authentication cancelled', choices[1]['detail'])
        self.assertEqual(len(attempts), 2)
        self.assertEqual((self.target/'good').read_bytes(), b'original')
        self.assertEqual((self.target/'private').read_bytes(), b'original')

    def test_repeated_admin_choices_share_one_pending_authentication(self):
        transfer = self.transfer()
        prompted, finish = threading.Event(), threading.Event()
        calls = []
        def authorize():
            calls.append(True); prompted.set()
            if not finish.wait(3): raise PermissionError('Test prompt was not released')
        transfer.access.authorize = authorize
        self.addCleanup(finish.set)
        transfer.access.request_authorization()
        self.assertTrue(prompted.wait(2))
        for _ in range(5): transfer.access.request_authorization()
        self.assertEqual(calls, [True]); self.assertEqual(transfer.access.authorization()[0], 'authorizing')
        finish.set(); transfer.access.auth_thread.join(2)
        self.assertEqual(transfer.access.authorization()[0], 'authorized')

    def test_closing_transfer_cancels_pending_authentication_and_removes_socket(self):
        transfer = self.transfer()
        prompt = threading.Event(); endpoints = []
        def event(value):
            if value.get('event') == 'authenticate':
                endpoints.append(value['socket']); prompt.set()
        self.on_event = event
        transfer.access.request_authorization()
        self.assertTrue(prompt.wait(2))
        transfer.access.close()
        self.assertFalse(transfer.access.auth_thread.is_alive())
        self.assertFalse(Path(endpoints[0]).exists())

    def test_helper_exit_during_authentication_is_not_reported_as_active(self):
        transfer = self.transfer()
        client, helper = socket.socketpair()
        self.addCleanup(client.close); self.addCleanup(helper.close)
        def authorize():
            transfer.access.connection = client
            helper.close()
            with self.assertRaises(PermissionError): transfer.access.remote('stat', {'path': str(self.source)})
        transfer.access.authorize = authorize
        transfer.access.request_authorization(); transfer.access.auth_thread.join(2)
        state, error = transfer.access.authorization()
        self.assertEqual(state, 'failed'); self.assertIn('connection ended', error)

    def test_skip_verification_failure_preserves_that_original(self):
        bad = self.write('bad'); good = self.write('good')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        verify = transfer.verify
        def corrupt(): (self.target/'source/bad').write_bytes(b'corrupt'); verify()
        transfer.verify = corrupt
        self.on_issue = lambda event: self.decide(event)
        self.assertTrue(transfer.run()['ok']); self.assertEqual(bad.read_bytes(), b'original')
        self.assertFalse(good.exists()); self.assertEqual((self.target/'source/good').read_bytes(), b'original')

    def test_cancel_waiting_queue_leaves_all_cross_device_originals(self):
        os.mkfifo(self.source/'pipe'); good = self.write('good')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        self.on_issue = lambda event: None
        def waiting(event):
            if event.get('phase') == 'Waiting for queued items':
                self.assertTrue((self.target/'source/good').exists()); self.control.cancelled = True
        self.on_event = waiting
        with self.assertRaises(Cancelled): transfer.run()
        self.assertTrue(good.exists()); self.assertTrue((self.source/'pipe').exists())

    def test_directory_iteration_error_retries_without_recopying_completed_files(self):
        self.write('one', b'one'); self.write('two', b'two')
        scandir = os.scandir; failed = []
        class BrokenIterator:
            def __init__(self, iterator): self.iterator, self.read = iterator, False
            def __next__(self):
                if self.read:
                    failed.append(True); raise OSError(errno.EIO, 'Directory read failed')
                self.read = True; return next(self.iterator)
            def close(self): self.iterator.close()
        def intermittent(path):
            result = scandir(path)
            if isinstance(path, int) and not failed: return BrokenIterator(result)
            return result
        self.on_issue = lambda event: self.decide(event, 'retry')
        transfer = self.transfer()
        with patch('transfer_worker.os.scandir', side_effect=intermittent):
            self.assertTrue(transfer.run()['ok'])
        self.assertEqual(transfer.files, 2); self.assertEqual(transfer.processed, 6)
        self.assertEqual((self.target/'source/one').read_bytes(), b'one')
        self.assertEqual((self.target/'source/two').read_bytes(), b'two')
        self.assertEqual(transfer.db.execute("SELECT count(*) FROM entries WHERE kind='file'").fetchone()[0], 2)

    def test_skipping_directory_flush_failure_retains_all_affected_originals(self):
        kept = self.write('unflushed/data'); moved = self.write('good/data')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        execute = transfer.ops.execute
        def fail_sync(action, args):
            if action == 'sync' and args['path'] == str(self.target/'source/unflushed'):
                raise OSError(errno.EIO, 'Could not flush this directory')
            return execute(action, args)
        transfer.ops.execute = fail_sync; self.on_issue = lambda event: self.decide(event)
        self.assertTrue(transfer.run()['ok']); self.assertTrue(kept.exists()); self.assertFalse(moved.exists())
        self.assertEqual((self.target/'source/good/data').read_bytes(), b'original')

    def test_failed_original_removal_queues_without_deleting_unverified_data(self):
        kept = self.write('keep'); moved = self.write('good')
        transfer = self.transfer(self.request(operation='move')); self.force_cross_device(transfer)
        execute = transfer.ops.execute
        def fail_remove(action, args):
            if action == 'remove' and args['path'] == str(kept): raise OSError(errno.EIO, 'Could not remove this original')
            return execute(action, args)
        transfer.ops.execute = fail_remove; self.on_issue = lambda event: self.decide(event)
        result = transfer.run(); self.assertTrue(result['ok']); self.assertTrue(result['warnings'])
        self.assertEqual(kept.read_bytes(), b'original'); self.assertFalse(moved.exists())
        self.assertEqual((self.target/'source/keep').read_bytes(), b'original')

    def test_skip_similar_summarizes_future_rows_but_full_report_retains_every_path(self):
        for n in range(12): os.mkfifo(self.source/f'pipe-{n}')
        transfer = self.transfer()
        def skip_similar(event):
            self.decide(event, 'skip', True)
            transfer.last_progress = 0  # Accept the decision before encountering the next item.
        self.on_issue = skip_similar
        self.assertTrue(transfer.run()['ok'])
        self.assertEqual(transfer.skipped, 12); self.assertEqual(transfer.pending.automatic, 11)
        self.assertEqual(len([e for e in self.events if e.get('event') == 'issue' and e['status'] == 'pending']), 1)
        self.assertEqual(transfer.db.execute('SELECT count(*) FROM issues').fetchone()[0], 12)
        report = io.StringIO(); export_report(transfer.journal, report)
        self.assertEqual(report.getvalue().count('Status: skipped'), 12)
        for n in range(12): self.assertIn(f'From: {self.source}/pipe-{n}\n', report.getvalue())

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
