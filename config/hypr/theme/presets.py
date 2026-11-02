"""Named snapshots and component plans. Only fixed, validated profile files are writable."""
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
import runtime
import layouts
sys.path.insert(0, str(runtime.ROOT.parent))
from file_jobs import preferences as transfer
from switcher import preferences as switcher
from terminal_fetch import model as terminal
from effects.burn import model as burn
from effects.cube import model as cube
from effects.minimize import model as minimize
from effects.wobbly import model as wobbly
from cursors import model as cursors

COMPONENTS = {
    'colors': ('Colors', 'Desktop palette, taskbar accents, terminal and application colors'),
    'layout': ('Navigation & controls', 'Tabs, icon rail, sidebar or ribbon; button and menu shapes'),
    'wallpaper': ('Wallpapers', 'The wallpaper selection for each display'),
    'launcher': ('Start menu', 'Menu style, background, tiles, groups and shortcut labels'),
    'avatar': ('Profile image', 'Your account image or animated GIF'),
    'transfer': ('File Transfer', 'Transfer window, animation and information choices'),
    'switcher': ('Task Switcher', 'Switcher style, preview FPS and layout options'),
    'effects': ('Window effects', 'Burn, cube, wobbly windows, minimizing, effect colors and window appearance'),
    'cursors': ('Cursors', 'Cursor style, size, trails and click feedback'),
    'terminal': ('Terminal welcome', 'Logo and information fields; aliases remain untouched'),
}
THEME_FIELDS = {
    'colors': ('design', 'mode'), 'layout': ('layout',), 'avatar': ('avatar',),
    'launcher': ('launcher_style', 'launcher_wallpaper', 'launcher_background', 'launcher_surfaces', 'launcher_labels', 'launcher_background_visibility'),
}
RESOURCE_PATHS = {'cursors': 'cursors/settings.json', 'transfer': 'file_jobs/preferences.json', 'switcher': 'switcher/preferences.json',
    'terminal': 'terminal_fetch/settings.json', 'burn': 'effects/burn/settings.conf', 'cube': 'effects/cube/settings.json', 'minimize': 'effects/minimize/settings.conf', 'wobbly': 'effects/wobbly/settings.json'}


def encode(value): return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def current(root=None):
    root = root or runtime.ROOT.parent
    state = copy.deepcopy(runtime.state()); state['layout'] = runtime.layout()
    state.setdefault('design',runtime.design());state.setdefault('mode',runtime.mode())
    value = {'version': 1, 'theme': state, 'wallpaper_theme': state.get('wallpaper_theme',state['design'])}
    for key, reader in [('transfer', transfer.load), ('switcher', switcher.load), ('burn', burn.load), ('cube', cube.load), ('minimize', minimize.load), ('wobbly', wobbly.load), ('cursors', cursors.load)]:
        path = root / RESOURCE_PATHS[key]
        if path.exists(): value[key] = reader(path)[0]
    value['terminal'] = terminal.load(root / RESOURCE_PATHS['terminal'])
    path = root / 'wallpaper/selection.json'
    if path.exists(): value['wallpapers'] = json.loads(path.read_text())
    path = root / 'control_center/appearance.conf'
    if path.exists(): value['appearance'] = path.read_text()
    return validate(value)


def validate(value):
    if not isinstance(value, dict) or value.get('version') != 1: raise ValueError('Unsupported preset format.')
    value = copy.deepcopy(value); state = value.get('theme', {})
    if not isinstance(state, dict) or state.get('design') not in runtime.DESIGNS or state.get('mode') not in runtime.MODES:
        raise ValueError('Invalid preset colors.')
    state['layout'] = state.get('layout', layouts.default(state['design']))
    if not isinstance(state['layout'],str) or state['layout'] not in layouts.LAYOUTS: raise ValueError('Invalid preset layout.')
    if 'wallpaper_theme' in value and (not isinstance(value['wallpaper_theme'],str) or value['wallpaper_theme'] not in runtime.DESIGNS):raise ValueError('Invalid wallpaper theme.')
    for key, normalizer in [('transfer', transfer.normalize), ('switcher', switcher.normalize), ('terminal', terminal.validate), ('burn', burn.validate), ('cube', cube.validate), ('minimize', minimize.validate), ('wobbly', wobbly.validate), ('cursors', cursors.validate)]:
        if key in value: value[key] = normalizer(value[key])
    if 'wallpapers' in value:
        if not isinstance(value['wallpapers'], dict): raise ValueError('Invalid preset wallpapers.')
        for name, item in value['wallpapers'].items():
            if not re.fullmatch(r'[\w.:-]+', name) or not isinstance(item, dict) or item.get('fit') not in ('cover', 'contain', 'fill', 'tile'):
                raise ValueError('Invalid preset wallpaper selection.')
            if not isinstance(item.get('path'), str): raise ValueError('Invalid wallpaper path.')
    if 'appearance' in value:
        # Presets cannot embed arbitrary Hyprland commands or startup programs.
        if not isinstance(value['appearance'],str):raise ValueError('Invalid window appearance options.')
        from preferences_page import APPEARANCE
        allowed = {field[1] for field in APPEARANCE}
        for line in value['appearance'].splitlines():
            if not line.strip() or line.lstrip().startswith('#'): continue
            key, sep, setting = line.partition('=')
            if not sep or key.strip() not in allowed or any(c in setting for c in '{};\0'):
                raise ValueError('Unsupported window appearance option in preset.')
    return value


