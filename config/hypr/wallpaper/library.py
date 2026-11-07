"""Local wallpaper collections. Removing a folder never removes its files."""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent
PREFERENCES = ROOT/'state/browser.json'
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.avif'}
TRANSITIONS = {'random': 'Random', 'bloom': 'Bloom', 'fade': 'Crossfade', 'sweep': 'Silk sweep',
               'ripple': 'Ripple', 'iris': 'Iris', 'glide': 'Glide', 'none': 'Instant'}
ANIMATED_TRANSITIONS = tuple(key for key in TRANSITIONS if key not in ('random', 'none'))
STYLES = {'overlay': 'Floating cards', 'window': 'Gallery window',
          'frame-lab': 'Frame Lab', 'orbit-atlas': 'Orbit Atlas'}
DESCRIPTIONS = {
    'window': 'The original gallery with a soft backdrop, reflections and a flowing wallpaper ribbon.',
    'overlay': 'Wallpaper cards float directly over your desktop, with compact controls and no background window.',
    'frame-lab': 'A brass-trimmed wallpaper studio with a filmstrip, collection shelves and a large preview.',
    'orbit-atlas': 'A midnight gallery with luminous orbits, floating previews and a quiet teal glow.',
}
DEFAULTS = {'version': 1, 'folders': [], 'bundled': True, 'transition': 'bloom', 'style': 'overlay'}


@dataclass(frozen=True)
class Picture:
    path: str
    collection: str
    caption: str = ''

    @property
    def title(self):
        return self.caption or Path(self.path).stem.replace('_', ' ').replace('-', ' ').strip().title()


def include_current(pictures, current):
    """Find the source of a cached wallpaper, or include it for this opening only."""
    candidates = []
    for key in ('original', 'path'):
        value = current.get(key)
        if not isinstance(value, str) or not value: continue
        try:
            path = Path(value).resolve(strict=True)
            if path.is_file(): candidates.append(str(path))
        except (OSError, RuntimeError): pass
    available = {picture.path for picture in pictures}
    for path in candidates:
        if path in available: return pictures, path
    if candidates:
        path = candidates[0]
        return [Picture(path, 'Current wallpaper', 'Current wallpaper'), *pictures], path
    return pictures, ''


def normalize(value):
    if not isinstance(value, dict) or value.get('version', 1) != 1:
        raise ValueError('The wallpaper folder settings need repair.')
    folders = value.get('folders', [])
    if not isinstance(folders, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in folders):
        raise ValueError('Choose folders using their full paths.')
    if len(folders) > 64:
        raise ValueError('Choose up to 64 wallpaper folders.')
    transition = value.get('transition', 'bloom')
    style = value.get('style', DEFAULTS['style'])
    if (not isinstance(transition, str) or transition not in TRANSITIONS or
            not isinstance(style, str) or style not in STYLES or type(value.get('bundled', True)) is not bool):
        raise ValueError('Invalid wallpaper browser settings.')
    return {'version': 1, 'folders': list(dict.fromkeys(str(Path(p).resolve()) for p in folders)),
            'bundled': value.get('bundled', True), 'transition': transition, 'style': style}


def read(path=None):
    path = path or PREFERENCES
    return normalize(json.loads(path.read_text()) if path.exists() else DEFAULTS)


def save(value, expected, path=None, fields=None):
    """Merge named controls so the gallery and Settings can save independently."""
    import fcntl
    path = path or PREFERENCES
    value = normalize(value)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = read(path); expected = normalize(expected)
        fields = tuple(fields) if fields is not None else tuple(DEFAULTS)
        if any(key not in DEFAULTS for key in fields): raise ValueError('Unknown wallpaper setting.')
        if any(current[key] != expected[key] for key in fields):
            raise ValueError('Wallpaper settings changed elsewhere. Reopen these controls and try again.')
        value = normalize({**current, **{key: value[key] for key in fields}})
        fd, name = tempfile.mkstemp(prefix='.browser-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    return value


def scan(options, root=None, cancelled=lambda: False, limit=20000):
    """Bounded, cancellable enumeration; no recursive symlink traversal or decoding."""
    root = root or ROOT
    pictures, notices, seen = [], [], set()

    def add(path, collection):
        try:
            path = path.resolve(strict=True)
            if path.suffix.lower() not in EXTENSIONS or not path.is_file(): return
            stat = path.stat(); identity = (stat.st_dev, stat.st_ino)
            if identity in seen: return
            seen.add(identity); pictures.append(Picture(str(path), collection))
        except OSError: pass

    if options['bundled']:
        names = {'raw': 'Original', 'modern': 'Xetal Modern', 'breakpoint': 'Breakpoint', 'binaryknife': 'Binary Knife', 'tidalglass': 'Tidal Glass', 'porcelainink': 'Porcelain Ink', 'obsidianforge': 'Obsidian Forge', 'candycloud': 'Candy Cloud', 'shadowedge': 'Shadow Edge', 'hollowgrove': 'Hollow Grove', 'gildedhollow': 'The Gilded Hollow', 'hyperfusionblue': 'HyperFusion Blue'}
        try:
            catalog = json.loads((root/'sets.json').read_text())
            for collection, paths in catalog.items():
                for relative in paths:
                    path = (root/relative).resolve()
                    if path.is_relative_to(root.resolve()): add(path, names.get(collection, collection))
        except (OSError, ValueError, TypeError): notices.append('The bundled wallpaper collection could not be read.')
    visited = 0
    for name in options['folders']:
        if cancelled(): break
        folder = Path(name)
        if not folder.is_dir():
            notices.append(f'Folder unavailable: {folder}'); continue
        errors = []
        for directory, subdirs, files in os.walk(folder, followlinks=False, onerror=errors.append):
            subdirs[:] = sorted(d for d in subdirs if not d.startswith('.') and not (Path(directory)/d).is_symlink())
            if cancelled(): break
            for filename in sorted(files):
                visited += 1
                if len(pictures) >= limit or visited > 100000 or cancelled(): break
                add(Path(directory)/filename, folder.name or str(folder))
            if len(pictures) >= limit or visited > 100000: break
        if errors: notices.append(f'Some files in {folder.name} could not be read.')
        if len(pictures) >= limit or visited > 100000:
            notices.append('Showing the first 20,000 images. Choose narrower folders to see more.'); break
    return pictures, notices


def active_screens(models):
    return [m for m in models if m.get('enabled', True) and not m.get('mirror')]


def screen_rectangles(models, width, height, margin=28):
    """Actual logical layout, including negative coordinates, scale and rotation."""
    screens = active_screens(models)
    if not screens: return {}
    dimensions = {}
    for m in screens:
        w, h = m['width'], m['height']
        if m.get('transform', 0) % 2: w, h = h, w
        scale = m.get('scale', 1) or 1
        dimensions[m['name']] = (w/scale, h/scale)
    left, top = min(m['x'] for m in screens), min(m['y'] for m in screens)
    right = max(m['x']+dimensions[m['name']][0] for m in screens)
    bottom = max(m['y']+dimensions[m['name']][1] for m in screens)
    ratio = max(.001, min(max(1, width-2*margin)/(right-left), max(1, height-2*margin)/(bottom-top)))
    ox, oy = (width-(right-left)*ratio)/2, (height-(bottom-top)*ratio)/2
    return {m['name']: (ox+(m['x']-left)*ratio, oy+(m['y']-top)*ratio,
                        dimensions[m['name']][0]*ratio, dimensions[m['name']][1]*ratio) for m in screens}
