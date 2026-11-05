"""Installed desktop sessions and public account presentation. No authentication."""
from __future__ import annotations
import configparser
from dataclasses import dataclass
import json
from pathlib import Path
import pwd
import shlex
import shutil

DESIGNS = {'raw': 'Xetal Raw', 'modern': 'Xetal Modern',
           'breakpoint': 'BreakPoint', 'binaryknife': 'Binary Knife', 'tidalglass': 'Tidal Glass', 'porcelainink': 'Porcelain Ink', 'obsidianforge': 'Obsidian Forge', 'candycloud': 'Candy Cloud', 'shadowedge': 'Shadow Edge', 'hollowgrove': 'Hollow Grove', 'gildedhollow': 'The Gilded Hollow'}
PROFILES = Path('/var/lib/xetal-fusion-login/profiles')
SESSION_DIRS = (('wayland', Path('/usr/share/wayland-sessions')),
                ('x11', Path('/usr/share/xsessions')))


@dataclass(frozen=True)
class Session:
    identifier: str
    name: str
    kind: str
    desktop: str
    command: tuple[str, ...]


def desktop_command(text, name, path, icon=''):
    """Desktop Entry Exec field codes; never evaluate shell substitutions."""
    result = []
    for token in shlex.split(text):
        if token in ('%f', '%F', '%u', '%U', '%d', '%D', '%n', '%N', '%v', '%m'):
            continue
        if token == '%i':
            if icon: result.extend(('--icon', icon))
            continue
        token = token.replace('%%', '\0').replace('%c', name).replace('%k', str(path))
        if '%' in token: raise ValueError('Unsupported desktop entry field code')
        result.append(token.replace('\0', '%'))
    if not result: raise ValueError('Desktop session has no command')
    return tuple(result)


def sessions(directories=SESSION_DIRS, which=shutil.which):
    result = []
    for kind, directory in directories:
        for path in sorted(directory.glob('*.desktop')):
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read_string(path.read_text())
                entry = parser['Desktop Entry']
                if entry.get('Hidden', 'false').lower() == 'true' or entry.get('NoDisplay', 'false').lower() == 'true':
                    continue
                name = entry.get('Name', path.stem)
                command = desktop_command(entry['Exec'], name, path, entry.get('Icon', ''))
                probe = entry.get('TryExec', command[0])
                if not which(probe): continue
                result.append(Session(kind+':'+path.name, name, kind,
                                      entry.get('DesktopNames', path.stem).replace(';', ':').strip(':'), command))
            except (OSError, KeyError, ValueError, configparser.Error):
                continue
    return sorted(result, key=lambda s: ('hyprland' not in s.identifier.lower(), s.name.casefold(), s.kind))


def accounts(entries=None):
    result = []
    for entry in pwd.getpwall() if entries is None else entries:
        if not 1000 <= entry.pw_uid < 65534 or Path(entry.pw_shell).name in ('nologin', 'false'):
            continue
        result.append({'username': entry.pw_name, 'uid': entry.pw_uid,
                       'name': entry.pw_gecos.split(',')[0].strip() or entry.pw_name})
    return sorted(result, key=lambda a: a['username'].casefold())


def read_json(path):
    try:
        if path.stat().st_size > 65536: return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}


def presentation(account, directory=PROFILES):
    folder = directory / str(account['uid'])
    value = read_json(folder/'profile.json')
    design = value.get('design', 'modern')
    mode = value.get('mode', 'dark')
    result = {'design': design if isinstance(design, str) and design in DESIGNS else 'modern',
              'mode': mode if mode in ('dark', 'light', 'contrast') else 'dark'}
    # Presentation data can refer only to fixed image filenames in this account's folder.
    for key, names in (('avatar', ('avatar.gif', 'avatar.png', 'avatar.jpg', 'avatar.webp')),
                       ('wallpaper', ('wallpaper.png', 'wallpaper.jpg', 'wallpaper.webp'))):
        name = value.get(key)
        path = folder / name if name in names else None
        try: result[key] = path if path and path.is_file() and path.stat().st_size <= 20*1024*1024 else None
        except OSError: result[key] = None
    if result['avatar'] is None:
        icon = Path('/var/lib/AccountsService/icons')/account['username']
        if icon.is_file(): result['avatar'] = icon
    return result


def session_environment(session):
    return ['XDG_SESSION_TYPE='+session.kind, 'XDG_CURRENT_DESKTOP='+session.desktop,
            'XDG_SESSION_DESKTOP='+session.identifier.split(':', 1)[1].removesuffix('.desktop'),
            'DESKTOP_SESSION='+session.identifier.split(':', 1)[1].removesuffix('.desktop'),
            'XETAL_FUSION_SIGNIN=1']
