#!/usr/bin/env python3
"""Streaming local copies and verified moves for Fusion Files.

Control and progress are JSON lines on private pipes. Data goes directly between
file descriptors, using reflinks/copy_file_range when possible. Counting never
blocks copying. Cross-filesystem sources survive until the entire copy and
verification phase succeeds. The on-disk journal also backs the Undo action.
"""
from __future__ import annotations
from contextlib import suppress
import errno
import base64
import fcntl
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import struct
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transfer_io import FileOps, beneath, snapshot, unchanged
from transfer_authority import send, receive
from transfer_pending import Pending, Conflict, SpecialFile

CHUNK = 8 * 1024 * 1024  # Bounded I/O buffer, never a file/transfer size limit.


class Cancelled(Exception):
    pass


class Control:
    def __init__(self, emit, stream=None):
        self.emit = emit
        self.condition = threading.Condition()
        self.cancelled = self.paused = False
        self.answers = []
        self.decisions = []
        self.auth_error = ''
        self.auth_token = ''
        if stream is not None:
            threading.Thread(target=self.read, args=(stream,), daemon=True).start()

    def read(self, stream):
        try:
            for line in stream:
                command = json.loads(line)
                with self.condition:
                    if command.get('command') == 'cancel': self.cancelled = True
                    elif command.get('command') in ('pause', 'resume'):
                        self.paused = command['command'] == 'pause'
                        self.emit({'event': 'state', 'suspended': self.paused})
                    elif command.get('command') == 'answer': self.answers.append(command)
                    elif command.get('command') == 'issue_answer': self.decisions.append(command)
                    elif command.get('command') == 'auth_failed' and command.get('token', self.auth_token) == self.auth_token:
                        self.auth_error = command.get('error') or 'Administrator authentication was cancelled.'
                    self.condition.notify_all()
        finally:
            with self.condition:
                self.cancelled = True
                self.condition.notify_all()

    def check(self):
        with self.condition:
            while self.paused and not self.cancelled: self.condition.wait()
            if self.cancelled: raise Cancelled()

    def question(self, source, destination, replace_allowed):
        self.emit({'event': 'question', 'source': source, 'destination': destination, 'replace_allowed': replace_allowed})
        with self.condition:
            while not self.answers and not self.cancelled: self.condition.wait()
            if self.cancelled: raise Cancelled()
            choice = self.answers.pop(0).get('choice')
        if choice not in ('replace', 'skip') or (choice == 'replace' and not replace_allowed): raise Cancelled()
        return choice


