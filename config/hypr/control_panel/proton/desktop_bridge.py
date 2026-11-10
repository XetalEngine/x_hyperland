#!/usr/bin/env python3
"""Hyprland URL handlers for saved Proton shortcuts. No shell, daemon or token logs."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

SCHEME = re.compile(r'^[a-z][a-z0-9+.-]*$')
IDENTIFIER = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
RESERVED = {'http', 'https', 'file', 'ftp', 'mailto', 'data', 'javascript', 'about'}


def schemes(value):
    values = list(dict.fromkeys(re.split(r'[\s,;]+', value.strip().lower())))
    if not values or any(not SCHEME.fullmatch(v) or v in RESERVED for v in values):
        raise ValueError('Enter custom URL schemes such as example-app, without ://. Web and file schemes are reserved.')
    return values


def validate(app):
    if not IDENTIFIER.fullmatch(app.get('id', '')):
        raise ValueError('Invalid shortcut identifier.')
    if not isinstance(app.get('schemes'), list) or not app['schemes']:
        raise ValueError('At least one custom URL scheme is required.')
    if schemes(' '.join(app['schemes'])) != app['schemes']:
        raise ValueError('Invalid URL schemes.')
    template = app.get('argument', '')
    if template.count('{url}') != 1 or any(ord(c) < 32 for c in template):
        raise ValueError('The URL argument must contain {url} exactly once, with no line breaks.')
    for key in ('argv', 'callback_argv'):
        if not isinstance(app.get(key), list) or not app[key] or any(not isinstance(v, str) or '\0' in v for v in app[key]):
            raise ValueError('The shortcut launch command is invalid.')
    if not isinstance(app.get('env'), dict) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k)
            or not isinstance(v, str) or '\0' in v for k, v in app['env'].items()):
        raise ValueError('The shortcut environment is invalid.')
    for key in ('cwd', 'prefix'):
        if not isinstance(app.get(key), str) or not Path(app[key]).is_absolute():
            raise ValueError('The working folder and prefix must be absolute paths.')
    return app


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        if default is not None:
            return default
        raise ValueError('The URL handler was removed. Save its shortcut again in Control Panel → Proton.') from None


def atomic_write(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(value)
            os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_bytes(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def defaults(text):
    active = False
    result = {}
    for line in text.splitlines():
        if line.strip().startswith('['):
            active = line.strip() == '[Default Applications]'
        elif active and '=' in line and not line.lstrip().startswith(('#', ';')):
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def edit_defaults(text, changes):
    """Preserve comments, other sections and unrelated associations verbatim."""
    output, written = [], set()
    active = found = False

    def append():
        missing = [(k, v) for k, v in changes.items() if k not in written and v is not None]
        if missing and output and not output[-1].endswith('\n'):
            output[-1] += '\n'
        for key, value in missing:
            output.append(key + '=' + value + '\n')
            written.add(key)

    for line in text.splitlines(keepends=True):
        if line.strip().startswith('['):
            if active:
                append()
            active = line.strip() == '[Default Applications]'
            found |= active
        if active and '=' in line and not line.lstrip().startswith(('#', ';')):
            key = line.split('=', 1)[0].strip()
            if key in changes:
                if key not in written and changes[key] is not None:
                    output.append(key + '=' + changes[key] + '\n')
                written.add(key)
                continue
        output.append(line)
    if active:
        append()
    if not found and any(v is not None for v in changes.values()):
        if output and not output[-1].endswith('\n'):
            output[-1] += '\n'
        output.append('\n[Default Applications]\n')
        append()
    return ''.join(output)


def desktop_quote(value):
    # Desktop-entry string escaping precedes Exec argument parsing.
    if any(ord(c) < 32 for c in value):
        raise ValueError('Handler paths cannot contain control characters.')
    value = value.replace('%', '%%')
    value = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + value.replace('\\', '\\\\') + '"'


def desktop_id(ident):
    return 'xetal-proton-' + ident + '.desktop'


def desktop_entry(app, manifest):
    name = str(app.get('name', 'Windows application')).replace('\\', '\\\\').replace('\n', ' ').replace('\r', ' ')
    command = ' '.join(desktop_quote(v) for v in [sys.executable, str(Path(__file__).resolve()), '--callback', str(manifest)]) + ' %u'
    return ('[Desktop Entry]\nType=Application\nName=' + name + '\n'
            'Comment=Open sign-in links in this Windows application\n'
            'Exec=' + command + '\nTerminal=false\nNoDisplay=true\n'
            'Icon=application-x-executable\nX-XetalProton-Shortcut=' + app['id'] + '\n'
            'MimeType=' + ''.join('x-scheme-handler/' + s + ';' for s in app['schemes']) + '\n').encode()


def sync(request):
    root, storage, config = (Path(request[k]) for k in ('root', 'storage', 'config_home'))
    if not all(p.is_absolute() for p in (root, storage, config)):
        raise ValueError('Handler folders must be absolute paths.')
    apps = [validate(app) for app in request['apps']]
    ids = [app['id'] for app in apps]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate shortcut identifiers.')
    wanted = {}
    for app in apps:
        if app.get('make_default', True):
            for scheme in app['schemes']:
                mime = 'x-scheme-handler/' + scheme
                if mime in wanted:
                    raise ValueError('Only one shortcut can be the default for ' + scheme + ' links.')
                wanted[mime] = desktop_id(app['id'])
    registry = storage / 'registry.json'
    if not apps and not registry.exists():
        return
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (storage / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = read_json(registry, {'version': 1, 'ids': [], 'defaults': {}})
        if previous.get('version') != 1:
            raise ValueError('Unrecognized handler registry; existing settings were preserved.')
        applications = root / 'desktop/data/applications'
        changes = {}
        locations = {config / 'hyprland-mimeapps.list'}
        for directory in (root / 'desktop/config', root / 'apps', root / 'dolphin/config'):
            if directory.is_dir():
                locations.add(directory / 'hyprland-mimeapps.list')
        locations.update(Path(p) for p in previous['defaults'])
        saved_defaults = {}
        for path in locations:
            text = path.read_text() if path.exists() else ''
            current, edits, saved = defaults(text), {}, {}
            old = previous['defaults'].get(str(path), {})
            for mime, record in old.items():
                if mime not in wanted and current.get(mime) == record['owner'] + ';':
                    edits[mime] = record['previous']
            for mime, owner in wanted.items():
                value = current.get(mime)
                before = old.get(mime)
                baseline = before['previous'] if before and value == before['owner'] + ';' else value
                saved[mime] = {'owner': owner, 'previous': baseline}
                edits[mime] = owner + ';'
            updated = edit_defaults(text, edits)
            if updated != text:
                changes[path] = (updated.encode(), path.stat().st_mode & 0o777 if path.exists() else 0o600)
            if saved:
                saved_defaults[str(path)] = saved
        for app in apps:
            manifest = storage / (app['id'] + '.json')
            entry = applications / desktop_id(app['id'])
            if entry.exists() and ('X-XetalProton-Shortcut=' + app['id'] + '\n') not in entry.read_text():
                raise ValueError('A desktop entry with this identifier is owned by another application.')
            document = dict(app, root=str(root), storage=str(storage), config_home=str(config), version=1)
            changes[manifest] = (json_bytes(document), 0o600)
            changes[entry] = (desktop_entry(app, manifest), 0o644)
        for ident in set(previous['ids']) - set(ids):
            if not IDENTIFIER.fullmatch(ident):
                raise ValueError('Invalid stored handler identifier.')
            entry = applications / desktop_id(ident)
            if entry.exists() and ('X-XetalProton-Shortcut=' + ident + '\n') in entry.read_text():
                changes[entry] = None
            changes[storage / (ident + '.json')] = None
            changes[storage / (ident + '.active.json')] = None
        changes[registry] = (json_bytes({'version': 1, 'ids': ids, 'defaults': saved_defaults}), 0o600)
        originals = {p: (p.read_bytes(), p.stat().st_mode & 0o777) if p.exists() else None for p in changes}
        applied = []
        try:
            for path, value in changes.items():
                if value is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, *value)
                applied.append(path)
        except Exception:
            for path in reversed(applied):
                before = originals[path]
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, *before)
            raise
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(applications)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, check=False)


def callback_command(app, url):
    validate(app)
    if not isinstance(url, str) or len(url) > 65536 or any(ord(c) < 32 for c in url):
        raise ValueError('Invalid application link.')
    if urlsplit(url).scheme.lower() not in app['schemes']:
        raise ValueError('This URL scheme is not enabled for the selected application.')
    return app['callback_argv'] + [app['argument'].replace('{url}', url)]


def launch(manifest, url=None, extra=()):
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        raise ValueError('Open this application from your Hyprland session.')
    app = validate(read_json(manifest))
    active = manifest.with_name(app['id'] + '.active.json')
    if url is None:
        registry = read_json(Path(app['storage']) / 'registry.json')
        apps = [read_json(Path(app['storage']) / (ident + '.json')) for ident in registry['ids']]
        sync(dict(root=app['root'], storage=app['storage'], config_home=app['config_home'], apps=apps))
        command = app['argv'] + list(extra)
    else:
        callback_command(app, url)  # A disabled or newly unregistered scheme never uses an old snapshot.
        if active.exists():
            app = validate(read_json(active))
        command = callback_command(app, url)
    env = dict(os.environ, **(app.get('callback_env', app['env']) if url is not None else app['env']))
    private = url is not None or app.get('private_output', True)
    if private:
        env.update(PROTON_LOG='0', PROTON_DUMP_DEBUG_COMMANDS='0', WINEDEBUG='-all')
    executable = shutil.which(command[0], path=env.get('PATH'))
    if not executable or not Path(app['cwd']).is_dir():
        raise ValueError('The runner or working folder is missing. Edit this shortcut in Control Panel → Proton.')
    prefix = Path(app['prefix'])
    (prefix / 'pfx').mkdir(parents=True, exist_ok=True)
    descriptor = os.open(prefix / '.xetalproton.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        raise ValueError('This prefix is busy installing dependencies. Try the link again when it finishes.') from None
    os.set_inheritable(descriptor, True)
    if url is None:
        atomic_write(active, json_bytes(app))
    os.chdir(app['cwd'])
    if private:
        with open(os.devnull, 'wb') as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
    os.execve(executable, command, env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sync', action='store_true')
    mode.add_argument('--launch', type=Path)
    mode.add_argument('--callback', type=Path)
    parser.add_argument('arguments', nargs='*')
    args = parser.parse_args()
    try:
        if args.sync:
            sync(json.load(sys.stdin))
        elif args.callback:
            if len(args.arguments) != 1:
                raise ValueError('A single application link is required.')
            launch(args.callback, url=args.arguments[0])
        else:
            launch(args.launch, extra=args.arguments)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Do not echo argv: a failed sign-in link may still contain valid credentials.
        message = str(error) if isinstance(error, ValueError) else 'Could not access the saved Proton handler. Save the shortcut again.'
        print('Proton browser sign-in: ' + message, file=sys.stderr)
        if not args.sync and shutil.which('notify-send'):
            subprocess.run(['notify-send', 'Proton browser sign-in', message], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5, check=False)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
