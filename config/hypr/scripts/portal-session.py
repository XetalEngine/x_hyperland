#!/usr/bin/env python3
"""Repair portals activated before graphical login, without changing shared settings."""
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from session_logging import write_json

FRONT = 'org.freedesktop.portal.Desktop'
BACK = 'org.freedesktop.impl.portal.desktop.hyprland'
UNITS = {FRONT: 'xdg-desktop-portal.service', BACK: 'xdg-desktop-portal-hyprland.service'}
EXECUTABLES = {FRONT: 'xdg-desktop-portal', BACK: 'xdg-desktop-portal-hyprland'}
ENV_KEYS = ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'XDG_CURRENT_DESKTOP')
SIGNATURE = re.compile(r'[A-Za-z0-9_-]+')


def run(args):
    return subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=10)


def owner_pid(name):
    result = run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
        '--object-path', '/org/freedesktop/DBus', '--method',
        'org.freedesktop.DBus.GetConnectionUnixProcessID', name])
    if result.returncode and 'org.freedesktop.DBus.Error.NameHasNoOwner' in result.stderr:
        return None
    match = re.fullmatch(r'\(uint32 (\d+),\)\s*', result.stdout)
    if result.returncode or not match:
        raise RuntimeError('Could not identify the portal owner: '+result.stderr.strip())
    return int(match[1])


def process_info(pid):
    try:
        folder = Path('/proc')/str(pid)
        environment = dict(part.decode(errors='replace').split('=', 1)
            for part in (folder/'environ').read_bytes().split(b'\0') if b'=' in part)
        return {'pid': pid, 'uid': folder.stat().st_uid, 'exe': (folder/'exe').readlink().name,
                'environment': {key: environment.get(key, '') for key in ENV_KEYS},
                'started': (folder/'stat').read_text().rsplit(') ', 1)[1].split()[19]}
    except (OSError, IndexError):
        return None


def compositor_alive(runtime, signature):
    if not Path(runtime).is_absolute() or not SIGNATURE.fullmatch(signature):
        return True  # Unknown identity must never authorize a restart.
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(.25)
            stream.connect(str(Path(runtime)/'hypr'/signature/'.socket.sock'))
        return True
    except OSError as error:
        return error.errno not in (errno.ENOENT, errno.ECONNREFUSED)


