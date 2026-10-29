"""Validated desktop menu documents. Reading and previewing never run actions."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'desktop_menu' / 'config.json'
KINDS = {'action': 'Shortcut', 'submenu': 'Submenu', 'heading': 'Section title',
         'separator': 'Divider', 'spacer': 'Spacer', 'column': 'Column split'}
TARGETS = {'file_manager': 'File Manager', 'wallpaper': 'Wallpaper', 'displays': 'Display Settings',
           'control_desk': 'Fusion Settings', 'menu_settings': 'Context Menu settings',
           'apps': 'Apps menu', 'terminal': 'Kitty terminal', 'application': 'Installed application',
           'command': 'Custom command', 'folder': 'Open folder', 'url': 'Open website'}
LIMITS = {'width': (180, 640), 'row_height': (28, 96), 'icon_size': (12, 48),
          'font_size': (10, 24), 'padding': (0, 24), 'rounding': (0, 32),
          'accent_width': (0, 20), 'opacity': (60, 100)}
CUSTOM_COLORS = {'background': '#1a2a3c', 'background_end': '#111d2c', 'text': '#e6edf8',
                 'hover': '#294953', 'hover_text': '#bdfff0', 'border': '#5b9fa6',
                 'accent': '#68dece', 'divider': '#3c5368'}
DEFAULT_STYLE = {'width': 260, 'row_height': 44, 'icon_size': 22, 'font_size': 13,
                 'padding': 7, 'rounding': 12, 'accent_width': 4, 'opacity': 98,
                 'font_family': 'Noto Sans', 'show_icons': True, 'show_hotkeys': True,
                 'shadow': True, 'palette': 'system', **CUSTOM_COLORS}


def new_item(kind='action', **values):
    item = {'id': uuid.uuid4().hex, 'kind': kind, 'label': KINDS[kind], 'enabled': True,
            'icon': 'application-x-executable', 'target': 'command', 'value': '',
            'directory': '', 'terminal': False, 'hold': True, 'shell': False,
            'height': 12, 'children': []}
    item.update(values)
    return item


def defaults():
    return {'version': 1, 'enabled': True, 'style': copy.deepcopy(DEFAULT_STYLE), 'items': [
        new_item(id='file-manager', label='File Manager', icon='system-file-manager', target='file_manager'),
        new_item(id='wallpaper', label='Wallpaper', icon='preferences-desktop-wallpaper', target='wallpaper'),
        new_item(id='displays', label='Display Settings', icon='preferences-desktop-display', target='displays')]}


def walk(items, enabled=True):
    for item in items:
        active = enabled and item.get('enabled', True)
        yield item, active
        yield from walk(item.get('children', []), active)


def find(config, ident, active=False):
    return next((item for item, enabled in walk(config['items'], config['enabled'])
                 if item['id'] == ident and (enabled or not active)), None)


def validate(config):
    if not isinstance(config, dict) or type(config.get('version')) is not int or config['version'] != 1:
        raise ValueError('Choose a version 1 Xetal context menu preset.')
    if type(config.get('enabled')) is not bool or not isinstance(config.get('style'), dict):
        raise ValueError('The menu settings are incomplete.')
    style = config['style']
    for key, (low, high) in LIMITS.items():
        if type(style.get(key)) is not int or not low <= style[key] <= high:
            raise ValueError(f'{key.replace("_", " ").title()} must be between {low} and {high}.')
    for key in ('show_icons', 'show_hotkeys', 'shadow'):
        if type(style.get(key)) is not bool:
            raise ValueError(f'{key} must be enabled or disabled.')
    if style.get('palette') not in ('system', 'custom'):
        raise ValueError('Choose System theme or Custom colors.')
    if not isinstance(style.get('font_family'), str) or not re.fullmatch(r'[\w .,-]{1,100}', style['font_family']):
        raise ValueError('Enter a font family name.')
    for key in CUSTOM_COLORS:
        if not isinstance(style.get(key), str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', style[key]):
            raise ValueError(f'Choose a valid {key.replace("_", " ")} color.')
    ids = set()
    def check(items, depth=0):
        if not isinstance(items, list) or (items and depth > 4):
            raise ValueError('Menus support up to four nested submenus.')
        columns = 1
        for item in items:
            if not isinstance(item, dict) or item.get('kind') not in KINDS:
                raise ValueError('Unknown menu item type.')
            ident = item.get('id')
            if not isinstance(ident, str) or not re.fullmatch(r'[\w-]{1,64}', ident) or ident in ids:
                raise ValueError('Every menu item needs a unique ID.')
            ids.add(ident)
            if len(ids) > 200:
                raise ValueError('A menu can contain up to 200 items.')
            for key in ('label', 'icon', 'value', 'directory'):
                value = item.get(key)
                if not isinstance(value, str) or len(value) > 8192 or any(c in value for c in '\r\n\0'):
                    raise ValueError(f'{key.title()} must be a single line of text.')
            for key in ('enabled', 'terminal', 'hold', 'shell'):
                if type(item.get(key)) is not bool:
                    raise ValueError(f'{key.title()} must be enabled or disabled.')
            if item['kind'] in ('action', 'submenu', 'heading') and not item['label'].strip():
                raise ValueError('Give each shortcut, submenu and section a name.')
            if type(item.get('height')) is not int or not 2 <= item['height'] <= 96:
                raise ValueError('Spacer height must be between 2 and 96 pixels.')
            if item['kind'] == 'column':
                columns += 1
                if columns > 4:
                    raise ValueError('Use up to four columns in each menu.')
            if item['kind'] == 'action':
                if item.get('target') not in TARGETS:
                    raise ValueError('Choose an action for '+item['label']+'.')
                if item['target'] in ('command', 'application', 'folder', 'url') and not item['value'].strip():
                    raise ValueError('Choose a destination for '+item['label']+'.')
                if item['target'] == 'command' and not item['shell']:
                    if not shlex.split(item['value']):
                        raise ValueError('Enter a command for '+item['label']+'.')
                if item['target'] == 'url' and not re.match(r'https?://\S+$', item['value']):
                    raise ValueError('Website addresses must start with https:// or http://.')
            children = item.get('children')
            if item['kind'] != 'submenu' and children:
                raise ValueError('Only submenus can contain other items.')
            check(children, depth+1)
    check(config.get('items'))
    return copy.deepcopy(config)


def decode(data):
    if len(data) > 1024 * 1024:
        raise ValueError('Menu preset is too large (maximum 1 MiB).')
    return validate(json.loads(data.decode('utf-8-sig')))


def read_preset(path):
    with Path(path).open('rb') as stream:
        return decode(stream.read(1024 * 1024 + 1))


def encode(config):
    return (json.dumps(validate(config), ensure_ascii=False, indent=2)+'\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else 'missing'


def atomic_write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Store:
    def __init__(self, path=CONFIG, state=Path.home()/'.local/state/hyprland-control'):
        self.path, self.state = Path(path), Path(state)

    def load(self):
        data = self.path.read_bytes() if self.path.exists() else None
        return (decode(data) if data is not None else defaults()), digest(data)

    def save(self, config, expected):
        data = encode(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent/'menu-save.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.is_symlink():
                raise ValueError('The menu configuration is a symlink; nothing was overwritten.')
            old = self.path.read_bytes() if self.path.exists() else None
            if digest(old) != expected:
                raise ValueError('The menu changed elsewhere. Reload before saving to keep those edits.')
            if old is not None:
                self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
                backup = self.state/('context-menu-'+stamp+'.json')
                backup.write_bytes(old); backup.chmod(0o600)
            atomic_write(self.path, data)
        return digest(data)

    def export(self, path, config):
        if Path(path).resolve() == self.path.resolve():
            raise ValueError('Use Apply changes to update the active menu. Choose another preset file.')
        atomic_write(Path(path), encode(config))
