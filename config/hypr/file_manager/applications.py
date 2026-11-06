#!/usr/bin/env python3
"""App discovery and launching without depending on a Plasma application menu."""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import sys
import uuid

from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'control_panel'))
import default_apps


def application_output():
    """Give launched apps a durable stream, separate from this helper's JSON."""
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if runtime and signature and Path(signature).name == signature and signature not in ('.', '..'):
        instance = Path(runtime)/'hypr'/signature
        if instance.is_dir():
            sys.path.insert(0, str(ROOT/'scripts'))
            import session_logging
            try:
                return session_logging.log_path(instance, 'file-applications.log').open('ab')
            except (OSError, ValueError):
                pass
    return open(os.devnull, 'ab')


def open_uris(app, urls):
    # ApplicationJob closes its QProcess pipes as soon as our JSON reply is
    # received. Sharing those pipes with a GUI app can corrupt that reply or
    # kill the app with SIGPIPE when it prints a startup diagnostic later.
    # GLib still handles desktop Exec field codes, terminals and D-Bus launch.
    with open(os.devnull, 'rb') as source, application_output() as output:
        return app.launch_uris_as_manager_with_fds(
            urls, Gio.AppLaunchContext(), GLib.SpawnFlags.SEARCH_PATH,
            None, None, None, None, source.fileno(), output.fileno(), output.fileno())


def choices(data):
    mimes = data.get('mimes', [])
    preferred = set()
    recommended = set()
    for mime in mimes:
        app = Gio.AppInfo.get_default_for_type(mime, False)
        if app:
            preferred.add(app.get_id())
        recommended.update(app.get_id() for app in Gio.AppInfo.get_recommended_for_type(mime) or [])
    apps = []
    for ident, app in default_apps.installed().items():
        if not (app.should_show() or ident in preferred):
            continue
        apps.append(dict(id=ident, name=app.get_display_name(),
                         description=app.get_description() or '',
                         executable=app.get_executable() or '',
                         icon=default_apps.icon_name(app.get_icon()),
                         recommended=ident in recommended, preferred=ident in preferred))
    apps.sort(key=lambda a: (not a['preferred'], not a['recommended'], a['name'].casefold(), a['id']))
    return dict(apps=apps, revision=default_apps.revision())


def launch(data):
    urls = data.get('urls', [])
    if not urls or not all(isinstance(url, str) and '\0' not in url for url in urls):
        raise ValueError('Choose files to open.')
    apps = default_apps.installed()
    mime = data.get('mime', '')
    command = data.get('command', '').strip()
    custom = None
    if command:
        # GLib parses desktop Exec arguments; never pass this through a shell.
        flags = Gio.AppInfoCreateFlags.SUPPORTS_URIS
        if data.get('terminal'):
            flags |= Gio.AppInfoCreateFlags.NEEDS_TERMINAL
        app = Gio.AppInfo.create_from_commandline(command, 'Custom application', flags)
    else:
        app = apps.get(data.get('app')) if data.get('app') else Gio.AppInfo.get_default_for_type(mime, False)
    if app is None:
        raise ValueError('No application is available. Choose Open with… and select an installed app.')
    if data.get('remember'):
        state = ROOT/'control_panel/state/default-apps'
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (state/'change.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if data.get('revision') != default_apps.revision():
                raise ValueError('Default apps changed elsewhere. Reopen the chooser and try again.')
            if command:
                directory = Path(GLib.get_user_data_dir())/'applications'
                directory.mkdir(parents=True, exist_ok=True)
                custom = directory/('xetal-openwith-'+uuid.uuid4().hex+'.desktop')
                entry = GLib.KeyFile()
                for key, value in [('Type', 'Application'), ('Name', app.get_name()),
                                   ('Exec', app.get_commandline()), ('Icon', 'application-x-executable')]:
                    entry.set_string('Desktop Entry', key, value)
                entry.set_boolean('Desktop Entry', 'NoDisplay', True)
                entry.set_boolean('Desktop Entry', 'Terminal', bool(data.get('terminal')))
                text, _ = entry.to_data()
                default_apps.atomic_write(custom, text)
                app = Gio.DesktopAppInfo.new_from_filename(str(custom))
                if app is None:
                    custom.unlink()
                    raise ValueError('The custom application could not be saved.')
            apps[app.get_id()] = app
            try:
                default_apps.apply_choice(dict(app=app.get_id(), type=mime, revision=data['revision']), applications=apps)
            except Exception:
                if custom:
                    custom.unlink(missing_ok=True)
                raise
    if not open_uris(app, urls):
        raise ValueError('The application could not be started.')
    return dict(ok=True)


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError('Invalid application request.')
        action = sys.argv[1] if len(sys.argv) == 2 else ''
        if action not in ('choices', 'launch'):
            raise ValueError('Unknown application action.')
        result = choices(data) if action == 'choices' else launch(data)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps(dict(error=str(error)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
