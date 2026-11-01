#!/usr/bin/env python3
"""One authenticated removal request. Never run the browser as administrator.

Trash uses same-filesystem atomic moves and standard .trashinfo records. It never
falls back to permanent deletion, follows directory symlinks or crosses mounts.
"""
from __future__ import annotations
import ctypes
from datetime import datetime
import errno
import json
import os
from pathlib import Path
import pwd
import stat
import sys
from urllib.parse import quote_from_bytes, unquote_to_bytes
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'control_panel'))
from disk_scan import OPEN_DIR, PROTECTED, VIRTUAL, beneath, mount_points, open_directory


def identity(info):
    return str(info.st_dev), str(info.st_ino)


def checked(info, expected):
    if identity(info) != (str(expected['dev']), str(expected['ino'])):
        raise ValueError('The selected item changed. Refresh the folder and try again.')


def rename_noreplace(source_fd, source, dest_fd, dest):
    libc = ctypes.CDLL(None, use_errno=True)
    call = libc.renameat2
    call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    call.restype = ctypes.c_int
    if call(source_fd, source, dest_fd, dest, 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def private_child(parent, name, uid, gid):
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
        created = True
    except FileExistsError:
        created = False
    fd = os.open(name, OPEN_DIR, dir_fd=parent)
    try:
        if created:
            os.fchown(fd, uid, gid)
        info = os.fstat(fd)
        if info.st_uid != uid or info.st_mode & 0o077:
            raise ValueError('Trash directories must be private and owned by your account.')
        return fd
    except BaseException:
        os.close(fd)
        raise


def data_directory(path, home, uid, gid):
    """Create a missing XDG data home only inside the account's actual home."""
    if not path.startswith(b'/') or b'..' in path.split(b'/'):
        raise ValueError('Invalid Trash data directory.')
    try:
        fd = open_directory(path)
    except FileNotFoundError:
        if not beneath(path, home):
            raise ValueError('Create the configured data directory before using Trash.')
        fd = open_directory(home)
        try:
            for part in path[len(home):].strip(b'/').split(b'/'):
                if not part:
                    continue
                try:
                    child = os.open(part, OPEN_DIR, dir_fd=fd)
                except FileNotFoundError:
                    child = private_child(fd, part, uid, gid)
                os.close(fd)
                fd = child
        except BaseException:
            os.close(fd)
            raise
    if os.fstat(fd).st_uid != uid:
        os.close(fd)
        raise ValueError('The Trash data directory is not owned by your account.')
    return fd


def trash_at(parent_fd, name, path, current, data_home, account, mounts):
    home = os.fsencode(os.path.realpath(account.pw_dir))
    data = data_directory(data_home, home, account.pw_uid, account.pw_gid)
    root = files = infos = None
    relative = path
    try:
        if os.fstat(data).st_dev == current.st_dev:
            trash_path = data_home + b'/Trash'
            root = private_child(data, b'Trash', account.pw_uid, account.pw_gid)
        else:
            # Every mounted volume gets the user's standard top-level Trash.
            candidates = [mount for mount in mounts if beneath(path, mount)]
            mount = max(candidates, key=len)
            top = open_directory(mount)
            try:
                trash_name = ('.Trash-'+str(account.pw_uid)).encode()
                root = private_child(top, trash_name, account.pw_uid, account.pw_gid)
                trash_path = mount.rstrip(b'/') + b'/' + trash_name
                relative = os.path.relpath(path, mount)
            finally:
                os.close(top)
        if beneath(path, trash_path) or beneath(trash_path, path):
            raise ValueError('A Trash directory cannot be moved into itself.')
        files = private_child(root, b'files', account.pw_uid, account.pw_gid)
        infos = private_child(root, b'info', account.pw_uid, account.pw_gid)
        if os.fstat(files).st_dev != current.st_dev:
            raise ValueError('No same-filesystem Trash is available. The item was not deleted.')
        # UUID reservation + renameat2 prevent replacing any existing item.
        key = uuid.uuid4().hex.encode() + b'-' + name[:160]
        info_name = key + b'.trashinfo'
        fd = os.open(info_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=infos)
        try:
            os.fchown(fd, account.pw_uid, account.pw_gid)
            record = '[Trash Info]\nPath='+quote_from_bytes(relative, safe='/')+'\nDeletionDate='+datetime.now().strftime('%Y-%m-%dT%H:%M:%S')+'\n'
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(record.encode('utf-8')); stream.flush(); os.fsync(fd)
        except BaseException:
            os.unlink(info_name, dir_fd=infos)
            raise
        finally:
            os.close(fd)
        try:
            checked(os.stat(name, dir_fd=parent_fd, follow_symlinks=False), dict(zip(('dev', 'ino'), identity(current))))
            rename_noreplace(parent_fd, name, files, key)
        except BaseException:
            os.unlink(info_name, dir_fd=infos)
            raise
        os.fsync(infos)
        os.fsync(files)
        return dict(path=os.fsdecode(path), trash=os.fsdecode(trash_path+b'/files/'+key))
    finally:
        for fd in (infos, files, root, data):
            if fd is not None:
                os.close(fd)


def remove_at(parent, name, path, expected, mounts, device):
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    checked(current, expected)
    if path in mounts or current.st_dev != device:
        raise ValueError('A mounted filesystem cannot be deleted.')
    if not stat.S_ISDIR(current.st_mode):
        os.unlink(name, dir_fd=parent)
        return
    fd = os.open(name, OPEN_DIR, dir_fd=parent)
    try:
        checked(os.fstat(fd), expected)
        for child in os.listdir(fd):
            child = os.fsencode(child)
            snapshot = os.stat(child, dir_fd=fd, follow_symlinks=False)
            remove_at(fd, child, path+b'/'+child, dict(zip(('dev', 'ino'), identity(snapshot))), mounts, device)
        checked(os.stat(name, dir_fd=parent, follow_symlinks=False), expected)
        os.rmdir(name, dir_fd=parent)
    finally:
        os.close(fd)


def trash_record(path, data_home, account, mounts):
    root = os.path.dirname(os.path.dirname(path))
    allowed = {data_home+b'/Trash'}
    for mount in mounts:
        allowed.add(mount.rstrip(b'/')+b'/.Trash-'+str(account.pw_uid).encode())
        allowed.add(mount.rstrip(b'/')+b'/.Trash/'+str(account.pw_uid).encode())
    if root not in allowed or os.path.basename(os.path.dirname(path)) != b'files':
        raise ValueError('Select a top-level item in your Trash.')
    directory = open_directory(root)
    try:
        info = os.fstat(directory)
        if info.st_uid != account.pw_uid or info.st_mode & 0o077:
            raise ValueError('This Trash does not belong to your account.')
        infos = os.open(b'info', OPEN_DIR, dir_fd=directory)
    finally:
        os.close(directory)
    name = os.path.basename(path)+b'.trashinfo'
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=infos)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != account.pw_uid or info.st_nlink != 1 or info.st_size > 32768:
                raise ValueError('The Trash record is not a private regular file.')
            text = os.read(fd, 32769).decode('utf-8')
        finally:
            os.close(fd)
        paths = [line[5:] for line in text.splitlines() if line.startswith('Path=')]
        if not text.startswith('[Trash Info]\n') or len(paths) != 1:
            raise ValueError('The Trash record is invalid.')
        original = unquote_to_bytes(paths[0])
        if not original.startswith(b'/'):
            mount = max((mount for mount in mounts if beneath(root, mount)), key=len)
            original = mount.rstrip(b'/')+b'/'+original
        if os.path.normpath(original) != original or b'..' in original.split(b'/'):
            raise ValueError('The original location is invalid.')
        return infos, name, info, original
    except BaseException:
        os.close(infos)
        raise


