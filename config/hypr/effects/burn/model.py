"""Compiz's option names, ranges and defaults; no desktop changes on import."""
import hashlib
import math
from pathlib import Path

DEFAULTS = dict(enabled=False, duration=200, time_step_intense=30, fire_particles=1000,
                fire_size=5.0, fire_slowdown=0.5, fire_life=0.7,
                fire_color=[65535, 13107, 1365, 65535], fire_direction=0,
                fire_constant_speed=False, fire_smoke=False, fire_mystical=False)
RANGES = dict(duration=(50,4000), time_step_intense=(1,400), fire_particles=(100,10000),
              fire_size=(0.1,20), fire_slowdown=(0.1,10), fire_life=(0.1,1), fire_direction=(0,5))
DIRECTIONS = ('Down', 'Up', 'Left', 'Right', 'Random', 'Automatic')
PATH = Path(__file__).resolve().with_name('settings.conf')


def validate(values):
    if set(values) != set(DEFAULTS):
        raise ValueError('Burn settings are incomplete or contain unknown options.')
    out = {}
    for key, default in DEFAULTS.items():
        v = values[key]
        if key == 'fire_color':
            if not isinstance(v, (list, tuple)) or len(v) != 4 or any(type(c) is not int or not 0 <= c <= 65535 for c in v):
                raise ValueError('Flame color needs four RGBA channels from 0 to 65535.')
            out[key] = list(v)
        elif type(default) is bool:
            if type(v) is not bool:
                raise ValueError(f'{key} must be on or off.')
            out[key] = v
        else:
            if type(v) not in (int, float) or not math.isfinite(v) or not RANGES[key][0] <= v <= RANGES[key][1]:
                raise ValueError(f'{key} must be between {RANGES[key][0]} and {RANGES[key][1]}.')
            if type(default) is int and int(v) != v:
                raise ValueError(f'{key} needs a whole number.')
            out[key] = type(default)(v)
    return out


def encode(values):
    values = validate(values)
    lines = ['# Xetal Burn — original Compiz option units; color is RGBA16.']
    for k, v in values.items():
        text = ' '.join(map(str, v)) if isinstance(v, list) else str(int(v)) if type(v) is bool else str(v)
        lines.append(f'{k}={text}')
    return '\n'.join(lines) + '\n'


def decode(text):
    values = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or key not in DEFAULTS or key in values:
            raise ValueError('Invalid or duplicate Burn setting.')
        if key == 'fire_color':
            values[key] = [int(c) for c in value.split()]
        elif type(DEFAULTS[key]) is bool:
            if value not in ('0','1'):
                raise ValueError('Invalid Burn switch.')
            values[key] = value == '1'
        else:
            values[key] = float(value)
    return validate(values)


def load(path=PATH):
    content = path.read_bytes() if path.exists() else b''
    return (decode(content.decode()) if content else validate(DEFAULTS)), hashlib.sha256(content).hexdigest()
