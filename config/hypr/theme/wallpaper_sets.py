"""Bundled monitor sets and independent user wallpaper choices for each design."""
import copy
import json
from pathlib import Path


def catalog(root):
    path = root/'sets.json'
    if not path.exists(): return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise ValueError('The wallpaper set catalog is invalid.')
    result = {}
    for design, names in value.items():
        if not isinstance(names, list) or len(names) < 3:
            raise ValueError('Each bundled theme needs at least three wallpapers.')
        paths = []
        for name in names:
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Invalid bundled wallpaper path.')
            paths.append(root/relative)
        result[design] = paths
    return result


def profiles(root):
    path = root/'profiles.json'
    if not path.exists(): return {'version': 1, 'themes': {}}
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('themes'), dict):
        raise ValueError('The saved theme wallpapers need repair; nothing was overwritten.')
    return value


def remember(root, design, selection):
    value = profiles(root)
    value['themes'][design] = copy.deepcopy(selection)
    return value


def screens(monitors):
    return sorted((m for m in monitors if not m.get('disabled') and m.get('enabled', True)
                   and not m.get('mirror') and m.get('mirrorOf', -1) in (-1, None, '', 'none')),
                  key=lambda m: (m.get('x', 0), m.get('y', 0), m['name']))


def bundled(root, design, monitors):
    paths = catalog(root).get(design, [])
    if not paths: return {}
    if not all(path.is_file() for path in paths):
        raise ValueError('A wallpaper in this theme is missing. Reinstall the bundled artwork.')
    # Additional artwork is offered in the chooser. Keep the original first
    # three as the monitor defaults, including on desktops with extra outputs.
    return {monitor['name']: {'path': str(paths[index%3]), 'original': str(paths[index%3]), 'fit': 'cover'}
            for index, monitor in enumerate(screens(monitors))}


def switching(root, previous_design, design, current, monitors):
    value = remember(root, previous_design, current)
    saved = value['themes'].get(design, {})
    if not isinstance(saved, dict): raise ValueError('The saved theme wallpaper selection is invalid.')
    defaults = bundled(root, design, monitors)
    bundled_paths = {path.resolve() for path in catalog(root).get(design, [])}
    target = copy.deepcopy(saved)
    for monitor in screens(monitors):
        name = monitor['name']
        choice = saved.get(name, {})
        if not isinstance(choice, dict): raise ValueError('Invalid saved wallpaper choice.')
        # Bundled artwork can be refreshed by an update. Do not resurrect an old
        # imported copy of it; personal images still prefer their portable cache.
        original = choice.get('original')
        bundled_original = isinstance(original, str) and Path(original).resolve() in bundled_paths
        order = ('original', 'path') if bundled_original else ('path', 'original')
        available = next((choice.get(key) for key in order
                          if isinstance(choice.get(key), str) and Path(choice[key]).is_file()), None)
        if available:
            target[name] = {**choice, 'path': available}
        elif name in defaults:
            target[name] = defaults[name]
        elif name in current:
            target[name] = copy.deepcopy(current[name])
    value['themes'][design] = copy.deepcopy(target)
    return target, value


def encode(value):
    return (json.dumps(value, indent=2)+'\n').encode()
