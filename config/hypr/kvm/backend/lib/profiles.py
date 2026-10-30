"""Independent Windows and macOS workspaces inside one launcher."""

from dataclasses import dataclass
import json
from pathlib import Path

NAMES = {"windows": "Windows", "macos": "Mac"}
RUNTIME_FILES = {"SCRIPT": "launch.sh", "LOG": "launch.log", "START": "start.sh",
                 "REVERT": "revert.sh", "STAMP": ".hooks.json",
                 "RT_SAVED": ".sched_rt_runtime_us", "TESTRUN": "testrun.sh"}


@dataclass(frozen=True)
class Paths:
    key: str
    root: Path
    directory: Path
    session: Path
    presets: Path
    template: Path
    defaults: Path
    default_theme: Path
    theme: Path
    run: Path


def paths(root, key):
    if key not in NAMES:
        raise ValueError(f"Unknown OS profile: {key}")
    root = Path(root)
    # Preserve existing Windows installations and their saved preset paths.
    directory = root if key == "windows" else root / "macos"
    presets = directory / "presets"
    return Paths(key, root, directory, directory / "last-session.json", presets,
                 presets / ("win10-template.json" if key == "windows" else "macos-template.json"),
                 directory / "settings_default.json", directory / "settings_default.theme.json",
                 directory / "theme.json", directory / "run")


def selected(root):
    try:
        key = json.loads((Path(root) / "selected-profile.json").read_text())["profile"]
        return key if key in NAMES else "windows"
    except (OSError, ValueError, KeyError, TypeError):
        return "windows"


def remember(root, key):
    from settings_defaults import atomic_write
    if key not in NAMES:
        raise ValueError(f"Unknown OS profile: {key}")
    atomic_write(Path(root) / "selected-profile.json",
                 (json.dumps({"profile": key}, indent=2) + "\n").encode())


def check(data, key):
    """Legacy, untagged presets belong to Windows."""
    if not isinstance(data, dict) or any(not isinstance(data.get(k), dict)
            for k in ("_meta", "machine", "cpu", "simple", "smp")):
        raise ValueError("This file is not a VM preset.")
    actual = data["_meta"].get("profile", "windows")
    if actual != key:
        raise ValueError(f"This preset belongs to {NAMES.get(actual, actual)}. "
                         f"Switch to that profile before loading it.")


def configure_runtime(module, directory):
    module.RUN_DIR = str(directory)
    for name, filename in RUNTIME_FILES.items():
        setattr(module, name, str(Path(directory) / filename))
