#!/usr/bin/env python3
"""File logging preferences, latched once per Hyprland login."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def setting_path(root=ROOT):
    return root / 'control_panel/state/runtime-log-guard.json'


def preferences(root=ROOT):
    value = {'version': 1, 'enabled': True, 'disable_file_logs': False}
    try: saved = json.loads(setting_path(root).read_text())
    except FileNotFoundError: return value
    if (not isinstance(saved, dict) or saved.get('version') != 1
            or type(saved.get('enabled')) is not bool
            or type(saved.get('disable_file_logs', False)) is not bool):
        raise ValueError('The session log settings are invalid.')
    return {**value, **saved}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)


def save(key, value, root=ROOT):
    if key not in ('enabled', 'disable_file_logs') or type(value) is not bool:
        raise ValueError('Invalid session log preference.')
    settings = preferences(root)
    settings[key] = value
    write_json(setting_path(root), settings)


def current(instance):
    try: value = json.loads((instance/'session-logging.json').read_text())
    except FileNotFoundError: return {'version': 1, 'disabled': False}
    if not isinstance(value, dict) or value.get('version') != 1 or type(value.get('disabled')) is not bool:
        raise ValueError('The current session logging status is invalid.')
    return value


def begin(instance, root=ROOT):
    # session.sh holds its singleton lock. Re-executing it after an update must
    # retain the current policy, including for processes already holding logs.
    if not (instance/'session-logging.json').exists():
        write_json(instance/'session-logging.json',
                   {'version': 1, 'disabled': preferences(root)['disable_file_logs']})
    return current(instance)


def log_path(instance, name):
    if Path(name).name != name or not name.endswith('.log'):
        raise ValueError('Expected a session log filename.')
    return Path(os.devnull) if current(instance)['disabled'] else instance/name


def main():
    if len(sys.argv) != 3 or sys.argv[1] != '--path': return 2
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature or Path(signature).name != signature: return 1
    print(log_path(Path(runtime)/'hypr'/signature, sys.argv[2]))
    return 0


if __name__ == '__main__': raise SystemExit(main())
