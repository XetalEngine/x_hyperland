"""Ordered Waybar pins, independent of Favorites and all Plasma settings."""
import fcntl
import json
import os
from pathlib import Path
import tempfile

STATE = Path(__file__).resolve().parent / 'bar-pins.json'


def pinned():
    try:
        data = json.loads(STATE.read_text())
    except FileNotFoundError:
        return []
    if (not isinstance(data, dict) or data.get('version') != 1
            or not isinstance(data.get('pins'), list)
            or not all(isinstance(i, str) and i for i in data['pins'])):
        raise ValueError('The bar pin settings have an unsupported format.')
    return list(dict.fromkeys(data['pins']))


def change(operation):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = pinned()
        after = operation(before.copy())
        if after == before:
            return
        fd, name = tempfile.mkstemp(prefix='.bar-pins-', dir=STATE.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'pins': after}, stream, indent=2)
                stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, STATE)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def pin(app_id, enabled=True):
    if not isinstance(app_id, str) or not app_id:
        raise ValueError('Select an application to pin.')
    def update(items):
        if enabled:
            return items if app_id in items else [*items, app_id]
        return [i for i in items if i != app_id]
    change(update)


def move(app_id, target, after=False):
    def update(items):
        if app_id not in items or target not in items:
            raise ValueError('This pin was removed while dragging. Try again.')
        if app_id == target:
            return items
        items.remove(app_id)
        items.insert(items.index(target) + bool(after), app_id)
        return items
    change(update)


def step(app_id, direction):
    def update(items):
        if app_id not in items:
            return items
        index = items.index(app_id)
        destination = max(0, min(len(items) - 1, index + direction))
        items.insert(destination, items.pop(index))
        return items
    change(update)


def entries(apps):
    result = []
    for ident in pinned():
        entry = apps.get(ident)
        result.append({'id': ident, 'name': entry.get_display_name() if entry else ident,
                       'icon': entry.fields['icon'] if entry else 'dialog-warning',
                       'available': entry is not None})
    return result
