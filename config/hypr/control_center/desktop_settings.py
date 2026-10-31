"""Validated Hyprland display/input/appearance settings; no shared desktop writes."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import time

import keys
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import monitor_preferences

ROOT = keys.ROOT
STATE = keys.STATE


def command(args, timeout=12):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def ctl(*args):
    return command(['hyprctl', *args])


def monitors():
    return json.loads(ctl('-j', 'monitors', 'all'))


def mode_parts(value):
    match = re.fullmatch(r'(\d+)x(\d+)@([\d.]+)(?:Hz)?', value)
    if not match: raise ValueError('Unrecognized display mode: ' + str(value))
    return int(match[1]), int(match[2]), float(match[3])


def display_models(raw):
    result = []
    for number, item in enumerate(raw, 1):
        modes = list(dict.fromkeys(item.get('availableModes', [])))
        width, height, rate = item.get('width', 0), item.get('height', 0), item.get('refreshRate', 0)
        if not width or not height:
            width, height, rate = mode_parts(modes[0]) if modes else (1920, 1080, 60)
        current = f'{width}x{height}@{rate:.2f}Hz'
        if current not in modes: modes.insert(0, current)
        result.append({'name': item['name'], 'label': item.get('model') or item['name'],
                       'number': number, 'enabled': not item.get('disabled', False),
                       'width': width, 'height': height, 'rate': round(rate, 2),
                       'x': item.get('x', 0), 'y': item.get('y', 0), 'scale': item.get('scale', 1) or 1,
                       'transform': item.get('transform', 0),
                       'mirror': '' if item.get('mirrorOf', 'none') in ('none', '', None) else item['mirrorOf'],
                       'modes': modes, 'bitdepth': 10 if '2101010' in item.get('currentFormat', '') else 8,
                       'vrr': int(bool(item.get('vrr'))), 'cm': item.get('colorManagementPreset', 'srgb')})
    chosen = monitor_preferences.select(raw, 'primary')
    for m in result: m['primary'] = bool(chosen and m['name'] == chosen['name'])
    return result


def layout_state(models):
    fields = ('name', 'enabled', 'width', 'height', 'rate', 'x', 'y', 'scale', 'transform', 'mirror')
    return sorted([{**{k: m[k] for k in fields}, 'primary': m.get('primary', False)} for m in models], key=lambda m: m['name'])


def logical_size(model):
    width, height = model['width'], model['height']
    if model['transform'] % 2: width, height = height, width
    return round(width/model['scale']), round(height/model['scale'])


def normalize(models):
    active = [m for m in models if m['enabled'] and not m['mirror']]
    if not active: return
    left, top = min(m['x'] for m in active), min(m['y'] for m in active)
    for m in models:
        m['x'] -= left; m['y'] -= top


def validate_displays(models, available):
    known = {m['name']: m for m in available}
    if len(models) != len(known) or {m['name'] for m in models} != set(known):
        raise ValueError('Connected displays changed. Reload the display list and try again.')
    active = [m for m in models if m['enabled']]
    if not active: raise ValueError('Keep at least one display enabled.')
    for m in models:
        if not re.fullmatch(r'[A-Za-z0-9_.:-]+', m['name']): raise ValueError('Unsupported display connector name.')
        if not m['enabled']: continue
        if not any(mode_parts(mode)[:2] == (m['width'], m['height']) and abs(mode_parts(mode)[2]-m['rate']) < .03
                   for mode in known[m['name']]['modes']):
            raise ValueError(m['name'] + ': choose a supported resolution and refresh rate.')
        if not math.isfinite(m['scale']) or not .5 <= m['scale'] <= 4:
            raise ValueError('Display scaling must be between 50% and 400%.')
        if m['transform'] not in range(8): raise ValueError('Choose a valid display rotation.')
        if any(not isinstance(m[k], int) or abs(m[k]) > 32000 for k in ('x', 'y')):
            raise ValueError('Display coordinates must be whole numbers between −32000 and 32000.')
        if m['mirror']:
            source = next((s for s in active if s['name'] == m['mirror']), None)
            if source is None or source['mirror'] or source['name'] == m['name']:
                raise ValueError('A mirrored display must use another enabled, extended display as its source.')
    independent = [m for m in active if not m['mirror']]
    if any('primary' in m for m in models):
        chosen = [m for m in models if m.get('primary')]
        if len(chosen) != 1 or chosen[0] not in independent:
            raise ValueError('Choose one enabled, extended display as the primary monitor.')
    for index, a in enumerate(independent):
        aw, ah = logical_size(a)
        for b in independent[index+1:]:
            bw, bh = logical_size(b)
            if max(a['x'], b['x']) < min(a['x']+aw, b['x']+bw) and max(a['y'], b['y']) < min(a['y']+ah, b['y']+bh):
                raise ValueError(f"{a['name']} and {b['name']} overlap. Drag them edge to edge or choose Mirror.")


def monitor_rule(m):
    if not m['enabled']: return m['name'] + ',disable'
    value = f"{m['name']},{m['width']}x{m['height']}@{m['rate']:.2f},{m['x']}x{m['y']},{m['scale']:g},transform,{m['transform']}"
    # Preserve the active output's color/depth/VRR settings when changing geometry.
    value += f",bitdepth,{m.get('bitdepth', 8)},vrr,{m.get('vrr', 0)}"
    cm = m.get('cm', 'srgb')
    if re.fullmatch('[a-zA-Z0-9_-]+', cm): value += ',cm,' + cm
    if m['mirror']: value += ',mirror,' + m['mirror']
    return value


def display_config(models, previous=''):
    names = {m['name'] for m in models}
    # Retain saved outputs that are currently disconnected, and all comments.
    retained = []
    for line in previous.splitlines():
        if line.startswith(monitor_preferences.MARKER): continue
        match = re.match(r'\s*monitor\s*=\s*([^,]+),', line)
        if match and match[1].strip() in names: continue
        if line.strip() and not line.startswith('# Managed'): retained.append(line)
    primary = next((m['name'] for m in models if m.get('primary')), '')
    if primary: retained.append(monitor_preferences.MARKER + primary)
    return '\n'.join(['# Managed by the Hyprland Control desk. Saved only after Keep changes.', *retained,
                      *('monitor = ' + monitor_rule(m) for m in models), ''])


def apply_runtime(models):
    # Enable independent outputs first; mirrors next; disable outputs last.
    for m in sorted(models, key=lambda m: (not m['enabled'], bool(m['mirror']))):
        result = ctl('keyword', 'monitor', monitor_rule(m))
        if result != 'ok': raise ValueError(result)


def matches_layout(wanted, actual):
    actual = {m['name']: m for m in actual}
    if {m['name'] for m in wanted} != set(actual): return False
    for m in wanted:
        a = actual.get(m['name'])
        if a is None or a['enabled'] != m['enabled']: return False
        if not m['enabled']: continue
        if any(a[k] != m[k] for k in ('width', 'height', 'transform', 'mirror')): return False
        if abs(a['rate']-m['rate']) > .1 or abs(a['scale']-m['scale']) > .01: return False
        if not m['mirror'] and any(abs(a[k]-m[k]) > 1 for k in ('x', 'y')): return False
    return True


class Store:
    def __init__(self, name, root=ROOT, state=STATE, runner=command):
        if name not in ('displays', 'input', 'appearance', 'workspaces', 'theme'): raise ValueError('Unknown settings page.')
        self.name, self.root, self.state, self.run = name, Path(root), Path(state), runner
        self.path = self.root/'control_center'/(name+'.conf')
        self.main = self.root/'hyprland.conf'
        self.source = 'source = ~/.config/hypr/control_center/'+name+'.conf'

    def load(self):
        content = self.path.read_text()
        return content, hashlib.sha256((self.main.read_text()+'\0'+content).encode()).hexdigest()

    def check(self, content, expected):
        if self.path.is_symlink() or self.main.is_symlink(): raise ValueError('Settings files must stay inside the Hyprland profile.')
        old, token = self.load()
        if token != expected: raise ValueError('Configuration changed outside this page. Reload before applying.')
        main = self.main.read_text()
        if main.count(self.source) != 1: raise ValueError('The settings source is missing or duplicated in hyprland.conf.')
        with tempfile.TemporaryDirectory(prefix='.settings-check-', dir=self.root) as directory:
            candidate = Path(directory)/'settings.conf'; candidate.write_text(content)
            test = Path(directory)/'hyprland.conf'; test.write_text(main.replace(self.source, 'source = '+str(candidate)))
            result = self.run(['Hyprland', '--verify-config', '--config', str(test)])
            if 'config ok' not in result: raise ValueError('Hyprland rejected the settings:\n'+result[-4000:])
        if self.load()[1] != expected: raise ValueError('Configuration changed during validation. Reload before applying.')
        return old

    def save(self, content, expected):
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state/(self.name+'-save.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            old = self.check(content, expected)
            backup = self.state/(self.name+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'.conf')
            backup.write_text(old); backup.chmod(0o600)
            keys.atomic_write(self.path, content.encode())
            try:
                if self.run(['hyprctl', 'reload']) != 'ok': raise ValueError('Hyprland could not reload the settings.')
                error = self.run(['hyprctl', 'configerrors'])
                if error: raise ValueError(error)
            except Exception:
                if self.path.read_text() == content:
                    keys.atomic_write(self.path, old.encode()); self.run(['hyprctl', 'reload'])
                raise
            return self.load()[1]


def read_options(names):
    result = {}
    for name in names:
        item = json.loads(ctl('-j', 'getoption', name))
        result[name] = next((item[k] for k in ('int', 'float', 'str', 'custom') if k in item), '')
        if result[name] == '[[EMPTY]]': result[name] = ''
    return result


def option_config(previous, changes):
    # Replace only edited keys; leave unrelated per-page settings and comments intact.
    lines = []
    for line in previous.splitlines():
        key = line.split('=', 1)[0].strip()
        if key not in changes: lines.append(line)
    for key, value in changes.items():
        if not re.fullmatch(r'[a-z_:][-a-z_0-9:]*', key) or any(c in str(value) for c in '\n\r\0#;{}'):
            raise ValueError('Invalid setting value.')
        if isinstance(value, bool): value = 'true' if value else 'false'
        lines.append(f'{key} = {value}')
    return '\n'.join(lines).rstrip()+'\n'
