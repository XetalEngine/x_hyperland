#!/usr/bin/env python3
"""Forget an empty numbered workspace without closing or moving any windows."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'control_center'))
import desktop_settings as settings


def snapshot():
    return (json.loads(settings.ctl('-j', 'workspaces')),
            json.loads(settings.ctl('-j', 'clients')),
            settings.monitors())


def removal_target(number, monitor, workspaces, clients, monitors):
    if number < 1:
        raise ValueError('Only numbered workspaces can be removed here.')
    target = next((w for w in workspaces if w['id'] == number), None)
    if target is None:
        return None, None
    if target['monitor'] != monitor or target['name'] != str(number):
        raise ValueError('That workspace changed. Try its button again.')
    if target.get('windows', 0) or any(c.get('workspace', {}).get('id') == number for c in clients):
        raise ValueError('This workspace has open windows. Move or close them first.')
    output = next((m for m in monitors if m['name'] == monitor and not m.get('disabled')), None)
    if output is None:
        raise ValueError('This display disconnected.')
    siblings = [w for w in workspaces if w['monitor'] == monitor and w['id'] > 0 and w['id'] != number]
    if not siblings:
        raise ValueError('Keep at least one workspace on this display.')
    active = output.get('activeWorkspace', {}).get('id')
    fallback = min(siblings, key=lambda w: (w['id'] != active, abs(w['id']-number), w['id']))
    return target, fallback if active == number else None


def removal_config(content, number):
    """Remove our simple + rule; retain any unrelated options and comments."""
    lines, found = [], False
    pattern = re.compile(r'^(\s*workspace\s*=\s*)' + str(number) + r'\s*,(.*)$')
    for line in content.splitlines():
        body, separator, comment = line.partition('#')
        match = pattern.match(body)
        if not match:
            lines.append(line)
            continue
        found = True
        options = [o.strip() for o in match[2].split(',') if o.strip()]
        other = [o for o in options if not o.startswith(('monitor:', 'persistent:'))]
        if other:
            options = [o for o in options if not o.startswith('persistent:')]
            lines.append(match[1] + str(number) + ', ' + ', '.join([*options, 'persistent:false'])
                         + (' #' + comment if separator else ''))
        elif separator:
            lines.append('#' + comment)
    # A workspace made persistent elsewhere needs a local override; never edit
    # another source file or remove its monitor/layout/default settings.
    if not found:
        lines.append(f'workspace = {number}, persistent:false')
    return '\n'.join(lines).rstrip()+'\n'


def monitor_at(monitors, x, y):
    for model in settings.display_models(monitors):
        width, height = settings.logical_size(model)
        if model['enabled'] and not model['mirror'] and model['x'] <= x < model['x']+width and model['y'] <= y < model['y']+height:
            return model['name']
    raise ValueError('This display disconnected. Try a connected display.')


def remove(number, x, y):
    store = settings.Store('workspaces')
    store.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Serialize + and × so a new workspace cannot reuse an ID mid-transaction.
    with (store.state/'new-workspace.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous, token = store.load()
        workspaces, clients, monitors = snapshot()
        monitor = monitor_at(monitors, x, y)
        target, _ = removal_target(number, monitor, workspaces, clients, monitors)
        if target is None:
            return number
        content = removal_config(previous, number) if target.get('ispersistent') else previous
        if content != previous:
            store.check(content, token)
        # Check again after validation. The bar's empty indicator can be stale.
        removal_target(number, monitor, *snapshot())
        saved = store.save(content, token) if content != previous else None
        try:
            target, fallback = removal_target(number, monitor, *snapshot())
            if target is None:
                return number
            if target.get('ispersistent'):
                # Fail closed when another source still pins this workspace.
                raise ValueError('Another workspace rule keeps this workspace persistent.')
            if fallback:
                result = settings.ctl('--batch', f'dispatch focusmonitor {monitor}; dispatch workspace {fallback["id"]}')
                if any(line.strip() != 'ok' for line in result.splitlines() if line.strip()):
                    raise ValueError(result)
            for _ in range(30):
                current = json.loads(settings.ctl('-j', 'workspaces'))
                if all(w['id'] != number for w in current):
                    return number
                time.sleep(.05)
            raise ValueError('The workspace is still in use. Its saved settings were kept.')
        except Exception:
            if saved is not None:
                store.save(previous, saved)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('number', type=int)
    parser.add_argument('x', type=int)
    parser.add_argument('y', type=int)
    args = parser.parse_args()
    try:
        print(json.dumps({'removed': remove(args.number, args.x, args.y)}))
    except Exception as exc:
        subprocess.run(['notify-send', '-a', 'Xetal', 'Could not remove workspace', str(exc)])
        raise SystemExit(1)
