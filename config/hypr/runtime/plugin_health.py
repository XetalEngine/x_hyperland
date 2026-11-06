#!/usr/bin/env python3
"""Read-only health report for the current Hyprland session's native plugins."""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Plugin:
    key: str
    label: str
    name: str
    command: str = ''
    settings: str = ''
    optional: bool = False
    log: str = ''


PLUGINS = (
    Plugin('notices', 'Startup notices', 'Hyper Fusion startup notices'),
    Plugin('window_memory', 'Window memory', 'Xetal Window Memory', 'xetal-windows', log='window-memory.log'),
    Plugin('cursor_probe', 'Cursor detection', 'Xetal Cursor Probe', 'xetal-cursor', log='floating-drag.log'),
    Plugin('burn', 'Burn close effect', 'Xetal Burn', 'xetal-burn', 'effects/burn/settings.conf', True, 'burn.log'),
    Plugin('cube', 'Desktop cube / 3D windows', 'Xetal Desktop Cube', 'xetal-cube', 'effects/cube/settings.json', log='cube.log'),
    Plugin('minimize', 'Minimize / animated dock', 'Xetal Minimize', 'xetal-minimize', 'effects/minimize/settings.conf', log='minimize.log'),
    Plugin('wobbly', 'Wobbly windows', 'Xetal Wobbly Windows', 'xetal-wobbly', 'effects/wobbly/settings.json', True, 'wobbly.log'),
    Plugin('window_close', 'Window buttons / forced layout', 'Xetal Window Close', 'xetal-windowclose',
           'effects/window_close/settings.conf', True, 'window-close.log'),
)


def query(*args):
    result = subprocess.run(['hyprctl', *args], capture_output=True, text=True, timeout=15)
    if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Hyprland IPC failed.')
    try: return json.loads(result.stdout)
    except ValueError: raise RuntimeError(result.stdout.strip() or 'Hyprland returned no status.') from None


def instance_path(env=None):
    env = os.environ if env is None else env
    runtime, signature = env.get('XDG_RUNTIME_DIR'), env.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature or Path(signature).name != signature or signature in ('.', '..'):
        raise RuntimeError('Run fusion-check as your desktop user inside the Hyprland session.')
    instance = Path(runtime)/'hypr'/signature
    if not (instance/'.socket.sock').is_socket(): raise RuntimeError('This Hyprland session has ended or its IPC socket is missing.')
    return instance


def enabled(root, plugin):
    if not plugin.settings: return None
    path = root/plugin.settings
    if path.suffix == '.json':
        value = json.loads(path.read_text())['enabled']
        if type(value) is not bool: raise ValueError('Invalid enabled setting in '+str(path))
        return value
    values = [line.partition('=')[2].strip() for line in path.read_text().splitlines()
              if line.partition('=')[0].strip() == 'enabled']
    if len(values) != 1 or values[0] not in ('0', '1'): raise ValueError('Invalid enabled setting in '+str(path))
    return values[0] == '1'


def required(root, plugin, configured):
    if not plugin.optional or configured: return True
    if plugin.key == 'window_close':
        try: policies = json.loads((root/'workspaces/rules.json').read_text())
        except FileNotFoundError: return False
        return any(p.get('controls') == 'on' for p in policies.get('workspaces', {}).values())
    return False


def startup_detail(instance, plugin):
    try:
        value = json.loads((instance/('plugin-startup-'+plugin.key+'.json')).read_text())
        if not isinstance(value, dict): return {}
        return value
    except (OSError, ValueError): return {}


def last_error(instance, plugin):
    if not plugin.log: return ''
    try:
        with (instance/plugin.log).open('rb') as stream:
            stream.seek(0, 2); stream.seek(max(0, stream.tell()-8192))
            lines = stream.read().decode('utf-8', errors='replace').strip().splitlines()
        return '\n'.join(lines[-8:])[-2000:]
    except OSError: return ''


