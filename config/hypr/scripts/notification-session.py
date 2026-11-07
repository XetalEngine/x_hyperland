#!/usr/bin/env python3
"""Own the themed notification daemon before clients can activate a default one."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import time

from session_logging import log_path, write_json

NOTIFICATIONS = 'org.freedesktop.Notifications'
CONTROL = 'org.erikreider.swaync.cc'
ROOT = Path(__file__).resolve().parents[1]


def owner_pid(name=NOTIFICATIONS):
    # Asking the bus for its owner never activates a notification server.
    result = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
        '--object-path', '/org/freedesktop/DBus', '--method',
        'org.freedesktop.DBus.GetConnectionUnixProcessID', name],
        capture_output=True, text=True, timeout=3)
    if result.returncode and 'org.freedesktop.DBus.Error.NameHasNoOwner' in result.stderr:
        return None
    match = re.fullmatch(r'\(uint32 (\d+),\)\s*', result.stdout)
    if result.returncode or not match:
        raise RuntimeError('Could not identify the notification bus owner: '+result.stderr.strip())
    return int(match[1])


def process_info(pid, proc=Path('/proc')):
    try:
        folder = proc/str(pid)
        return {'pid': pid, 'uid': folder.stat().st_uid,
                'command': [part.decode(errors='replace') for part in (folder/'cmdline').read_bytes().split(b'\0') if part],
                'environment': dict(part.decode(errors='replace').split('=', 1)
                    for part in (folder/'environ').read_bytes().split(b'\0') if b'=' in part),
                'started': (folder/'stat').read_text().rsplit(') ', 1)[1].split()[19]}
    except (OSError, IndexError):
        return None


def same_session(info, environment):
    if not info or info['uid'] != os.getuid() or not info['command']:
        return False
    if Path(info['command'][0]).name != 'swaync':
        return False
    # A shared user bus can include another desktop or another Hyprland login.
    # Do not stop either, even when it also runs SwayNC.
    return all(environment.get(key) and info['environment'].get(key) == environment[key]
               for key in ('HYPRLAND_INSTANCE_SIGNATURE', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR'))


def uses_profile(info, root):
    args = info['command'][1:]
    def value(short, long):
        for index, arg in enumerate(args):
            if arg in (short, long):
                return args[index+1] if index+1 < len(args) else None
            if arg.startswith(long+'='):
                return arg.split('=', 1)[1]
        return None
    return (value('-c', '--config') == str(root/'swaync/config.json')
            and value('-s', '--style') == str(root/'swaync/style.css'))


class ActivationPause:
    """Block generic D-Bus activation only during a same-session handover."""
    def __init__(self, runtime):
        self.path = Path(runtime)/'systemd/user/swaync.service'
        self.identity = None

    def acquire(self):
        if self.identity is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.symlink_to('/dev/null')
        except FileExistsError:
            if self.path.is_symlink() and self.path.readlink() == Path('/dev/null'):
                return  # An existing mask belongs to its owner, never to us.
            raise RuntimeError('An existing runtime SwayNC unit prevents automatic handover.')
        info = self.path.lstat()
        self.identity = (info.st_dev, info.st_ino)
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True, timeout=5)

    def release(self):
        if self.identity is None:
            return
        try:
            info = self.path.lstat()
            if (info.st_dev, info.st_ino) == self.identity and self.path.readlink() == Path('/dev/null'):
                self.path.unlink()
                subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True, timeout=5)
        except FileNotFoundError:
            pass
        finally:
            self.identity = None


def retire_default(info, environment, activation=None):
    if not same_session(info, environment) or process_info(info['pid']) != info:
        raise RuntimeError('Notification owner changed before handover; leaving it alone.')
    if activation is not None:
        activation.acquire()
    service = subprocess.run(['systemctl', '--user', 'show', 'swaync.service',
                              '--property=MainPID', '--value'], capture_output=True, text=True, timeout=3)
    if service.returncode == 0 and service.stdout.strip() == str(info['pid']):
        # Stop this activation without changing saved configuration/enablement.
        # A direct kill would trigger its Restart=on-failure policy.
        # Existing clients can cancel a stop job by requesting activation again;
        # temporarily block that path until our daemon owns both bus names.
        subprocess.run(['systemctl', '--user', 'stop', 'swaync.service'], check=True, timeout=5)
    else:
        # A pidfd cannot signal an unrelated process if the numeric PID is reused.
        descriptor = os.pidfd_open(info['pid'])
        try:
            if process_info(info['pid']) != info:
                raise RuntimeError('Notification owner changed before handover.')
            signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        finally:
            os.close(descriptor)
    print('Stopped the default SwayNC for this Hyprland session; using the Fusion profile.', flush=True)


def stop(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        child.kill(); child.wait()


def serve(instance, root=ROOT, environment=None):
    environment = os.environ if environment is None else environment
    ready = instance/'notifications-ready.json'
    with (instance/'notifications.lock').open('a') as lock, socket.socket(socket.AF_UNIX) as events:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        events.connect(str(instance/'.socket2.sock'))
        events.setblocking(False)
        write_json(ready, {'pid': os.getpid(), 'status': 'starting'})
        stopping = False
        def on_stop(*_):
            nonlocal stopping
            stopping = True
        handlers = {sig: signal.signal(sig, on_stop) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        child = None
        registered = False
        started = 0
        retry_at = 0
        failures = 0
        activation = ActivationPause(environment.get('XDG_RUNTIME_DIR', str(instance)))
        try:
            while not stopping:
                if select.select([events], [], [], .1)[0] and not events.recv(65536):
                    break
                if child is not None:
                    if child.poll() is None:
                        if not registered:
                            if owner_pid() == child.pid and owner_pid(CONTROL) == child.pid:
                                registered = True
                                activation.release()
                                write_json(ready, {'pid': os.getpid(), 'daemon_pid': child.pid, 'status': 'ready'})
                                print('Fusion notifications are ready.', flush=True)
                            elif time.monotonic()-started > 5:
                                stop(child)
                        continue
                    print(f'Notification daemon exited ({child.returncode}); retrying.', flush=True)
                    child = None
                    write_json(ready, {'pid': os.getpid(), 'status': 'starting'})
                    failures += 1
                    retry_at = time.monotonic()+min(2**min(failures-1, 5), 30)
                if time.monotonic() < retry_at:
                    continue
                pid = owner_pid() or owner_pid(CONTROL)
                if pid is not None:
                    info = process_info(pid)
                    if not same_session(info, environment):
                        write_json(ready, {'pid': os.getpid(), 'status': 'external'})
                        print('Keeping the notification server owned by another desktop/session.', flush=True)
                        return 0
                    if uses_profile(info, root) and owner_pid(CONTROL) == pid:
                        write_json(ready, {'pid': os.getpid(), 'daemon_pid': pid, 'status': 'ready'})
                        return 0
                    retire_default(info, environment, activation)
                with log_path(instance, 'swaync.log').open('ab') as log:
                    child = subprocess.Popen(['swaync', '--config', str(root/'swaync/config.json'),
                        '--style', str(root/'swaync/style.css')], stdout=log, stderr=subprocess.STDOUT,
                        env=environment)
                    registered = False
                    started = time.monotonic()
        finally:
            stop(child)
            activation.release()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    return 0


def wait_ready(instance, timeout=8):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            if json.loads((instance/'notifications-ready.json').read_text()).get('status') in ('ready', 'external'):
                return 0
        except (OSError, ValueError):
            pass
        time.sleep(.05)
    print('Notification startup is taking longer than expected; see notification-session.log.', file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-ready', action='store_true')
    args = parser.parse_args()
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not Path(runtime).is_absolute() or not re.fullmatch(r'[A-Za-z0-9_-]+', signature):
        return 1
    instance = Path(runtime)/'hypr'/signature
    if not (instance/'.socket.sock').is_socket():
        return 1
    try:
        return wait_ready(instance) if args.wait_ready else serve(instance)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Notification session: {error}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
