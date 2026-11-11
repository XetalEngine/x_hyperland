"""Independent file-transfer appearance and behavior, confined to this profile."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

PATH = Path(__file__).with_name('preferences.json')
STYLES = {'follow': 'Follow desktop theme', 'raw': 'Xetal Raw',
          'modern': 'Xetal Modern', 'breakpoint': 'BreakPoint', 'binaryknife': 'Binary Knife', 'tidalglass': 'Tidal Glass', 'porcelainink': 'Porcelain Ink', 'obsidianforge': 'Obsidian Forge', 'candycloud': 'Candy Cloud', 'shadowedge': 'Shadow Edge', 'hollowgrove': 'Hollow Grove', 'gildedhollow': 'The Gilded Hollow', 'hyperfusionblue': 'HyperFusion Blue', 'midnighttransit': 'Midnight Transit', 'blackwood': 'Blackwood', 'atomicafterglow': 'Atomic Afterglow', 'mycelium': 'Mycelium', 'mystery98': 'Windows 98 Mystery', 'platform95': 'Platform 95', 'midnightrun': 'Midnight Run', 'infernalencore': 'Infernal Encore', 'polaris': 'Polaris', 'leviathan': 'Leviathan', 'ghostbusters': 'Ghostbusters'}
APPEARANCE = dict(width=448, height=168, radius=16, opacity=100, glow=55,
                  border=1, track_height=5, accent='')
PROFILES = {name: {**APPEARANCE, **values} for name, values in {
    'raw': {}, 'modern': dict(radius=20, glow=35, track_height=6),
    'breakpoint': dict(radius=12, opacity=94, glow=25, track_height=4),
    'binaryknife': dict(radius=4, opacity=97, glow=45, track_height=4),
    'tidalglass': dict(radius=22, opacity=96, glow=70, track_height=6),
    'porcelainink': dict(radius=2, opacity=100, glow=0, track_height=4),
    'obsidianforge': dict(radius=3, opacity=100, glow=65, track_height=4),
    'hollowgrove': dict(radius=20, opacity=100, glow=22, track_height=5),
    'infernalencore': dict(radius=5, opacity=100, glow=40, track_height=7),
    'ghostbusters': dict(radius=10, opacity=100, glow=40, track_height=5),
    'leviathan': dict(radius=6, opacity=100, glow=30, track_height=5),
    'polaris': dict(radius=12, opacity=100, glow=35, track_height=7),
    'midnightrun': dict(radius=7, opacity=100, glow=40, track_height=7),
    'mystery98': dict(radius=1, opacity=100, glow=10, track_height=8), 'platform95': dict(radius=1, opacity=100, glow=10, track_height=8),
    'mycelium': dict(radius=14, opacity=100, glow=24, track_height=6),
    'atomicafterglow': dict(radius=5, opacity=100, glow=24, track_height=5),
    'blackwood': dict(radius=5, opacity=100, glow=14, track_height=4),
    'midnighttransit': dict(radius=7, opacity=100, glow=18, track_height=5),
    'hyperfusionblue': dict(radius=9, opacity=100, glow=35, track_height=6),
    'gildedhollow': dict(radius=17, opacity=100, glow=50, track_height=5),
    'shadowedge': dict(radius=3, opacity=100, glow=18, track_height=4),
    'candycloud': dict(radius=26, opacity=100, glow=40, track_height=8)}.items()}
DEFAULTS = dict(version=1, style='follow', profiles=PROFILES,
    animation=dict(enabled=True, speed=100, density=3, trails=True, smooth=True),
    information=dict(paths='names', percentage=True, amount=True, speed=True, remaining=False),
    behavior=dict(show_delay=500, auto_close=True, close_delay=1600))
RANGES = dict(width=(360, 760), height=(156, 280), radius=(0, 28), opacity=(40, 100),
              glow=(0, 100), border=(0, 3), track_height=(3, 12), speed=(25, 250),
              density=(1, 7), show_delay=(0, 3000), close_delay=(500, 15000))


def section(value, defaults):
    if not isinstance(value, dict):
        raise ValueError('File Transfer settings must be an object.')
    result = copy.deepcopy(defaults)
    for key, default in defaults.items():
        item = value.get(key, default)
        if type(default) is bool:
            valid = type(item) is bool
        elif type(default) is int:
            valid = type(item) is int and RANGES[key][0] <= item <= RANGES[key][1]
        elif key == 'accent':
            valid = isinstance(item, str) and (item == '' or re.fullmatch(r'#[0-9a-fA-F]{6}', item))
        elif key == 'paths':
            valid = isinstance(item, str) and item in ('hidden', 'names', 'full')
        else:
            valid = False
        if not valid:
            raise ValueError(f'Invalid File Transfer setting: {key}.')
        result[key] = item
    return result


def normalize(value):
    if not isinstance(value, dict) or type(value.get('version', 1)) is not int or value.get('version', 1) != 1:
        raise ValueError('Unsupported File Transfer settings format.')
    style = value.get('style', 'follow')
    if not isinstance(style, str) or style not in STYLES:
        raise ValueError('Choose a supported File Transfer style.')
    profiles = value.get('profiles', {})
    if not isinstance(profiles, dict):
        raise ValueError('Invalid File Transfer style profiles.')
    return dict(version=1, style=style,
                profiles={name: section(profiles.get(name, {}), defaults) for name, defaults in PROFILES.items()},
                **{name: section(value.get(name, {}), DEFAULTS[name])
                   for name in ('animation', 'information', 'behavior')})


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path=None):
    path = path or PATH
    data = path.read_bytes() if path.exists() else b''
    return normalize(json.loads(data) if data else {}), digest(data)


def current():
    try:
        return load()[0]
    except (OSError, ValueError):
        return normalize({})


def selected(values, desktop):
    return desktop if values['style'] == 'follow' and desktop in PROFILES else (
        'raw' if values['style'] == 'follow' else values['style'])


def save(values, expected, path=None):
    path = path or PATH
    values = normalize(values)
    data = (json.dumps(values, indent=2)+'\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = path.read_bytes() if path.exists() else b''
        if digest(before) != expected:
            raise ValueError('File Transfer settings changed elsewhere. Reload before applying.')
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.transfer-', delete=False) as temporary:
                name = temporary.name
                temporary.write(data); temporary.flush(); os.fsync(temporary.fileno())
            os.replace(name, path)
        finally:
            if name and os.path.exists(name): os.unlink(name)
    return values, digest(data)
