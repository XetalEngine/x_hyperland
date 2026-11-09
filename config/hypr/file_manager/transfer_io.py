"""Filesystem operations for one local transfer, also used by its Polkit helper.

All paths are confined to the selected sources and destination. Directory walks
use O_NOFOLLOW and dirfds; copying a link never grants access to its target.
No shell, recursive deletion, password storage, or unrestricted root commands.
"""
from __future__ import annotations
from contextlib import contextmanager
import ctypes
import base64
import errno
import os
import stat
import uuid

DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def beneath(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


def snapshot(info):
    return {name: getattr(info, 'st_' + name) for name in
            ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns', 'atime_ns')}


def unchanged(info, expected, content=True):
    now = snapshot(info)
    keys = ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns') if content else ('dev', 'ino')
    if any(now[k] != expected[k] for k in keys):
        raise OSError(errno.ESTALE, 'The item changed during the transfer; it was left in place.')
    return now


@contextmanager
def directory(path):
    if not os.path.isabs(path) or '..' in path.split('/'):
        raise ValueError('An absolute path without parent traversal is required.')
    fd = os.open('/', DIRECTORY)
    try:
        for part in path.split('/'):
            if part in ('', '.'):
                continue
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def rename_noreplace(source, source_fd, target, target_fd):
    call = ctypes.CDLL(None, use_errno=True).renameat2
    call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    call.restype = ctypes.c_int
    if call(source_fd, os.fsencode(source), target_fd, os.fsencode(target), 1):
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


class FileOps:
    """Explicit, small capability surface shared by user and administrator workers."""
    def __init__(self, sources, destination, moving=False, uid=None, gid=None, undo=False):
        self.sources = [os.path.normpath(p) for p in sources]
        self.destination = os.path.normpath(destination)
        self.moving, self.undo = moving, undo
        self.uid = os.getuid() if uid is None else uid
        self.gid = os.getgid() if gid is None else gid
        for path in [*self.sources, self.destination]:
            if not os.path.isabs(path) or path == '/':
                raise ValueError('Select files or folders inside a storage filesystem.')

    def check(self, path, write=False, source=False):
        if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
            raise ValueError('Invalid transfer path.')
        in_source = any(beneath(path, root) for root in self.sources)
        in_destination = beneath(path, self.destination)
        if source and not in_source:
            raise ValueError('This item is outside the selected sources.')
        if not (in_source or in_destination):
            raise ValueError('This path is outside the transfer.')
        if write and not in_destination and not (in_source and (self.moving or self.undo)):
            raise ValueError('This copy cannot modify its source.')
        if write and path == self.destination:
            raise ValueError('The destination container itself cannot be changed.')
        return path

    def execute(self, action, args):
        """Return (JSON-compatible value, optional descriptor owned by the caller)."""
        if action == 'sync' and args['path'] in [os.path.dirname(p) for p in self.sources]:
            path = args['path']  # fsync only; does not grant access to other children.
        else:
            path = self.check(args['path'], write=action in
                              ('mkdir', 'temporary', 'publish', 'remove', 'metadata', 'symlink', 'hardlink', 'rename'))
        with directory(os.path.dirname(path)) as parent:
            name = os.path.basename(path)
            if action == 'stat':
                return snapshot(os.stat(name, dir_fd=parent, follow_symlinks=False)), None
            if action == 'list':
                fd = os.open(name, DIRECTORY, dir_fd=parent)
                if args.get('expected'):
                    try: unchanged(os.fstat(fd), args['expected'], False)
                    except BaseException: os.close(fd); raise
                return None, fd
            if action == 'read':
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError('Only regular files can be read by the transfer.')
                    if args.get('expected'): unchanged(info, args['expected'])
                    return snapshot(info), fd
                except BaseException:
                    os.close(fd); raise
            if action == 'readlink':
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if args.get('expected'): unchanged(info, args['expected'])
                return os.readlink(name, dir_fd=parent), None
            if action == 'sync':
                fd = os.open(name, DIRECTORY, dir_fd=parent)
                try: os.fsync(fd)
                finally: os.close(fd)
                return None, None
            if action == 'mkdir':
                os.mkdir(name, 0o700, dir_fd=parent)
                if os.geteuid() == 0:
                    os.chown(name, self.uid, self.gid, dir_fd=parent, follow_symlinks=False)
                return snapshot(os.stat(name, dir_fd=parent, follow_symlinks=False)), None
            if action == 'temporary':
                # The requested filename is only a location hint. Reserve our
                # own unpredictable name; never truncate an existing file.
                name = '.fusion-' + uuid.uuid4().hex + '.part'
                fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
                try:
                    if os.geteuid() == 0: os.fchown(fd, self.uid, self.gid)
                    return {'path': os.path.join(os.path.dirname(path), name), 'info': snapshot(os.fstat(fd))}, fd
                except BaseException:
                    os.close(fd); os.unlink(name, dir_fd=parent); raise
            if action in ('publish', 'rename'):
                origin = self.check(args['origin'], write=True)
                if action == 'rename' and not self.moving and not self.undo:
                    raise ValueError('Renaming sources is only allowed for a move.')
                with directory(os.path.dirname(origin)) as original_parent:
                    original_name = os.path.basename(origin)
                    unchanged(os.stat(original_name, dir_fd=original_parent, follow_symlinks=False), args['expected'])
                    old = args.get('replaced')
                    if old is None:
                        rename_noreplace(original_name, original_parent, name, parent)
                    else:
                        unchanged(os.stat(name, dir_fd=parent, follow_symlinks=False), old)
                        if stat.S_ISDIR(old['mode']):
                            raise ValueError('A folder cannot be overwritten by a file.')
                        os.rename(original_name, name, src_dir_fd=original_parent, dst_dir_fd=parent)
                    if args.get('durable'):
                        os.fsync(parent)
                        if action == 'rename': os.fsync(original_parent)
                return snapshot(os.stat(name, dir_fd=parent, follow_symlinks=False)), None
            if action == 'remove':
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
                is_dir = stat.S_ISDIR(current.st_mode)
                unchanged(current, args['expected'], not is_dir)
                if is_dir:
                    if os.path.ismount(path): raise ValueError('A mounted filesystem cannot be removed.')
                    os.rmdir(name, dir_fd=parent)  # Empty only; never delete new/unrecorded children.
                else:
                    # Claim the exact name atomically, then inspect the inode
                    # again. A concurrent replacement must never be unlinked.
                    held = '.fusion-remove-' + uuid.uuid4().hex
                    rename_noreplace(name, parent, held, parent)
                    try:
                        after = os.stat(held, dir_fd=parent, follow_symlinks=False)
                        # rename may update ctime. Size/mtime/inode must agree.
                        expected = args['expected']
                        now = snapshot(after)
                        if any(now[k] != expected[k] for k in ('dev','ino','size','mtime_ns')):
                            raise OSError(errno.ESTALE, 'The source changed before removal; it was kept.')
                        os.unlink(held, dir_fd=parent)
                    except BaseException:
                        try: rename_noreplace(held, parent, name, parent)
                        except FileExistsError:
                            raise OSError(errno.ESTALE, 'The source name changed. The retained original is at ' + os.path.join(os.path.dirname(path), held))
                        raise
                os.fsync(parent)
                return None, None
            if action == 'symlink':
                os.symlink(args['target'], name, dir_fd=parent)
                if os.geteuid() == 0: os.chown(name, self.uid, self.gid, dir_fd=parent, follow_symlinks=False)
                return snapshot(os.stat(name, dir_fd=parent, follow_symlinks=False)), None
            if action == 'hardlink':
                origin = self.check(args['origin'])
                with directory(os.path.dirname(origin)) as original_parent:
                    original_name = os.path.basename(origin)
                    unchanged(os.stat(original_name, dir_fd=original_parent, follow_symlinks=False), args['expected'])
                    os.link(original_name, name, src_dir_fd=original_parent, dst_dir_fd=parent, follow_symlinks=False)
                return snapshot(os.stat(name, dir_fd=parent, follow_symlinks=False)), None
            if action == 'metadata':
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
                try:
                    unchanged(os.fstat(fd), args['expected'], False)
                    original = args['original']
                    unsupported = False
                    # Copies belong to the desktop account. Moves retain the
                    # original ownership, asking the scoped helper if needed.
                    if self.moving:
                        current = os.fstat(fd)
                        if (current.st_uid, current.st_gid) != (original['uid'], original['gid']):
                            os.fchown(fd, original['uid'], original['gid'])
                    for key, value in args.get('attributes', {}).items():
                        if key.startswith('user.') or key in ('system.posix_acl_access', 'system.posix_acl_default') or (self.moving and key == 'security.capability'):
                            try: os.setxattr(fd, key, base64.b64decode(value))
                            except OSError as error:
                                if error.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP): raise
                                unsupported = True
                    for apply in (lambda: os.fchmod(fd, stat.S_IMODE(original['mode']) & (0o7777 if self.moving else 0o777)),
                                  lambda: os.utime(fd, ns=(original['atime_ns'], original['mtime_ns']))):
                        try: apply()
                        except OSError as error:
                            if error.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL): raise
                            unsupported = True
                    if args.get('durable'): os.fsync(fd)
                    return dict(snapshot(os.fstat(fd)), unsupported=unsupported), None
                finally: os.close(fd)
        raise ValueError('Unsupported transfer operation.')