class Access:
    def __init__(self, ops, control, emit):
        self.ops, self.control, self.emit = ops, control, emit
        self.connection = None
        self.temporary = None
        self.rpc_lock = threading.Lock()
        self.authorized = threading.Event()
        self.defer_authorization = False
        self.auth_lock = threading.Lock()
        self.auth_thread = None
        self.auth_stop = threading.Event()
        self.auth_state, self.auth_message = 'idle', ''

    def authorization(self):
        with self.auth_lock:
            return self.auth_state, self.auth_message

    def request_authorization(self):
        """Request credentials now; the copy loop never waits for the dialog."""
        with self.auth_lock:
            if self.connection:
                self.auth_state, self.auth_message = 'authorized', ''
                return
            if self.auth_state == 'authorizing': return
            self.auth_state, self.auth_message = 'authorizing', ''
            self.control.auth_error = ''
            self.auth_thread = threading.Thread(target=self._authenticate, daemon=True)
            self.auth_thread.start()

    def _authenticate(self):
        try:
            self.authorize()
            state, message = 'authorized', ''
        except Cancelled:
            state, message = 'failed', 'Administrator authorization was cancelled.'
        except Exception as error:
            state, message = 'failed', str(error)
        with self.auth_lock:
            # The counter can use a newly connected helper immediately. If it
            # observes EOF first, do not overwrite that failure with success.
            if state == 'failed' or self.auth_state == 'authorizing':
                self.auth_state, self.auth_message = state, message
        with self.control.condition:
            self.control.condition.notify_all()

    def authorize(self):
        if self.connection: return
        temporary = tempfile.TemporaryDirectory(prefix='fusion-transfer-')
        os.chmod(temporary.name, 0o700)
        endpoint = temporary.name + '/access'
        token = uuid.uuid4().hex
        with self.control.condition:
            self.control.auth_token = token
            self.control.auth_error = ''
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(endpoint); listener.listen(1); listener.settimeout(.1)
                self.emit({'event': 'authenticate', 'socket': endpoint, 'token': token,
                           'sources': self.ops.sources, 'destination': self.ops.destination,
                           'moving': self.ops.moving, 'undo': self.ops.undo,
                           'background': self.defer_authorization})
                while True:
                    # Pausing data transfer must not prevent authentication or
                    # cancellation of a prompt that is already on screen.
                    if self.control.cancelled or self.auth_stop.is_set(): raise Cancelled()
                    if self.control.auth_error: raise PermissionError(self.control.auth_error)
                    try: connection, _ = listener.accept()
                    except socket.timeout: continue
                    accepted = False
                    try:
                        _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                        if uid != 0: continue
                        connection.settimeout(1)  # Only the tiny local authentication handshake.
                        hello, fd = receive(connection)
                        if fd is not None: os.close(fd)
                        if hello != {'token': token}: continue
                        if self.control.cancelled or self.auth_stop.is_set(): raise Cancelled()
                        connection.settimeout(None)
                        with self.rpc_lock:
                            if self.temporary: self.temporary.cleanup()
                            self.temporary, temporary = temporary, None
                            self.connection = connection
                            accepted = True
                            self.authorized.set()
                        return
                    finally:
                        if not accepted: connection.close()
        finally:
            if temporary: temporary.cleanup()

    def call(self, action, **args):
        self.control.check()
        try: return self.ops.execute(action, args)
        except PermissionError:
            if self.defer_authorization:
                if not self.connection: raise
            else: self.authorize()
            return self.remote(action, args)

    def inspect(self, action, **args):
        """Counting may reuse existing authorization, but never request it."""
        if action not in ('stat', 'list'): raise ValueError('Counting is read-only.')
        try: return self.ops.execute(action, args)
        except PermissionError:
            if not self.connection: raise
            return self.remote(action, args)

    def remote(self, action, args):
        with self.rpc_lock:
            if self.connection is None:
                raise PermissionError(errno.EACCES, 'Administrator authorization is needed to retry this item.')
            try:
                send(self.connection, {'action': action, 'args': args})
                result, fd = receive(self.connection)
            except (ConnectionError, EOFError) as error:
                if self.connection: self.connection.close()
                self.connection = None; self.authorized.clear()
                with self.auth_lock:
                    self.auth_state, self.auth_message = 'failed', 'The administrator connection ended. Authorize again to retry.'
                raise PermissionError(errno.EACCES, 'The administrator connection ended. Authorize again to retry this item.') from error
            if not result.get('ok'):
                if fd is not None: os.close(fd)
                raise OSError(result.get('errno') or errno.EACCES, result.get('error') or 'Administrator file access failed.')
            return result.get('value'), fd

    def value(self, action, **args):
        value, fd = self.call(action, **args)
        if fd is not None: os.close(fd)
        return value

    def close(self):
        self.auth_stop.set()
        if self.auth_thread: self.auth_thread.join()
        if self.connection: self.connection.close(); self.connection = None
        if self.temporary: self.temporary.cleanup()


class Counter:
    """Low-priority, read-only source enumeration; never poll the destination."""
    def __init__(self, sources, access=None):
        self.files = self.bytes = 0
        self.complete = False
        self.stop = threading.Event()
        self.sources = sources
        self.access = access
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        with suppress(OSError): os.nice(10)
        self.scan(False)
        if not self.complete and self.access:
            while not self.stop.is_set() and not self.access.authorized.wait(.1): pass
            if not self.stop.is_set():
                self.files = self.bytes = 0
                self.scan(True)

    def scan(self, privileged):
        pending = list(self.sources)
        accessible = True
        while pending and not self.stop.is_set():
            path = pending.pop()
            try:
                if privileged:
                    info, _ = self.access.inspect('stat', path=path)
                    if stat.S_ISDIR(info['mode']):
                        _, fd = self.access.inspect('list', path=path, expected=info)
                        try:
                            with os.scandir(fd) as entries:
                                for entry in entries:
                                    if self.stop.is_set(): return
                                    child = os.path.join(path, entry.name)
                                    value, _ = self.access.inspect('stat', path=child)
                                    if stat.S_ISDIR(value['mode']): pending.append(child)
                                    elif not stat.S_ISSOCK(value['mode']):
                                        self.files += 1
                                        if stat.S_ISREG(value['mode']): self.bytes += value['size']
                        finally: os.close(fd)
                    elif not stat.S_ISSOCK(info['mode']):
                        self.files += 1
                        if stat.S_ISREG(info['mode']): self.bytes += info['size']
                    continue
                info = os.lstat(path)
                if stat.S_ISDIR(info.st_mode):
                    with os.scandir(path) as entries:
                        for item in entries:
                            if self.stop.is_set(): return
                            if item.is_dir(follow_symlinks=False): pending.append(item.path)
                            else:
                                value = item.stat(follow_symlinks=False)
                                if stat.S_ISSOCK(value.st_mode): continue
                                self.files += 1
                                if stat.S_ISREG(value.st_mode): self.bytes += value.st_size
                elif not stat.S_ISSOCK(info.st_mode):
                    self.files += 1
                    if stat.S_ISREG(info.st_mode): self.bytes += info.st_size
            except OSError: accessible = False
        self.complete = accessible and not self.stop.is_set()


