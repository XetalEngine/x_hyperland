#!/usr/bin/env python3
"""Shared widget behaviour for vmstart_2."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtWidgets import (QComboBox, QSpinBox, QDoubleSpinBox, QAbstractSpinBox,
                             QScrollArea, QLabel, QFormLayout, QTableWidget,
                             QAbstractItemView)


# --------------------------------------------------------------- privilege ---
def _passwordless_sudo():
    try:
        return subprocess.run(["sudo", "-n", "true"],
                              capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def _find_askpass(prompt):
    """A binary sudo can run to ask for the password graphically.

    Prefers the bundled themed prompt, then a real ssh-askpass (ksshaskpass on
    KDE, seahorse on GNOME). Finally, synthesises one from kdialog or zenity.
    """
    # Use the desktop's themed password prompt, without persistent services or
    # a predictable writable script in /tmp.
    from portable import ROOT
    built_in=ROOT.parent/'scripts/sudo-askpass.sh'
    if built_in.is_file() and os.access(built_in,os.X_OK):
        return str(built_in)
    for c in ("ksshaskpass", "ssh-askpass", "lxqt-openssh-askpass",
              "x11-ssh-askpass", "/usr/lib/ssh/ssh-askpass",
              "/usr/lib/seahorse/ssh-askpass"):
        p = c if (c.startswith("/") and os.path.exists(c)) else shutil.which(c)
        if p:
            return p
    for gui, arg in (("kdialog", f'--password {_shq(prompt)}'),
                     ("zenity", f'--password --title={_shq("vmstart_2 (sudo)")}')):
        if shutil.which(gui):
            fd,path = tempfile.mkstemp(prefix="xetal-kvm-askpass-")
            with os.fdopen(fd, "w") as f:
                f.write(f"#!/bin/sh\nexec {gui} {arg}\n")
            os.chmod(path, 0o700)
            return path
    return None


def _shq(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def sudo_command(cmd, prompt="KVM Settings needs administrator rights"):
    """Wrap a command list so it runs as root, returning (argv, env, ok).

    Give the actual command an askpass fallback. sudo still reuses valid cached
    credentials and NOPASSWD rules without prompting. A successful `sudo -n true`
    probe cannot guarantee that another command, possibly in a new session or
    after the credentials expire, can run noninteractively.

    Without a graphical helper, retain noninteractive sudo where available.
    ok is False (argv None) when neither authentication route is available.
    """
    env = dict(os.environ)
    askpass = _find_askpass(prompt)
    if askpass:
        env["SUDO_ASKPASS"] = askpass
        return ["sudo", "-A", *cmd], env, True
    if _passwordless_sudo():
        return ["sudo", "-n", *cmd], env, True
    return None, env, False


class _WheelBlocker(QObject):
    """Swallow wheel events on unfocused value widgets.

    Inside a scroll area a combo box under the cursor eats the wheel and
    silently changes value while the user thinks they are scrolling the page.
    On this app that means silently repointing a disk at the wrong physical
    device, so the wheel only adjusts a widget that was deliberately clicked
    into focus first.
    """

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Wheel and not obj.hasFocus():
            ev.ignore()
            return True
        return False


_BLOCKER = _WheelBlocker()
_GUARDED = "_vmstart2_wheel_guarded"


def wheel_guard(widget):
    """Make one combo/spin ignore the wheel until it has focus."""
    if getattr(widget, _GUARDED, False):
        return widget
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.installEventFilter(_BLOCKER)
    setattr(widget, _GUARDED, True)
    return widget


def guard_all(root):
    """Apply wheel_guard to every value widget under root."""
    for cls in (QComboBox, QSpinBox, QDoubleSpinBox, QAbstractSpinBox):
        for w in root.findChildren(cls):
            wheel_guard(w)
    return root


def polish_page(page):
    """Apply shared spacing and readable wrapping without changing controls."""
    content = page.widget() if isinstance(page, QScrollArea) else page
    if content.layout() is not None:
        content.layout().setContentsMargins(12, 12, 12, 12)
        content.layout().setSpacing(14)
    for label in content.findChildren(QLabel):
        if len(label.text()) > 110:
            label.setWordWrap(True)
    for form in content.findChildren(QFormLayout):
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
    for table in content.findChildren(QTableWidget):
        table.setAlternatingRowColors(True)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
