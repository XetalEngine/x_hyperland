"""Launcher-only shortcut copies and overrides; never write installed desktop files."""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid
import sys

from gi.repository import Gio, GLib
import floating as floating_windows

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'theme'))
import runtime as theme_runtime
STATE = ROOT / 'launcher/shortcuts.json'
ICONS = ROOT / 'launcher/icons'
FIELDS = ('name', 'command', 'icon', 'directory', 'description', 'terminal', 'keep_open', 'floating', 'administrator')


def leave_dashboard():
    try:
        result=subprocess.run(['hyprctl','-j','monitors'],capture_output=True,text=True,timeout=2)
        for monitor in json.loads(result.stdout):
            if monitor.get('focused') and monitor.get('specialWorkspace',{}).get('name')=='special:xetal-startup':
                subprocess.run(['hyprctl','dispatch','togglespecialworkspace','xetal-startup'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
                break
    except (ValueError,OSError,subprocess.TimeoutExpired):pass


def read_state():
    if not STATE.exists():
        return {'version': 1, 'overrides': {}, 'copies': {}}
    data = json.loads(STATE.read_text())
    if data.get('version') != 1 or not all(isinstance(data.get(k), dict) for k in ('overrides', 'copies')):
        raise ValueError('The launcher shortcut settings have an unsupported format.')
    return data


def write_state(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.shortcuts-', dir=STATE.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def fields_for(info):
    return {'name': info.get_display_name() or '', 'command': info.get_commandline() or '',
            'icon': info.get_string('Icon') or '', 'directory': info.get_string('Path') or '',
            'description': info.get_description() or '', 'terminal': info.get_boolean('Terminal'),
            'keep_open': True, 'floating': False, 'administrator': False}


class Entry:
    def __init__(self, app_id, info, changes=None, origin=None, custom=False):
        self.app_id, self.base, self.custom = app_id, info, custom
        self.origin = origin or app_id
        self.changes = changes or {}
        self.fields = fields_for(info) if info else dict.fromkeys(FIELDS, '')
        self.fields.update({'terminal': False, 'keep_open': True, 'floating': False, 'administrator': False} if not info else {})
        self.fields.update({k: v for k, v in self.changes.items() if k in FIELDS})
        self.source = info.get_filename() if info else None

    def __getattr__(self, name):
        return getattr(self.base, name)

    def get_id(self):
        return self.app_id

    def get_display_name(self):
        return self.fields['name']

    def get_description(self):
        return self.fields['description']

    def get_commandline(self):
        return self.fields['command']

    def get_executable(self):
        try:
            return self.argv()[0]
        except (ValueError, GLib.Error):
            return self.fields['command']

    def get_categories(self):
        return self.base.get_categories() if self.base else 'Utility;'

    def get_keywords(self):
        return self.base.get_keywords() if self.base else []

    def get_icon(self):
        name = self.fields['icon']
        if not name:
            return Gio.ThemedIcon.new('application-x-executable')
        if Path(name).is_absolute():
            return Gio.FileIcon.new(Gio.File.new_for_path(name))
        return Gio.ThemedIcon.new(name)

    def argv(self):
        return command_argv(self.fields['command'], self.fields, self.source)

    def launch(self, files=None, context=None, terminal=None, floating=None):
        environment = theme_runtime.environment()
        context = context or Gio.AppLaunchContext()
        for key in ('QT_QPA_PLATFORMTHEME','QT_STYLE_OVERRIDE','QT_PLUGIN_PATH','XETAL_THEME_CONFIG','GTK_THEME','KDE_COLOR_SCHEME_PATH',
                    'XDG_CONFIG_DIRS','XDG_DATA_DIRS','XCURSOR_THEME','XCURSOR_SIZE','XCURSOR_PATH',
                    'GTK_USE_PORTAL','GTK3_MODULES','FONTCONFIG_FILE'):
            if key in environment: context.setenv(key, environment[key])
        in_terminal = self.fields['terminal'] if terminal is None else terminal
        in_float = self.fields['floating'] if floating is None else floating
        managed_launch = bool(environment.get('HYPRLAND_INSTANCE_SIGNATURE')) and not files
        launch_changes = any(k in self.changes for k in ('command', 'directory', 'terminal', 'administrator'))
        if (not managed_launch and self.base and not self.custom and not launch_changes and not in_terminal and not in_float
                and terminal is not False and self.origin not in ('org.kde.dolphin.desktop', 'kitty.desktop')):
            return self.base.launch(files or [], context)
        argv = self.argv()
        # Dolphin and the default terminal retain their Hyprland profiles even
        # when the shortcut name or icon is customized or copied.
        isolated = Path(argv[0]).name in ('dolphin', 'kitty')
        if Path(argv[0]).name == 'dolphin':
            argv[0] = str(ROOT / 'scripts/dolphin.sh')
        elif Path(argv[0]).name == 'kitty' and '--config' not in argv and '-c' not in argv:
            argv[1:1] = ['--config', str(ROOT / 'kitty.conf')]
        directory = self.fields['directory'] or None
        if directory and not Path(directory).is_dir():
            raise ValueError('The working folder no longer exists: ' + directory)
        if self.fields['administrator']:
            argv = [str(ROOT / 'scripts/xsudo.sh'), *argv]
        if in_terminal:
            prefix = ['kitty', '--config', str(ROOT / 'kitty.conf'), '--title', self.fields['name']]
            if self.fields['keep_open']:
                prefix.append('--hold')
            argv = [*prefix, '-e', *argv]
        if in_float or managed_launch:
            if not environment.get('HYPRLAND_INSTANCE_SIGNATURE'):
                raise ValueError('Floating launch is available in the Hyprland session.')
            # Use the app's requested size on its first floating launch; later
            # launches restore only sizes recorded while it was floating.
            ticket = floating_windows.prepare(self, in_terminal, environment, floating=bool(in_float))
            command='exec '+shlex.join(['python3', str(ROOT/'launcher/floating.py'), '--exec-token', ticket['token'],
                                       '--', 'python3', str(ROOT/'theme/run.py'), *argv])
            if directory:command='cd '+shlex.quote(directory)+' && '+command
            success = False
            try:
                result=subprocess.run(['hyprctl','dispatch','exec','['+ticket['rules']+'] '+command],
                                      env=environment,capture_output=True,text=True,timeout=4)
                if result.returncode or result.stdout.strip()!='ok':
                    raise ValueError((result.stderr or result.stdout or 'Could not start a floating window.').strip())
                success = True
            finally:
                try:floating_windows.finish(ticket, success, environment)
                except (OSError, ValueError) as error:print('Floating size memory:', error, file=sys.stderr)
            return result
        if in_terminal or isolated or self.custom or self.changes or terminal is False:
            return subprocess.Popen(argv, cwd=directory, start_new_session=True, env=environment,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.base.launch(files or [], context)


def command_argv(command, fields, source=None):
    try:
        _, tokens = GLib.shell_parse_argv(command)
    except GLib.Error as exc:
        raise ValueError('Check the command and its quotation marks: ' + exc.message) from exc
    result = []
    for token in tokens:
        if token == '%i':
            if fields.get('icon'):
                result.extend(['--icon', fields['icon']])
            continue
        def replace(match):
            code = match[1]
            if code == '%':
                return '%'
            if code in 'fFuUdDnNvm':
                return ''
            if code == 'c':
                return fields.get('name', '')
            if code == 'k':
                return source or ''
            raise ValueError(f'Unknown desktop command placeholder %{code}. Use %% for a literal percent sign.')
        expanded = re.sub(r'%(.)', replace, token)
        if token.endswith('%') and not token.endswith('%%'):
            raise ValueError('Use %% for a literal percent sign in a desktop command.')
        if expanded or not token:
            result.append(expanded)
    if not result or not result[0]:
        raise ValueError('Enter a program and any arguments to launch.')
    return result


def validate(fields):
    cleaned = {k: fields.get(k, '') for k in FIELDS}
    for key in ('name', 'command', 'icon', 'directory', 'description'):
        value = cleaned[key]
        if not isinstance(value, str) or any(c in value for c in '\0\n\r'):
            raise ValueError(f'{key.title()} must be a single line.')
        cleaned[key] = value.strip()
    cleaned['terminal'] = bool(fields.get('terminal'))
    cleaned['keep_open'] = bool(fields.get('keep_open', True))
    cleaned['floating'] = bool(fields.get('floating', False))
    cleaned['administrator'] = bool(fields.get('administrator', False))
    if not cleaned['name']:
        raise ValueError('Give this shortcut a name.')
    argv = command_argv(cleaned['command'], cleaned)
    if not shutil.which(argv[0]):
        raise ValueError('Program not found: ' + argv[0])
    if cleaned['directory']:
        directory = Path(cleaned['directory']).expanduser()
        if not directory.is_dir():
            raise ValueError('Choose an existing working folder.')
        cleaned['directory'] = str(directory.resolve())
    if cleaned['icon'] and (cleaned['icon'].startswith(('/', '~'))):
        icon = Path(cleaned['icon']).expanduser()
        if not icon.is_file():
            raise ValueError('The selected icon file does not exist.')
        cleaned['icon'] = str(icon.resolve())
    return cleaned


def cache_icon(fields, previous=''):
    value = fields['icon']
    if value and value != previous and Path(value).is_absolute():
        source = Path(value)
        ICONS.mkdir(parents=True, exist_ok=True)
        destination = ICONS / (hashlib.sha256(source.read_bytes()).hexdigest()[:24] + source.suffix.lower())
        if source != destination and not destination.exists():
            shutil.copyfile(source, destination)
            destination.chmod(0o600)
        fields['icon'] = str(destination)
    return fields


def save(entry, fields):
    values = cache_icon(validate(fields), entry.fields['icon'])
    data = read_state()
    if entry.custom:
        data['copies'][entry.app_id]['fields'] = values
    else:
        original = fields_for(entry.base)
        delta = {k: v for k, v in values.items() if original.get(k) != v}
        if delta:
            data['overrides'][entry.app_id] = delta
        else:
            data['overrides'].pop(entry.app_id, None)
    write_state(data)
    return entry.app_id


def duplicate(entry, fields):
    values = cache_icon(validate(fields), entry.fields['icon'] if entry else '')
    data = read_state()
    ident = 'xetal-shortcut-' + uuid.uuid4().hex + '.desktop'
    data['copies'][ident] = {'origin': entry.origin if entry else '', 'fields': values}
    write_state(data)
    return ident


def reset(entry):
    data = read_state()
    data['overrides'].pop(entry.app_id, None)
    write_state(data)


def remove_copy(entry):
    if not entry.custom:
        raise ValueError('Only launcher shortcut copies can be removed here.')
    data = read_state()
    data['copies'].pop(entry.app_id, None)
    write_state(data)


def catalog_entries(native):
    data = read_state()
    result = {ident: Entry(ident, app, data['overrides'].get(ident)) for ident, app in native.items()}
    for ident, record in data['copies'].items():
        origin = record.get('origin', '')
        base = native.get(origin) or (Gio.DesktopAppInfo.new(origin) if origin else None)
        result[ident] = Entry(ident, base, record['fields'], origin=origin, custom=True)
    return result
