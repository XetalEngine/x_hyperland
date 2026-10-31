"""Profile-local minimize preferences; effects can be extended without changing the handler."""
import hashlib
from pathlib import Path

DEFAULTS = dict(enabled=True, effect='fireball', duration=420, size=76)
RANGES = dict(duration=(150, 1200), size=(48, 120))
PATH = Path(__file__).resolve().with_name('settings.conf')


def validate(values):
    if set(values) != set(DEFAULTS):
        raise ValueError('Minimize settings are incomplete or contain unknown options.')
    if type(values['enabled']) is not bool or values['effect'] != 'fireball':
        raise ValueError('Choose whether minimizing is enabled and select Fireball.')
    for key, (lo, hi) in RANGES.items():
        if type(values[key]) is not int or not lo <= values[key] <= hi:
            raise ValueError(f'{key} must be a whole number between {lo} and {hi}.')
    return dict(values)


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
        if key == 'enabled':
            if value not in ('0', '1'):
                raise ValueError('Invalid Minimize switch.')
            value = value == '1'
        elif key in RANGES:
            value = int(value)
        values[key] = value
    return validate(values)


def load(path=PATH):
    data = path.read_bytes() if path.exists() else b''
    return (decode(data.decode()) if data else dict(DEFAULTS)), hashlib.sha256(data).hexdigest()