def perform(data, account):
    if data.get('operation') not in ('trash', 'delete', 'restore'):
        raise ValueError('Unknown removal operation.')
    entries = data.get('items')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 4096:
        raise ValueError('Select a finite list of files or folders.')
    home = os.fsencode(os.path.realpath(account.pw_dir))
    data_home = os.fsencode(data.get('dataHome', os.fsdecode(home+b'/.local/share')))
    mounts = mount_points()
    completed = []
    for entry in entries:
        path = os.fsencode(entry['path'])
        if not path.startswith(b'/') or os.path.normpath(path) != path or b'..' in path.split(b'/'):
            raise ValueError('Choose an absolute normalized path.')
        if path in PROTECTED or path in mounts or beneath(home, path):
            raise ValueError('A system root, home directory or mounted filesystem cannot be removed.')
        if any(beneath(path, mount) for mount, fs in mounts.items() if fs in VIRTUAL):
            raise ValueError('Virtual kernel files cannot be removed.')
        parent = open_directory(os.path.dirname(path))
        record = None
        try:
            name = os.path.basename(path)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            checked(current, entry)
            if not (stat.S_ISREG(current.st_mode) or stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode)):
                raise ValueError('Choose a regular file, folder or symbolic link.')
            if stat.S_ISDIR(current.st_mode) and any(beneath(mount, path) for mount in mounts):
                raise ValueError('Unmount nested filesystems before removing this folder.')
            if data['operation'] == 'restore' or entry.get('fromTrash'):
                record = trash_record(path, data_home, account, mounts)
            if data['operation'] == 'restore':
                infos, info_name, info, original = record
                if entry.get('restoreTo') and os.fsencode(entry['restoreTo']) != original:
                    raise ValueError('The original location changed. Refresh Trash before restoring.')
                if original in PROTECTED or original in mounts or beneath(home, original):
                    raise ValueError('A system root or home directory cannot be replaced.')
                destination = open_directory(os.path.dirname(original))
                try:
                    rename_noreplace(parent, name, destination, os.path.basename(original))
                finally:
                    os.close(destination)
                result = dict(path=os.fsdecode(path), restored=os.fsdecode(original))
            elif data['operation'] == 'trash':
                result = trash_at(parent, name, path, current, data_home, account, mounts)
            else:
                remove_at(parent, name, path, entry, mounts, current.st_dev)
                result = dict(path=os.fsdecode(path))
            if record:
                infos, info_name, info, _ = record
                checked(os.stat(info_name, dir_fd=infos, follow_symlinks=False), dict(zip(('dev', 'ino'), identity(info))))
                os.unlink(info_name, dir_fd=infos)
            completed.append(result)
        except Exception as error:
            return dict(ok=False, completed=completed, error=str(error))
        finally:
            if record:os.close(record[0])
            os.close(parent)
    return dict(ok=True, completed=completed)


def main():
    try:
        if os.geteuid() != 0:
            raise PermissionError('Administrator authentication is required for this action.')
        uid = int(os.environ.get('PKEXEC_UID', os.environ.get('SUDO_UID', '0')))
        if uid <= 0:
            raise PermissionError('The requesting desktop account could not be verified.')
        raw = sys.stdin.buffer.read(1024*1024+1)
        if len(raw) > 1024*1024:
            raise ValueError('The removal request is too large.')
        result = perform(json.loads(raw), pwd.getpwuid(uid))
    except Exception as error:
        result = dict(ok=False, error=str(error))
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
