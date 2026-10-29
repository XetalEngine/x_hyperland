"""Per-profile task switcher choices. No compositor or shared desktop settings."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

PATH = Path(__file__).with_name('preferences.json')
STYLES = {
    'fusion': 'Fusion Cards', 'application': 'Application Switcher',
    'static': 'Static Application Switcher', 'ring': 'Ring Switcher',
    'cover': 'Shift · Cover', 'flip': 'Shift · Flip',
    'stack': 'Stack Window Switcher', 'scale': 'Scale · Window Overview',
}
DESCRIPTIONS = {
    'fusion': 'Our familiar app cards, with a fixed grid and large application icons.',
    'application': 'Compiz’s classic thumbnail strip. Windows slide past the centered selection.',
    'static': 'A stable thumbnail grid. The selection moves while the windows stay in place.',
    'ring': 'Windows orbit an ellipse, growing brighter and larger as they come to the front.',
    'cover': 'Compiz Shift’s Cover mode: a perspective carousel with a reflected floor.',
    'flip': 'Compiz Shift’s Flip mode: a diagonal deck of windows that flips forward.',
    'stack': 'Compiz’s tilted window rows, with the selected window lifted from the stack.',
    'scale': 'Compiz’s Scale overview: see a grid of window previews and choose one directly.',
}
SCOPES = {'all': 'All monitors and workspaces', 'monitor': 'Current monitor',
          'workspace': 'Current workspace', 'application': 'Current application'}
# Visual defaults come from the bundled Compiz metadata. Timing uses milliseconds
# rather than Compiz's frame-dependent spring/timestep settings.
PROFILES = {
    'fusion': dict(columns=4),
    'application': dict(thumb_width=250, thumb_height=200, icon_only=False),
    'static': dict(columns=4, thumb_width=250, thumb_height=200),
    'ring': dict(ring_width=70, ring_height=60, thumb_width=350, thumb_height=250,
                 min_scale=40, min_brightness=50, clockwise=False),
    'cover': dict(size=50, cover_offset=0, reflection=True, reflection_intensity=40),
    'flip': dict(size=50, flip_rotation=30, reflection=True, reflection_intensity=40),
    'stack': dict(tilt=30, inactive_rotate=True),
    'scale': dict(spacing=10),
}
DEFAULTS = dict(version=1, style='fusion', scope='all', duration=200, size=80,
                inactive_opacity=80, live_previews=True,
                show_titles=True, show_icons=True, profiles=PROFILES)
RANGES = dict(duration=(0, 700), size=(30, 100), inactive_opacity=(20, 100),
              columns=(2, 8), thumb_width=(100, 650), thumb_height=(80, 450),
              ring_width=(10, 100), ring_height=(10, 100), min_scale=(10, 100),
              min_brightness=(10, 100), cover_offset=(-40, 40),
              reflection_intensity=(0, 80), flip_rotation=(-75, 75), tilt=(0, 75), spacing=(0, 100))


def section(value, defaults):
    if not isinstance(value, dict):
        raise ValueError('Task Switcher settings must be an object.')
    result = copy.deepcopy(defaults)
    for key, default in defaults.items():
        item = value.get(key, default)
        valid = type(item) is bool if type(default) is bool else (
            type(item) is int and RANGES[key][0] <= item <= RANGES[key][1])
        if not valid:
            raise ValueError(f'Invalid Task Switcher setting: {key}.')
        result[key] = item
    return result


def normalize(value):
    if not isinstance(value, dict) or type(value.get('version', 1)) is not int or value.get('version', 1) != 1:
        raise ValueError('Unsupported Task Switcher settings format.')
    style, scope = value.get('style', 'fusion'), value.get('scope', 'all')
    if not isinstance(style, str) or style not in STYLES or not isinstance(scope, str) or scope not in SCOPES:
        raise ValueError('Choose a supported switcher style and window scope.')
    profiles = value.get('profiles', {})
    if not isinstance(profiles, dict):
        raise ValueError('Invalid Task Switcher style profiles.')
    common = {k: v for k, v in DEFAULTS.items() if k not in ('version', 'style', 'scope', 'profiles')}
    return dict(version=1, style=style, scope=scope, **section(value, common),
                profiles={k: section(profiles.get(k, {}), v) for k, v in PROFILES.items()})


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


def save(values, expected, path=None):
    path = path or PATH
    values = normalize(values)
    data = (json.dumps(values, indent=2)+'\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = path.read_bytes() if path.exists() else b''
        if digest(before) != expected:
            raise ValueError('Task Switcher settings changed elsewhere. Reload before applying.')
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.switcher-', delete=False) as temporary:
                name = temporary.name
                temporary.write(data); temporary.flush(); os.fsync(temporary.fileno())
            os.replace(name, path)
        finally:
            if name and os.path.exists(name): os.unlink(name)
    return values, digest(data)
