"""Preferences for the modifier-held window close button."""
import hashlib
from pathlib import Path

PATH = Path(__file__).with_name('settings.conf')
DEFAULTS = dict(enabled=True, modifier='SUPER', size=18, inset=8, pulse=True)


def validate(values):
    if set(values) != set(DEFAULTS):
        raise ValueError('Window close settings are incomplete or contain unknown options.')
    if type(values['enabled']) is not bool or type(values['pulse']) is not bool:
        raise ValueError('Invalid window close switch.')
    if values['modifier'] not in ('SUPER', 'ALT', 'SUPER+SHIFT'):
        raise ValueError('Choose Super, Alt, or Super+Shift.')
    for key, lo, hi in (('size', 10, 64), ('inset', 4, 32)):
        if type(values[key]) is not int or not lo <= values[key] <= hi:
            raise ValueError(f'{key} must be between {lo} and {hi}.')
    return dict(values)


def encode(values):
    return '# Fusion window close button\n' + ''.join(
        f'{k}={int(v) if type(v) is bool else v}\n' for k, v in validate(values).items())


def decode(text):
    values = {}
    for line in text.splitlines():
        if not line or line.startswith('#'): continue
        key, sep, value = line.partition('=')
        if not sep or key not in DEFAULTS or key in values:
            raise ValueError('Invalid or duplicate window close setting.')
        if key in ('enabled', 'pulse'):
            if value not in ('0', '1'): raise ValueError('Invalid window close switch.')
            value = value == '1'
        elif key in ('size', 'inset'): value = int(value)
        values[key] = value
    return validate(values)


def load(path=PATH):
    data = path.read_bytes() if path.exists() else b''
    return (decode(data.decode()) if data else dict(DEFAULTS)), hashlib.sha256(data).hexdigest()
