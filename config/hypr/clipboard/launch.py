#!/usr/bin/env python3
"""Fast bar/hotkey toggle; leave capture and Qt in the session-owned process."""
import argparse
import os
from pathlib import Path
import socket
import sys


def send(address, *, from_bar=False):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(.3)
            peer.connect(str(address))
            peer.sendall(b'bar\n' if from_bar else b'show\n')
        return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--show', action='store_true')
    parser.add_argument('--from-bar', action='store_true')
    args = parser.parse_args()
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature or '/' in signature:
        return 1
    address = Path(runtime) / 'hypr' / signature / '.clip.sock'
    if not args.serve and send(address, from_bar=args.from_bar):
        return 0
    command = [sys.executable, str(Path(__file__).with_name('app.py')), '--serve']
    if not args.serve or args.show:
        command.append('--show')
    if args.from_bar:
        command.append('--from-bar')
    os.execv(sys.executable, command)


if __name__ == '__main__':
    raise SystemExit(main())
