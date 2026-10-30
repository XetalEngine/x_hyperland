#!/usr/bin/env python3
"""Small IPC clients: a warm UI click must not import Qt or rebuild its theme."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]


def contact(endpoint, request):
    directory, signature = os.environ.get('XDG_RUNTIME_DIR'), os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not directory or not signature: return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(.15)
            peer.connect(str(Path(directory) / 'hypr' / signature / endpoint))
            peer.sendall(json.dumps(request).encode() + b'\n')
        return True
    except OSError: return False


def main():
    kind, *arguments = sys.argv[1:]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--preload', action='store_true'); parser.add_argument('--preview')
    if kind == 'panel':
        parser.add_argument('--section', default='')
        args, unknown = parser.parse_known_args(arguments)
        if not args.preview and not unknown and contact('.xpanel.sock', {'section': args.section, 'preload': args.preload}): return 0
        command = [sys.executable, str(ROOT / 'control_panel/launch.py'), *arguments]
    elif kind == 'kvm':
        if not arguments and contact('kvm-settings.sock', {}): return 0
        command = [sys.executable, str(ROOT / 'theme/run.py'), sys.executable, str(ROOT / 'kvm/app.py'), *arguments]
    else:
        if kind == 'theme':
            parser.add_argument('filename', nargs='?', default='')
            args, unknown = parser.parse_known_args(arguments)
            if args.preview or unknown:
                command = [sys.executable, str(ROOT / 'theme/run.py'), sys.executable, str(ROOT / 'wallpaper/app.py'), *arguments]
                os.execv(command[0], command)
            arguments = ['--tab', 'theme'] + (['--wallpaper', args.filename] if args.filename else []) + (['--preload'] if args.preload else [])
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--tab', default='hotkeys'); parser.add_argument('--wallpaper', default='')
        parser.add_argument('--window-hints', action='store_true'); parser.add_argument('--preload', action='store_true'); parser.add_argument('--preview')
        args, unknown = parser.parse_known_args(arguments)
        request = {'tab': 'window-hints' if args.window_hints else args.tab, 'wallpaper': args.wallpaper, 'preload': args.preload}
        if not args.preview and not unknown and contact('control-center.sock', request): return 0
        command = [sys.executable, str(ROOT / 'theme/run.py'), sys.executable, str(ROOT / 'control_center/app.py'), *arguments]
    os.execv(command[0], command)


if __name__ == '__main__': raise SystemExit(main())
