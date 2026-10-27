"""Desktop entries and a read-only view of the active KDE menu favorites."""
from pathlib import Path
import configparser
import json
import re

import gi
from gi.repository import Gio
import shortcuts

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'launcher/favorites.json'


def read_ini(path):
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read(path)
    return config


def kde_favorites(config_root=None):
    root = Path(config_root) if config_root else Path.home() / '.config'
    plasma = read_ini(root / 'plasma-org.kde.plasma.desktop-appletsrc')
    active = []
    for section in plasma.sections():
        if plasma.get(section, 'plugin', fallback='') in ('org.kde.plasma.kickoff', 'org.kde.plasma.kicker'):
            match = re.search(r'Applets\]\[(\d+)', section)
            if match:
                active.append(match[1])
    stats = read_ini(root / 'kactivitymanagerd-statsrc')
    sections = [s for s in stats.sections() if any(f'instance-{i}-' in s for i in active)]
    sections.sort(key=lambda s: not s.endswith('-global'))
    if not sections:
        sections = [s for s in stats.sections() if s.endswith('-global')]
    result = []
    for section in sections:
        for value in stats.get(section, 'ordering', fallback='').split(','):
            value = value.strip().removeprefix('applications:')
            if value == 'preferred://browser':
                browser = Gio.AppInfo.get_default_for_type('text/html', False)
                value = browser.get_id() if browser else ''
            if value and value not in result:
                result.append(value)
    return result


def local_preferences():
    try:
        data = json.loads(LOCAL.read_text())
        return {'add': list(data.get('add', [])), 'hide': list(data.get('hide', []))}
    except (OSError, ValueError, TypeError):
        return {'add': [], 'hide': []}


def favorites():
    data = local_preferences()
    return list(dict.fromkeys(i for i in [*kde_favorites(), *data['add']] if i not in data['hide']))


def pin(app_id, enabled):
    data = local_preferences()
    data['add'] = [i for i in data['add'] if i != app_id]
    data['hide'] = [i for i in data['hide'] if i != app_id]
    if enabled:
        data['add'].append(app_id)
    else:
        data['hide'].append(app_id)
    tmp = LOCAL.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(LOCAL)


def applications():
    pinned = set(favorites())
    result = {}
    for app in Gio.AppInfo.get_all():
        if app.get_id() and (app.should_show() or app.get_id() in pinned):
            result[app.get_id()] = app
    return shortcuts.catalog_entries(result)