def builtin(design, mode=None, root=None):
    mode = mode or runtime.designs.DEFAULT_MODES[design]
    value = current(root); value['theme'].update(design=design, mode=mode, layout=layouts.default(design), launcher_style=design)
    value['transfer']['style'] = design
    # Built-in presets supply their visual language, while keeping timing and hardware preferences.
    value.pop('wallpapers', None); value['wallpaper_theme'] = design
    value.pop('burn', None); value.pop('cube', None); value.pop('minimize', None); value.pop('wobbly', None); value.pop('appearance', None)
    if design == 'tidalglass':
        value.setdefault('cursors',copy.deepcopy(cursors.DEFAULTS))
        value['cursors'].update(style='pearl',color='#65dced',trail='glow',intensity=30)
    elif design == 'porcelainink':
        value.setdefault('cursors',copy.deepcopy(cursors.DEFAULTS))
        value['cursors'].update(style='sumi',color='#ab3429',trail='none',intensity=20)
    return value


def merged_theme(previous, target, selected):
    if not set(selected) <= COMPONENTS.keys(): raise ValueError('Unknown theme component.')
    result = copy.deepcopy(previous)
    # Pin dependent appearance choices before switching the palette.
    if result.get('layout') not in layouts.LAYOUTS:result['layout']=layouts.default(previous.get('design','raw'))
    result.setdefault('design',runtime.design());result.setdefault('mode',runtime.mode())
    if 'colors' in selected and target['theme']['design']!=previous.get('design','raw') and 'launcher' not in selected and previous.get('launcher_style', 'follow') == 'follow':
        result['launcher_style'] = previous.get('design', 'raw')
    for component, fields in THEME_FIELDS.items():
        if component in selected:
            for key in fields:
                if key in target['theme']: result[key] = copy.deepcopy(target['theme'][key])
    return result


def resources(root, target, selected, previous_design):
    """Return validated bytes; the backend writes and rolls them back in one transaction."""
    files, reloads = {}, []
    for component in ('transfer', 'switcher', 'terminal', 'cursors'):
        if component in selected and component in target:
            files[root / RESOURCE_PATHS[component]] = encode(target[component])
    if 'colors' in selected and 'transfer' not in selected and target['theme']['design'] != previous_design:
        existing, _ = transfer.load(root / RESOURCE_PATHS['transfer'])
        if existing['style'] == 'follow':
            existing['style'] = previous_design; files[root / RESOURCE_PATHS['transfer']] = encode(existing)
    if 'cursors' in selected and 'cursors' in target:
        reloads.append(('Xetal Desktop Cube', 'xetalcube:cursor'))
    if 'effects' in selected:
        for key, plugin, dispatcher in [('burn', 'Xetal Burn', 'xetalburn:reload'), ('cube', 'Xetal Desktop Cube', 'xetalcube:reload'), ('minimize', 'Xetal Minimize', 'xetalminimize:reload'), ('wobbly', 'Xetal Wobbly Windows', 'xetalwobbly:reload')]:
            if key in target:
                files[root / RESOURCE_PATHS[key]] = burn.encode(target[key]).encode() if key == 'burn' else minimize.encode(target[key]).encode() if key == 'minimize' else encode(target[key])
                reloads.append((plugin, dispatcher))
        if 'appearance' in target: files[root / 'control_center/appearance.conf'] = target['appearance'].encode()
    return files, reloads


def activate_effects(target,ctl):
    """A saved enabled effect should work immediately, including when currently unloaded."""
    if not any(target.get(key,{}).get('enabled') for key in ('burn','cube','minimize','wobbly')):return
    loaded={item.get('name') for item in json.loads(ctl('-j','plugin','list'))}
    for key,name in (('burn','Xetal Burn'),('cube','Xetal Desktop Cube'),('minimize','Xetal Minimize'),('wobbly','Xetal Wobbly Windows')):
        value=target.get(key,{})
        if value.get('enabled') and name not in loaded:
            if key=='burn':from effects.burn import controller
            elif key=='cube':from effects.cube import controller
            elif key=='minimize':from effects.minimize import controller
            else:from effects.wobbly import controller
            controller.activate(value)


def library(path=None):
    path = path or runtime.ROOT / 'custom-presets.json'
    value = json.loads(path.read_text()) if path.exists() else {'version': 1, 'presets': []}
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('presets'), list): raise ValueError('The custom preset library needs repair.')
    for item in value['presets']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not isinstance(item.get('name'), str): raise ValueError('Invalid custom preset.')
        validate(item.get('config'))
    return value


def save(name, config, ident=None, path=None):
    import keys
    name = name.strip()
    if not name or len(name) > 64 or any(not c.isprintable() for c in name): raise ValueError('Use a name between 1 and 64 characters.')
    config = validate(config); path = path or runtime.ROOT / 'custom-presets.json'
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = library(path)
        if any(p['name'].casefold() == name.casefold() and p['id'] != ident for p in data['presets']): raise ValueError('A preset already has this name.')
        item = {'id': ident or uuid.uuid4().hex, 'name': name, 'created': datetime.now(timezone.utc).isoformat(), 'config': config}
        if ident and not any(p['id'] == ident for p in data['presets']): raise ValueError('This preset was removed elsewhere.')
        data['presets'] = [item if p['id'] == ident else p for p in data['presets']] if ident else [*data['presets'], item]
        keys.atomic_write(path, encode(data))
    return item


def remove(ident, path=None):
    import keys
    path = path or runtime.ROOT / 'custom-presets.json'
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX); data = library(path)
        data['presets'] = [p for p in data['presets'] if p['id'] != ident]
        keys.atomic_write(path, encode(data))
