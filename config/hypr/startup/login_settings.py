"""Session-local preference for the login dashboard; manual opening is separate."""
import json
import os
from pathlib import Path
import tempfile


def settings_path():
    root = Path(os.environ.get('XETAL_HYPR_ROOT', Path(__file__).resolve().parents[1]))
    return root / 'control_panel' / 'state' / 'startup-screen.json'


def load(path=None):
    path = Path(path) if path is not None else settings_path()
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError('Startup screen settings must be an object.')
        if type(value.get('show_on_login', True)) is not bool:
            raise ValueError('Startup screen preference must be true or false.')
        return value
    except FileNotFoundError:
        return {}


def enabled():
    return load().get('show_on_login', True)


def save(value):
    if type(value) is not bool:
        raise ValueError('Startup screen preference must be true or false.')
    path = settings_path()
    data = load(path)
    data['show_on_login'] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return value
