"""Build reset defaults from installer output, never from a personalized desktop."""
import json
from pathlib import Path

from . import archive, catalog
from effects.window_close.rules import KDE_APP_DEFAULTS

LAUNCHER_DEFAULTS = {
    'favorites.json': {'add': ['xetal-files-computer.desktop', 'kitty.desktop', 'xetal-calculator.desktop', 'xmusic.desktop'], 'hide': []},
    'shortcuts.json': {'version': 1, 'overrides': {'xetal-calculator.desktop': {'floating': True}}, 'copies': {}},
    'bar-pins.json': {'version': 1, 'pins': []},
    'window.json': {'width': 980, 'height': 720},
}
THEME_DEFAULTS = dict(design='hp4', mode='dark', layout='sidebar', wallpaper_theme='hp4',
                      bar_style='follow', bar_variant='full', launcher_style='follow',
                      launcher_wallpaper=True, launcher_background='')
WALLPAPER_DEFAULTS = dict(image='hp4/midnight-pit.png', fit='cover')


def build(source, destination, home, *, rendered=False):
    """Called by foreground Setup before any recipient preference merge.

    For an update, capture the source configuration and apply exactly the same
    forced fresh defaults as installer.render. Colors are rendered on activation.
    Release assets and code are already installed and are not duplicated here.
    """
    source, destination, home = Path(source), Path(destination), Path(home)
    roots = catalog.roots(source, home)
    # No runtime/private state from the maintainer checkout can become a default.
    from updates.file_policy import KEEP, PREFERENCES
    records, blobs = [], {}
    private = {'effects/window_close/saved-windows.json', 'settings_profiles/audio.json', 'theme/custom-presets.json',
               'launcher/favorite-layout.json', 'launcher/floating-sizes.json', 'desktop_menu/icons.json',
               'file_manager/automount.json', 'wallpaper/profiles.json'}
    for name in sorted((KEEP | PREFERENCES) - private):
        path = source/name
        if not path.exists(): continue
        if path.is_symlink(): raise ValueError('Factory preferences must be regular files: ' + name)
        data = archive.read_stable(path); sha = archive.digest(data); blobs[sha] = data
        records.append(dict(scope='profile', path=name, category=catalog.profile_category(name), kind='file',
                            sha256=sha, size=len(data), mode=0o600))
    for r in records:
        if r['kind'] != 'file': raise ValueError('Factory preferences must be regular files.')
        try: text = blobs[r['sha256']].decode().replace('@HOME@', str(home)).replace('@HYPR@', str(home/'.config/hypr'))
        except UnicodeDecodeError: continue
        data = text.encode(); sha = archive.digest(data); blobs[sha] = data
        r.update(sha256=sha, size=len(data))
    table = {r['path']: r for r in records}
    def put(name, data):
        data = archive.encode(data) if not isinstance(data, bytes) else data
        sha = archive.digest(data); blobs[sha] = data
        table[name] = dict(scope='profile', path=name, category=catalog.profile_category(name),
                           kind='file', sha256=sha, size=len(data), mode=0o600)
    for name, data in LAUNCHER_DEFAULTS.items(): put('launcher/' + name, data)
    put('theme/icons.json', {'version': 1, 'system': 'other', 'other': 'theme:Papirus-Dark', 'overrides': {}})
    put('workspaces/rules.json', {'version': 1, 'default_layout': 'kde', 'workspaces': {}})
    put('effects/window_close/rules.json', {'version': 1, 'apps': {}})
    put('effects/window_close/kde-rules.json', {'version': 1, 'apps': KDE_APP_DEFAULTS})
    # Always clear maintainer-owned choices which are explicitly not delivered.
    for name in ('theme/custom-presets.json', 'launcher/favorite-layout.json', 'launcher/floating-sizes.json',
                 'desktop_menu/icons.json', 'file_manager/automount.json', 'wallpaper/profiles.json'):
        table.pop(name, None)
    theme = json.loads(blobs[table['theme/state.json']['sha256']]); theme.update(THEME_DEFAULTS)
    put('theme/state.json', theme)
    if not rendered:
        from theme import effect_colors
        for path,data in effect_colors.fresh_files(source,THEME_DEFAULTS['design'],THEME_DEFAULTS['mode']).items():
            put(path.relative_to(source).as_posix(),data)
        put('control_center/displays.conf', b'# Automatic fresh-install monitor detection.\nmonitor = ,preferred,auto,1\n')
        put('control_center/workspaces.conf', b'# Workspaces are assigned to connected outputs at login.\n')
        choice = json.loads(blobs[table['wallpaper/default.json']['sha256']])
        choice.update(WALLPAPER_DEFAULTS)
        put('wallpaper/default.json', choice)
        table.pop('wallpaper/selection.json', None)
        wallpaper = str(home/'.config/hypr/wallpaper'/choice['image'])
        put('wallpaper/hyprpaper.conf', ('ipc = true\nsplash = false\nwallpaper {\n    monitor =\n    path = ' + wallpaper + '\n    fit_mode = cover\n}\n').encode())
    # Standard shell files are defaults, not the exporting user's custom aliases.
    for name in ('.bashrc', '.bash_profile', '.zshrc', '.zprofile'):
        path = Path('/etc/skel') / name
        if path.is_file() and not path.is_symlink():
            data = archive.read_stable(path); sha = archive.digest(data); blobs[sha] = data
            table['home:' + name] = dict(scope='home', path=name, category='terminal', kind='file',
                                         sha256=sha, size=len(data), mode=0o600)
    document = archive.manifest(catalog.USER_IDS, list(table.values()), factory=True, home=str(home),
                                profile=str(home/'.config/hypr'), render_theme=True)
    archive.write(destination, document, blobs)
    return destination
