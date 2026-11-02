#!/usr/bin/env python3
"""Recover a missing X11 pathname using this compositor's surviving listener.

Hyprland creates X<N> and, with abstract sockets disabled, X<N>_. Losing the
first pathname breaks new X11 clients even while the server and old clients
remain alive. Restore a socket hard link: protected_symlinks prevents root GUI
apps from following a user-owned symlink in the root-owned sticky X11 folder.
Only a verified legacy link to this exact backup may be migrated.
"""
from contextlib import contextmanager
import argparse
import fcntl
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import sys
import time


def peer(stream):
    pid, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    return pid, uid


def display_number(display):
    match = re.fullmatch(r':([0-9]{1,5})(?:\.[0-9]+)?', display)
    if not match:
        raise ValueError('DISPLAY is not a local XWayland display.')
    return int(match[1])


def same_listener(path, compositor):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(.5)
            stream.connect(str(path))
            return peer(stream) == compositor
    except OSError:
        return False


def recover(number, compositor, *, repair=False, socket_dir=Path('/tmp/.X11-unix'), lock_dir=Path('/tmp')):
    """Return (status, detail); injected directories are for disposable tests."""
    pid, uid = compositor
    name, alternate = f'X{number}', f'X{number}_'
    public = socket_dir/name
    try:
        # The X display lock must belong to the PID authenticated by the
        # compositor IPC socket, not merely to a process named Hyprland.
        fd = os.open(lock_dir/f'.X{number}-lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                    or int(os.read(fd, 64).strip()) != pid):
                return 'unavailable', 'The display lock does not belong to this compositor.'
        finally:
            os.close(fd)
        directory = os.open(socket_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(directory)
            if (info.st_uid not in (0, uid)
                    or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)):
                return 'unavailable', 'The X11 socket directory has unexpected ownership or permissions.'
            try:
                current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                current = None
            legacy = False
            if current is not None:
                if current.st_uid != uid or not (stat.S_ISSOCK(current.st_mode) or stat.S_ISLNK(current.st_mode)):
                    return 'unavailable', 'The display pathname is occupied; it was left untouched.'
                legacy = (stat.S_ISLNK(current.st_mode)
                          and os.readlink(name, dir_fd=directory) in (alternate, str(socket_dir/alternate))
                          and same_listener(public, compositor))
                if not legacy and same_listener(public, compositor):
                    return 'healthy', f'Display :{number} accepts connections to this compositor.'
                if not legacy:
                    return 'unavailable', 'The existing display endpoint is not responding as this compositor.'
            candidate = os.stat(alternate, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISSOCK(candidate.st_mode) or candidate.st_uid != uid:
                return 'unavailable', 'No owned backup XWayland socket is available.'
            if not same_listener(socket_dir/alternate, compositor):
                return 'unavailable', 'The backup socket is not a live listener from this compositor.'
            after = os.stat(alternate, dir_fd=directory, follow_symlinks=False)
            if (candidate.st_dev, candidate.st_ino) != (after.st_dev, after.st_ino):
                return 'unavailable', 'The backup socket changed during inspection.'
            if not repair:
                if legacy:
                    return 'recoverable', f'Display :{number} uses a legacy symlink that blocks elevated applications.'
                return 'recoverable', f'Display :{number} is missing its pathname; its verified backup listener is alive.'
            if legacy:
                latest = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if (latest.st_dev, latest.st_ino) != (current.st_dev, current.st_ino):
                    return 'unavailable', 'The legacy display link changed during recovery.'
                os.unlink(name, dir_fd=directory)
            # Atomic, no clobber: a concurrently created entry always wins.
            # A socket hard link also works with Linux protected_symlinks=1.
            try:
                os.link(alternate, name, src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
            except FileExistsError:
                return 'unavailable', 'The display pathname changed during recovery; it was left untouched.'
            return 'recovered', f'Restored display :{number} through its verified backup listener.'
        finally:
            os.close(directory)
    except (OSError, ValueError) as error:
        return 'unavailable', f'Cannot verify display :{number}: {error}'


def instance_path(env=None):
    env = os.environ if env is None else env
    runtime, signature = env.get('XDG_RUNTIME_DIR', ''), env.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not Path(runtime).is_absolute() or not re.fullmatch(r'[A-Za-z0-9_-]+', signature):
        raise RuntimeError('No active Hyprland session was found.')
    base = Path(runtime)
    for path in (base, base/'hypr', base/'hypr'/signature):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise RuntimeError('The compositor runtime directory is not private to this user.')
    return base/'hypr'/signature


@contextmanager
def session(instance):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as events:
        events.settimeout(2)
        events.connect(str(instance/'.socket2.sock'))
        compositor = peer(events)
        if compositor[1] != os.getuid():
            raise RuntimeError('The compositor belongs to another user.')
        events.setblocking(False)
        yield events, compositor


def connected(events):
    try:
        # Drain events but never use a leftover filesystem socket as evidence
        # that a session is still alive after logout or a compositor crash.
        return bool(events.recv(65536))
    except BlockingIOError:
        return True
    except OSError:
        return False


def serve(instance, number, *, interval=5, socket_dir=Path('/tmp/.X11-unix'), lock_dir=Path('/tmp')):
    with session(instance) as (events, compositor):
        lock = os.open(instance/'xwayland-session.lock',
                       os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise RuntimeError('Unexpected XWayland recovery lock.')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            last, due = None, 0.0
            while connected(events):
                if time.monotonic() >= due:
                    result = recover(number, compositor, repair=True, socket_dir=socket_dir, lock_dir=lock_dir)
                    if result != last:
                        print('XWayland '+result[0]+': '+result[1], flush=True)
                        last = result
                    due = time.monotonic()+interval
                select.select([events], [], [], max(0, due-time.monotonic()))
            return 0
        finally:
            os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--session', action='store_true', help='Watch only this Hyprland session and recover missing socket paths.')
    mode.add_argument('--check', action='store_true', help='Inspect the current display without changing anything.')
    args = parser.parse_args()
    try:
        instance = instance_path()
        number = display_number(os.environ.get('DISPLAY', ''))
        if args.session:
            return serve(instance, number)
        with session(instance) as (events, compositor):
            if not connected(events):
                raise RuntimeError('The compositor disconnected.')
            status, detail = recover(number, compositor)
            print('XWayland '+status+': '+detail)
            return 0 if status == 'healthy' else 1
    except (OSError, ValueError, RuntimeError) as error:
        print('XWayland check: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
