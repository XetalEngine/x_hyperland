"""Save theme-specific effect colors while preserving gestures and physics."""
import copy
import json
import sys
from pathlib import Path

BURN_KEYS = ('fire_color', 'fire_mystical')
CUBE_KEYS = ('edge_color', 'cap_color', 'sky_top', 'sky_bottom', 'window_color')


def rgba(color):
    return [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]+[1.0]


def plan(root, previous, design, palette):
    if design == previous: return {}, []
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from effects.burn import model as burn
    from effects.cube import model as cube
    profile = root/'theme/effect-colors.json'
    saved = json.loads(profile.read_text()) if profile.exists() else {'version': 1, 'themes': {}}
    if not isinstance(saved, dict) or saved.get('version') != 1 or not isinstance(saved.get('themes'), dict):
        raise ValueError('Saved effect colors need repair; nothing was overwritten.')
    old = saved['themes'].setdefault(previous, {})
    chosen = saved['themes'].setdefault(design, {})
    if not isinstance(old, dict) or not isinstance(chosen, dict):
        raise ValueError('The saved theme effect colors are invalid.')
    files, reloads = {}, []
    fire_path = root/'effects/burn/settings.conf'
    if fire_path.exists():
        current, _ = burn.load(fire_path)
        old['burn'] = {key: copy.deepcopy(current[key]) for key in BURN_KEYS}
        default_color = [round(c*65535) for c in rgba(palette['Accent'])]
        defaults = {'fire_color': default_color, 'fire_mystical': False}
        if design == 'raw': defaults = {key: copy.deepcopy(burn.DEFAULTS[key]) for key in BURN_KEYS}
        selected = chosen.get('burn', defaults)
        if not isinstance(selected, dict) or any(key not in selected for key in BURN_KEYS):
            raise ValueError('The saved theme flame color is invalid.')
        values = burn.validate({**current, **{key: selected[key] for key in BURN_KEYS}})
        chosen['burn'] = {key: copy.deepcopy(values[key]) for key in BURN_KEYS}
        files[fire_path] = burn.encode(values).encode()
        if values != current: reloads.append(('Xetal Burn', 'xetalburn:reload'))
    cube_path = root/'effects/cube/settings.json'
    if cube_path.exists():
        current, _ = cube.load(cube_path)
        old['cube'] = {key: copy.deepcopy(current[key]) for key in CUBE_KEYS}
        defaults = dict(edge_color=rgba(palette['Accent']), cap_color=rgba(palette['Window']),
                        sky_top=rgba(palette['Base']), sky_bottom=rgba(palette['Highlight']),
                        window_color=rgba(palette['Midlight']))
        selected = chosen.get('cube', defaults)
        if not isinstance(selected, dict) or any(key not in selected for key in CUBE_KEYS):
            raise ValueError('The saved theme cube colors are invalid.')
        values = cube.validate({**current, **{key: selected[key] for key in CUBE_KEYS}})
        chosen['cube'] = {key: copy.deepcopy(values[key]) for key in CUBE_KEYS}
        files[cube_path] = (json.dumps(values, indent=2)+'\n').encode()
        if values != current: reloads.append(('Xetal Desktop Cube', 'xetalcube:reload'))
    if files: files[profile] = (json.dumps(saved, indent=2)+'\n').encode()
    return files, reloads


def reload_active(ctl, changes):
    if not changes: return
    plugins = {p.get('name') for p in json.loads(ctl('-j', 'plugin', 'list'))}
    for name, dispatcher in changes:
        if name in plugins:
            result = ctl('dispatch', dispatcher)
            if result.strip().lower() != 'ok':
                raise ValueError(name+' could not reload its theme colors: '+result)
