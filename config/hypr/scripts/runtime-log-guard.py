#!/usr/bin/env python3
"""Bound this Hyprland session's logs without unlinking active writer files."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 64 * 1024 * 1024
INTERVAL = 60
# Explicitly owned log files only: never walk /run, other sessions or app data.
LOGS = ('hyprland.log', 'cached-apps.log', 'cached-settings.log', 'cached-panel.log',
        'update-activation.log', 'desktop-updates.log', 'theme-build.log',
        'burn.log', 'cube.log', 'minimize.log', 'panel-startup.log',
        'session-ui-preload.log', 'switcher.log', 'floating-drag.log',
        'file-progress.log', 'waybar-supervisor.log', 'waybar.log', 'waybar.log.1',
        'hyprpaper.log', 'desktop-menu.log', 'network-applet.log',
        'swaync.log', 'polkit-agent.log', 'sign-in-artwork.log',
        'startup-scene.log', 'startup-projects.log', 'startup-clock.log',
        'startup-matrix.log', 'startup-info.log', 'floating-geometry.log',
        'screenshot-notify.log')


def setting_path(root=ROOT):
    return root / 'control_panel/state/runtime-log-guard.json'


def enabled(root=ROOT):
    try: value = json.loads(setting_path(root).read_text())
    except FileNotFoundError: return True
    if not isinstance(value, dict) or value.get('version') != 1 or type(value.get('enabled')) is not bool:
        raise ValueError('The log guard setting is invalid. Switch protection on or off to save it again.')
    return value['enabled']


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)


def instance_path(env=None):
    env = os.environ if env is None else env
    runtime, signature = env.get('XDG_RUNTIME_DIR', ''), env.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not runtime or not Path(runtime).is_absolute() or not re.fullmatch(r'[A-Za-z0-9_-]+', signature):
        raise RuntimeError('No active Hyprland session was found.')
    base = Path(runtime)
    for path in (base, base/'hypr', base/'hypr'/signature):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise RuntimeError('The Hyprland runtime directory is not private to this user.')
    return base/'hypr'/signature


@contextmanager
def session(instance):
    directory = os.open(instance, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as events:
            events.settimeout(2)
            events.connect(str(instance/'.socket2.sock'))
            _, owner, _ = struct.unpack('3i', events.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if owner != os.getuid(): raise RuntimeError('The compositor belongs to another user.')
            events.setblocking(False)
            yield directory, events
    finally: os.close(directory)


def connected(events):
    if select.select([events], [], [], 0)[0]:
        try: return bool(events.recv(65536))
        except BlockingIOError: pass
    return True


def safe_info(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ValueError('Only single-link, user-owned regular logs can be managed.')
    return info


def logs(directory, trim=False, limit=LIMIT):
    rows, errors = [], []
    for name in LOGS:
        fd = None
        try:
            fd = os.open(name, (os.O_WRONLY if trim else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
            if trim: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = safe_info(fd)
            allocated = info.st_blocks * 512
            cleared = trim and max(info.st_size, allocated) > limit
            if cleared: os.ftruncate(fd, 0)
            rows.append({'name': name, 'bytes': 0 if cleared else allocated,
                         'size': 0 if cleared else info.st_size, 'cleared': cleared,
                         'freed': allocated if cleared else 0})
        except FileNotFoundError: pass
        except (OSError, ValueError) as error: errors.append(name+': '+str(error))
        finally:
            if fd is not None: os.close(fd)
    return rows, errors


def running(directory):
    try: fd = os.open('runtime-log-guard.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError: return False
    try:
        safe_info(fd)
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return True
        return False
    finally: os.close(fd)


def check(directory, root=ROOT, limit=LIMIT):
    rows, errors = logs(directory, trim=True, limit=limit)
    cleared = [row['name'] for row in rows if row['cleared']]
    freed = sum(row['freed'] for row in rows)
    if cleared:
        try:
            write_json(root/'control_panel/state/runtime-log-guard-last.json',
                       {'time': int(time.time()), 'logs': cleared, 'freed': freed})
        except OSError as error: errors.append('Cleanup succeeded, but its history could not be saved: '+str(error))
    return {'cleared': cleared, 'freed': freed, 'errors': errors}


def status(root=ROOT):
    value = {'enabled': enabled(root), 'limit': LIMIT, 'interval': INTERVAL,
             'active': False, 'running': False, 'logs': []}
    try:
        instance = instance_path()
        with session(instance) as (directory, events):
            if not connected(events): return value
            rows, errors = logs(directory)
            space = os.fstatvfs(directory)
            value.update(active=True, running=running(directory), logs=rows, errors=errors,
                         used=sum(row['bytes'] for row in rows), runtime_free=space.f_bavail*space.f_frsize)
    except (OSError, RuntimeError) as error: value['message'] = str(error)
    try: value['last'] = json.loads((root/'control_panel/state/runtime-log-guard-last.json').read_text())
    except (OSError, ValueError): pass
    return value


def serve(instance, root=ROOT, interval=INTERVAL, limit=LIMIT):
    with session(instance) as (directory, events):
        # Free space before creating our lock when tmpfs is already full.
        if connected(events) and enabled(root): check(directory, root, limit)
        fd = os.open('runtime-log-guard.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=directory)
        try:
            safe_info(fd)
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return 0
            stopping = False
            def stop(*_):
                nonlocal stopping
                stopping = True
            previous = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
            deadline = time.monotonic()+interval
            try:
                while not stopping:
                    select.select([events], [], [], min(1, max(0, deadline-time.monotonic())))
                    if not connected(events): break
                    if time.monotonic() >= deadline:
                        try:
                            if enabled(root): check(directory, root, limit)
                        except (OSError, ValueError) as error: print(str(error), file=sys.stderr, flush=True)
                        deadline = time.monotonic()+interval
            finally:
                for s, handler in previous.items(): signal.signal(s, handler)
        finally: os.close(fd)
    return 0


def start(instance, root=ROOT):
    with session(instance) as (directory, events):
        if not connected(events): raise RuntimeError('This Hyprland session has ended.')
        if running(directory): return
        process = subprocess.Popen([sys.executable, str(root/'scripts/runtime-log-guard.py'), '--session'],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            if running(directory): return
            if process.poll() is not None: break
            time.sleep(.025)
        raise RuntimeError('The setting was saved, but the session guard could not start. Try enabling it again.')


def main():
    try:
        args = sys.argv[1:]
        if args == ['--session']: return serve(instance_path())
        if args == ['--status']: value = status()
        elif args == ['--once']:
            with session(instance_path()) as (directory, events):
                if not connected(events): raise RuntimeError('This Hyprland session has ended.')
                result = check(directory)
            value = {**status(), 'checked': result}
        elif args in (['--enable'], ['--disable']):
            choice = args == ['--enable']
            write_json(setting_path(), {'version': 1, 'enabled': choice})
            if choice: start(instance_path())
            value = status()
        else: raise ValueError('Use --status, --once, --enable, --disable or --session.')
        print(json.dumps(value)); return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'error': str(error)})); return 1


if __name__ == '__main__': raise SystemExit(main())
