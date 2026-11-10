"""Pin direct Control Panel page shortcuts in the shared Apps Favorites."""
import json
import os
from pathlib import Path
import sys
import tempfile

from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'launcher'))
import catalog


def tools():
    groups = json.loads((ROOT/'control_panel/tools.json').read_text())
    return {tool['id']: tool for group in groups for tool in group['tools']}


def desktop_id(ident):
    return 'xetal-control-panel-' + ident + '.desktop'


def applications_dir():
    location = Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')
    if not location.is_absolute():
        location = Path.home()/'.local/share'
    return location/'applications'


def owned_entry(path, ident):
    if path.is_symlink():
        return None
    try:
        info = Gio.DesktopAppInfo.new_from_filename(str(path)) if path.is_file() else None
    except (TypeError, GLib.Error):
        # PyGObject raises for a malformed file instead of returning nullptr.
        return None
    if (info and info.get_string('X-HyperFusion-ControlPanelTool') == ident
            and info.get_string('X-HyperFusion-ControlPanelRoot') == str(ROOT)):
        return info
    return None


def snapshot():
    pinned = set(catalog.favorites())
    directory = applications_dir()
    return {'favorites': [ident for ident in tools()
                          if desktop_id(ident) in pinned and owned_entry(directory/desktop_id(ident), ident)]}


def exec_quote(value):
    if any(ord(char) < 32 for char in value):
        raise ValueError('Shortcut paths cannot contain control characters.')
    # KeyFile handles the outer desktop-file escaping; this is Exec quoting.
    value = value.replace('%', '%%')
    return '"' + ''.join('\\' + char if char in '\\"`$' else char for char in value) + '"'


def entry_bytes(tool):
    entry = GLib.KeyFile()
    fields = {
        'Type': 'Application', 'Name': tool['title'],
        'Comment': 'Control Panel · ' + tool.get('description', ''),
        'Icon': tool.get('icon', 'preferences-system'),
        'Exec': ' '.join(exec_quote(value) for value in
                         [sys.executable, str(ROOT/'session_ui/client.py'), 'panel', '--section', tool['id']]),
        'Terminal': 'false', 'NoDisplay': 'true', 'Categories': 'Settings;System;',
        'X-HyperFusion-ControlPanelTool': tool['id'],
        'X-HyperFusion-ControlPanelRoot': str(ROOT),
    }
    for key, value in fields.items():
        entry.set_string('Desktop Entry', key, value)
    return entry.to_data()[0].encode()


def set_favorite(data):
    ident, enabled = data.get('id'), data.get('enabled')
    available = tools()
    if not isinstance(ident, str) or ident not in available:
        raise ValueError('Unknown Control Panel tool.')
    if type(enabled) is not bool:
        raise ValueError('Favorite selection must be true or false.')
    path = applications_dir()/desktop_id(ident)
    created = None
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(path):
            if not owned_entry(path, ident):
                raise ValueError('A different shortcut already uses this name; it was left unchanged: ' + str(path))
        else:
            fd, temporary = tempfile.mkstemp(prefix='.panel-favorite-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(entry_bytes(available[ident]))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, 0o644)
                # Publish fully written data without overwriting a new file.
                try:
                    os.link(temporary, path)
                    created = path.stat()
                except FileExistsError:
                    if not owned_entry(path, ident):
                        raise ValueError('A different shortcut was created at this path; it was left unchanged.')
            finally:
                os.unlink(temporary)
    try:
        catalog.pin(desktop_id(ident), enabled)
    except (OSError, ValueError):
        if created and path.exists() and not path.is_symlink():
            current = path.stat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                path.unlink()
        raise
    # Keep the hidden desktop entry on unpin: other user shortcuts may refer
    # to it. It does not appear in All apps unless the user pins it again.
    return snapshot()
