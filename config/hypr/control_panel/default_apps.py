#!/usr/bin/env python3
"""Desktop app associations, shared by the panel and the folder launcher.

Only an explicit apply/undo request writes preferences. Association files follow
the freedesktop MIME Apps specification; installed desktop entries remain intact.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

from gi.repository import Gio

ROOT = Path(__file__).resolve().parents[1]
TYPE = re.compile(r'^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$')
APP_ID = re.compile(r'^[^\x00-\x20/\\;=]+\.desktop$')

# Broad media choices cover installed MIME definitions, including uncommon
# formats. Documents remain separate from plain text and web pages.
ROLES = [
    ('browser', 'Web browser', 'Websites and web links', 'internet-web-browser',
     ['x-scheme-handler/https', 'x-scheme-handler/http', 'text/html', 'application/xhtml+xml']),
    ('email', 'Email', 'Email links and messages', 'internet-mail',
     ['x-scheme-handler/mailto', 'message/rfc822']),
    ('files', 'File manager', 'Folders, Super + E and Show in folder', 'system-file-manager', ['inode/directory']),
    ('music', 'Music', 'Songs, albums and audio files', 'audio-x-generic', ['audio/mpeg']),
    ('video', 'Video', 'Movies, clips and recordings', 'video-x-generic', ['video/mp4']),
    ('images', 'Images', 'Photos, screenshots and artwork', 'image-x-generic', ['image/png']),
    ('pdf', 'PDF reader', 'PDF documents and books', 'application-pdf', ['application/pdf']),
    ('text', 'Text editor', 'Notes, source code and configuration', 'text-x-generic',
     ['text/plain', 'text/markdown', 'application/json', 'application/xml', 'application/x-yaml', 'application/javascript', 'application/x-shellscript']),
    ('archives', 'Archives', 'Compressed files and packages', 'package-x-generic',
     ['application/zip', 'application/x-7z-compressed', 'application/vnd.rar', 'application/x-rar',
      'application/x-tar', 'application/gzip', 'application/x-bzip2', 'application/x-xz',
      'application/zstd', 'application/x-compressed-tar', 'application/x-bzip-compressed-tar',
      'application/x-xz-compressed-tar', 'application/x-zstd-compressed-tar', 'application/x-lzma',
      'application/x-lzma-compressed-tar', 'application/x-lzip', 'application/x-lzip-compressed-tar']),
    ('documents', 'Documents', 'Word and OpenDocument text', 'x-office-document',
     ['application/vnd.oasis.opendocument.text', 'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/rtf']),
    ('spreadsheets', 'Spreadsheets', 'Tables, workbooks and CSV files', 'x-office-spreadsheet',
     ['application/vnd.oasis.opendocument.spreadsheet', 'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv']),
    ('presentations', 'Presentations', 'Slides and presentations', 'x-office-presentation',
     ['application/vnd.oasis.opendocument.presentation', 'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation']),
]


def association_paths():
    """Include profile fallbacks used by apps with isolated config homes."""
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
    desktops = [d.lower() for d in os.environ.get('XDG_CURRENT_DESKTOP', '').split(':')
                if re.fullmatch(r'[A-Za-z0-9_-]+', d)]
    roots = [(config, True), (ROOT/'desktop/config', (ROOT/'desktop/config').is_dir()),
             (ROOT/'dolphin/config', False), (ROOT/'apps', False)]
    result = {}
    for directory, create in roots:
        generic = directory/'mimeapps.list'
        if create or generic.is_file():
            result[generic.resolve()] = False
        for desktop in desktops:
            specific = directory/(desktop+'-mimeapps.list')
            if specific.is_file():
                result[specific.resolve()] = True
    return result


def read(path):
    return path.read_text(encoding='utf-8') if path.exists() else None


def digest(value):
    return hashlib.sha256(('missing' if value is None else 'file\0'+value).encode()).hexdigest()


def revision():
    return digest(json.dumps([(str(p), digest(read(p))) for p in association_paths()]))


def icon_name(icon):
    if isinstance(icon, Gio.ThemedIcon):
        return next(iter(icon.get_names()), 'application-x-executable')
    if isinstance(icon, Gio.FileIcon):
        return icon.get_file().get_path() or 'application-x-executable'
    return 'application-x-executable'


def installed():
    return {a.get_id(): a for a in Gio.AppInfo.get_all()
            if a.get_id() and APP_ID.fullmatch(a.get_id())}


def registered_types(apps):
    result = set(Gio.content_types_get_registered())
    for app in apps.values():
        result.update(app.get_supported_types() or [])
    for role in ROLES:
        result.update(role[4])
    return sorted(t for t in result if TYPE.fullmatch(t))


def role_types(role, types):
    ident = role[0]
    result = set(role[4])
    prefixes = {'music': 'audio/', 'video': 'video/', 'images': 'image/'}
    if ident in prefixes:
        result.update(t for t in types if t.startswith(prefixes[ident]))
    if ident == 'text':
        excluded = {'text/html', 'text/csv', 'text/calendar', 'text/vcard', 'text/directory', 'text/rtf'}
        result.update(t for t in types if t.startswith('text/') and t not in excluded)
    return sorted(result)


def extensions():
    result = {}
    data_home = os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))
    for directory in [data_home, *os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')]:
        path = Path(directory)/'mime/globs2'
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            parts = line.split(':')
            if len(parts) >= 3 and not line.startswith('#'):
                result.setdefault(parts[1], set()).add(parts[2])
    return {key: '  '.join(sorted(values)) for key, values in result.items()}


def snapshot():
    token = revision()
    apps = installed()
    types = registered_types(apps)
    defaults = {}
    for mime in types:
        app = Gio.AppInfo.get_default_for_type(mime, False)
        defaults[mime] = app.get_id() if app else ''
        if app and app.get_id() and APP_ID.fullmatch(app.get_id()):
            apps.setdefault(app.get_id(), app)
    current = set(defaults.values())
    applications = [dict(id=ident, name=app.get_display_name(), description=app.get_description() or '',
                         icon=icon_name(app.get_icon()), types=list(app.get_supported_types() or []))
                    for ident, app in apps.items()
                    if app.should_show() or ident in current or ident == 'xetal-dolphin.desktop']
    roles = []
    for role in ROLES:
        members = role_types(role, types)
        chosen = defaults.get(role[4][0], '')
        roles.append(dict(id=role[0], title=role[1], description=role[2], icon=role[3],
                          types=members, default=chosen,
                          mixed=any(defaults.get(m, '') != chosen for m in members)))
    globs = extensions()
    filetypes = [dict(id=mime, name=(mime.split('/', 1)[1].upper()+' links')
                     if mime.startswith('x-scheme-handler/') else (Gio.content_type_get_description(mime) or mime),
                     extensions=globs.get(mime, ''), default=defaults[mime]) for mime in types]
    return dict(revision=token, apps=sorted(applications, key=lambda a: (a['name'].casefold(), a['id'])),
                roles=roles, filetypes=filetypes)


def entries(text, section):
    result = {}
    active = False
    for line in (text or '').splitlines():
        if line.strip().startswith('['):
            active = line.strip() == '['+section+']'
        elif active and '=' in line and not line.lstrip().startswith(('#', ';')):
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def edit_section(text, section, changes):
    """Keep comments, unrelated preferences and their ordering byte-for-byte."""
    lines = (text or '').splitlines(keepends=True)
    output, written = [], set()
    active = found = False
    def append_missing():
        if output and not output[-1].endswith('\n'):
            output[-1] += '\n'
        for key, value in changes.items():
            if key not in written and value is not None:
                output.append(key+'='+value+'\n')
                written.add(key)
    for line in lines:
        if line.strip().startswith('['):
            if active:
                append_missing()
            active = line.strip() == '['+section+']'
            found |= active
        if active and '=' in line and not line.lstrip().startswith(('#', ';')):
            key = line.split('=', 1)[0].strip()
            if key in changes:
                if key not in written and changes[key] is not None:
                    output.append(key+'='+changes[key]+'\n')
                written.add(key)
                continue
        output.append(line)
    if active:
        append_missing()
    if not found and any(v is not None for v in changes.values()):
        if output and not output[-1].endswith('\n'):
            output[-1] += '\n'
        if output and output[-1].strip():
            output.append('\n')
        output.append('['+section+']\n')
        append_missing()
    return ''.join(output)


def updated(text, types, app_id, desktop_specific=False):
    result = edit_section(text, 'Default Applications', {m: app_id+';' for m in types})
    if not desktop_specific:
        existing = entries(text, 'Added Associations')
        result = edit_section(result, 'Added Associations', {
            m: ';'.join(dict.fromkeys([app_id, *filter(None, existing.get(m, '').split(';'))]))+';' for m in types})
        removed = entries(text, 'Removed Associations')
        changes = {}
        for mime in types:
            if app_id in removed.get(mime, '').split(';'):
                values = [a for a in removed[mime].split(';') if a and a != app_id]
                changes[mime] = ';'.join(values)+';' if values else None
        result = edit_section(result, 'Removed Associations', changes)
    return result


def atomic_write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def apply_choice(data, *, applications=None):
    apps = installed() if applications is None else applications
    ident = data.get('app', '')
    if not isinstance(ident, str) or not APP_ID.fullmatch(ident) or ident not in apps:
        raise ValueError('That app is no longer installed. Refresh the list and choose another app.')
    types = registered_types(apps)
    if data.get('role'):
        role = next((r for r in ROLES if r[0] == data['role']), None)
        if role is None:
            raise ValueError('Unknown default-app category.')
        selected = role_types(role, types)
        title = role[1]
    elif isinstance(data.get('type'), str) and data['type'] in types:
        selected, title = [data['type']], data['type']
    else:
        raise ValueError('Choose a registered file type or link.')
    if data.get('revision') != revision():
        raise ValueError('Defaults changed elsewhere. Refresh the page before choosing an app.')
    changes = []
    for path, specific in association_paths().items():
        before = read(path)
        changes.append(dict(path=str(path), before=before,
                            after=updated(before, selected, ident, specific),
                            mode=path.stat().st_mode & 0o777 if path.exists() else 0o600))
    completed = []
    try:
        for change in changes:
            path = Path(change['path'])
            if read(path) != change['before']:
                raise ValueError('Defaults changed while saving. Please refresh and try again.')
            atomic_write(path, change['after'], change['mode'])
            completed.append(change)
        token = uuid.uuid4().hex
        atomic_write(ROOT/'control_panel/state/default-apps/last-change.json',
                     json.dumps(dict(token=token, changes=changes), ensure_ascii=False))
    except (OSError, ValueError):
        for change in reversed(completed):
            path = Path(change['path'])
            if read(path) == change['after']:
                if change['before'] is None:
                    path.unlink()
                else:
                    atomic_write(path, change['before'], change['mode'])
        raise
    return dict(ok=True, undo=token, message=apps[ident].get_display_name()+' is now the default for '+title+'.')


def undo(data):
    saved = ROOT/'control_panel/state/default-apps/last-change.json'
    try:
        record = json.loads(saved.read_text())
    except (OSError, ValueError):
        raise ValueError('No saved change is available to undo.')
    if record.get('token') != data.get('token'):
        raise ValueError('A newer change was saved. Refresh the page first.')
    allowed = association_paths()
    for change in record['changes']:
        path = Path(change['path'])
        if path not in allowed or read(path) != change['after']:
            raise ValueError('Defaults changed elsewhere. Undo would replace newer settings.')
    completed = []
    try:
        for change in record['changes']:
            path = Path(change['path'])
            if read(path) != change['after']:
                raise ValueError('Defaults changed while restoring. Please refresh and try again.')
            if change['before'] is None:
                path.unlink()
            else:
                atomic_write(path, change['before'], change['mode'])
            completed.append(change)
        saved.unlink()
    except (OSError, ValueError):
        for change in reversed(completed):
            path = Path(change['path'])
            if read(path) == change['before']:
                atomic_write(path, change['after'], change['mode'])
        raise
    return dict(ok=True, message='Your previous defaults were restored.')


def prepare_session_environment():
    """Give notification/IPC helpers the same app defaults as the desktop.

    Old background processes can predate the session environment configuration.
    Only this process is changed; user defaults still outrank profile fallbacks.
    """
    for variable, local, fallback in (
        ('XDG_CONFIG_DIRS', ROOT/'desktop/config', '/etc/xdg'),
        ('XDG_DATA_DIRS', ROOT/'desktop/data', '/usr/local/share:/usr/share'),
    ):
        paths = [str(local), *os.environ.get(variable, fallback).split(':')]
        os.environ[variable] = ':'.join(dict.fromkeys(p for p in paths if p))


def open_folder(arguments):
    """Use the chosen folder handler; the Fusion desktop entry stays direct."""
    select = bool(arguments and arguments[0] == '--select')
    if select:
        arguments = arguments[1:]
    app = Gio.AppInfo.get_default_for_type('inode/directory', False)
    if not app or app.get_id() == 'xetal-files.desktop':
        command = [str(ROOT/'scripts/files.sh'), *(['--select'] if select else []), *arguments]
        os.execv(command[0], command)
    if select and app.get_id() in ('org.kde.dolphin.desktop', 'xetal-dolphin.desktop'):
        # An explicit alternative should retain Show in folder's selection.
        import shutil
        executable = str(ROOT/'scripts/dolphin.sh') if app.get_id() == 'xetal-dolphin.desktop' else shutil.which('dolphin')
        if executable:
            os.execv(executable, [executable, '--select', *arguments])
    files = [Gio.File.new_for_commandline_arg(a) for a in arguments] if arguments else [Gio.File.new_for_path(str(Path.home()))]
    if select:
        files = [f.get_parent() or f for f in files]
    if not app.launch(files, Gio.AppLaunchContext()):
        raise ValueError('The selected file manager could not be opened.')
    return 0


def main():
    try:
        prepare_session_environment()
        action = sys.argv[1] if len(sys.argv) > 1 else 'snapshot'
        if action == 'open-folder':
            return open_folder(sys.argv[2:])
        if action == 'snapshot':
            result = snapshot()
        elif action in ('apply', 'undo'):
            data = json.load(sys.stdin)
            if not isinstance(data, dict):
                raise ValueError('Invalid default-app request.')
            state = ROOT/'control_panel/state/default-apps'
            state.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (state/'change.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = apply_choice(data) if action == 'apply' else undo(data)
        else:
            raise ValueError('Unknown default-app action.')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        # Gio errors and filesystem failures must reach the page, not disappear
        # into a session log. No command text or environment is returned.
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