def disposition(info, name, environment):
    if not info or info['uid'] != os.getuid() or info['exe'] != EXECUTABLES[name]:
        return 'external'
    previous = info['environment']
    if previous.get('XDG_RUNTIME_DIR') != environment.get('XDG_RUNTIME_DIR'):
        return 'external'
    desktop = previous.get('XDG_CURRENT_DESKTOP', '')
    signature = previous.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not any(previous.get(key) for key in ('WAYLAND_DISPLAY', 'DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'XDG_CURRENT_DESKTOP')):
        return 'unbound'
    if desktop and desktop.lower() != 'hyprland':
        return 'external'
    if signature and signature != environment.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return 'external' if compositor_alive(previous['XDG_RUNTIME_DIR'], signature) else 'stale'
    if previous.get('WAYLAND_DISPLAY') == environment.get('WAYLAND_DISPLAY') and (signature or desktop):
        return 'current'
    return 'external'


def inspect_owner(name, environment):
    pid = owner_pid(name)
    if pid is None:
        return None, 'absent'
    info = process_info(pid)
    return info, disposition(info, name, environment)


def property_uint(name, interface, key):
    result = run(['gdbus', 'call', '--session', '--dest', name,
        '--object-path', '/org/freedesktop/portal/desktop', '--method',
        'org.freedesktop.DBus.Properties.Get', interface, key])
    match = re.fullmatch(r'\(<uint32 (\d+)>,\)\s*', result.stdout)
    return int(match[1]) if result.returncode == 0 and match else None


def capabilities(name):
    # Check ownership first: diagnosis must not activate a service too early.
    if owner_pid(name) is None:
        return None
    interface = 'org.freedesktop.'+('portal.ScreenCast' if name == FRONT else 'impl.portal.ScreenCast')
    version = property_uint(name, interface, 'version')
    sources = property_uint(name, interface, 'AvailableSourceTypes')
    return {'version': version, 'sources': sources} if version and sources and sources & 1 else None


def activation_ready(environment):
    result = run(['systemctl', '--user', 'show-environment'])
    if result.returncode:
        raise RuntimeError('Cannot read the portal service environment: '+result.stderr.strip())
    manager = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    # Hyprland publishes these itself. Never export PATH, themes or other
    # profile settings into the shared D-Bus/systemd activation environment.
    return all(environment.get(key) and manager.get(key) == environment[key]
               for key in ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'XDG_CURRENT_DESKTOP'))


def wait_for(predicate, message, timeout=8):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    raise RuntimeError(message)


def start_service(name, previous, environment):
    if not activation_ready(environment):
        raise RuntimeError('The service environment changed; leaving the portal alone.')
    if owner_pid(name) != (previous['pid'] if previous else None):
        raise RuntimeError('The portal owner changed before repair; leaving it alone.')
    result = run(['systemctl', '--user', 'show', UNITS[name], '--property=MainPID', '--value'])
    expected = str(previous['pid']) if previous else '0'
    if result.returncode or result.stdout.strip() != expected:
        raise RuntimeError('The portal is not owned by its expected service; leaving it alone.')
    if previous and (process_info(previous['pid']) != previous or disposition(previous, name, environment) == 'external'):
        raise RuntimeError('The portal process changed before repair; leaving it alone.')
    action = 'restart' if previous else 'start'
    result = run(['systemctl', '--user', action, UNITS[name]])
    if result.returncode:
        raise RuntimeError('Could not '+action+' '+UNITS[name]+': '+result.stderr.strip())
    return {'unit': UNITS[name], 'action': action}


def ensure(environment):
    front, front_state = inspect_owner(FRONT, environment)
    backend, backend_state = inspect_owner(BACK, environment)
    if 'external' in (front_state, backend_state):
        return {'status': 'external', 'frontend': front_state, 'backend': backend_state,
                'message': 'Keeping portals owned by another desktop or an unidentified process.'}
    if front_state == backend_state == 'current':
        front_caps, back_caps = capabilities(FRONT), capabilities(BACK)
        if front_caps and back_caps:
            return {'status': 'ready', 'frontend': front_caps, 'backend': back_caps, 'changes': []}
    wait_for(lambda: activation_ready(environment), 'Hyprland has not published its current service environment; portals were not changed.')
    changes = []
    if backend_state != 'current' or not capabilities(BACK):
        changes.append(start_service(BACK, backend, environment))
    def ready(name):
        _info, state = inspect_owner(name, environment)
        return capabilities(name) if state == 'current' else None
    back_caps = wait_for(lambda: ready(BACK), 'The Hyprland screen-sharing backend did not become ready.')
    if changes or front_state != 'current' or not capabilities(FRONT):
        changes.append(start_service(FRONT, front, environment))
    front_caps = wait_for(lambda: ready(FRONT), 'The desktop portal did not expose monitor screen sharing.')
    return {'status': 'ready', 'frontend': front_caps, 'backend': back_caps, 'changes': changes}


def main():
    environment = dict(os.environ)
    runtime = environment.get('XDG_RUNTIME_DIR', '')
    signature = environment.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if (not Path(runtime).is_absolute() or not SIGNATURE.fullmatch(signature)
            or environment.get('XDG_CURRENT_DESKTOP', '').lower() != 'hyprland'):
        print('Run this check inside the Hyper Fusion desktop.', file=sys.stderr)
        return 1
    instance = Path(runtime)/'hypr'/signature
    if not (instance/'.socket.sock').is_socket() or not compositor_alive(runtime, signature):
        return 1
    with (instance/'portal-session.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            result = ensure(environment)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            result = {'status': 'failed', 'error': str(error)}
        write_json(instance/'portal-session.json', result)
        print(json.dumps(result), flush=True)
        return 0 if result['status'] == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