def numbered(path, directory=False):
    name = os.path.basename(path)
    suffix = '' if directory else os.path.splitext(name)[1]
    if not directory:
        for ending in ('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst', '.tar.lz', '.tar.lzma'):
            if name.lower().endswith(ending): suffix = name[-len(ending):]; break
    stem = name[:-len(suffix)] if suffix else name
    return stem, suffix


class Transfer:
    def __init__(self, request, control, emit, access=None):
        self.request, self.control, self.emit = request, control, emit
        self.moving = request['operation'] == 'move'
        self.sources = [os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p)) for p in request['sources']]
        self.destination = os.path.realpath(request['destination'])
        self.ops = FileOps(self.sources, self.destination, self.moving)
        self.access = access or Access(self.ops, control, emit)
        self.access.defer_authorization = True
        self.current = self.target = ''
        self.phase = 'Copying'
        self.processed = self.files = self.skipped = self.skipped_bytes = self.verified = self.renamed = 0
        self.skipped_folders = 0
        self.ignored_sockets = 0
        self.attributes_done = self.attributes_total = 0
        self.last_progress = 0
        self.last_bytes = 0
        self.last_speed_time = time.monotonic()
        self.speed = 0
        self.counter = None
        self.warnings = set()
        self.journal = request['journal']
        self.db = sqlite3.connect(self.journal)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE meta (value TEXT)')
        self.db.execute('INSERT INTO meta VALUES (?)', (json.dumps(dict(request, sources=self.sources, destination=self.destination)),))
        self.db.execute('CREATE TABLE entries (id INTEGER PRIMARY KEY, kind TEXT, source TEXT, target TEXT, original TEXT, final TEXT, created INTEGER, removed INTEGER DEFAULT 0, parent TEXT, retained INTEGER DEFAULT 0)')
        self.db.execute('CREATE INDEX entry_paths ON entries(source,target)')
        self.pending = Pending(self)
        self.db.execute('CREATE TABLE directory_metadata (id INTEGER PRIMARY KEY, source TEXT, target TEXT, value TEXT)')
        # Diagnostic records are separate from copied files and the attention
        # queue. They never contribute bytes, files, skips or pending decisions.
        self.db.execute('CREATE TABLE ignored_sockets (source TEXT, target TEXT, original TEXT, PRIMARY KEY(source,target))')
        self.db.commit()

    def record(self, kind, source, target, original, final, created=True, removed=False):
        self.db.execute('INSERT INTO entries(kind,source,target,original,final,created,removed,parent) VALUES (?,?,?,?,?,?,?,?)',
                        (kind, source, target, json.dumps(original), json.dumps(final), created, removed, os.path.dirname(target)))

    def get(self, path):
        try: return self.access.value('stat', path=path)
        except FileNotFoundError: return None

    def ignore_socket(self, source, target, info):
        recorded = self.db.execute('INSERT OR IGNORE INTO ignored_sockets VALUES (?,?,?)',
                                   (source, target, json.dumps(info)))
        self.ignored_sockets += recorded.rowcount

    def progress(self, force=False, complete=False):
        now = time.monotonic()
        if not force and now - self.last_progress < .1: return
        self.pending.accept()
        if now - self.last_speed_time >= .5:
            self.speed = max(0, int((self.processed-self.last_bytes)/(now-self.last_speed_time)))
            self.last_bytes, self.last_speed_time = self.processed, now
        self.last_progress = now
        auth_state, auth_message = self.access.authorization()
        counter = self.counter
        total = max(self.processed+self.skipped_bytes, counter.bytes if counter and not complete else 0)
        total_files = max(self.files+self.skipped-self.skipped_folders, counter.files if counter and not complete else 0)
        known = complete or bool(counter and counter.complete)
        percent = min(99, (self.processed+self.skipped_bytes)*100//total) if total else 0
        self.emit({'event': 'progress', 'processedBytes': self.processed, 'totalBytes': total,
                   'processedFiles': self.files, 'totalFiles': total_files, 'skippedFiles': self.skipped,
                   'totalsKnown': known, 'percent': percent, 'speed': self.speed if self.phase == 'Copying' else 0,
                   'currentFile': self.current, 'phase': self.phase, 'verifiedBytes': self.verified,
                   'renamedItems': self.renamed, 'pendingIssues': self.pending.count, 'issueCount': self.pending.total,
                   'skippedFolders': self.skipped_folders, 'autoSkippedIssues': self.pending.automatic,
                   'processedFolderAttributes': self.attributes_done, 'totalFolderAttributes': self.attributes_total,
                   'administratorAccess': auth_state, 'administratorError': auth_message})

    def conflict(self, source, target, info, approved=None):
        old = self.get(target)
        if old is None: return None, False
        if stat.S_ISDIR(info['mode']) and stat.S_ISDIR(old['mode']): return old, False
        can_replace = not stat.S_ISDIR(info['mode']) and not stat.S_ISDIR(old['mode'])
        if approved and can_replace and all(old[k] == approved[k] for k in ('dev','ino','size','mtime_ns','ctime_ns')):
            return old, False
        raise Conflict(old, can_replace)

    def skip_task(self, task):
        # Skipping a verification or removal error retains that original. The
        # verified copies of other files may still finish their move.
        if task.get('entry'):
            self.db.execute('UPDATE entries SET retained=1 WHERE id=?', (task['entry'],))
        elif task['kind'] == 'directory_done':
            self.db.execute("UPDATE entries SET retained=1 WHERE kind='directory' AND source=? AND target=?",
                            (task['source'], task['target']))
        elif task['kind'] == 'sync':
            # A directory that could not be flushed cannot safely lose any of
            # its originals, even if individual file fsync calls succeeded.
            prefix = task['target'].rstrip('/') + '/'
            self.db.execute("UPDATE entries SET retained=1 WHERE substr(target,1,?)=? OR target=?",
                            (len(prefix), prefix, task['target']))
        if task['kind'] not in ('verify', 'precheck', 'remove', 'sync', 'directory_done'):
            self.skipped += 1
        else:
            self.warnings.add('Some copied items were kept at their original locations or could not preserve all metadata. See the transfer queue for details.')
        info = task.get('info') or {}
        if task['kind'] in ('item', 'root', 'rescan') and (not info or stat.S_ISDIR(info.get('mode', 0))):
            self.skipped_folders += 1
        if task['kind'] in ('item', 'root') and stat.S_ISREG(info.get('mode', 0)):
            self.skipped_bytes += info['size']

    def retry_task(self, task, choice):
        kind, source, target = task['kind'], task['source'], task['target']
        if kind == 'root': self.root_item(source, target)
        elif kind in ('item', 'rescan'):
            self.walk(source, target, approved=task.get('replace_expected') if choice == 'replace' else None, rescan=kind == 'rescan')
        elif kind == 'directory_done': self.apply_directory(source, target, task['info'])
        elif kind == 'verify': self.verify_entry(task['entry'])
        elif kind == 'precheck': self.precheck_entry(task['entry'])
        elif kind == 'remove':
            # After waiting for a decision, validate again; a changed original
            # or destination is never removed merely because Retry was clicked.
            self.precheck_entry(task['entry'])
            self.remove_entry(task['entry'])
        elif kind == 'sync': self.access.value('sync', path=target)

    def guarded(self, task, operation):
        self.control.check()
        try: operation()
        except OSError as error: self.pending.add(task, error)

    def root_item(self, source, target):
        info = self.get(source)
        if info is None: raise FileNotFoundError(errno.ENOENT, 'The source no longer exists.', source)
        if self.moving and os.path.ismount(source):
            raise ValueError('Move the contents of a mounted drive, not the mount point itself.')
        if stat.S_ISDIR(info['mode']) and beneath(self.destination, source):
            raise ValueError('A folder cannot be copied or moved into itself.')
        if self.moving and self.get(target) is None:
            try:
                final = self.access.value('rename', path=target, origin=source, expected=info, durable=True)
                self.record('rename', source, target, info, final, removed=True)
                self.db.commit(); self.renamed += 1
                self.emit({'event': 'moved', 'source': source, 'destination': target})
                self.progress(); return
            except OSError as error:
                if error.errno != errno.EXDEV: raise
        if self.counter is None:
            self.counter = Counter(self.sources, self.access); self.counter.thread.start()
            self.progress(True)
        self.walk(source, target, info)

    def run(self):
        # Only inspect selected roots before starting. Same-filesystem renames
        # do not read their contents or allocate another tree's worth of space.
        for source in self.sources:
            self.control.check()
            self.current = source
            target = os.path.join(self.destination, os.path.basename(source))
            self.target = target
            if source == target:
                if self.moving: continue
                stem, suffix = numbered(source, os.path.isdir(source) and not os.path.islink(source))
                number = 1
                while self.get(target) is not None:
                    target = os.path.join(self.destination, f'{stem}_copy{number}{suffix}'); number += 1
            self.emit({'event': 'target', 'destination': target})
            self.guarded(dict(kind='root', source=source, target=target), lambda: self.root_item(source, target))
        self.pending.drain()
        self.attributes_total = self.db.execute('SELECT count(*) FROM directory_metadata').fetchone()[0]
        if self.attributes_total:
            self.phase = 'Saving folder attributes'; self.current = ''; self.progress(True)
        for source, target, encoded in self.db.execute('SELECT source,target,value FROM directory_metadata ORDER BY length(target) DESC,id'):
            self.current, self.target = source, target
            info = json.loads(encoded)
            self.guarded(dict(kind='directory_done', source=source, target=target, info=info),
                         lambda: self.apply_directory(source, target, info))
            self.attributes_done += 1
            self.progress()
        if self.attributes_total: self.progress(True)
        self.pending.drain()
        self.db.commit()
        if self.moving:
            self.verify()
            self.cleanup_sources()
        self.pending.finish()
        self.phase = 'Finishing'
        self.current = ''
        self.progress(True, True)
        self.db.commit()
        if self.skipped:
            self.warnings.add(f'{self.skipped:,} items were skipped or kept at their original locations. See the transfer queue for details.')
        return {'event': 'result', 'ok': True, 'journal': self.journal, 'skippedFiles': self.skipped,
                'ignoredSockets': self.ignored_sockets,
                'warnings': sorted(self.warnings)}

    def walk(self, source, target, info=None, approved=None, rescan=False):
        # Iterator stack keeps memory proportional to directory depth, not count.
        pending = [('item', source, target, info)]
        iterators = []
        try:
            while pending:
                self.control.check()
                kind, source, target, info = pending.pop()
                self.current, self.target = source, target
                if kind == 'children':
                    iterator, fd = info
                    try: entry = next(iterator)
                    except (StopIteration, OSError) as error:
                        iterator.close(); os.close(fd); iterators.remove((iterator, fd))
                        if isinstance(error, OSError):
                            self.pending.add(dict(kind='rescan', source=source, target=target), error)
                        continue
                    pending.append((kind, source, target, info))
                    child = os.path.join(source, entry.name)
                    pending.append(('item', child, os.path.join(target, entry.name), None))
                    continue
                task = dict(kind=kind, source=source, target=target, info=info)
                try:
                    if kind == 'directory_done':
                        self.finish_directory(source, target, info)
                    else:
                        info = info or self.get(source); task['info'] = info
                        if info is None: raise FileNotFoundError(errno.ENOENT, 'A source disappeared during copying.', source)
                        # Use no-follow metadata, never the filename or an I/O
                        # error. Links to sockets are still transferable links.
                        # Do this before destination/conflict checks: omitting a
                        # runtime socket must not touch an existing destination.
                        if stat.S_ISSOCK(info['mode']):
                            self.ignore_socket(source, target, info)
                            self.progress()
                            continue
                        if rescan and self.completed_item(source, target, info): continue
                        if not (stat.S_ISDIR(info['mode']) or stat.S_ISREG(info['mode']) or stat.S_ISLNK(info['mode'])):
                            raise SpecialFile(info['mode'])
                        old, _ = self.conflict(source, target, info, approved)
                        if stat.S_ISDIR(info['mode']):
                            # Obtain a readable iterator before creating a destination.
                            _, fd = self.access.call('list', path=source, expected=info)
                            try:
                                attrs = self.attributes(fd)
                                created = old is None
                                final = self.access.value('mkdir', path=target) if created else old
                                iterator = os.scandir(fd)
                            except BaseException:
                                os.close(fd); raise
                            iterators.append((iterator, fd))
                            pending.append(('directory_done', source, target, (info, final, created, attrs)))
                            pending.append(('children', source, target, (iterator, fd)))
                        elif stat.S_ISREG(info['mode']): self.copy_file(source, target, info, old)
                        else: self.copy_link(source, target, info, old)
                except OSError as error: self.pending.add(task, error)
                self.progress()
        finally:
            for iterator, fd in iterators:
                iterator.close(); os.close(fd)

    def completed_item(self, source, target, info):
        row = self.db.execute("SELECT original,final FROM entries WHERE source=? AND target=? AND kind IN ('file','link') LIMIT 1", (source, target)).fetchone()
        if not row: return False
        old, final = map(json.loads, row)
        current = self.get(target)
        return bool(current and all(info[k] == old[k] and current[k] == final[k] for k in ('dev','ino','size','mtime_ns','ctime_ns')))

    def finish_directory(self, source, target, info):
        original, final, created, attributes = info
        if not self.db.execute("SELECT 1 FROM entries WHERE source=? AND target=? AND kind='directory'", (source, target)).fetchone():
            self.record('directory', source, target, original, final, created)
            if created:
                self.db.execute('INSERT INTO directory_metadata(source,target,value) VALUES (?,?,?)', (source, target, json.dumps(info)))

    def apply_directory(self, source, target, info):
        original, final, created, attributes = info
        if created:
            final = self.metadata(target, final, original, attributes)
            self.db.execute("UPDATE entries SET final=? WHERE source=? AND target=? AND kind='directory'", (json.dumps(final), source, target))

    def attributes(self, fd):
        try:
            return {name: base64.b64encode(os.getxattr(fd, name)).decode('ascii') for name in os.listxattr(fd)
                    if name.startswith('user.') or name in ('system.posix_acl_access', 'system.posix_acl_default')
                    or (self.moving and name == 'security.capability')}
        except OSError as error:
            if error.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP): raise
            return {}

    def metadata(self, path, final, original, attributes=None):
        try:
            result = self.access.value('metadata', path=path, expected=final, original=original, attributes=attributes or {})
            if result.pop('unsupported', False):
                self.warnings.add('The destination filesystem does not support all Unix permissions, timestamps or extended attributes.')
            return result
        except OSError as error:
            if error.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL): raise
            self.warnings.add('The destination filesystem does not support all Unix permissions or timestamps.')
            return self.get(path)

    def discard(self, path, expected=None):
        # Cleanup must also work after Cancel/Pause. Never unlink by name alone.
        def cleanup_call(action, args):
            try: return self.ops.execute(action, args)[0]
            except PermissionError:
                if not self.access.connection: raise
                with self.access.rpc_lock:
                    send(self.access.connection, {'action': action, 'args': args})
                    result, fd = receive(self.access.connection)
                if fd is not None: os.close(fd)
                if not result.get('ok'): raise OSError(result.get('error'))
                return result['value']
        try:
            info = cleanup_call('stat', {'path': path})
            if expected and any(info[k] != expected[k] for k in ('dev', 'ino')):
                raise OSError('The temporary file was replaced by another process.')
            cleanup_call('remove', {'path': path, 'expected': info})
        except FileNotFoundError: pass
        except (OSError, EOFError):
            # A protected unfinished file remains visibly marked .part rather
            # than risking another authenticated operation after cancellation.
            self.warnings.add('An unfinished temporary file remains at ' + path)

    def copy_link(self, source, target, info, old):
        link = self.access.value('readlink', path=source, expected=info)
        temporary = os.path.join(os.path.dirname(target), '.fusion-' + uuid.uuid4().hex + '.part')
        reserved = None
        try:
            final = self.access.value('symlink', path=temporary, target=link)
            reserved = final
            final = self.access.value('publish', path=target, origin=temporary, expected=final, replaced=old)
            temporary = None
        finally:
            if temporary and reserved: self.discard(temporary, reserved)
        self.record('link', source, target, info, final)
        self.files += 1

    def copy_file(self, source, target, info, old):
        _, source_fd = self.access.call('read', path=source, expected=info)
        target_fd = None
        temporary = None
        previous_bytes = self.processed
        published = False
        try:
            reserved, target_fd = self.access.call('temporary', path=target)
            temporary = reserved['path']
            try:
                fcntl.ioctl(target_fd, 0x40049409, source_fd)  # FICLONE; optional acceleration.
                self.processed += info['size']
            except OSError as error:
                if error.errno not in (errno.EXDEV, errno.EOPNOTSUPP, errno.ENOTTY, errno.EINVAL, errno.ENOSYS): raise
                self.copy_data(source_fd, target_fd, info['size'])
            unchanged(os.fstat(source_fd), info)
            if os.pread(source_fd, 1, info['size']):
                raise OSError(errno.ESTALE, 'The source grew or does not report a reliable size. Its original was kept.')
            if os.fstat(target_fd).st_size != info['size']: raise OSError('The copied file has the wrong size.')
            os.close(target_fd); target_fd = None
            final = self.metadata(temporary, reserved['info'], info, self.attributes(source_fd))
            final = self.access.value('publish', path=target, origin=temporary, expected=final, replaced=old)
            temporary = None
            self.record('file', source, target, info, final)
            self.files += 1
            published = True
        finally:
            if not published:
                self.processed = previous_bytes
                self.last_bytes = min(self.last_bytes, self.processed)
            os.close(source_fd)
            if target_fd is not None: os.close(target_fd)
            if temporary: self.discard(temporary, reserved['info'])

    def copy_data(self, source_fd, target_fd, size):
        position = 0
        sparse = True
        accelerated = True
        while position < size:
            self.control.check()
            end = size
            if sparse:
                try:
                    data = os.lseek(source_fd, position, os.SEEK_DATA)
                    end = min(size, os.lseek(source_fd, data, os.SEEK_HOLE))
                    self.processed += min(data, size) - position
                    position = min(data, size)
                except OSError as error:
                    if error.errno == errno.ENXIO:
                        self.processed += size-position; position = size; break
                    if error.errno not in (errno.EINVAL, errno.ENOTSUP): raise
                    sparse = False
            os.lseek(source_fd, position, os.SEEK_SET); os.lseek(target_fd, position, os.SEEK_SET)
            while position < end:
                self.control.check()
                count = min(CHUNK, end-position)
                if accelerated:
                    try: copied = os.copy_file_range(source_fd, target_fd, count)
                    except OSError as error:
                        if error.errno not in (errno.EXDEV, errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP): raise
                        accelerated = False; continue
                    if copied == 0: accelerated = False; continue
                else:
                    data = os.read(source_fd, count)
                    if not data: raise OSError(errno.ESTALE, 'The source ended before all expected data could be read.')
                    copied = len(data); view = memoryview(data)
                    while view:
                        written = os.write(target_fd, view)
                        if not written: raise OSError(errno.EIO, 'Writing the destination stopped unexpectedly.')
                        view = view[written:]
                position += copied; self.processed += copied
                self.progress()
        os.ftruncate(target_fd, size)

    def entry(self, identifier):
        return self.db.execute('SELECT kind,source,target,original,final FROM entries WHERE id=?', (identifier,)).fetchone()

    def verify_entry(self, identifier):
        kind, source, target, original, final = self.entry(identifier)
        original, final = json.loads(original), json.loads(final)
        self.current, self.target = source, target
        if kind == 'link':
            a = self.access.value('readlink', path=source, expected=original)
            b = self.access.value('readlink', path=target, expected=final)
            if a != b: raise OSError(errno.EIO, 'The copied symbolic link failed verification.')
        else:
            _, source_fd = self.access.call('read', path=source, expected=original)
            target_fd = None
            previous = self.verified
            try:
                _, target_fd = self.access.call('read', path=target, expected=final)
                while True:
                    self.control.check()
                    a, b = self.read_block(source_fd), self.read_block(target_fd)
                    if a != b: raise OSError(errno.EIO, 'The copied file failed content verification. Its original was kept.')
                    if not a: break
                    self.verified += len(a); self.progress()
                unchanged(os.fstat(source_fd), original); unchanged(os.fstat(target_fd), final)
                os.fsync(target_fd)
            except BaseException:
                self.verified = previous
                raise
            finally:
                os.close(source_fd)
                if target_fd is not None: os.close(target_fd)

    def verify(self):
        self.phase = 'Verifying copied files'; self.progress(True)
        for identifier, source, target in self.db.execute("SELECT id,source,target FROM entries WHERE kind IN ('file','link') AND retained=0"):
            self.guarded(dict(kind='verify', source=source, target=target, entry=identifier), lambda: self.verify_entry(identifier))
        self.pending.drain()
        # Directory entries also have to reach stable storage before deletion.
        for (path,) in self.db.execute("SELECT target FROM entries WHERE kind='directory' UNION SELECT parent FROM entries WHERE kind IN ('file','link')"):
            self.guarded(dict(kind='sync', source=path, target=path), lambda: self.access.value('sync', path=path))
        self.pending.drain()
        self.db.commit()

    def read_block(self, fd):
        data = bytearray()
        while len(data) < CHUNK:
            self.control.check()
            piece = os.read(fd, CHUNK-len(data))
            if not piece: break
            data.extend(piece)
        return data

    def precheck_entry(self, identifier):
        kind, source, target, original, final = self.entry(identifier)
        self.current, self.target = source, target
        if kind == 'directory': return  # Removal still checks identity and emptiness.
        for path, expected in ((source, json.loads(original)), (target, json.loads(final))):
            current = self.get(path)
            if current is None or any(current[k] != expected[k] for k in ('dev','ino','size','mtime_ns','ctime_ns')):
                raise OSError(errno.ESTALE, 'An item changed before cleanup. Its original was kept: ' + path)

    def remove_entry(self, identifier):
        kind, source, target, original, final = self.entry(identifier)
        self.current, self.target = source, target
        expected = json.loads(original)
        if kind != 'directory':
            current = self.get(target); wanted = json.loads(final)
            if current is None or any(current[k] != wanted[k] for k in ('dev','ino','size','mtime_ns','ctime_ns')):
                raise OSError(errno.ESTALE, 'The verified destination changed. Its original was kept: ' + target)
        try: self.access.value('remove', path=source, expected=expected)
        except OSError as error:
            if kind == 'directory' and error.errno == errno.ENOTEMPTY:
                self.warnings.add('Folders containing skipped, new or untransferred items remain at their original locations.')
                return
            raise
        self.db.execute('UPDATE entries SET removed=1 WHERE id=?', (identifier,))
        if kind == 'file' and expected.get('nlink', 1) > 1:
            # Our own unlink changes the shared inode ctime. Save the new value
            # in the journal so deferred retries see the same guarded state.
            key = expected['dev'], expected['ino']
            linked = self.db.execute("SELECT source FROM entries WHERE kind='file' AND removed=0 AND json_extract(original,'$.dev')=? AND json_extract(original,'$.ino')=? LIMIT 1", key).fetchone()
            if linked:
                current = self.get(linked[0])
                if current:
                    self.db.execute("UPDATE entries SET original=json_set(original,'$.ctime_ns',?) WHERE kind='file' AND removed=0 AND json_extract(original,'$.dev')=? AND json_extract(original,'$.ino')=?", (current['ctime_ns'], *key))
        self.progress()

    def cleanup_sources(self):
        self.phase = 'Checking originals before removal'; self.progress(True)
        for identifier, source, target in self.db.execute("SELECT id,source,target FROM entries WHERE kind IN ('file','link') AND retained=0"):
            self.guarded(dict(kind='precheck', source=source, target=target, entry=identifier), lambda: self.precheck_entry(identifier))
        self.pending.drain()
        self.phase = 'Removing verified originals'; self.progress(True)
        for identifier, source, target in self.db.execute("SELECT id,source,target FROM entries WHERE kind != 'rename' AND retained=0 ORDER BY kind='directory',length(source) DESC,id"):
            self.guarded(dict(kind='remove', source=source, target=target, entry=identifier), lambda: self.remove_entry(identifier))
        self.pending.drain()
        # A deferred file removal may have left its now-empty parent behind.
        for identifier, source, target in self.db.execute("SELECT id,source,target FROM entries WHERE kind='directory' AND removed=0 AND retained=0 ORDER BY length(source) DESC"):
            self.guarded(dict(kind='remove', source=source, target=target, entry=identifier), lambda: self.remove_entry(identifier))
        self.pending.drain()
        self.db.commit()
        for source in self.sources:
            try: missing = self.get(source) is None
            except OSError: missing = False
            if missing:
                self.emit({'event': 'moved', 'source': source,
                           'destination': os.path.join(self.destination, os.path.basename(source))})

    def close(self):
        if self.counter:
            self.counter.stop.set()
            self.counter.thread.join(timeout=1)
        self.db.commit(); self.db.close(); self.access.close()


