#!/usr/bin/env python3
"""Create one persistent empty workspace on the bar's own monitor."""
import argparse
import fcntl
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'control_center'))
import desktop_settings as settings


def monitor_at(models, x, y):
    for m in models:
        width, height = settings.logical_size(m)
        if m['enabled'] and not m['mirror'] and m['x'] <= x < m['x']+width and m['y'] <= y < m['y']+height:
            return m['name']
    raise ValueError('This display disconnected. Try the + button on a connected display.')


def next_id(workspaces, rules):
    used = {w['id'] for w in workspaces}
    used.update(int(n) for n in re.findall(r'^\s*workspace\s*=\s*(\d+)\s*,', rules, re.M))
    number = 1
    while number in used: number += 1
    return number


def create(x, y):
    store = settings.Store('workspaces')
    store.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (store.state/'new-workspace.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous, token = store.load()
        target = monitor_at(settings.display_models(settings.monitors()), x, y)
        workspaces = json.loads(settings.ctl('-j', 'workspaces'))
        # Include configured workspace rules, including empty persistent ones.
        rules = previous + '\n' + store.main.read_text()
        for rule in json.loads(settings.ctl('-j', 'workspacerules')):
            name = str(rule.get('workspaceString', ''))
            if name.isdecimal(): rules += '\nworkspace = '+name+', reserved\n'
        number = next_id(workspaces, rules)
        content = previous.rstrip() + f'\nworkspace = {number}, monitor:{target}, persistent:true\n'
        store.save(content, token)
        result = settings.ctl('--batch', f'dispatch focusmonitor {target}; dispatch workspace {number}')
        if any(line.strip() != 'ok' for line in result.splitlines() if line.strip()): raise ValueError(result)
        return number, target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('x', type=int); parser.add_argument('y', type=int)
    args = parser.parse_args()
    try: print(json.dumps(create(args.x, args.y)))
    except Exception as exc:
        subprocess.run(['notify-send', '-a', 'Hyprland', 'Could not add workspace', str(exc)])
        raise SystemExit(1)
