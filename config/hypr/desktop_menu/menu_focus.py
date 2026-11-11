"""Bind a popup to its invocation, not the arrival order of IPC notifications."""
from dataclasses import dataclass
import json
import subprocess


@dataclass(frozen=True)
class Monitor:
    workspace: int
    special: int
    origin: tuple[int, int]


@dataclass(frozen=True)
class Session:
    monitors: dict[str, Monitor]
    focused: str
    active_window: str


def read_session(env):
    # Both replies describe one compositor turn. Socket2 events can lag behind
    # the Wayland button event, so their payloads are not the current state.
    try:
        reply = subprocess.check_output(
            ['hyprctl', '--batch', 'j/monitors; j/activewindow'], env=env,
            text=True, timeout=.5, stderr=subprocess.DEVNULL).lstrip()
        monitors, end = json.JSONDecoder().raw_decode(reply)
        active = json.loads(reply[end:])
        if not isinstance(monitors, list) or not isinstance(active, dict):
            return None
        states = {}
        focused = ''
        for monitor in monitors:
            name = monitor['name']
            if not isinstance(name, str) or not name:
                return None
            states[name] = Monitor(int(monitor['activeWorkspace']['id']),
                                  int(monitor['specialWorkspace']['id']),
                                  (int(monitor['x']), int(monitor['y'])))
            if monitor['focused']:
                focused = name
        address = active.get('address', '')
        if not isinstance(address, str):
            return None
        return Session(states, focused, address)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        # A failed query is not evidence that the user left the menu. GTK still
        # owns its ordinary outside-click / Escape / popup-grab dismissal.
        return None


@dataclass
class MenuContext:
    monitor: str
    workspace: int
    special: int
    focused: str
    active_window: str

    @classmethod
    def capture(cls, session, monitor, origin):
        if session is None:
            return None
        if monitor not in session.monitors:
            # The first click can precede the icon layout's connector lookup.
            monitor = next((name for name, state in session.monitors.items()
                            if state.origin == origin), None)
        state = session.monitors.get(monitor)
        if state is None:
            return None
        return cls(monitor, state.workspace, state.special,
                   session.focused, session.active_window)

    def changed(self, session):
        if session is None:
            return False
        state = session.monitors.get(self.monitor)
        if state is None or (state.workspace, state.special) != (self.workspace, self.special):
            return True
        # Focusing the menu's own output is part of opening it. Also tolerate
        # an unchanged initial focus until the compositor grants that focus.
        if session.focused and session.focused not in (self.monitor, self.focused):
            return True
        if session.active_window and session.active_window != self.active_window:
            return True
        self.focused = session.focused
        self.active_window = session.active_window
        return False
