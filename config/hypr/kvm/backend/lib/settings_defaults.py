"""Restore a fixed settings snapshot while preserving the setup it replaces."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile

from model import APP_DIR

DEFAULT_STATE = os.path.join(APP_DIR, "settings_default.json")
DEFAULT_THEME = os.path.join(APP_DIR, "settings_default.theme.json")


def read_defaults(state_path, theme_path):
    """Read both masters before changing any files or editor state."""
    state_bytes = Path(state_path).read_bytes()
    theme_bytes = Path(theme_path).read_bytes()
    state, appearance = json.loads(state_bytes), json.loads(theme_bytes)
    if not isinstance(state, dict) or any(
            not isinstance(state.get(key), dict)
            for key in ("_meta", "machine", "cpu", "simple", "smp")):
        raise ValueError("The master VM settings are not a valid configuration.")
    if (not isinstance(appearance, dict)
            or any(not isinstance(appearance.get(key), str)
                   for key in ("accent", "background", "text"))
            or not isinstance(appearance.get("preset"), int)):
        raise ValueError("The master appearance settings are not valid.")
    return state, appearance, state_bytes, theme_bytes


def atomic_write(path, data):
    """Replace a complete file; a failed write leaves the old file intact."""
    path = Path(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restore_files(replacements, current_state, current_theme):
    """Back up saved files and unsaved edits, then install the master copies.

    Backups are unique and retained. If either replacement fails, restore any
    files already replaced so the saved setup and appearance stay together.
    """
    replacements = [(Path(path), data) for path, data in replacements]
    backup_root = replacements[0][0].parent / "settings_backups"
    backup_root.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = Path(tempfile.mkdtemp(prefix=f"before-reset-{stamp}-", dir=backup_root))
    (backup / "current-session.json").write_text(json.dumps(current_state, indent=2))
    (backup / "current-theme.json").write_text(json.dumps(current_theme, indent=2))
    originals = {}
    for path, _data in replacements:
        originals[path] = path.read_bytes() if path.exists() else None
        if path.exists():
            shutil.copy2(path, backup / path.name)
    changed = []
    try:
        for path, data in replacements:
            atomic_write(path, data)
            changed.append(path)
    except Exception as error:
        rollback_errors = []
        for path in reversed(changed):
            try:
                if originals[path] is None:
                    path.unlink()
                else:
                    atomic_write(path, originals[path])
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        detail = f"\nCould not restore: {'; '.join(rollback_errors)}" if rollback_errors else ""
        raise OSError(f"{error}{detail}\nRecovery copies: {backup}") from error
    return backup