def inspect(root=ROOT, instance=None, request=query):
    instance = instance_path() if instance is None else instance
    version = request('-j', 'version')
    plugins = request('-j', 'plugin', 'list')
    if not isinstance(version, dict) or not isinstance(plugins, list) or any(not isinstance(p, dict) for p in plugins):
        raise RuntimeError('Hyprland returned an invalid plugin inventory.')
    loaded = {p.get('name'): p for p in plugins}
    rows = []
    for plugin in PLUGINS:
        row = dict(key=plugin.key, name=plugin.name, label=plugin.label, ok=False,
                   loaded=plugin.name in loaded, detail='', log=str(instance/plugin.log) if plugin.log else '')
        startup = startup_detail(instance, plugin)
        try:
            preference = enabled(root, plugin)
            row['enabled'] = preference
            if plugin.name not in loaded:
                if not required(root, plugin, preference):
                    row.update(ok=True, message='Disabled in settings')
                elif startup.get('state') in ('waiting', 'starting', 'retrying'):
                    row.update(message='Still starting / retrying', detail=startup.get('error', ''))
                else:
                    row.update(message='NOT LOADED', detail=startup.get('error') or last_error(instance, plugin))
            else:
                row['version'] = loaded[plugin.name].get('version', '')
                state = request(plugin.command) if plugin.command else {}
                if not isinstance(state, dict): raise RuntimeError('Invalid health response from '+plugin.command)
                if state.get('error'): raise RuntimeError(str(state['error']))
                if preference is not None and state.get('enabled') is not preference:
                    raise RuntimeError('Loaded, but its active enabled setting does not match the saved preference.')
                row.update(ok=True, message='Loaded · responding' if plugin.command else 'Loaded')
                if preference is False: row['message'] += ' · effect disabled'
                if startup.get('error') or startup.get('previous_error'):
                    row['detail'] = 'Recovered after startup error: '+(startup.get('error') or startup['previous_error'])
                if plugin.key == 'minimize':
                    helper = startup_detail(instance, Plugin('minimize-icons', '', ''))
                    if helper.get('state') == 'failed':
                        row.update(ok=False, message='Loaded · dock icon helper failed', detail=helper.get('error', ''))
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
            row.update(message='FAILED', detail=str(error))
        rows.append(row)
    known = {p.name for p in PLUGINS}
    for plugin in plugins:
        if plugin.get('name') not in known:
            rows.append(dict(key='', name=plugin.get('name', 'Unknown plugin'), label=plugin.get('name', 'Unknown plugin'),
                             loaded=True, ok=True, message='Loaded · no Fusion health endpoint', version=plugin.get('version', ''), detail='', log=''))
    return dict(ok=all(row['ok'] for row in rows), hyprland=version, plugins=rows, instance=str(instance))


def safe_text(text):
    # Compositor/plugin diagnostics are data, never terminal control sequences.
    return ''.join(c if c.isprintable() or c == '\n' else ' ' for c in str(text))


def display(report, color=False, stream=None):
    stream = sys.stdout if stream is None else stream
    print('Hyper Fusion · plugin check', file=stream)
    version = report['hyprland']
    print('Hyprland '+safe_text(version.get('version') or version.get('tag') or version.get('commit', 'unknown')), file=stream)
    print(file=stream)
    for row in report['plugins']:
        mark = '[✓]' if row['ok'] else '[✗]'
        if color: mark = ('\033[32m' if row['ok'] else '\033[31m')+mark+'\033[0m'
        print(f"{mark} {safe_text(row['label']):<31} {safe_text(row['message'])}", file=stream)
        if row['detail']:
            for line in safe_text(row['detail']).splitlines(): print('    '+line, file=stream)
        if not row['ok'] and row['log']: print('    Log: '+safe_text(row['log']), file=stream)
    print(file=stream)
    failed = sum(not row['ok'] for row in report['plugins'])
    print(f'{len(report["plugins"])-failed} passed · {failed} need attention', file=stream)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print machine-readable results.')
    parser.add_argument('--color', choices=('auto', 'always', 'never'), default='auto')
    args = parser.parse_args(argv)
    try:
        report = inspect()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        if args.json: print(json.dumps(dict(ok=False, error=str(error))))
        else: print('[✗] '+safe_text(error), file=sys.stderr)
        return 2
    if args.json: print(json.dumps(report, indent=2))
    else: display(report, args.color == 'always' or (args.color == 'auto' and sys.stdout.isatty() and 'NO_COLOR' not in os.environ))
    return 0 if report['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
