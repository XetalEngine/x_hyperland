#!/usr/bin/env python3
"""Paths and tools tab for vmstart_2.

Every file the VM touches, in one place and editable: the emulator, the
firmware and its NVRAM, the SMBIOS blobs, the ACPI tables, the TPM socket and
state, the KVM module build script, and the guest/host helper scripts.

Nothing here is hardcoded into the launch path. Swapping in a second build of
the kernel module or a different OVMF is editing one line, not editing code.
"""

import os
import re

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                             QCheckBox, QPushButton, QLineEdit, QScrollArea,
                             QGridLayout, QFileDialog, QPlainTextEdit, QComboBox,
                             QSpinBox, QApplication, QSizePolicy)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFont

from uiutil import guard_all

MONO = "Monospace"

# Knobs build-kvm.sh reads from the environment. Exposed because they change
# what the guest can detect, and editing them meant editing the script.
KVM_KNOBS = [
    ("KVM_INTERCEPT_CPUID", "1",
     "Keep CPUID intercepted. REQUIRED at guest boot - Windows enumerates topology "
     "from CPUID early. Drop it afterwards with vmstealth75.sh, not here."),
    ("KVM_INTERCEPT_VMMCALL", "0",
     "0 leaves VMMCALL un-intercepted so it raises #UD like bare metal. Gives up "
     "KVM's paravirtual hypercall ABI for every guest on this host."),
    ("KVM_CPUID_CLEAR_BUFFERS", "1",
     "Keep the VERW CPU-buffer clear on the burst re-entry path. 0 disables an "
     "MDS / transient-scheduler mitigation."),
    ("KVM_CPUID_BURST_MAX", "4096", "Burst limit for consecutive CPUID exits."),
    ("KVM_PRIVATE_MSR_BURST", "1", "Native handling of private MSR reads."),
    ("KVM_PRIVATE_MSR_BURST_MAX", "4096", "Burst limit for private MSR exits."),
    ("KVM_AVIC", "0", "AMD Advanced Virtual Interrupt Controller."),
    ("KVM_IPIV", "0", "IPI virtualisation."),
    ("KVM_POSTED_IRQS", "0", "Posted interrupts."),
]


class PathRow(QWidget):
    """One editable path with a browse button and a live existence check."""

    def __init__(self, label, getter, setter, on_change, tip="",
                 kind="file", missing_ok=False):
        super().__init__()
        self.getter, self.setter, self.on_change = getter, setter, on_change
        self.kind, self.missing_ok = kind, missing_ok

        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(6)

        lb = QLabel(label + ":")
        if tip:
            lb.setToolTip(tip)
        g.addWidget(lb, 0, 0)

        self.edit = QLineEdit()
        if tip:
            self.edit.setToolTip(tip)
        self.edit.textEdited.connect(self._edited)
        g.addWidget(self.edit, 1, 0, 1, 2)

        b = QPushButton("Browse…")
        b.setToolTip("Choose " + label.lower())
        b.clicked.connect(self._browse)
        g.addWidget(b, 1, 2)

        self.status = QLabel("")
        g.addWidget(self.status, 0, 1, 1, 2, Qt.AlignmentFlag.AlignRight)
        g.setColumnStretch(1, 1)
        self.reload()

    def reload(self):
        v = self.getter() or ""
        if v != self.edit.text():
            self.edit.setText(v)
        self._check()

    def _edited(self, text):
        self.setter(text.strip())
        self._check()
        self.on_change()

    def _browse(self):
        cur = self.edit.text().strip()
        start = cur if os.path.exists(cur) else os.path.dirname(cur) or os.path.expanduser("~")
        if self.kind == "dir":
            p = QFileDialog.getExistingDirectory(self, "Select directory", start)
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Select file", start)
        if p:
            self.edit.setText(p)
            self._edited(p)

    def _check(self):
        p = self.edit.text().strip()
        if not p:
            self.status.setText("not set")
            self.status.setStyleSheet("color: #888;")
        elif self.kind == "dir":
            # missing_ok applies to directories too. The hugepage mount is
            # created by the start hook, so its absence between runs is the
            # normal state, not a fault to colour red.
            if os.path.isdir(p):
                self.status.setText("directory")
                self.status.setStyleSheet("color: #888;")
            else:
                self.status.setText("created at launch" if self.missing_ok
                                    else "missing")
                self.status.setStyleSheet("color: #888;" if self.missing_ok
                                          else "color: #e06c75;")
        elif not os.path.exists(p):
            if '/components/sources-' in p:
                self.status.setText('Choose a local build script')
                self.status.setStyleSheet('color: #888;')
                return
            # Sockets and state files are created at launch, so their absence
            # now is expected rather than an error.
            self.status.setText("created at launch" if self.missing_ok else "MISSING")
            self.status.setStyleSheet("color: #888;" if self.missing_ok
                                      else "color: #e06c75;")
        else:
            size = os.path.getsize(p) if os.path.isfile(p) else 0
            exe = os.access(p, os.X_OK) and os.path.isfile(p)
            self.status.setText(f"{'exec  ' if exe else ''}{_human(size)}")
            self.status.setStyleSheet("color: #98c379;")