class Undo(Transfer):
    """Reverse only journalled, unchanged items; never recursively delete a tree."""
    def __init__(self, request, control, emit):
        self.old = sqlite3.connect('file:' + request['undoJournal'] + '?mode=ro', uri=True)
        previous = json.loads(self.old.execute('SELECT value FROM meta').fetchone()[0])
        self.was_move = previous['operation'] == 'move'
        super().__init__(dict(previous, journal=request['journal']), control, emit)
        self.ops.undo = True
        self.access.defer_authorization = False
        self.restored_directories = []

    def rows(self, reverse=False):
        return self.old.execute('SELECT kind,source,target,original,final,created,removed FROM entries ORDER BY ' + ("kind!='directory',length(source),id DESC" if reverse else "kind='directory',length(target) DESC,id"))

    def run(self):
        self.phase = 'Undoing transfer'
        # Validate before the first mutation; an edited destination stays put.
        for kind, source, target, original, final, created, removed in self.rows():
            self.control.check()
            if kind == 'directory': continue
            current, expected = self.get(target), json.loads(final)
            if current is None: continue
            if any(current[k] != expected[k] for k in ('dev','ino','size','mtime_ns','ctime_ns')):
                raise OSError(errno.ESTALE, 'A transferred item was changed. Undo left it in place: ' + target)
            if self.was_move and removed and self.get(source) is not None:
                raise FileExistsError(errno.EEXIST, 'Undo would overwrite a new item at the original location.', source)
        # Directory entries were recorded after their children, so reverse
        # order recreates parents before restoring any files into them.
        for kind, source, target, original, final, created, removed in self.rows(True):
            self.control.check()
            self.current, self.target = target, source
            original, final = json.loads(original), json.loads(final)
            if kind == 'directory':
                if self.was_move and removed and self.get(source) is None:
                    restored = self.access.value('mkdir', path=source)
                    self.restored_directories.append((source, restored, original))
                continue
            if self.get(target) is None: continue
            if kind == 'rename':
                self.access.value('rename', path=source, origin=target, expected=final, durable=True)
                self.emit({'event': 'moved', 'source': target, 'destination': source})
                self.renamed += 1
            elif self.was_move and removed:
                if kind == 'link': self.copy_link(target, source, final, None)
                else: self.copy_file(target, source, final, None)
            self.progress()
        self.db.commit()
        if self.was_move:
            self.verify()
            self.cleanup_sources()
        # Copies and unremoved move originals only require removing the
        # unchanged copied item. Existing destination directories are retained.
        for kind, source, target, original, final, created, removed in self.rows():
            self.control.check()
            self.current, self.target = target, source
            current = self.get(target)
            if current is None or kind == 'rename': continue
            if kind == 'directory':
                if not created: continue
                try: self.access.value('remove', path=target, expected=json.loads(final))
                except OSError as error:
                    if error.errno != errno.ENOTEMPTY: raise
            elif not (self.was_move and removed):
                self.access.value('remove', path=target, expected=json.loads(final))
        for path, final, original in reversed(self.restored_directories):
            self.metadata(path, final, original)
        self.progress(True, True)
        return {'event': 'result', 'ok': True, 'warnings': sorted(self.warnings)}

    def close(self):
        super().close(); self.old.close()


def main():
    lock = threading.Lock()
    def emit(value):
        with lock:
            print(json.dumps(value, ensure_ascii=True, separators=(',', ':')), flush=True)
    request = json.loads(sys.stdin.readline())
    control = Control(emit, sys.stdin)
    transfer = None
    try:
        transfer = (Undo if request['operation'] == 'undo' else Transfer)(request, control, emit)
        emit(transfer.run())
    except Cancelled:
        emit({'event': 'result', 'ok': False, 'cancelled': True})
    except Exception as error:
        context = '' if transfer is None else '\nFrom: ' + transfer.current + '\nTo: ' + transfer.target + '\nStage: ' + transfer.phase
        emit({'event': 'result', 'ok': False, 'error': str(error) + context +
              '\nCompleted copies are kept. Files that were not successfully moved remain at their original locations.'})
    finally:
        if transfer: transfer.close()


if __name__ == '__main__': main()
