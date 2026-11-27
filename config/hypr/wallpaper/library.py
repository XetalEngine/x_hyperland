"""Local wallpaper collections. Removing a folder never removes its files."""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
PREFERENCES = ROOT/'state/browser.json'
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mkv', '.mov', '.m4v', '.avi'}
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
DEFAULTS = {'version': 1, 'folders': [], 'bundled': True, 'transition': 'bloom', 'style': 'overlay',
            'media': 'pictures', 'video_folders': [], 'pause_on_battery': True, 'hidden': [],
            'hidden_tabs': [{'id':'hidden','name':'Hidden','paths':[]}], 'active_hidden_tab':'hidden'}
HIDDEN_FIELDS = ('hidden','hidden_tabs','active_hidden_tab')


def tab_name(value):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>48 or not value.isprintable():
        raise ValueError('Give the tab a name of 1–48 characters.')
    return value.strip()


def normalize_tabs(value, hidden):
    """Every hidden path has one owner; migrate the original shelf intact."""
    tabs = value.get('hidden_tabs',[{'id':'hidden','name':'Hidden','paths':hidden}])
    if not isinstance(tabs,list) or not 1<=len(tabs)<=64:
        raise ValueError('Keep between 1 and 64 hidden wallpaper tabs.')
    ids, names, assigned, result = set(), set(), set(), []; total_paths = 0
    available = set(hidden)
    for tab in tabs:
        if not isinstance(tab,dict) or not isinstance(tab.get('id'),str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',tab['id']):
            raise ValueError('Invalid hidden wallpaper tab.')
        name = tab_name(tab.get('name'))
        if tab['id'] in ids or name.casefold() in names: raise ValueError('Each tab needs its own name.')
        ids.add(tab['id']); names.add(name.casefold())
        paths = tab.get('paths',[])
        if (not isinstance(paths,list) or len(paths)>40000 or
                any(not isinstance(p,str) or not Path(p).is_absolute() or '\x00' in p for p in paths)):
            raise ValueError('Invalid wallpapers in a hidden tab.')
        total_paths += len(paths)
        if total_paths>40000: raise ValueError('Too many wallpapers in hidden tabs.')
        owned = []
        for path in paths:
            path = path if path in available else str(Path(path).resolve())
            # The flat list remains the global hide/restore membership, including
            # preferences written by a selector from before tabs were supported.
            if path not in available: continue
            if path in assigned: raise ValueError('A hidden wallpaper can belong to only one tab.')
            owned.append(path); assigned.add(path)
        result.append({'id':tab['id'],'name':name,'paths':owned})
    active = value.get('active_hidden_tab',result[0]['id'])
    if not isinstance(active,str) or active not in ids: active = result[0]['id']
    next(t for t in result if t['id']==active)['paths'].extend(p for p in hidden if p not in assigned)
    return result, active


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
    video_folders = value.get('video_folders', [])
    if (not isinstance(video_folders, list) or len(video_folders)>64 or
            any(not isinstance(p,str) or not Path(p).is_absolute() for p in video_folders)):
        raise ValueError('Choose up to 64 video folders using their full paths.')
    if value.get('media','pictures') not in ('pictures','videos') or type(value.get('pause_on_battery',True)) is not bool:
        raise ValueError('Invalid wallpaper media settings.')
    hidden = value.get('hidden', [])
    if (not isinstance(hidden, list) or len(hidden) > 40000 or
            any(not isinstance(p, str) or not Path(p).is_absolute() or '\x00' in p for p in hidden)):
        raise ValueError('Invalid hidden wallpaper list.')
    hidden = list(dict.fromkeys(str(Path(p).resolve()) for p in hidden))
    tabs, active_tab = normalize_tabs(value,hidden)
    transition = value.get('transition', 'bloom')
    style = value.get('style', DEFAULTS['style'])
    if (not isinstance(transition, str) or transition not in TRANSITIONS or
            not isinstance(style, str) or style not in STYLES or type(value.get('bundled', True)) is not bool):
        raise ValueError('Invalid wallpaper browser settings.')
    return {'version': 1, 'folders': list(dict.fromkeys(str(Path(p).resolve()) for p in folders)),
            'bundled': value.get('bundled', True), 'transition': transition, 'style': style,
            'media':value.get('media','pictures'), 'video_folders':list(dict.fromkeys(str(Path(p).resolve()) for p in video_folders)),
            'pause_on_battery':value.get('pause_on_battery',True),
            'hidden':hidden, 'hidden_tabs':tabs, 'active_hidden_tab':active_tab}


def hidden_pictures(options, pictures):
    """The active tab remains available across media and folder filters."""
    known = {picture.path: picture for picture in pictures}
    paths = hidden_tab(options)['paths']
    return [known.get(path, Picture(path, 'Hidden wallpapers')) for path in paths]


def hidden_tab(options, identity=None):
    identity = identity or options['active_hidden_tab']
    tab = next((t for t in options['hidden_tabs'] if t['id']==identity),None)
    if tab is None: raise ValueError('That hidden wallpaper tab no longer exists.')
    return tab


def add_hidden_tab(options, name):
    value = normalize(options); identity = uuid.uuid4().hex
    value['hidden_tabs'].append({'id':identity,'name':tab_name(name),'paths':[]})
    value['active_hidden_tab'] = identity
    return normalize(value)


def rename_hidden_tab(options, identity, name):
    value = normalize(options); hidden_tab(value,identity)['name'] = tab_name(name)
    return normalize(value)


def transfer_hidden_tab(options, source, destination):
    """Deleting a container transfers every entry, including missing files."""
    value = normalize(options)
    if source==destination: raise ValueError('Choose a different tab for these wallpapers.')
    if len(value['hidden_tabs'])<2: raise ValueError('Create another tab before deleting this one.')
    origin = hidden_tab(value,source); target = hidden_tab(value,destination)
    target['paths'].extend(origin['paths'])
    value['hidden_tabs'].remove(origin); value['active_hidden_tab'] = destination
    return normalize(value)


def move_hidden_picture(options, path, destination):
    value = normalize(options); target = hidden_tab(value,destination)
    if path not in value['hidden']: raise ValueError('That wallpaper is no longer hidden.')
    for tab in value['hidden_tabs']:
        if path in tab['paths']: tab['paths'].remove(path)
    target['paths'].append(path); value['active_hidden_tab'] = destination
    return normalize(value)


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
    videos = options.get('media','pictures') == 'videos'
    extensions = VIDEO_EXTENSIONS if videos else EXTENSIONS

    def add(path, collection):
        try:
            path = path.resolve(strict=True)
            if path.suffix.lower() not in extensions or not path.is_file(): return
            stat = path.stat(); identity = (stat.st_dev, stat.st_ino)
            if identity in seen: return
            seen.add(identity); pictures.append(Picture(str(path), collection))
        except OSError: pass

    if options['bundled'] and not videos:
        names = {'raw': 'Original', 'modern': 'Xetal Modern', 'breakpoint': 'Breakpoint', 'binaryknife': 'Binary Knife', 'tidalglass': 'Tidal Glass', 'porcelainink': 'Porcelain Ink', 'obsidianforge': 'Obsidian Forge', 'candycloud': 'Candy Cloud', 'shadowedge': 'Shadow Edge', 'hollowgrove': 'Hollow Grove', 'gildedhollow': 'The Gilded Hollow', 'hyperfusionblue': 'HyperFusion Blue', 'midnighttransit': 'Midnight Transit', 'blackwood': 'Blackwood', 'atomicafterglow': 'Atomic Afterglow', 'mycelium': 'Mycelium', 'mystery98': 'Windows 98 Mystery', 'platform95': 'Platform 95', 'midnightrun': 'Midnight Run', 'prisonbreak': 'Prison Break', 'killerinstinct': 'Killer Instinct · Arcade 94', 'kitemple': 'Killer Instinct · Jade Temple', 'kiprimal': 'Killer Instinct · Primal Storm', 'kifireice': 'Killer Instinct · Fire & Ice', 'starcraft': 'StarCraft II', 'mortalkombat2': 'Mortal Kombat II', 'facadasexu': '777 Facadas Exu', 'infernalencore': 'Infernal Encore', 'polaris': 'Polaris', 'hp4': 'BMW S1000RR HP4', 'integra': 'Integra · Ivory Midnight', 'amazon': 'Amazon', 'leviathan': 'Leviathan', 'ghostbusters': 'Ghostbusters'}
        try:
            catalog = json.loads((root/'sets.json').read_text())
            for collection, paths in catalog.items():
                for relative in paths:
                    path = (root/relative).resolve()
                    if path.is_relative_to(root.resolve()): add(path, names.get(collection, collection))
        except (OSError, ValueError, TypeError): notices.append('The bundled wallpaper collection could not be read.')
    visited = 0
    for name in options.get('video_folders', []) if videos else options['folders']:
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
            notices.append('Showing the first 20,000 wallpapers. Choose narrower folders to see more.'); break
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