def _first_existing(candidates):
    """First path that is actually there, else the first as a placeholder."""
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def _human(n):
    for u in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}T"


class PathsTab(QScrollArea):
    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.rows = []
        self.setWidgetResizable(True)
        self._build()
        guard_all(self)

    # ------------------------------------------------------------ helpers ---
    def tools(self):
        """External scripts vmstart_2 runs around the VM.

        Kept in the config rather than in code so a second build of the module
        or a different stealth script is a path edit, not a code edit.
        """
        t = self.cfg.data.setdefault("tools", {})
        if self.cfg.profile == "macos":
            # These are Windows helper paths, not dependencies of the Mac VM.
            for key in ("vmstealth_host", "vmstealth_guest", "tpm_reconstruct",
                        "swtpm_binary", "swtpm_state", "tpm_root", "ovmf_build"):
                t.pop(key, None)
            t.setdefault("kvm_build_enabled", False)
            t.setdefault("kvm_build", "")
            t.setdefault("kvm_build_args", "")
            if not t["kvm_build_enabled"]:
                t.pop("kvm_env", None)
            return t
        from portable import tool_defaults, upgrade_guest_script
        for key, value in tool_defaults().items():
            t.setdefault(key, value)
        upgrade_guest_script(t)
        return t

    def _blockdev(self, node):
        for b in self.cfg.blockdevs:
            if b.get("node-name") == node:
                return b
        return None

    def _bd_get(self, node):
        b = self._blockdev(node)
        return (b or {}).get("filename", "")

    def _bd_set(self, node, v):
        b = self._blockdev(node)
        if b is not None:
            b["filename"] = v

    def _obj(self, oid):
        for o in self.cfg.objects:
            if o.get("id") == oid:
                return o
        return None

    def _chardev(self, cid):
        for c in self.cfg.data.get("chardevs", []):
            if c.get("id") == cid:
                return c
        return None

    def _chardev_path_get(self, cid):
        c = self._chardev(cid)
        return (c or {}).get("path", "")

    def _chardev_path_set(self, cid, v):
        c = self._chardev(cid)
        if c is None:
            return
        c["path"] = v
        # _raw is what actually gets emitted, so it has to move with the field.
        raw = c.get("_raw", "")
        c["_raw"] = (re.sub(r"path=[^,]*", "path=" + v, raw) if "path=" in raw
                     else raw + ",path=" + v)

    def _simple_file_get(self, flag):
        v = self.cfg.simple.get(flag) or ""
        if flag == "smbios" and not v.startswith("file="):
            return ""
        return v.split("=", 1)[1] if v.startswith("file=") else v

    def _simple_file_set(self, flag, v):
        self.cfg.simple[flag] = "file=" + v if v else ""

    def _add(self, grid, row, label, getter, setter, **kw):
        r = PathRow(label, getter, setter, self._touched, **kw)
        self.rows.append(r)
        grid.addWidget(r, row, 0)
        return r

    def _touched(self):
        self.changed.emit()

    def _set_guest_batch_path(self, path):
        self.cfg.data["tools"]["vmstealth_guest"] = path
        self._refresh_guest_batch()

    def _refresh_guest_batch(self):
        if not hasattr(self, "guest_batch_preview"):
            return
        self.guest_batch_copy_timer.stop()
        self.guest_batch_copy.setText("Copy")
        path = self.cfg.data.get("tools", {}).get("vmstealth_guest", "")
        self.guest_batch_name.setText("Guest .bat · " + os.path.basename(path)
                                      if path else "No guest script selected")
        self.guest_batch_name.setToolTip(path)
        self._guest_batch_text = ""
        message = "Choose the Guest script below to preview its contents."
        if path:
            try:
                if not os.path.isfile(path):
                    raise OSError("The guest script is missing or is not a file.")
                with open(path, "rb") as stream:
                    contents = stream.read(1024 * 1024 + 1)
                if len(contents) > 1024 * 1024:
                    raise ValueError("The guest script is too large to preview (limit: 1 MiB).")
                self._guest_batch_text = contents.decode("utf-8-sig")
                message = "The guest script is empty."
            except (OSError, UnicodeError, ValueError) as error:
                self._guest_batch_text = ""
                message = f"Cannot preview the guest script:\n{error}"
        # QPlainTextEdit normalizes line endings for display; copy the original
        # text so the Windows batch retains its CRLF endings and trailing newline.
        displayed = self._guest_batch_text.replace("\r\n", "\n").replace("\r", "\n")
        if self.guest_batch_preview.toPlainText() != displayed:
            self.guest_batch_preview.setPlainText(displayed)
        self.guest_batch_preview.setPlaceholderText(message)
        self.guest_batch_copy.setEnabled(bool(self._guest_batch_text))

    def _copy_guest_batch(self):
        self._refresh_guest_batch()
        if self._guest_batch_text:
            QApplication.clipboard().setText(self._guest_batch_text)
            self.guest_batch_copy.setText("Copied")
            self.guest_batch_copy_timer.start(1800)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_guest_batch()

    # ------------------------------------------------------------- build ---
    def _build(self):
        if self.cfg.profile == "macos":
            self._build_mac()
            return
        w = QWidget()
        self.setWidget(w)
        lay = QVBoxLayout(w)
        lay.addWidget(_wrap(QLabel(
            "Every file the VM depends on. Green means it exists, red means the "
            "launch will fail on it. Editing a path here rewrites the matching "
            "command line argument, so switching to a second build of anything "
            "is one edit.")))

        t = self.tools()

        # Short label+path boxes go two per row: at full width the line edits
        # were mostly empty space, and the tab needed a page of scrolling.
        pairs = QGridLayout()
        pairs.setSpacing(14)
        pairs.setColumnStretch(0, 1)
        pairs.setColumnStretch(1, 1)
        lay.addLayout(pairs)

        # ---- emulator -------------------------------------------------------
        g, box = _group("QEMU")
        self._add(g, 0, "Emulator binary",
                  lambda: self.cfg.data["_meta"]["binary"],
                  lambda v: self.cfg.data["_meta"].__setitem__("binary", v),
                  tip="The qemu-system-x86_64 that gets executed.")
        self._add(g, 1, "Build / install script",
                  lambda: t.get("qemu_build", ""),
                  lambda v: t.__setitem__("qemu_build", v),
                  tip="What 'xbuild qemu' runs. Not executed by launch.")
        pairs.addWidget(box, 0, 0, Qt.AlignmentFlag.AlignTop)

        # ---- firmware --------------------------------------------------------
        g, box = _group("Firmware (OVMF)")
        self._add(g, 0, "OVMF_CODE (pflash0)",
                  lambda: self._bd_get("libvirt-pflash0-storage"),
                  lambda v: self._bd_set("libvirt-pflash0-storage", v),
                  tip="Read-only firmware image. Swapping this is how you switch "
                      "between OVMF builds.")
        self._add(g, 1, "NVRAM VARS (pflash1)",
                  lambda: self._bd_get("libvirt-pflash1-storage"),
                  lambda v: self._bd_set("libvirt-pflash1-storage", v),
                  tip="Per-VM writable variable store: boot entries, Secure Boot "
                      "keys. Must match the CODE image it was created against, and "
                      "must be writable.")
        self._add(g, 2, "Build script",
                  lambda: t.get("ovmf_build", ""),
                  lambda v: t.__setitem__("ovmf_build", v),
                  tip="What 'xbuild ovmf' runs. Not executed by launch.")
        pairs.addWidget(box, 0, 1, Qt.AlignmentFlag.AlignTop)

        # ---- smbios -----------------------------------------------------------
        g, box = _group("SMBIOS")
        sm = self.cfg.smbios
        self._add(g, 0, "Blob handed to QEMU",
                  lambda: self._simple_file_get("smbios"),
                  lambda v: self._simple_file_set("smbios", v),
                  tip="-smbios file=. This blob's Type 1 UUID overrides -uuid.")
        self._add(g, 1, "Pristine template",
                  lambda: sm.get("template_blob", ""),
                  lambda v: sm.__setitem__("template_blob", v),
                  tip="The untouched dump. Never written to; patches are applied "
                      "to a copy.")
        self._add(g, 2, "Patched output",
                  lambda: sm.get("output_blob", ""),
                  lambda v: sm.__setitem__("output_blob", v),
                  tip="Where the patched blob is written. Should be the same file "
                      "as the blob handed to QEMU above.")
        pairs.addWidget(box, 1, 0, Qt.AlignmentFlag.AlignTop)

        # ---- tpm ----------------------------------------------------------------
        g, box = _group("TPM")
        self._add(g, 0, "swtpm socket",
                  lambda: self._chardev_path_get("chrtpm"),
                  lambda v: self._chardev_path_set("chrtpm", v),
                  missing_ok=True,
                  tip="Unix socket QEMU talks to. swtpm derives its control socket "
                      "as <path>.ctrl. Created at launch.")
        self._add(g, 1, "swtpm binary",
                  lambda: t.get("swtpm_binary", ""),
                  lambda v: t.__setitem__("swtpm_binary", v),
                  tip="The custom swtpm build with the spoofed vendor identity.")
        self._add(g, 2, "swtpm state directory",
                  lambda: t.get("swtpm_state", ""),
                  lambda v: t.__setitem__("swtpm_state", v),
                  kind="dir", missing_ok=True,
                  tip="Where the NV store and EK live. Blank means let swtpm decide.")
        self._add(g, 3, "Reconstruct script",
                  lambda: t.get("tpm_reconstruct", ""),
                  lambda v: t.__setitem__("tpm_reconstruct", v),
                  tip="tpm-reconstruct.sh. Not executed by launch.")
        pairs.addWidget(box, 1, 1, Qt.AlignmentFlag.AlignTop)

        # ---- kvm module ------------------------------------------------------------
        g, box = _group("KVM kernel module")
        hdr = QLabel("Built and loaded before the VM starts. Point this at another "
                     "build to test one without touching the other.")
        hdr.setWordWrap(True)
        g.addWidget(hdr, 0, 0)

        self.chk_kvm = QCheckBox("Build and load this module before launching")
        self.chk_kvm.setChecked(bool(t.get("kvm_build_enabled", True)))
        self.chk_kvm.stateChanged.connect(
            lambda s: (t.__setitem__("kvm_build_enabled", bool(s)), self._touched()))
        g.addWidget(self.chk_kvm, 1, 0)

        self._add(g, 2, "build-kvm.sh",
                  lambda: t.get("kvm_build", ""),
                  lambda v: t.__setitem__("kvm_build", v),
                  tip="Builds the ported native-MSR KVM modules and loads them "
                      "for this boot.")

        argrow = QWidget()
        ag = QGridLayout(argrow)
        ag.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Arguments:")
        lbl.setMinimumWidth(140)
        ag.addWidget(lbl, 0, 0)
        self.kvm_args = QComboBox()
        self.kvm_args.setEditable(True)
        for a, d in (("", "load for this boot only (default)"),
                     ("--install", "also overwrite the distro modules, persists across reboots"),
                     ("--restore", "put the distro modules back")):
            self.kvm_args.addItem(a or "(none)", a)
            self.kvm_args.setItemData(self.kvm_args.count() - 1, d,
                                      Qt.ItemDataRole.ToolTipRole)
        cur = t.get("kvm_build_args", "")
        self.kvm_args.setEditText(cur if cur else "(none)")
        self.kvm_args.activated.connect(
            lambda i: (self.kvm_args.setEditText(self.kvm_args.itemData(i) or "(none)"),
                       t.__setitem__("kvm_build_args", self.kvm_args.itemData(i) or ""),
                       self._touched()))
        ag.addWidget(self.kvm_args, 0, 1)
        ag.setColumnStretch(1, 1)
        g.addWidget(argrow, 3, 0)

        env_box = QGroupBox("Module build environment")
        eg = QGridLayout(env_box)
        self.kvm_env = {}
        env = t.setdefault("kvm_env", {})
        for i, (name, default, desc) in enumerate(KVM_KNOBS):
            e = QLineEdit(str(env.get(name, default)))
            e.setFixedWidth(80)
            e.setToolTip(desc)
            e.textEdited.connect(lambda v, n=name: (env.__setitem__(n, v.strip()),
                                                    self._touched()))
            lb = QLabel(name)
            lb.setToolTip(desc)
            note = QLabel(desc)
            note.setWordWrap(True)
            note.setStyleSheet("color: #888;")
            eg.addWidget(lb, i, 0)
            eg.addWidget(e, i, 1)
            # The long boot/interception explanations keep the full width;
            # the shorter rows leave room for the guest batch preview.
            eg.addWidget(note, i, 2, 1, 2 if i < 2 else 1)
            self.kvm_env[name] = e
            env.setdefault(name, default)
        eg.setColumnStretch(2, 3)
        eg.setColumnStretch(3, 2)

        batch_box = QWidget()
        batch_layout = QVBoxLayout(batch_box)
        batch_layout.setContentsMargins(12, 0, 0, 0)
        batch_layout.setSpacing(6)
        batch_header = QHBoxLayout()
        self.guest_batch_name = QLabel()
        self.guest_batch_name.setTextFormat(Qt.TextFormat.PlainText)
        self.guest_batch_name.setSizePolicy(QSizePolicy.Policy.Ignored,
                                          QSizePolicy.Policy.Preferred)
        self.guest_batch_name.setStyleSheet("color: #888;")
        batch_header.addWidget(self.guest_batch_name, 1)
        self.guest_batch_copy = QPushButton("Copy")
        self.guest_batch_copy.setObjectName("accent")
        self.guest_batch_copy.setMinimumWidth(72)
        self.guest_batch_copy.setToolTip("Copy the entire guest .bat file to the clipboard")
        self.guest_batch_copy.clicked.connect(self._copy_guest_batch)
        batch_header.addWidget(self.guest_batch_copy)
        batch_layout.addLayout(batch_header)
        self.guest_batch_preview = QPlainTextEdit()
        self.guest_batch_preview.setReadOnly(True)
        self.guest_batch_preview.setFont(QFont(MONO, 9))
        self.guest_batch_preview.setMinimumSize(280, 170)
        self.guest_batch_preview.setAccessibleName("Guest batch file contents")
        batch_layout.addWidget(self.guest_batch_preview)
        self.guest_batch_copy_timer = QTimer(self)
        self.guest_batch_copy_timer.setSingleShot(True)
        self.guest_batch_copy_timer.timeout.connect(lambda: self.guest_batch_copy.setText("Copy"))
        eg.addWidget(batch_box, 2, 3, len(KVM_KNOBS) - 2, 1)
        self._refresh_guest_batch()
        g.addWidget(env_box, 4, 0)
        lay.addWidget(box)

        pairs2 = QGridLayout()
        pairs2.setSpacing(6)
        pairs2.setColumnStretch(0, 1)
        pairs2.setColumnStretch(1, 1)
        lay.addLayout(pairs2)

        # ---- helper scripts ---------------------------------------------------------
        g, box = _group("Stealth helpers")
        hdr = QLabel("Run by hand, not by launch: the CPUID drop must happen after "
                     "Windows has finished enumerating topology. The Windows guest script is included "
                     "with the desktop. Set its SSH login before use; it requires the matching "
                     "custom AMD KVM module and host helper.")
        hdr.setWordWrap(True)
        g.addWidget(hdr, 0, 0)
        self._add(g, 1, "Host script",
                  lambda: t.get("vmstealth_host", ""),
                  lambda v: t.__setitem__("vmstealth_host", v),
                  tip="vmstealth75.sh. Drops CPUID interception once the guest is up.")
        self._add(g, 2, "Guest script",
                  lambda: t.get("vmstealth_guest", ""),
                  self._set_guest_batch_path,
                  tip="Included Windows .bat template. Copy it into the guest, then edit HOST_LOGIN and any custom paths before running.")
        pairs2.addWidget(box, 0, 0, Qt.AlignmentFlag.AlignTop)

        # ---- memory / sockets ----------------------------------------------------------
        g, box = _group("Runtime paths")
        ram = self._obj("pc.ram")
        if ram is not None:
            self._add(g, 0, "Hugepage mount",
                      lambda: (self._obj("pc.ram") or {}).get("mem-path", ""),
                      lambda v: (self._obj("pc.ram") or {}).__setitem__("mem-path", v),
                      kind="dir", missing_ok=True,
                      tip="Directory on a hugetlbfs mount that backs guest RAM.")
        self._add(g, 1, "QMP socket",
                  lambda: (self.cfg.simple.get("qmp") or "").replace("unix:", "").split(",")[0],
                  self._set_qmp, missing_ok=True,
                  tip="Control socket. This is how anything talks to the running VM.")
        self._add(g, 2, "Launch script",
                  lambda: os.path.join(self.cfg.root, "macos" if self.cfg.profile == "macos" else "", "run", "launch.sh"),
                  lambda v: None, missing_ok=True,
                  tip="Generated on every launch. Read only here.")
        pairs2.addWidget(box, 0, 1, Qt.AlignmentFlag.AlignTop)

        # ---- acpi ------------------------------------------------------------------------
        g, box = _group("ACPI tables")
        hdr = QLabel("Passed as -acpitable file=..., in this order. One per line.")
        hdr.setWordWrap(True)
        g.addWidget(hdr, 0, 0)
        self.acpi_edit = QPlainTextEdit()
        self.acpi_edit.setFont(QFont(MONO, 9))
        self.acpi_edit.setPlainText("\n".join(
            x.split("=", 1)[1] if x.startswith("file=") else x
            for x in self.cfg.acpitables))
        self.acpi_edit.setMinimumHeight(180)
        self.acpi_edit.textChanged.connect(self._push_acpi)
        g.addWidget(self.acpi_edit, 1, 0)
        self.acpi_status = QLabel("")
        self.acpi_status.setWordWrap(True)
        g.addWidget(self.acpi_status, 2, 0)
        lay.addWidget(box)

        self._push_acpi()
        lay.addStretch()

    def _build_mac(self):
        from pathlib import Path
        import opencore
        import profiles
        w = QWidget()
        self.setWidget(w)
        lay = QVBoxLayout(w)
        note = QLabel("Mac runtime files and tools. Keep OVMF_CODE and its private NVRAM together. "
                      "Use Mac & OpenCore to edit boot settings and keep recoverable versions.")
        note.setWordWrap(True)
        lay.addWidget(note)
        tools = self.tools()
        grid = QGridLayout()
        for col in (0, 1):
            grid.setColumnStretch(col, 1)
        lay.addLayout(grid)
        group, box = _group("QEMU")
        self._add(group, 0, "Emulator binary", lambda: self.cfg.data["_meta"]["binary"],
                  lambda value: self.cfg.data["_meta"].__setitem__("binary", value))
        self._add(group, 1, "QEMU build script", lambda: tools.get("qemu_build", ""),
                  lambda value: tools.__setitem__("qemu_build", value), missing_ok=True,
                  tip="Optional host QEMU build script; not executed by launch.")
        grid.addWidget(box, 0, 0)
        group, box = _group("Mac firmware and NVRAM")
        for row, label, node in [(0, "OVMF_CODE", "libvirt-pflash0-storage"),
                                 (1, "Private NVRAM", "libvirt-pflash1-storage")]:
            self._add(group, row, label, lambda n=node: self._bd_get(n),
                      lambda value, n=node: self._bd_set(n, value))
        grid.addWidget(box, 0, 1)
        group, box = _group("OpenCore")
        meta = self.cfg.data.setdefault("_meta", {})
        self.opencore_disk = QComboBox()
        self.opencore_disk.addItem("Select the OpenCore image disk…", "")
        for device in self.cfg.devices:
            if device.get("_disabled") or device.get("driver") in ("ide-cd", "scsi-cd"):
                continue
            node = device.get("drive", "")
            seen = set()
            while node and node not in seen:
                seen.add(node)
                block = self._blockdev(node) or {}
                if block.get("filename"):
                    filename = block["filename"]
                    if not filename.startswith("/dev/") and device.get("id"):
                        self.opencore_disk.addItem(f"{device['id']} · {os.path.basename(filename)}", device["id"])
                    break
                node = block.get("file", "")
        selected = meta.get("opencore_boot_device", "opencore-boot")
        self.opencore_disk.setCurrentIndex(max(0, self.opencore_disk.findData(selected)))
        group.addWidget(self.opencore_disk, 0, 0)
        def boot_node():
            dev = next((d for d in self.cfg.devices if d.get("id") == self.opencore_disk.currentData()
                        and not d.get("_disabled")), {})
            node, seen = dev.get("drive", ""), set()
            while node and node not in seen:
                seen.add(node)
                block = self._blockdev(node) or {}
                if "filename" in block:
                    return node
                node = block.get("file", "")
            return ""
        row = self._add(group, 1, "Writable boot image", lambda: self._bd_get(boot_node()),
                        lambda value: self._bd_set(boot_node(), value),
                        tip="The disk containing EFI/OC/config.plist. Editing in Mac & OpenCore creates an independent copy.")
        row.setEnabled(bool(boot_node()))
        def select_boot_disk(_index):
            meta["opencore_boot_device"] = self.opencore_disk.currentData()
            row.setEnabled(bool(boot_node()))
            row.reload()
            self._touched()
        self.opencore_disk.currentIndexChanged.connect(select_boot_disk)
        label = QLabel("Select the disk containing OpenCore, not the macOS installation disk. "
                       "For an ISO, attach a separate writable OpenCore .img first.")
        label.setWordWrap(True)
        group.addWidget(label, 2, 0)
        self._add(group, 3, "Matching validators", lambda: tools.get("opencore_validators") or str(opencore.BUNDLES),
                  lambda value: tools.__setitem__("opencore_validators", value), kind="dir",
                  tip="Versioned ocvalidate bundles. The editor matches the exact OpenCore binary and verifies the validator checksum.")
        grid.addWidget(box, 1, 0)
        group, box = _group("Mac runtime")
        self._add(group, 0, "QMP socket", lambda: (self.cfg.simple.get("qmp") or "").replace("unix:", "").split(",")[0],
                  self._set_qmp, missing_ok=True)
        label = QLabel("Launch files: " + str(profiles.paths(self.cfg.root, "macos").run))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        group.addWidget(label, 1, 0)
        grid.addWidget(box, 1, 1)
        group, box = _group("Optional host KVM module")
        self.chk_kvm = QCheckBox("Build and load a custom host module before Single GPU launch")
        self.chk_kvm.setChecked(bool(tools["kvm_build_enabled"]))
        self.chk_kvm.toggled.connect(lambda value: (tools.__setitem__("kvm_build_enabled", value), self._touched()))
        group.addWidget(self.chk_kvm, 0, 0)
        self._add(group, 1, "Build script", lambda: tools.get("kvm_build", ""),
                  lambda value: tools.__setitem__("kvm_build", value), missing_ok=True)
        args = QLineEdit(tools.get("kvm_build_args", ""))
        args.setPlaceholderText("Optional build arguments")
        args.textEdited.connect(lambda value: (tools.__setitem__("kvm_build_args", value), self._touched()))
        group.addWidget(args, 2, 0)
        label = QLabel("This controls the Linux host module. Virtual GPU and Dual GPU use the module already loaded on the host.")
        label.setWordWrap(True)
        group.addWidget(label, 3, 0)
        lay.addWidget(box)
        if self.cfg.acpitables:
            group, box = _group("Additional QEMU ACPI tables")
            label = QLabel("These extra host files are separate from the ACPI entries inside OpenCore.")
            label.setWordWrap(True)
            group.addWidget(label, 0, 0)
            self.acpi_edit = QPlainTextEdit("\n".join(x.removeprefix("file=") for x in self.cfg.acpitables))
            self.acpi_status = QLabel()
            self.acpi_edit.textChanged.connect(self._push_acpi)
            group.addWidget(self.acpi_edit, 1, 0)
            group.addWidget(self.acpi_status, 2, 0)
            lay.addWidget(box)
        lay.addStretch()

    def _set_qmp(self, v):
        cur = self.cfg.simple.get("qmp") or "unix:,server,nowait"
        tail = ",".join(cur.split(",")[1:])
        self.cfg.simple["qmp"] = f"unix:{v}" + ("," + tail if tail else "")

    def _push_acpi(self):
        paths = [l.strip() for l in self.acpi_edit.toPlainText().splitlines() if l.strip()]
        self.cfg.data["acpitables"] = ["file=" + p for p in paths]
        missing = [p for p in paths if not os.path.isfile(p)]
        if missing:
            self.acpi_status.setText(f"{len(missing)} missing: " + ", ".join(
                os.path.basename(p) for p in missing))
            self.acpi_status.setStyleSheet("color: #e06c75;")
        else:
            self.acpi_status.setText(f"{len(paths)} tables, all present")
            self.acpi_status.setStyleSheet("color: #98c379;")
        self.changed.emit()

    def refresh(self):
        for r in self.rows:
            r.reload()
        self._refresh_guest_batch()


def _group(title):
    box = QGroupBox(title)
    g = QGridLayout(box)
    g.setContentsMargins(8, 4, 8, 8)
    g.setSpacing(4)
    return g, box


def _wrap(lbl):
    lbl.setWordWrap(True)
    return lbl
