#!/usr/bin/env python3
"""Launch Procedure tab: the two host-side hooks, side by side and editable.

start.sh is everything before QEMU, revert.sh is everything after. They are
generated from the config the first time and then belong to the user: launch.sh
only calls them, so a hand edit survives every subsequent launch.
"""

import os

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                             QPushButton, QPlainTextEdit, QMessageBox, QSplitter,
                             QGridLayout, QSizePolicy)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

import launcher

MONO = "Monospace"


class HookEditor(QGroupBox):
    """One hook file with save / reload / regenerate."""

    changed = pyqtSignal()

    def __init__(self, key, title, blurb, owner):
        super().__init__(title)
        self.key, self.owner = key, owner
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.setSpacing(4)

        note = QLabel(blurb)
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        lay.addWidget(note)

        self.path_lbl = QLabel("")
        self.path_lbl.setWordWrap(True)
        self.path_lbl.setMinimumWidth(0)
        self.path_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.path_lbl.setStyleSheet("color: #888;")
        self.path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.path_lbl)

        self.edit = QPlainTextEdit()
        self.edit.setFont(QFont(MONO, 9))
        self.edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.edit.setTabStopDistance(32)
        self.edit.textChanged.connect(self._dirty)
        lay.addWidget(self.edit, 1)

        row = QGridLayout()
        for i, (text, slot, tip) in enumerate((
                ("Save", self.save, "Write the editor contents to the file"),
                ("Reload", self.reload, "Discard editor changes and re-read the file"),
                ("Regenerate from config", self.regenerate,
                 "Replace this hook with a fresh one built from the current config. "
                 "Your edits are lost."),
                ("Show generated", self.show_generated,
                 "Load what the config would generate, without saving it"))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            if text == "Save":
                b.setObjectName("accent")
            row.addWidget(b, i // 2, i % 2)
        lay.insertLayout(0, row)
        self.state_lbl = QLabel("")
        self.state_lbl.setWordWrap(True)
        lay.addWidget(self.state_lbl)

        self._loading = False
        self._unsaved = False

    # ------------------------------------------------------------ state ---
    def load(self, state):
        self.state = state
        self._loading = True
        self.edit.setPlainText(state["current"] or state["generated"])
        self._loading = False
        self._unsaved = not state["exists"]
        mode = ""
        if state["exists"]:
            try:
                mode = f"  mode {oct(os.stat(state['path']).st_mode & 0o777)}"
            except Exception:
                pass
        self.path_lbl.setText(state["path"] + mode)
        self._status()

    def _dirty(self):
        if self._loading:
            return
        self._unsaved = True
        self._status()

    def _status(self):
        s = getattr(self, "state", None)
        if s is None:
            return
        if self._unsaved:
            self.state_lbl.setText("UNSAVED")
            self.state_lbl.setStyleSheet("color: #e5c07b; font-weight: bold;")
        elif not s["exists"]:
            self.state_lbl.setText("not written yet")
            self.state_lbl.setStyleSheet("color: #888;")
        elif s["edited"]:
            self.state_lbl.setText("edited by you (kept on launch)")
            self.state_lbl.setStyleSheet("color: #61afef;")
        elif s["stale"]:
            self.state_lbl.setText("config changed since generated")
            self.state_lbl.setStyleSheet("color: #e5c07b;")
        else:
            self.state_lbl.setText("matches config")
            self.state_lbl.setStyleSheet("color: #98c379;")

    # ----------------------------------------------------------- actions ---
    def save(self):
        launcher.save_hook(self.key, self.edit.toPlainText())
        self._unsaved = False
        self.owner.refresh()
        self.changed.emit()

    def reload(self):
        self.owner.refresh()

    def regenerate(self):
        if QMessageBox.question(
                self, "Regenerate",
                f"Rebuild {os.path.basename(self.state['path'])} from the current "
                f"config?\n\nAny edits you made to it are lost."
                ) != QMessageBox.StandardButton.Yes:
            return
        self.owner.regenerate(self.key)
        self.changed.emit()

    def show_generated(self):
        self._loading = True
        self.edit.setPlainText(self.state["generated"])
        self._loading = False
        self._unsaved = True
        self._status()


class ProcedureTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, cfg, get_pinning, get_reboot):
        super().__init__()
        self.cfg = cfg
        self.get_pinning = get_pinning
        self.get_reboot = get_reboot
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        head = QLabel(
            "The two halves of the launch that used to live in "
            "/etc/libvirt/hooks. Generated from the config the first time, then "
            "yours: launch.sh only calls them, so your edits survive every "
            "launch. Files are mode 0775 in the app's run/ directory, so no sudo "
            "to edit them.")
        head.setWordWrap(True)
        lay.addWidget(head)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.start = HookEditor(
            "start", "start.sh   (before QEMU)",
            "Hugepages, RT throttling, KVM module build, then the GPU handoff: "
            "stop the display manager, unload nvidia, bind to vfio-pci. Exits "
            "non-zero to abort; everything before the display section fails free.",
            self)
        self.revert = HookEditor(
            "revert", "revert.sh   (after QEMU)",
            "Runs when the guest shuts down, and also if start.sh fails after the "
            "display was taken down. On normal shutdown, the Single GPU page's "
            "reboot option selects host reboot or desktop restoration. Failed starts "
            "restore the desktop. The NO_REBOOT file also suppresses reboot.",
            self)
        for e in (self.start, self.revert):
            e.changed.connect(self.changed)
            split.addWidget(e)
        split.setSizes([1, 1])
        lay.addWidget(split, 1)

        row = QHBoxLayout()
        b = QPushButton("Write both if missing")
        b.setToolTip("Create the hooks that do not exist yet. Never overwrites an "
                     "edited file.")
        b.clicked.connect(self._write_missing)
        row.addWidget(b)
        b = QPushButton("Regenerate both from config")
        b.clicked.connect(lambda: self.regenerate(None, confirm=True))
        row.addWidget(b)
        b = QPushButton("Open run/ directory")
        b.clicked.connect(self._open_dir)
        row.addWidget(b)
        row.addStretch()
        self.summary = QLabel("")
        row.addWidget(self.summary)
        lay.addLayout(row)

    # --------------------------------------------------------------- ops ---
    def _state(self):
        return launcher.hook_state(self.cfg, self.get_pinning(), self.get_reboot())

    def refresh(self):
        st = self._state()
        self.start.load(st["start"])
        self.revert.load(st["revert"])
        n = sum(1 for k in st if st[k]["edited"])
        self.summary.setText(f"{n} of 2 hooks hand-edited" if n else "both match config")

    def _write_missing(self):
        written = launcher.write_hooks(self.cfg, self.get_pinning(),
                                       reboot_after=self.get_reboot())
        self.refresh()
        self.changed.emit()
        self.summary.setText(f"wrote {len(written)} file(s)" if written
                             else "nothing to write")

    def regenerate(self, key, confirm=False):
        if confirm and QMessageBox.question(
                self, "Regenerate both",
                "Rebuild start.sh and revert.sh from the current config?\n\n"
                "Any edits you made to them are lost."
                ) != QMessageBox.StandardButton.Yes:
            return
        st = self._state()
        for k in (["start", "revert"] if key is None else [key]):
            # generated=True re-stamps only this hook. Touching the other one's
            # stamp would make an edit there look like generated output.
            launcher.save_hook(k, st[k]["generated"], generated=True)
        self.refresh()
        self.changed.emit()

    def _open_dir(self):
        import subprocess
        subprocess.Popen(["xdg-open", launcher.RUN_DIR],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
