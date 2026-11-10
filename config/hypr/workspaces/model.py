"""Persistent workspace overrides, independent of app and window preferences."""
import copy
import hashlib
import json
from pathlib import Path

from effects.window_close import rules

PATH = Path(__file__).with_name('rules.json')
LAYOUTS = {'off': 'Individual', 'tile': 'Force tiling', 'floating': 'Force floating', 'kde': 'KDE mode'}
CONTROLS = {'individual': 'Individual', 'on': 'On', 'off': 'Off'}
DEFAULT = dict(layout='off', controls='individual', rule=dict(rules.DEFAULTS, mode='always'))


def identity(value):
    key = str(value)
    if not key.isascii() or not key.isdecimal() or str(int(key)) != key or not 1 <= int(key) <= 2147483647:
        raise ValueError('Choose a numbered workspace.')
    return key


def validate(data):
    if not isinstance(data, dict) or set(data) != {'version', 'workspaces'} or type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Unsupported workspace settings file.')
    entries = data['workspaces']
    if not isinstance(entries, dict) or len(entries) > 512: raise ValueError('Invalid workspace settings.')
    result = copy.deepcopy(data)
    for key, item in entries.items():
        identity(key)
        if not isinstance(item, dict) or set(item) != {'layout', 'controls', 'rule'}:
            raise ValueError('Incomplete workspace settings.')
        if not isinstance(item['layout'], str) or not isinstance(item['controls'], str) or item['layout'] not in LAYOUTS or item['controls'] not in CONTROLS:
            raise ValueError('Unknown workspace mode.')
        result['workspaces'][key]['rule'] = rules.validate(item['rule'])
        if item['rule']['mode'] != 'always': raise ValueError('Workspace controls use the On / Off menu for visibility.')
    return result


def load(path=None):
    path = PATH if path is None else path
    raw = path.read_bytes() if path.exists() else b''
    if len(raw) > 1024*1024: raise ValueError('Workspace settings file is too large.')
    return validate(json.loads(raw) if raw else {'version': 1, 'workspaces': {}}), hashlib.sha256(raw).hexdigest()


def effective(data, workspace):
    return copy.deepcopy(data['workspaces'].get(identity(workspace), DEFAULT))


def encode(data): return json.dumps(validate(data), indent=2)+'\n'
