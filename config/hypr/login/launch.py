#!/usr/bin/python3
"""Start the selected installed desktop only after greetd authenticates its user."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
if __package__:
    from .model import sessions, session_environment
else:
    from model import sessions, session_environment


def main():
    # greetd/PAM may not supply PATH. execvp finds programs using its fallback,
    # but the desktop's children (notably Python) also need an exported path.
    if not os.environ.get('PATH'):
        os.environ['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--x11-client', action='store_true')
    parser.add_argument('--with-bus', action='store_true')
    args = parser.parse_args()
    session = next((s for s in sessions() if s.identifier == args.session), None)
    if session is None: raise RuntimeError('The selected desktop session is no longer installed.')
    os.environ.update(item.split('=', 1) for item in session_environment(session))
    if args.x11_client:
        os.execvp(session.command[0], session.command)
    runtime = os.environ.get('XDG_RUNTIME_DIR', '/run/user/'+str(os.getuid()))
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        if (Path(runtime)/'bus').exists():
            os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path='+runtime+'/bus'
        elif not args.with_bus:
            os.execvp('dbus-run-session', ['dbus-run-session', '--', sys.executable, __file__,
                                         '--session', args.session, '--with-bus'])
    # Reload newly installed activation units; PAM has already received the login password.
    subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True, timeout=10)
    keyring = shutil.which('gnome-keyring-daemon')
    if keyring:
        result = subprocess.run([keyring, '--start', '--components=secrets'], capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            key, separator, value = line.partition('=')
            if separator and key == 'GNOME_KEYRING_CONTROL': os.environ[key] = value.rstrip(';')
    if session.kind == 'wayland': os.execvp(session.command[0], session.command)
    if not shutil.which('startx'): raise RuntimeError('Install xinit to start an X11 desktop.')
    display = next(number for number in range(64) if not (Path('/tmp')/f'.X{number}-lock').exists()
                   and not (Path('/tmp/.X11-unix')/f'X{number}').exists())
    vt = os.environ.get('XDG_VTNR', '1')
    if not vt.isdigit(): raise RuntimeError('Missing virtual console for the X11 session.')
    os.execvp('startx', ['startx', str(Path(__file__).resolve()), '--session', args.session, '--x11-client',
                         '--', ':'+str(display), 'vt'+vt, '-keeptty', '-nolisten', 'tcp'])


if __name__ == '__main__':
    try: main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('Fusion desktop session: '+str(error), file=sys.stderr)
        raise SystemExit(1)
