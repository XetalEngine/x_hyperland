#!/usr/bin/env python3
"""Small subprocess interface for the native Waybar pin widget."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import catalog
import pins


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['list', 'launch', 'terminal', 'edit', 'unpin', 'move', 'left', 'right'])
    parser.add_argument('app_id', nargs='?')
    parser.add_argument('target', nargs='?')
    parser.add_argument('side', nargs='?', choices=['before', 'after'])
    args = parser.parse_args()
    if args.action == 'list':
        print(json.dumps(pins.entries(catalog.applications()), ensure_ascii=False))
        return 0
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        raise ValueError('Bar actions belong to the Hyprland session.')
    if not args.app_id:
        parser.error('an application ID is required')
    if args.action == 'unpin':
        pins.pin(args.app_id, False)
    elif args.action == 'move':
        pins.move(args.app_id, args.target, args.side == 'after')
    elif args.action in ('left', 'right'):
        pins.step(args.app_id, -1 if args.action == 'left' else 1)
    elif args.action == 'edit':
        subprocess.Popen([str(catalog.ROOT/'scripts/launcher.sh'), '--edit', args.app_id], start_new_session=True)
    else:
        from app import leave_dashboard
        entry = catalog.applications().get(args.app_id)
        if entry is None:
            raise ValueError('The pinned application is no longer installed.')
        leave_dashboard()
        entry.launch(terminal=True if args.action == 'terminal' else None)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
            subprocess.run(['notify-send', '-a', 'Xetal bar', 'Could not update or open this pin', str(exc)], check=False)
        raise SystemExit(1)
