"""Keep a Waybar click from reopening a menu dismissed by that same click."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

MAX_AGE = 1.5


def marker_path():
    runtime=os.environ.get('XDG_RUNTIME_DIR')
    signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature:return None
    return Path(runtime)/'hypr'/signature/'launcher-dismissed.json'


def pointer():
    try:
        result=subprocess.run(['hyprctl','-j','cursorpos'],capture_output=True,text=True,timeout=.5,check=True)
        value=json.loads(result.stdout);position=[float(value['x']),float(value['y'])]
        return position if all(math.isfinite(v) for v in position) else None
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):return None


def remember():
    path=marker_path()
    if path is None:return
    position=pointer()
    if position is None:return
    temporary=None
    try:
        fd,temporary=tempfile.mkstemp(prefix='.launcher-dismissed-',dir=path.parent)
        with os.fdopen(fd,'w') as stream:
            json.dump({'time':time.monotonic(),'position':position},stream)
        os.replace(temporary,path)
    except OSError:pass
    finally:
        if temporary:
            try:Path(temporary).unlink(missing_ok=True)
            except OSError:pass


def clear():
    path=marker_path()
    if path:
        try:path.unlink(missing_ok=True)
        except OSError:pass


def consume():
    """Used only for the bar button; hotkeys always keep their usual behavior."""
    path=marker_path()
    if path is None:return False
    try:
        value=json.loads(path.read_text())
        age=time.monotonic()-float(value['time'])
        old=value['position']
        if not 0<=age<=MAX_AGE or len(old)!=2:return False
        position=pointer()
        return position is not None and all(math.isfinite(float(v)) for v in old) and math.dist(position,old)<=12
    except (OSError,ValueError,KeyError,TypeError):return False
    finally:clear()
