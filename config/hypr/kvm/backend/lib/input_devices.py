"""Discover evdev metadata without reading or grabbing keyboard/mouse events."""

import os
from pathlib import Path
import re
import stat
import struct

DEV = Path("/dev/input")
SYS = Path("/sys/class/input")
TOGGLES = {"ctrl-ctrl": "Both Ctrl keys", "alt-alt": "Both Alt keys",
           "shift-shift": "Both Shift keys"}
TOGGLE_KEYS = {"ctrl-ctrl": (29, 97), "alt-alt": (56, 100), "shift-shift": (42, 54)}


def _bitmap(path):
    # sysfs prints native-width words, most significant first, without padding.
    words = path.read_text().split()
    bits = struct.calcsize("L") * 8
    return sum(int(word, 16) << (n * bits) for n, word in enumerate(reversed(words)))


def _device_number(path):
    info = path.stat()
    if not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev) != 13:
        raise ValueError("Choose a Linux input event device")
    return f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"


def inspect(path):
    if not path:
        raise ValueError("Select both an evdev keyboard and mouse")
    node = Path(path).resolve(strict=True)
    if node.parent != DEV.resolve() or not re.fullmatch(r"event\d+", node.name):
        raise ValueError("Choose an event device under /dev/input")
    number = _device_number(node)
    entry = SYS / node.name
    if (entry / "dev").read_text().strip() != number:
        raise ValueError("Input device changed; refresh the keyboard and mouse list")
    device = entry / "device"
    key = _bitmap(device / "capabilities/key")
    rel = _bitmap(device / "capabilities/rel")
    has_keys = lambda codes: all(key & (1 << code) for code in codes)
    roles = []
    if has_keys((16, 30, 44, 57)):  # Q, A, Z, space: exclude media-only devices.
        roles.append("keyboard")
    if rel & 3 == 3 and has_keys((272,)):  # Relative X/Y and left button.
        roles.append("mouse")
    identity = {}
    for attr in ("name", "phys", "uniq", "id/bustype", "id/vendor", "id/product", "id/version"):
        identity[attr] = (device / attr).read_text().strip()
    return dict(path=str(path), node=str(node), number=number, identity=identity,
                name=identity["name"] or node.name, roles=roles,
                toggles=[name for name, keys in TOGGLE_KEYS.items() if has_keys(keys)])


def discover():
    result, seen = [], set()
    # Stable USB IDs first, then physical ports, then event numbers as a fallback.
    paths = [*sorted((DEV / "by-id").glob("*event*")),
             *sorted((DEV / "by-path").glob("*event*")), *sorted(DEV.glob("event*"))]
    for path in paths:
        try:
            info = inspect(str(path))
        except (OSError, ValueError):
            continue
        if info["node"] in seen or not info["roles"]:
            continue
        seen.add(info["node"])
        result.append(info)
    return result


def selection(opts):
    mode = opts.get("input_mode", "viewer")
    if mode == "viewer":
        return []
    if mode != "evdev":
        raise ValueError("Choose viewer input or evdev input")
    toggle = opts.get("evdev_toggle", "ctrl-ctrl")
    if toggle not in TOGGLES:
        raise ValueError("Choose a supported evdev switch shortcut")
    devices = []
    for role in ("keyboard", "mouse"):
        path = opts.get("evdev_" + role, "")
        try:
            info = inspect(path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"evdev {role}: {exc}") from exc
        if role not in info["roles"]:
            raise ValueError(f"{info['name']} is not a suitable evdev {role}")
        if role == "keyboard" and toggle not in info["toggles"]:
            raise ValueError(f"{info['name']} does not expose {TOGGLES[toggle].lower()}; "
                             "choose another switch shortcut or keyboard interface")
        if all(d["node"] != info["node"] for d in devices):
            devices.append(info)
    return devices


def objects(devices, toggle, fresh):
    # Create the keyboard first; grab_all switches the mouse with it.
    return [{"qom-type": "input-linux", "id": fresh(f"dual-input-{n}"),
             "evdev": dev["path"], **({"grab_all": True, "repeat": True,
                                      "grab-toggle": toggle} if n == 0 else {})}
            for n, dev in enumerate(devices)]


def verify_plan(plan):
    """Recheck selected devices before the privileged runtime binds any GPU."""
    devices = selection(plan["options"])
    if devices != plan.get("input_devices", []):
        raise RuntimeError("Keyboard or mouse changed since launch was prepared; refresh input devices")
    expected = objects(devices, plan["options"].get("evdev_toggle", "ctrl-ctrl"), lambda x: x)
    actual = [o for o in plan["config"].get("objects", [])
              if o.get("qom-type") == "input-linux" and not o.get("_disabled")]
    # IDs may have collision suffixes; all device properties must still match.
    strip_id = lambda items: [{k: v for k, v in o.items() if k != "id"} for o in items]
    if strip_id(actual) != strip_id(expected):
        raise RuntimeError("The launch plan includes unexpected evdev input devices")
