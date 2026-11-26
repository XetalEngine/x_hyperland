"""Keep disposable compositors away from the desktop's real login seat and VT."""
import os
from pathlib import Path
import re


def nested_environment(environment=None):
    result=dict(os.environ if environment is None else environment)
    # Aquamarine 0.16 does not recognize AQ_BACKENDS. Its DRM probe can open
    # logind even when it eventually falls back to the parent Wayland display.
    # Explicitly selecting a nonexistent libseat backend fails the seat probe
    # before TakeControl/ReleaseControl can alter the real console keyboard.
    result['LIBSEAT_BACKEND']='none'
    for key in ('XDG_SESSION_ID','XDG_SEAT','XDG_VTNR'):
        result.pop(key,None)
    result['HYPRLAND_NO_SD_VARS']='1'
    result['HYPRLAND_NO_SD_NOTIFY']='1'
    return result


def assert_seat_isolated(pid, log_path):
    """Verify the running test compositor has no real seat or input devices."""
    proc=Path('/proc')/str(pid)
    environment=dict(item.split(b'=',1) for item in (proc/'environ').read_bytes().split(b'\0') if b'=' in item)
    if environment.get(b'LIBSEAT_BACKEND')!=b'none' or any(
            name in environment for name in (b'XDG_SESSION_ID',b'XDG_SEAT',b'XDG_VTNR')):
        raise RuntimeError('Test compositor inherited access to a login seat')
    if 'Seat opened with backend' in Path(log_path).read_text(errors='replace'):
        raise RuntimeError('Test compositor opened a physical login seat')
    for fd in (proc/'fd').iterdir():
        try:target=str(fd.readlink())
        except FileNotFoundError:continue  # A descriptor can close during inspection.
        if re.match(r'^/dev/(?:input/|tty(?:\d|$)|dri/card)',target):
            raise RuntimeError('Test compositor opened a physical device: '+target)
