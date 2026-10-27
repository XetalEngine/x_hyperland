"""Keep the menu visible while this Hyprland session captures a screenshot."""
import fcntl
import os
from pathlib import Path


def active():
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature:
        return False
    path = Path(runtime) / 'hypr' / signature / 'screenshot-active.lock'
    try:
        with path.open('rb') as guard:
            try:
                fcntl.flock(guard, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False
    except OSError:
        return False
