"""Profile-local minimize preferences; effects can be extended without changing the handler."""
import hashlib
import re
from pathlib import Path

SHAPES = {'random': 'Random per window', 'bloom': 'Bloom', 'star': 'Starburst',
          'spill': 'Spill', 'claw': 'Tendrils', 'wide': 'Wide splash', 'coral': 'Coral',
          'web': 'Webbed splash', 'droplets': 'Heavy droplets'}
SURFACES = {'slime': 'Living slime', 'membrane': 'Alien membrane', 'paint': 'Glossy paint'}
EDGES = {'left': 'Left', 'right': 'Right'}
ORDERS = {'bottom-to-top': 'Bottom to top', 'top-to-bottom': 'Top to bottom'}
DEFAULTS = dict(enabled=True, effect='fireball', duration=420, size=76,
                follow_theme=True, color='#39a9ff', shape='random', speed=100, bubbles=70, surface='slime',
                edge='left', order='bottom-to-top')
RANGES = dict(duration=(150, 1200), size=(48, 160), speed=(25, 200), bubbles=(0, 100))
LEGACY = {'enabled', 'effect', 'duration', 'size'}
PATH = Path(__file__).resolve().with_name('settings.conf')


def validate(values):
    if set(values) != set(DEFAULTS):
        raise ValueError('Minimize settings are incomplete or contain unknown options.')
    if any(type(values[key]) is not bool for key in ('enabled', 'follow_theme')):
        raise ValueError('Invalid Minimize switch.')
    if values['effect'] not in ('fireball', 'splat') or not isinstance(values['shape'], str) or values['shape'] not in SHAPES:
        raise ValueError('Choose a supported effect and splat shape.')
    if not isinstance(values['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', values['color']):
        raise ValueError('Choose a valid effect color.')
    if not isinstance(values['surface'], str) or values['surface'] not in SURFACES:
        raise ValueError('Choose a supported Splat surface.')
    if values['edge'] not in EDGES or values['order'] not in ORDERS:
        raise ValueError('Choose a screen edge and stacking direction.')
    for key, (lo, hi) in RANGES.items():
        if type(values[key]) is not int or not lo <= values[key] <= hi:
            raise ValueError(f'{key} must be a whole number between {lo} and {hi}.')
    return dict(values, color=values['color'].lower())


def encode(values):
    return '# Xetal Minimize\n' + ''.join(
        f'{key}={int(value) if type(value) is bool else value}\n'
        for key, value in validate(values).items())


def decode(text):
    values = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or key not in DEFAULTS or key in values:
            raise ValueError('Invalid or duplicate Minimize setting.')
        if key in ('enabled', 'follow_theme'):
            if value not in ('0', '1'):
                raise ValueError('Invalid Minimize switch.')
            value = value == '1'
        elif key in RANGES:
            value = int(value)
        values[key] = value
    # Upgrade the original four-field format without discarding preferences.
    if set(values) in (LEGACY, set(DEFAULTS)-{'surface', 'edge', 'order'}, set(DEFAULTS)-{'edge', 'order'}):
        values = dict(DEFAULTS, **values)
    return validate(values)


def load(path=PATH):
    data = path.read_bytes() if path.exists() else b''
    return (decode(data.decode()) if data else dict(DEFAULTS)), hashlib.sha256(data).hexdigest()
