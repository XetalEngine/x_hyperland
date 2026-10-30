"""Remember the windowed size of an external console on X11.

The detached observer outlives the launcher, but only watches the viewer PID
and process start time passed to it. Guest display settings are left to the
viewer. Dialogs, minimized windows and fullscreen/maximized sizes are ignored.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


def unavailable_reason():
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        return "Remembering console window size requires an X11 desktop session."
    if not os.environ.get("DISPLAY"):
        return "Remembering console window size requires an X11 display."
    missing = [tool for tool in ("xdotool", "xprop") if not shutil.which(tool)]
    if missing:
        return "Install " + " and ".join(missing) + " to remember console window size."
    return ""


def process_start(pid):
    try:
        # comm may contain spaces or parentheses. Fields after it start at #3.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] if fields[0] not in ("Z", "X") else None
    except (OSError, IndexError):
        return None


def valid_size(value):
    if isinstance(value, dict) and all(type(value.get(k)) is int and 200 <= value[k] <= 32768
                                       for k in ("width", "height")):
        return {k: value[k] for k in ("width", "height")}
    return None


def load_size(path):
    try:
        return valid_size(json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        return None


def save_size(path, size):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump(size, output)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def command(*args):
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=2)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


class SizeObserver:
    def __init__(self, pid, started, path):
        self.pid, self.started, self.path = pid, started, Path(path)
        self.saved = load_size(path)
        self.window = None
        self.ready_at = 0
        self.restored = False
        self.sample = None

    def properties(self, window):
        properties = command("xprop", "-id", window, "_NET_WM_PID", "_NET_WM_WINDOW_TYPE",
                             "WM_TRANSIENT_FOR", "_NET_WM_STATE", "WM_CLASS", "WM_NAME")
        if properties is None:
            return None
        owner = re.search(r"_NET_WM_PID\(CARDINAL\) = (\d+)", properties)
        if not owner or int(owner[1]) != self.pid:
            return None
        if "_NET_WM_WINDOW_TYPE_NORMAL" not in properties:
            # TigerVNC's FLTK window omits the optional EWMH type. Its console
            # title distinguishes it from connection/options/error dialogs.
            if ("_NET_WM_WINDOW_TYPE(ATOM)" in properties
                    or 'WM_CLASS(STRING) = "vncviewer", "Vncviewer"' not in properties
                    or not re.search(r'^WM_NAME\(STRING\) = ".* - TigerVNC"$', properties, re.MULTILINE)):
                return None
        transient = re.search(r"WM_TRANSIENT_FOR.*window id # (0x[0-9a-fA-F]+)", properties)
        if transient and int(transient[1], 16):
            return None
        return properties

    def poll(self):
        if process_start(self.pid) != self.started:
            return False
        windows = (command("xdotool", "search", "--onlyvisible", "--pid", str(self.pid)) or "").split()
        if self.window not in windows:
            self.window = next((wid for wid in windows if wid.isdecimal() and self.properties(wid)), None)
            # Viewers size themselves when the initial framebuffer arrives.
            self.ready_at = time.monotonic() + 2
            self.restored = False
            self.sample = None
        if self.window is None or time.monotonic() < self.ready_at:
            return True
        properties = self.properties(self.window)
        if properties is None or any(state in properties for state in (
                "_NET_WM_STATE_FULLSCREEN", "_NET_WM_STATE_MAXIMIZED_", "_NET_WM_STATE_HIDDEN")):
            return True
        if not self.restored:
            self.restored = True
            if self.saved:
                width, height = self.saved["width"], self.saved["height"]
                screen = (command("xdotool", "getdisplaygeometry") or "").split()
                if len(screen) == 2 and all(n.isdecimal() for n in screen):
                    width = min(width, max(200, int(screen[0]) - 40))
                    height = min(height, max(200, int(screen[1]) - 80))
                command("xdotool", "windowsize", self.window, str(width), str(height))
                return True
        output = command("xdotool", "getwindowgeometry", "--shell", self.window)
        if output is None:
            return True
        fields = dict(re.findall(r"^(WIDTH|HEIGHT)=(\d+)$", output, re.MULTILINE))
        size = valid_size({k.lower(): int(v) for k, v in fields.items()})
        # Avoid writing every intermediate size while the user drags a corner.
        if size and size == self.sample and size != self.saved:
            try:
                save_size(self.path, size)
                self.saved = size
            except OSError:
                pass  # A read-only state directory must never close the viewer.
        self.sample = size
        return True


def observe(pid, path):
    """Start a size observer without changing the viewer's lifetime or session."""
    started = process_start(pid)
    if started and not unavailable_reason():
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(pid), started, str(path)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)


if __name__ == "__main__":
    observer = SizeObserver(int(sys.argv[1]), sys.argv[2], sys.argv[3])
    while observer.poll():
        time.sleep(0.25)
