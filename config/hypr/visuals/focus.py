"""Small, cached focus policy shared by Fusion client headers."""
import time
from visuals import model,controller
_checked=0.
_enabled=False


def header_enabled():
    global _checked,_enabled
    now=time.monotonic()
    if now-_checked> .25:
        _checked=now
        try:_enabled=model.theme_settings(controller.runtime_settings(),model.theme_name())['focus']['enabled']
        except (OSError,ValueError):_enabled=False
    return _enabled
