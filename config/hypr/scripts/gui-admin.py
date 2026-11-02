#!/usr/bin/env python3
"""Run one authenticated command; lease root's access to this X display.

Leases are shared by concurrent launches. The last launcher removes only the
permission we added, never a pre-existing grant. No global environment changes.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def process_token(pid):
    try:
        # starttime disambiguates PID reuse; comm may itself contain spaces.
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def xhost(*arguments):
    result = subprocess.run(['xhost', *arguments], capture_output=True, text=True,
                            timeout=4, env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'Cannot authorize this display.').strip())
    return result.stdout


class DisplayLease:
    def __init__(self, directory=None):
        runtime = Path(os.environ.get('XDG_RUNTIME_DIR') or Path.home()/'.cache')
        self.directory = Path(directory) if directory else runtime/'xetal-admin-display'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError('The graphical administrator runtime folder is not private.')
        identity = os.environ.get('DISPLAY', '') + '\n' + os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
        name = hashlib.sha256(identity.encode()).hexdigest()[:24]
        self.path = self.directory/(name+'.json')
        self.lock = self.directory/(name+'.lock')
        self.token = [os.getpid(), process_token(os.getpid())]

    @contextmanager
    def locked(self):
        fd = os.open(self.lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def read(self):
        try:
            state = json.loads(self.path.read_text())
        except (OSError, ValueError):
            state = {'owned': False, 'clients': []}
        state['clients'] = [client for client in state['clients']
                            if client[1] is not None and process_token(client[0]) == client[1]]
        return state

    def write(self, state):
        temporary = self.path.with_suffix('.new')
        temporary.write_text(json.dumps(state))
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def __enter__(self):
        with self.locked():
            state = self.read()
            access = xhost()
            allowed = 'SI:localuser:root' in {line.strip() for line in access.splitlines()}
            if not allowed and 'access control disabled' not in access:
                xhost('+SI:localuser:root')
                state['owned'] = True
            state['clients'].append(self.token)
            self.write(state)
        return self

    def __exit__(self, *_):
        with self.locked():
            state = self.read()
            state['clients'] = [client for client in state['clients'] if client != self.token]
            if state['clients']:
                self.write(state)
            else:
                if state['owned']:
                    xhost('-SI:localuser:root')
                self.path.unlink(missing_ok=True)


@contextmanager
def display_session():
    """Repair only this compositor's verified socket before authorizing it."""
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        yield None
        return
    spec = importlib.util.spec_from_file_location('xwayland_session', ROOT/'xwayland-session.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with module.session(module.instance_path()) as (events, compositor):
        number = module.display_number(os.environ['DISPLAY'])
        status, detail = module.recover(number, compositor, repair=True)
        if status not in ('healthy', 'recovered'):
            raise RuntimeError(detail)
        yield lambda: module.connected(events)


def command(arguments):
    options = []
    if not sys.stdin.isatty() and os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        os.environ['SUDO_ASKPASS'] = str(ROOT/'sudo-askpass.sh')
        options.append('--askpass')
    if os.environ.get('DISPLAY'):
        # Avoid handing bundled Qt applications the session's binary plugins.
        # Root GUI apps use XWayland and their own normal theme/plugin defaults.
        return ['sudo', *options, '--preserve-env=DISPLAY,XAUTHORITY', '--',
                'env', '-u', 'QT_PLUGIN_PATH', '-u', 'QT_QPA_PLATFORMTHEME',
                '-u', 'QT_STYLE_OVERRIDE', '-u', 'WAYLAND_DISPLAY',
                'QT_QPA_PLATFORM=xcb', *arguments]
    return ['sudo', *options, '--', *arguments]


def run(arguments, connected=None):
    child = subprocess.Popen(command(arguments))
    previous = {}
    def stop(signum, _frame):
        if child.poll() is None:
            child.send_signal(signum)
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, stop)
    try:
        while True:
            try:
                return child.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                if connected is not None and not connected():
                    child.terminate()
                    return child.wait(timeout=5)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(arguments):
    if not arguments:
        print('Usage: xsudo.sh command [arguments...]', file=sys.stderr)
        return 2
    try:
        if not os.environ.get('DISPLAY'):
            return run(arguments)
        with display_session() as connected, DisplayLease():
            return run(arguments, connected)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('Administrator launch: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
