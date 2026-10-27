"""Window size preference for the Hyprland app menu only."""
import json
import os
from pathlib import Path
import tempfile

STATE = Path(__file__).resolve().parent / 'window.json'
DEFAULT = (980, 720)
MINIMUM = (740, 480)


def size():
    try:
        data = json.loads(STATE.read_text())
        width, height = int(data['width']), int(data['height'])
        if MINIMUM[0] <= width <= 7680 and MINIMUM[1] <= height <= 4320:
            return width, height
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return DEFAULT


def save(width, height):
    fd, name = tempfile.mkstemp(prefix='.window-', dir=STATE.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'width': width, 'height': height}, stream)
            stream.write('\n')
        os.replace(name, STATE)
    finally:
        if os.path.exists(name): os.unlink(name)
