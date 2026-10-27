#!/usr/bin/env python3
"""Force-kill the app under the pointer without changing keyboard focus."""
import argparse
import json
import re
import subprocess


def ctl(*args):
    result = subprocess.run(['hyprctl', *args], capture_output=True, text=True,
                            timeout=4, check=True)
    return result.stdout.strip()


def contains(x, y, left, top, width, height):
    return left <= x < left + width and top <= y < top + height


def target_at(cursor, monitors, clients, layers):
    x, y = cursor['x'], cursor['y']
    monitor = None
    for item in monitors:
        if item.get('disabled'):
            continue
        width, height = item['width'], item['height']
        if item.get('transform', 0) % 2:
            width, height = height, width
        if contains(x, y, item['x'], item['y'], width / item['scale'], height / item['scale']):
            monitor = item
            break
    if monitor is None:
        return None

    # Top/overlay surfaces (bar, notifications, menus) are not app windows.
    # Do not kill an application behind one of those surfaces.
    levels = layers.get(monitor['name'], {}).get('levels', {})
    for level in ('2', '3'):
        for layer in levels.get(level, []):
            if contains(x, y, layer['x'], layer['y'], layer['w'], layer['h']):
                return None

    special = monitor.get('specialWorkspace', {}).get('id', 0)
    workspace = special or monitor['activeWorkspace']['id']
    candidates = []
    for client in clients:
        if not client.get('mapped') or client.get('hidden'):
            continue
        if client.get('workspace', {}).get('id') != workspace and not client.get('pinned'):
            continue
        if contains(x, y, *client['at'], *client['size']):
            candidates.append(client)
    if not candidates:
        return None

    def recency(client):
        value = client.get('focusHistoryID', -1)
        return value if value >= 0 else 1_000_000

    # Fullscreen covers older floating windows. A floating dialog focused after
    # the fullscreen window can be above it, as can a pinned window.
    fullscreen = [c for c in candidates if c.get('fullscreen', 0) >= 2]
    if fullscreen:
        front = min(fullscreen, key=recency)
        candidates = [c for c in candidates if c is front or c.get('pinned') or
                      (c.get('floating') and recency(c) < recency(front))]
    return max(candidates, key=lambda c: (c.get('workspace', {}).get('id') == special,
                                          bool(c.get('floating')), -recency(c)))


def snapshot():
    return tuple(json.loads(ctl('-j', query)) for query in ('cursorpos', 'monitors', 'clients', 'layers'))


def identity(client):
    address, pid = client.get('address', ''), client.get('pid', 0)
    if not re.fullmatch(r'0x[0-9a-fA-F]+', address) or int(address, 16) == 0 or not isinstance(pid, int) or pid <= 1:
        raise ValueError('The hovered application has no valid window/process identity.')
    return address, pid


def force_kill(dry_run=False):
    target = target_at(*snapshot())
    if target is None:
        return None
    address, pid = identity(target)
    if dry_run:
        return target
    # A window may close, move, or be covered while the IPC queries run.
    current = target_at(*snapshot())
    if current is None or identity(current) != (address, pid):
        return None
    # An explicit address never falls back to the focused window. The compositor
    # resolves the app process for both Wayland and XWayland windows.
    result = ctl('dispatch', 'signalwindow', f'address:{address},9')
    if result != 'ok':
        raise RuntimeError(result or 'The compositor could not force-kill this application.')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Print the target without closing anything.')
    args = parser.parse_args()
    try:
        target = force_kill(args.dry_run)
        if args.dry_run:
            print(json.dumps({k: target.get(k) for k in ('address', 'pid', 'class')} if target else None))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        subprocess.run(['notify-send', '-a', 'Xetal', 'Could not force-kill application', str(error)], check=False)
        raise SystemExit(1)
