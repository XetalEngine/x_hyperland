#!/usr/bin/env python3
"""Run only the login applications explicitly saved in this Hyprland profile."""
import argparse
import fcntl
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def environment_values(path):
    if not path.is_file():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or '\0' in value:
            raise ValueError('Invalid environment entry: ' + key)
        result[key] = value
    return result


def entry_command(path, automatic=True):
    sys.path.insert(0, str(ROOT/'launcher'))
    from gi.repository import Gio
    from shortcuts import command_argv, fields_for
    info = Gio.DesktopAppInfo.new_from_filename(str(path))
    if info is None:
        raise ValueError('Invalid desktop entry or missing executable: ' + path.name)
    if automatic:
        only = (info.get_string('OnlyShowIn') or '').split(';')
        excluded = (info.get_string('NotShowIn') or '').split(';')
        if (info.get_boolean('Hidden') or 'Hyprland' in excluded
                or any(only) and 'Hyprland' not in only
                or info.get_string('X-GNOME-Autostart-enabled') == 'false'):
            return None
    fields = fields_for(info)
    argv = command_argv(fields['command'], fields, str(path))
    if fields['terminal']:
        argv = ['kitty', '--config', str(ROOT/'kitty.conf'), '--title', fields['name'], '-e', *argv]
    elif Path(argv[0]).name == 'dolphin':
        argv[0] = str(ROOT/'scripts/dolphin.sh')
    return argv, fields['directory'] or None


def launch(path, automatic=True):
    command = entry_command(path, automatic)
    if command is None:
        return None
    sys.path.insert(0, str(ROOT/'theme'))
    import runtime
    return subprocess.Popen(command[0], cwd=command[1], env=runtime.environment(), start_new_session=True)


def session():
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not runtime_dir:
        return 1
    instance = Path(runtime_dir)/'hypr'/signature
    with (instance/'panel-startup.lock').open('a') as lock, socket.socket(socket.AF_UNIX) as connection:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        connection.connect(str(instance/'.socket2.sock'))
        children = []
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        for event in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(event, stop)
        try:
            values = environment_values(ROOT/'control_panel/state/environment.env')
            for key, value in values.items():
                # argv is literal: environment values are never evaluated as shell code.
                subprocess.run(['hyprctl', 'keyword', 'env', key+','+value], check=True, timeout=4)
            os.environ.update(values)
            for path in sorted((ROOT/'control_panel/state/autostart').glob('*.desktop')):
                if stopping:
                    break
                try:
                    child = launch(path)
                    if child is not None:
                        children.append(child)
                except (OSError, ValueError) as error:
                    print(str(error), file=sys.stderr)
            while not stopping:
                if select.select([connection], [], [], 0.5)[0] and not connection.recv(65536):
                    break
        finally:
            for child in children:
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
    return 0


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--session', action='store_true')
    mode.add_argument('--run', type=Path)
    args = parser.parse_args()
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return 1
    if args.run:
        launch(args.run, automatic=False)
        return 0
    return session()


if __name__ == '__main__':
    raise SystemExit(main())
