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
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_logging
from session_logging import setting_path, write_json

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 64 * 1024 * 1024
INTERVAL = 60
# Explicitly owned log files only: never walk /run, other sessions or app data.
LOGS = ('hyprland.log', 'cached-apps.log', 'cached-settings.log', 'cached-panel.log',
        'update-activation.log', 'desktop-updates.log', 'theme-build.log',
        'burn.log', 'cube.log', 'minimize.log', 'window-close.log', 'panel-startup.log',
        'session-ui-preload.log', 'switcher.log', 'floating-drag.log',
        'file-progress.log', 'waybar-supervisor.log', 'waybar.log', 'waybar.log.1',
        'hyprpaper.log', 'desktop-menu.log', 'network-applet.log',
        'swaync.log', 'polkit-agent.log', 'sign-in-artwork.log',
        'startup-scene.log', 'startup-projects.log', 'startup-clock.log',
        'startup-matrix.log', 'startup-info.log', 'floating-geometry.log',
        'screenshot-notify.log', 'xwayland-session.log')


def enabled(root=ROOT):
    return session_logging.preferences(root)['enabled']


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


def connected(events, receive=None):
    if select.select([events], [], [], 0)[0]:
        try:
            data = events.recv(65536)
            if data and receive: receive(data)
            return bool(data)
        except BlockingIOError: pass
    return True


def apply_logging(instance):
    value = session_logging.current(instance)
    if not value['disabled']: return
    error = ''
    try:
        result = subprocess.run(['hyprctl', 'keyword', 'debug:disable_logs', 'true'],
                                capture_output=True, text=True, timeout=2)
        if result.returncode or result.stdout.strip() != 'ok':
            error = 'Could not disable Hyprland file logging: ' + (result.stderr or result.stdout).strip()[:300]
    except (OSError, subprocess.TimeoutExpired) as exc: error = str(exc)
    if value.get('error', '') != error:
        value['error'] = error
        write_json(instance/'session-logging.json', value)


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
    settings = session_logging.preferences(root)
    value = {'enabled': settings['enabled'], 'file_logs_disabled': settings['disable_file_logs'],
             'session_file_logs_disabled': False, 'logging_pending': False,
             'limit': LIMIT, 'interval': INTERVAL, 'active': False, 'running': False, 'logs': []}
    try:
        instance = instance_path()
        with session(instance) as (directory, events):
            if not connected(events): return value
            rows, errors = logs(directory)
            space = os.fstatvfs(directory)
            policy = session_logging.current(instance)
            value.update(active=True, running=running(directory), logs=rows, errors=errors,
                         used=sum(row['bytes'] for row in rows), runtime_free=space.f_bavail*space.f_frsize,
                         session_file_logs_disabled=policy['disabled'], logging_error=policy.get('error', ''),
                         logging_pending=policy['disabled'] != settings['disable_file_logs'])
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
            pending = b''
            def refresh_logging():
                # A failed status write or compositor option must not stop the
                # guard from reclaiming space (especially on a full tmpfs).
                try: apply_logging(instance)
                except (OSError, ValueError) as error: print(str(error), file=sys.stderr, flush=True)
            def receive(data):
                nonlocal pending
                lines = (pending+data).split(b'\n'); pending = lines.pop()[-4096:]
                if any(line.startswith(b'configreloaded>>') for line in lines): refresh_logging()
            try:
                refresh_logging()
                while not stopping:
                    select.select([events], [], [], min(1, max(0, deadline-time.monotonic())))
                    if not connected(events, receive): break
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
        if args == ['--begin-session']:
            instance = instance_path()
            with session(instance) as (_, events):
                if not connected(events): raise RuntimeError('This Hyprland session has ended.')
                policy = session_logging.begin(instance)
                apply_logging(instance)
            print(int(policy['disabled'])); return 0
        if args == ['--status']: value = status()
        elif args == ['--once']:
            with session(instance_path()) as (directory, events):
                if not connected(events): raise RuntimeError('This Hyprland session has ended.')
                result = check(directory)
            value = {**status(), 'checked': result}
        elif args in (['--enable'], ['--disable']):
            choice = args == ['--enable']
            session_logging.save('enabled', choice)
            if choice: start(instance_path())
            value = status()
        elif args in (['--disable-file-logs'], ['--enable-file-logs']):
            session_logging.save('disable_file_logs', args == ['--disable-file-logs'])
            value = status()
        else: raise ValueError('Use --status, --once, --enable, --disable, --disable-file-logs, --enable-file-logs or --session.')
        print(json.dumps(value)); return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'error': str(error)})); return 1


if __name__ == '__main__': raise SystemExit(main())
