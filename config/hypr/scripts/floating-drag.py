#!/usr/bin/env python3
"""An invisible title grip for floating windows in this Hyprland session."""
import fcntl
import math
import os
from pathlib import Path
import runpy
import select
import signal
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from effects.window_close import drag_settings
from effects.session import initialize
from window_rules.window_types import geometry_managed, window_metadata
sys.path.insert(0, str(ROOT/'scripts'))
from drag_cursor import CursorGuard, ensure_probe
sys.path.insert(0, str(ROOT/'launcher'))
from floating import Hypr

# Use the same visible-window selection as the hover tools, including layers,
# pinned windows and fullscreen coverage. Loading this module never runs a kill.
target_at = runpy.run_path(str(ROOT/'scripts/kill-hovered.py'))['target_at']
PRESS = 'custom>>xetal-floating-drag-press'
RELEASE = 'custom>>xetal-floating-drag-release'


def in_grip(window, cursor, border=0):
    if not window or not window.get('floating') or window.get('fullscreen'):
        return False
    if not window.get('mapped') or window.get('hidden'): return False
    x, y = cursor['x']-window['at'][0], cursor['y']-window['at'][1]
    width, height = window['size']
    # Include the visible upper border, with no inset/dead strip. Keep the
    # left/right button clusters alone; resize/text cursors still veto a grab.
    return min(48, width/5) <= x < width-min(96, width/4) and -border <= y < min(32, height/3)


class Drag:
    def __init__(self, hypr, guard=None, settings_loader=drag_settings.load):
        self.hypr, self.candidate, self.dragging = hypr, None, False
        self.last_position = None
        self.guard = guard if guard is not None else CursorGuard(hypr)
        self.press_serial = None
        self.native = False
        self.settings_loader=settings_loader
        self.thresholds=dict(drag_settings.DEFAULTS)

    def hovered(self):
        cursor = self.hypr.query('cursorpos')
        target = target_at(cursor, self.hypr.query('monitors'), self.hypr.query('clients'), self.hypr.query('layers'))
        return cursor, target

    def pressed(self, state):
        if 'origin' not in state:
            # An already loaded older probe is updated at the next login.
            cursor, target = self.hovered()
            return cursor, target, 0
        origin = state['origin']
        if not isinstance(origin, dict): return None, None, 0
        target = next((w for w in self.hypr.query('clients')
                       if w.get('address') == origin.get('address')
                       and w.get('stableId') == origin.get('stableId')), None)
        return origin, target, origin.get('border', 0)

    def press(self, now):
        self.release()
        try:self.thresholds,_=self.settings_loader()
        except (OSError,ValueError):self.thresholds=dict(drag_settings.DEFAULTS)
        state = self.hypr.query('xetal-cursor')
        if not isinstance(state, dict): return
        cursor, target, border = self.pressed(state)
        if in_grip(target, cursor, border) and geometry_managed(target, window_metadata(self.hypr).get(target['address'])):
            self.press_serial = self.guard.allowed(state.get('serial'))
            if self.press_serial is not None:
                self.candidate = (target, cursor, now)

    def tick(self, now):
        if self.candidate is None: return
        target, origin, started = self.candidate
        if now-started > 30:
            self.release(); return
        if self.dragging and self.native:return
        cursor = self.hypr.query('cursorpos')
        if self.dragging:
            self.move(cursor); return
        # Latch rejection until release, even if the pointer leaves the text
        # field. Recheck before the threshold for delayed client cursor updates.
        if self.guard.allowed(self.press_serial) is None:
            self.release(); return
        # Never take over a quick press/release, even if the mouse slips across
        # a tab's close button. Both deliberate hold and motion are required.
        if now-started < self.thresholds['hold_ms']/1000: return
        if math.hypot(cursor['x']-origin['x'], cursor['y']-origin['y']) < self.thresholds['distance']: return
        # The press owns this gesture. A fast pointer can leave the window
        # during the hold delay; that must not discard an otherwise valid grab.
        current = next((w for w in self.hypr.query('clients') if w.get('address') == target.get('address')), None)
        if (current is None or current.get('address') != target.get('address')
                or current.get('stableId') != target.get('stableId')
                or not geometry_managed(current, window_metadata(self.hypr).get(current['address']))
                or current.get('pid') != target.get('pid') or not current.get('mapped')
                or current.get('hidden') or not current.get('floating')
                or current.get('fullscreen') or current['at'] != target['at']
                or current['size'] != target['size']):
            self.candidate = None
            return  # A native title bar may already be handling this gesture.
        # Older installed probes keep the addressed fallback until an update.
        # A native grip uses exactly the same movement as an app title bar.
        state=self.hypr.query('xetal-cursor')
        native=isinstance(state,dict) and state.get('native_drag') is True
        if native:
            self.hypr.dispatch('xetaldrag:begin',target['address']+' '+str(self.press_serial))
            self.native=True;self.dragging=True
            return
        self.hypr.dispatch('tagwindow', '+xetal-title-drag,address:' + target['address'])
        self.dragging = True
        self.move(cursor)

    def move(self, cursor):
        if self.native:return
        target, origin, _ = self.candidate
        if not geometry_managed(target, window_metadata(self.hypr).get(target['address'])):
            self.release(); return
        position = (round(target['at'][0]+cursor['x']-origin['x']),
                    round(target['at'][1]+cursor['y']-origin['y']))
        if position != self.last_position:
            self.hypr.dispatch('movewindowpixel', f'exact {position[0]} {position[1]},address:' + target['address'])
            self.last_position = position

    def release(self):
        target = self.candidate[0] if self.candidate else None
        self.candidate = None
        self.last_position = None
        self.press_serial = None
        if self.dragging:
            self.dragging = False
            native,self.native=self.native,False
            try:
                if native:self.hypr.dispatch('xetaldrag:end','')
                else:self.hypr.dispatch('tagwindow', '-xetal-title-drag,address:' + target['address'])
            except (OSError, ValueError): pass  # The window may have just closed.


def main():
    runtime, signature = os.environ.get('XDG_RUNTIME_DIR'), os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature: return 1
    instance = Path(runtime)/'hypr'/signature
    with (instance/'floating-drag.lock').open('a') as lock, socket.socket(socket.AF_UNIX) as events:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return 0
        events.connect(str(instance/'.socket2.sock'))
        hypr = Hypr(instance)
        # A first-login compile belongs to this helper. Interrupting it must
        # also stop its compiler group; the builder cleans up on SystemExit.
        def cancel_start(*_): raise SystemExit(0)
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(number, cancel_start)
        initialize('cursor_probe', lambda: ensure_probe(hypr), instance, threading.Event())
        drag = Drag(hypr)
        drag.guard.refresh()
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(number, stop)
        pending = b''
        try:
            while not stopping:
                if select.select([events], [], [], .016 if drag.candidate else 1)[0]:
                    chunk = events.recv(65536)
                    if not chunk: break
                    pending += chunk
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        event = line.decode(errors='replace')
                        try:
                            if event == PRESS: drag.press(time.monotonic())
                            elif event == RELEASE or event.startswith(('submap>>', 'workspace>>', 'closewindow>>', 'changefloatingmode>>', 'fullscreen>>')):
                                drag.release()
                        except (OSError, ValueError, KeyError, TypeError): drag.release()
                try: drag.tick(time.monotonic())
                except (OSError, ValueError, KeyError, TypeError): drag.release()
        finally:
            try: drag.release()
            except (OSError, ValueError): pass
    return 0


if __name__ == '__main__': raise SystemExit(main())
