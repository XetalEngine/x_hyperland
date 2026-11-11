#!/usr/bin/env python3
"""Disk editor for vmstart_2.

Each card edits one disk end to end: the -blockdev that opens the host device
and the -device that presents it to the guest. They are two command line
arguments but one decision, so the UI treats them as one.

Cards use one or two columns as space allows, and every dropdown ignores the
wheel until clicked, because a stray scroll here repoints a disk at the wrong
physical device.
"""

import os

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                             QCheckBox, QComboBox, QSpinBox, QPushButton, QLineEdit,
                             QScrollArea, QGridLayout, QFormLayout, QFileDialog,
                             QPlainTextEdit, QSizePolicy, QMessageBox, QStyleOptionGroupBox,
                             QStyleOptionComboBox, QStyle)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QRectF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QPainterPath, QPalette

import hostinfo
from uiutil import guard_all
import randomize
import model

MONO = "Monospace"

# libvirt's cache modes expressed as the QEMU flags they actually become.
# write-cache lives on the front-end device, cache.* on the blockdev, which is
# why picking "writeback" by hand means editing two arguments in two places.
CACHE_MODES = {
    "none":         (True,  False, "on",  "Bypass the host page cache, guest flushes honoured. Safe, and what a bare metal disk behaves like."),
    "writeback":    (False, False, "on",  "Host page cache used, guest flushes honoured. Fast; survives a guest crash, not host power loss."),
    "writethrough": (False, False, "off", "Every write reaches the disk before completing. Slow."),
    "directsync":   (True,  False, "off", "No host cache and no write cache. Slowest, strongest."),
    "unsafe":       (False, True,  "on",  "Flushes are ignored. Fastest, and will corrupt the guest on a host crash."),
}

AIO_MODES = [
    ("threads",  "Userspace thread pool. Most compatible, the libvirt default."),
    ("native",   "Linux AIO. Lower overhead on raw block devices, needs cache=none."),
    ("io_uring", "io_uring. Lowest overhead on a modern kernel."),
]

DISCARD_MODES = [
    ("unmap",  "Pass guest TRIM through to the host device. Keeps SSDs healthy."),
    ("ignore", "Drop TRIM requests."),
]

FRONTENDS = [
    ("ide-hd",         "SATA disk on the built-in AHCI controller."),
    ("ide-cd",         "SATA optical drive. Needed for an installer ISO or key image."),
    ("nvme-ns",        "Namespace on the emulated NVMe controller. Guest sees a real NVMe disk."),
    ("virtio-blk-pci", "VirtIO block. Fastest, but the guest sees a paravirtual device."),
    ("scsi-hd",        "SCSI disk. Needs a SCSI controller present."),
]

# Which front-ends actually have a 'serial' property. nvme-ns does NOT: its
# identity is the controller serial plus the namespace uuid/eui64/nguid.
# Setting serial= on one makes QEMU refuse to start with "Property
# 'nvme-ns.serial' not found".
SERIAL_CAPABLE = {"ide-hd", "ide-cd", "virtio-blk-pci", "scsi-hd"}


def _random_serial(n):
    """Serial for a newly added device.

    Random rather than sequential: a predictable serial is itself a signature,
    and duplicates across devices confuse Windows' storage stack.
    """
    return randomize.serial(n)


class DevicePicker(QComboBox):
    """Keep the editable device dropdown visible even without theme arrow images."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QComboBox { padding-right: 28px; }"
                           "QComboBox::drop-down { width: 24px; }"
                           "QComboBox::down-arrow { image: none; width: 0; height: 0; }")

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        arrow = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                           QStyle.SubControl.SC_ComboBoxArrow, self)
        x, y = arrow.center().x(), arrow.center().y()
        chevron = QPainterPath()
        chevron.moveTo(x - 4, y - 2)
        chevron.lineTo(x, y + 2)
        chevron.lineTo(x + 4, y - 2)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.Text), 1.6,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(chevron)


class DiskRow(QGroupBox):
    """One blockdev + one front-end device, edited together."""

    changed = pyqtSignal()
    removed = pyqtSignal(object)
    active_changed = pyqtSignal(object, bool)

    def __init__(self, cfg, blockdev, device, host_disks, owner=None, host_labels=None):
        super().__init__()
        self.cfg, self.bd, self.dev = cfg, blockdev, device
        self.setProperty("inactive", bool(device.get("_inactive")))
        self.host_disks = host_disks
        self.host_labels = host_labels if host_labels is not None else {}
        self.owner = owner            # DisksTab, asked for free buses and nsids
        self._loading = True
        self._build()
        self._load()
        self._loading = False
        self._retitle()
        guard_all(self)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.active.isChecked():
            return
        # Paint inside the card so the glow stays visible at the scroll edges.
        # The widgets keep their normal theme and their normal hit targets.
        option = QStyleOptionGroupBox()
        self.initStyleOption(option)
        frame = QGroupBox.style(self).subControlRect(
            QStyle.ComplexControl.CC_GroupBox, option,
            QStyle.SubControl.SC_GroupBoxFrame, self)
        rect = QRectF(frame).adjusted(1, 1, -1, -1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for inset, alpha in ((6, 8), (5, 12), (4, 18), (3, 26), (2, 40)):
            painter.setPen(QPen(QColor(48, 164, 255, alpha), 2.0))
            painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset), 12, 12)
        painter.setPen(QPen(QColor(48, 164, 255, 220), 1.5))
        painter.drawRoundedRect(rect, 15, 15)
        painter.end()

    # ------------------------------------------------------------- build ---
    def _build(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        g = QGridLayout(self)
        g.setContentsMargins(8, 4, 8, 6)
        g.setVerticalSpacing(4)
        g.setHorizontalSpacing(6)
        r = 0

        # --- host device -------------------------------------------------
        self.path = DevicePicker()
        self.path.setEditable(True)
        self.path.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.path.setMinimumContentsLength(28)
        self.path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for d in self.host_disks:
            # The item TEXT is the path and nothing else. Anything decorative in
            # the text ends up written into the config when the combo is
            # editable, which is how a label once became a filename.
            self.path.addItem(d["preferred"], d["preferred"])
            self.path.setItemData(self.path.count() - 1,
                                  f"{d['size_h']}  {d['model']}  -> {d['dev']}",
                                  Qt.ItemDataRole.ToolTipRole)
        self.path.lineEdit().textEdited.connect(self._on_path)
        self.path.activated.connect(self._on_pick)
        b = QPushButton("…")
        b.setFixedWidth(30)
        b.setToolTip("Browse for a block device or image file")
        b.clicked.connect(self._browse)

        self.active = QCheckBox("Is Active")
        self.active.setToolTip(
            "Include this disk in the VM. Uncheck to keep its settings at the end "
            "of this page. Check again to use the last active slot on its controller.")
        self.active.toggled.connect(self._on_active)
        self.active.toggled.connect(self.update)

        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setFixedWidth(64)
        self.btn_remove.setToolTip(
            "Remove this disk. The highest remaining SATA port or NVMe namespace "
            "on the same controller takes its slot.")
        self.btn_remove.clicked.connect(lambda: self.removed.emit(self))
        host = QHBoxLayout()
        host.setSpacing(6)
        host.addWidget(QLabel("Device:"))
        host.addWidget(self.path, 1)
        host.addWidget(b)
        host.addWidget(self.active)
        host.addWidget(self.btn_remove)
        g.addLayout(host, r, 0, 1, 6)
        r += 1

        self.style = QComboBox()
        self.style.setFixedWidth(100)
        self.style.addItem("by-id", "by-id")
        self.style.addItem("/dev node", "dev")
        self.style.setToolTip("by-id survives reboots and controller reordering. "
                              "A few boards never create the symlink, so the kernel "
                              "name stays available.")
        self.style.activated.connect(self._on_style)

        # Keep the path style and resolved node together, with the remaining
        # space used for the drive's filesystem labels.
        self.lbl_resolved = QLabel("")
        self.lbl_resolved.setMinimumWidth(0)
        self.lbl_resolved.setSizePolicy(QSizePolicy.Policy.Ignored,
                                        QSizePolicy.Policy.Preferred)
        self.lbl_drive_label = QLabel("—")
        self.lbl_drive_label.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_drive_label.setMinimumWidth(0)
        self.lbl_drive_label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                           QSizePolicy.Policy.Preferred)
        prow = QHBoxLayout()
        prow.setContentsMargins(0, 0, 0, 0)
        prow.setSpacing(6)
        prow.addWidget(QLabel("Path:"))
        prow.addWidget(self.style)
        prow.addWidget(self.lbl_resolved, 1)
        prow.addSpacing(4)
        prow.addWidget(QLabel("Label:"))
        prow.addWidget(self.lbl_drive_label, 1)
        self.btn_mac_format = QPushButton("Mac Format…")
        self.btn_mac_format.setToolTip("Prepare this whole disk with a GUID partition map and APFS. "
                                      "Review the drive and confirm the erase before starting.")
        self.btn_mac_format.clicked.connect(lambda: self.owner.format_mac_disk(self) if self.owner else None)
        prow.addWidget(self.btn_mac_format)
        g.addLayout(prow, r, 0, 1, 6)
        r += 1

        # --- front end / bus / boot --------------------------------------
        # Keep guest placement together on its own row, below the host path.
        self.frontend = QComboBox()
        self.frontend.setFixedWidth(124)
        for name, desc in FRONTENDS:
            self.frontend.addItem(name, name)
            self.frontend.setItemData(self.frontend.count() - 1, desc,
                                      Qt.ItemDataRole.ToolTipRole)
        self.frontend.activated.connect(self._on_frontend)

        self.busline = QLineEdit()
        self.busline.setFixedWidth(88)
        self.busline.setPlaceholderText("ide.0 / nvme0")
        self.busline.textEdited.connect(self._push)
        self.busline.editingFinished.connect(self._on_bus_done)

        self.nsid = QSpinBox()
        self.nsid.setFixedWidth(54)
        self.nsid.setRange(0, 256)
        self.nsid.setSpecialValueText("-")
        self.nsid.setToolTip("NVMe namespace id")
        self.nsid.valueChanged.connect(self._push)
        self.boot = QSpinBox()
        self.boot.setFixedWidth(54)
        self.boot.setRange(0, 65535)
        self.boot.setSpecialValueText("-")
        self.boot.setToolTip("Boot index. Must be unique or QEMU refuses to start.")
        self.boot.valueChanged.connect(self._push)
        sub = QHBoxLayout()
        sub.setContentsMargins(0, 0, 0, 0)
        sub.setSpacing(4)
        for lbl, wid in (("Guest:", self.frontend), ("Bus:", self.busline),
                         ("Namespace:", self.nsid), ("Boot order:", self.boot)):
            sub.addWidget(QLabel(lbl))
            sub.addWidget(wid)
        sub.addStretch()
        g.addLayout(sub, r, 0, 1, 6)
        r += 1

        # --- driver options ------------------------------------------------
        self.cache = QComboBox()
        self.cache.setMinimumWidth(110)
        for name, spec in CACHE_MODES.items():
            self.cache.addItem(name, name)
            self.cache.setItemData(self.cache.count() - 1, spec[3], Qt.ItemDataRole.ToolTipRole)
        self.cache.activated.connect(self._on_cache)

        self.aio = QComboBox()
        self.aio.setMinimumWidth(90)
        for name, desc in AIO_MODES:
            self.aio.addItem(name, name)
            self.aio.setItemData(self.aio.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.aio.activated.connect(self._push)

        self.discard = QComboBox()
        self.discard.setMinimumWidth(90)
        for name, desc in DISCARD_MODES:
            self.discard.addItem(name, name)
            self.discard.setItemData(self.discard.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.discard.activated.connect(self._push)
        self.ro = QCheckBox("Read only")
        self.ro.setToolTip("Open the host device read only")
        self.ro.stateChanged.connect(self._push)
        options = QHBoxLayout()
        options.setSpacing(6)
        for label, widget in (("Cache:", self.cache), ("I/O mode:", self.aio),
                              ("Discard:", self.discard)):
            options.addWidget(QLabel(label))
            options.addWidget(widget, 1)
        options.addWidget(self.ro)
        g.addLayout(options, r, 0, 1, 6)
        r += 1

        # --- identity --------------------------------------------------------
        self.serial = QLineEdit()
        self.serial.setPlaceholderText("guest-visible serial")
        self.serial.textEdited.connect(self._push)
        srow = QHBoxLayout()
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(6)
        srow.addWidget(QLabel("Serial:"))
        srow.addWidget(self.serial, 1)
        self.btn_serial = QPushButton("Regen")
        self.btn_serial.setFixedWidth(76)
        self.btn_serial.clicked.connect(self.regen_serial)
        srow.addWidget(self.btn_serial)

        self.rot = QComboBox()
        self.rot.setFixedWidth(110)
        self.rot.addItem("rot: n/a", None)
        self.rot.addItem("rot: SSD", 1)
        self.rot.addItem("rot: HDD", 7200)
        self.rot.setToolTip("rotation_rate reported to the guest. 1 means solid state.")
        self.rot.activated.connect(self._push)
        srow.addWidget(self.rot)

        self.lbl_nodes = QLabel("")
        self.lbl_nodes.setStyleSheet("color: #888;")
        self.lbl_nodes.setMinimumWidth(0)
        self.lbl_nodes.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        srow.addWidget(self.lbl_nodes, 1)
        srow.setStretch(1, 3)
        g.addLayout(srow, r, 0, 1, 6)
        r += 1

        # Only warnings live here now. The cache-mode description this used to
        # repeat is already the tooltip on the cache combo itself, so it cost a
        # row on every card to say something you get by hovering. The row hides
        # itself when there is nothing to warn about, which is most of the time.
        self.opt_note = QLabel("")
        self.opt_note.setWordWrap(True)
        self.opt_note.setStyleSheet("color: #e5c07b;")
        self.opt_note.setVisible(False)
        g.addWidget(self.opt_note, r, 0, 1, 6)

        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

    # -------------------------------------------------------------- load ---
    def _load(self):
        self.active.setChecked(not self.dev.get("_disabled"))
        fn = self.bd.get("filename", "")
        self.path.setEditText(fn)
        self.style.setCurrentIndex(0 if "/by-id/" in fn else 1)

        self.frontend.setCurrentText(self.dev.get("driver", "ide-hd"))
        controller = model.disk_controller(self.dev)
        self.busline.setText(controller[1] if self.dev.get("_inactive") and controller
                             else str(self.dev.get("bus", "")))
        self._bus_loaded = self.busline.text()
        self.nsid.setValue(0 if self.dev.get("_inactive") else int(self.dev.get("nsid", 0) or 0))
        self.boot.setValue(int(self.dev.get("bootindex", 0) or 0))
        self.serial.setText(str(self.dev.get("serial", "")))
        self.ro.setChecked(bool(self.bd.get("read-only")))

        rr = self.dev.get("rotation_rate")
        self.rot.setCurrentIndex({None: 0, 1: 1, 7200: 2}.get(rr, 0))

        self.aio.setCurrentText(self.bd.get("aio", "threads"))
        self.discard.setCurrentText(self.bd.get("discard", "unmap"))
        self.cache.setCurrentText(self._detect_cache())

        self.lbl_nodes.setText(self.bd.get("node-name", "?"))
        self.lbl_nodes.setToolTip(self.lbl_nodes.text())
        self._update_notes()
        self._resolve()

    def _detect_cache(self):
        """Recover the libvirt cache mode name from the three QEMU flags."""
        c = self.bd.get("cache", {}) or {}
        got = (bool(c.get("direct")), bool(c.get("no-flush")),
               self.dev.get("write-cache", "on"))
        for name, want in CACHE_MODES.items():
            if want[:3] == got:
                return name
        return "writeback"

    # -------------------------------------------------------------- edit ---
    def _on_active(self, active):
        if not self._loading:
            self.active_changed.emit(self, active)

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select block device or image",
                                           "/dev/disk/by-id")
        if p:
            self.path.setEditText(p)
            self._on_path()

    def _on_pick(self, index):
        """A dropdown selection carries the path in userData, never the label."""
        data = self.path.itemData(index)
        if data:
            self.path.setEditText(data)
        self._on_path()

    def _on_path(self, *_):
        self._resolve()
        self._push()

    def _on_style(self, *_):
        """Switch the same disk between its by-id path and its kernel name.

        Some boards enumerate NVMe late and /dev/nvme1n1 becomes /dev/nvme0n1
        between boots, which is why by-id is the default; but a few firmwares
        never create the symlink, so the choice stays available.
        """
        cur = self.path.currentText().strip()
        want = self.style.currentData()
        real = os.path.realpath(cur) if os.path.exists(cur) else cur
        if want == "dev":
            if real != cur:
                self.path.setEditText(real)
        else:
            for d in self.host_disks:
                if os.path.realpath(d["dev"]) == real and d["by_id"]:
                    self.path.setEditText(d["preferred"])
                    break
        self._on_path()

    def _resolve(self):
        p = self.path.currentText().strip()
        self.path.setToolTip(p)
        self.lbl_resolved.setToolTip("")
        labels = {}
        if not p:
            self.lbl_resolved.setText("")
        elif not os.path.exists(p):
            self.lbl_resolved.setText("MISSING")
            self.lbl_resolved.setStyleSheet("color: #e06c75;")
        else:
            real = os.path.realpath(p)
            labels = self.host_labels.get(real, {})
            self.lbl_resolved.setText(f"-> {real}" if real != p else "ok")
            self.lbl_resolved.setStyleSheet("color: #888;")
            self.lbl_resolved.setToolTip(real)
        self.lbl_drive_label.setText(", ".join(dict.fromkeys(labels.values())) or "—")
        self.lbl_drive_label.setToolTip(
            "\n".join(f"{device}: {label}" for device, label in labels.items())
            or "No filesystem label found")
        verified = self.bd.get("_mac_format", {})
        if (self.cfg.profile == "macos" and p and os.path.exists(p)
                and verified.get("target", {}).get("realpath") == os.path.realpath(p)):
            self.lbl_drive_label.setText(verified["label"])
            self.lbl_drive_label.setToolTip(
                f"APFS volume verified by Mac Format: {verified.get('formatted_at', '')}\n"
                "Linux may not expose the volume label inside an APFS container.")

    def _on_frontend(self, *_):
        """Re-home the disk when its front-end type changes.

        An nvme-ns needs a controller to hang off and a namespace id unique to
        that controller; an ide-hd needs a free AHCI port. Leaving those blank
        produces a QEMU that refuses to start, so they are filled in here rather
        than left as an exercise.
        """
        fe = self.frontend.currentText()
        if not self._loading and self.owner:
            if fe == "nvme-ns":
                ctrl = self.owner.ensure_nvme_controller()
                if ctrl:
                    self.busline.setText(ctrl["id"])
                    self.nsid.setValue(self.owner.free_nsid(ctrl["id"], self.dev))
            elif fe in ("ide-hd", "ide-cd"):
                controller = model.disk_controller(self.dev)
                if self.dev.get("_inactive") and controller and controller[0] == "ide":
                    self.busline.setText(controller[1])
                elif not controller or controller[0] != "ide":
                    self.busline.setText(self.owner.free_ide_port(self.dev))
                self.nsid.setValue(0)
            elif fe in ("virtio-blk-pci", "scsi-hd"):
                if str(self.busline.text()).startswith(("ide.", "nvme")):
                    self.busline.setText("")
                self.nsid.setValue(0)
        self._update_notes()
        self._push()
        self._repair_layout()

    def _on_bus_done(self):
        if self.busline.text() != self._bus_loaded:
            self._repair_layout()

    def _repair_layout(self):
        """Ask the tab to re-lay the grid so pairing stays true.

        A namespace lives next to its controller, and that grouping is computed
        only at layout time; without this, retargeting a disk leaves it
        stranded where it was and the controller claiming no namespaces.
        Deferred a tick because the reload destroys this very widget.
        """
        if not self._loading and self.owner:
            QTimer.singleShot(0, self.owner.reload)

    def _on_cache(self, *_):
        self._update_notes()
        self._push()

    def _update_notes(self):
        fe = self.frontend.currentText()
        self.btn_mac_format.setVisible(self.cfg.profile == "macos" and fe != "ide-cd")
        self.btn_mac_format.setEnabled(not self.dev.get("_disabled")
                                       and bool(self.path.currentText().strip()) and not self.ro.isChecked()
                                       and self.bd.get("driver") in ("file", "host_device"))
        notes = []
        if self.aio.currentText() == "native" and self.cache.currentText() != "none":
            notes.append("aio=native without cache=none silently falls back to threads.")
        self.opt_note.setText("  ".join(notes))
        self.opt_note.setVisible(bool(notes))
        is_ns = fe == "nvme-ns"
        self.nsid.setEnabled(is_ns and not self.dev.get("_inactive"))
        self.rot.setEnabled(fe in ("ide-hd", "scsi-hd"))
        can = fe in SERIAL_CAPABLE
        self.serial.setEnabled(can)
        self.btn_serial.setEnabled(can or is_ns)
        if is_ns:
            self.serial.setPlaceholderText("nvme-ns has no serial - see the "
                                           "controller above")
            self.btn_serial.setText("New UUID")
            self.btn_serial.setToolTip("A namespace is identified by its UUID, not "
                                       "a serial. This generates a new one.")
        else:
            self.serial.setPlaceholderText("guest-visible serial")
            self.btn_serial.setText("Regen")
            self.btn_serial.setToolTip("New random serial, same length as the "
                                       "current one (or 12 characters if empty)")

    # -------------------------------------------------------------- push ---
    def _push(self, *_):
        """Write the widgets back into the two dicts the emitter reads."""
        if self._loading:
            return
        direct, noflush, wcache = CACHE_MODES[self.cache.currentText()][:3]

        self.bd["filename"] = self.path.currentText().strip()
        if ("_mac_format" in self.bd and os.path.realpath(self.bd["filename"]) !=
                self.bd["_mac_format"].get("target", {}).get("realpath")):
            self.bd.pop("_mac_format")
        self.bd["aio"] = self.aio.currentText()
        self.bd["discard"] = self.discard.currentText()
        self.bd["read-only"] = self.ro.isChecked()
        self.bd["cache"] = {"direct": direct, "no-flush": noflush}

        fe = self.frontend.currentText()
        self.dev["driver"] = fe
        self.dev["drive"] = self.bd.get("node-name")
        self.dev["bus"] = self.busline.text().strip()
        if self.dev.get("_inactive") and fe in ("ide-hd", "ide-cd"):
            # The inactive editor shows a controller, not a port reservation.
            placement = model.disk_slot(self.dev)
            self.dev["_inactive_controller"] = (placement[0][1] if placement
                                                 else self.busline.text().strip())
            self.dev.pop("bus", None)
        else:
            self.dev.pop("_inactive_controller", None)

        for key, widget in (("bootindex", self.boot), ("nsid", self.nsid)):
            v = widget.value()
            if v == 0 or (key == "nsid" and (fe != "nvme-ns" or self.dev.get("_inactive"))):
                self.dev.pop(key, None)
            else:
                self.dev[key] = v

        s = self.serial.text().strip()
        if s and fe in SERIAL_CAPABLE:
            self.dev["serial"] = s
        else:
            self.dev.pop("serial", None)
        if fe != "nvme-ns":
            self.dev.pop("uuid", None)

        # write-cache is meaningless on a CD, and rotation_rate only exists on
        # disks that claim to spin.
        if fe == "ide-cd":
            self.dev.pop("write-cache", None)
            self.dev.pop("rotation_rate", None)
        else:
            self.dev["write-cache"] = wcache
            rr = self.rot.currentData()
            if rr and fe in ("ide-hd", "scsi-hd"):
                self.dev["rotation_rate"] = rr
            else:
                self.dev.pop("rotation_rate", None)

        self._retitle()
        self._update_notes()
        self.changed.emit()

    def regen_serial(self):
        """New identity for this disk, in whatever form its front-end has one."""
        if self.frontend.currentText() == "nvme-ns":
            self.dev["uuid"] = randomize.uuid4().lower()
            self.serial.setText("")
            self._push()
            self.changed.emit()
            return
        cur = self.serial.text().strip()
        self.serial.setText(randomize.serial(len(cur) if cur else 12))
        self._push()

    def _retitle(self):
        name = os.path.basename(self.path.currentText().strip()) or "(no device)"
        if len(name) > 44:
            name = name[:41] + "..."
        status = "Inactive · " if self.dev.get("_inactive") else ""
        self.setTitle(f"{status}{self.dev.get('id','disk')}   {self.frontend.currentText()}   {name}")
        self.busline.setToolTip("Inactive: no slot assigned. This controller will be used when reactivated."
                                if self.dev.get("_inactive") else "Guest controller / port")


class DisksTab(QScrollArea):
    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.rows = []
        self.ctrl_cards = []
        self.setWidgetResizable(True)
        self.host_disks = hostinfo.block_devices()
        self.host_labels = hostinfo.block_device_labels()
        self._build()
        self.reload()

    def _build(self):
        w = QWidget()
        self.setWidget(w)
        self.lay = QVBoxLayout(w)
        self.lay.setSpacing(6)

        head = QLabel(
            "Choose a host device or image for each disk, then set how the guest sees it. "
            "Uncheck Is Active to keep a disk for later. NVMe controllers stay with their active namespaces.")
        head.setWordWrap(True)
        self.lay.addWidget(head)

        # Use a second column only when both cards fit without horizontal scrolling.
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("""
            QGroupBox { margin-top: 12px; padding: 8px 0px 2px; }
            QGroupBox::title { left: 8px; padding: 0px 4px; }
            QGroupBox[inactive="true"] { border-style: dashed; }
            QGroupBox[inactive="true"]::title { color: #888; }
            QPushButton { padding: 3px 6px; }
        """)
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(0, 1)
        self.lay.addWidget(self.grid_host)

        btns = QHBoxLayout()
        add = QPushButton("Add disk")
        add.setObjectName("accent")
        add.clicked.connect(self.add_disk)
        btns.addWidget(add)
        addiso = QPushButton("Add ISO (CD-ROM)")
        addiso.setToolTip("Attach an .iso file as a read-only SATA optical drive "
                          "(ide-cd). Use it for an installer or a driver disc.")
        addiso.clicked.connect(self.add_iso)
        btns.addWidget(addiso)
        addc = QPushButton("Add NVMe controller")
        addc.setToolTip("Namespaces attach to a controller. A second one makes "
                        "the guest see two separate NVMe devices.")
        addc.clicked.connect(self.add_controller_with_slot)
        btns.addWidget(addc)
        btns.addStretch()
        self.lbl_count = QLabel("")
        btns.addWidget(self.lbl_count)
        self.lay.insertLayout(1, btns)
        maintenance = QHBoxLayout()
        rescan = QPushButton("Rescan host disks")
        rescan.clicked.connect(self._rescan)
        maintenance.addWidget(rescan)
        regen = QPushButton("Regenerate all serials")
        regen.setToolTip("New random serial for every disk and every NVMe "
                         "controller. Lengths are preserved.")
        regen.clicked.connect(self.regen_all_serials)
        maintenance.addWidget(regen)
        maintenance.addStretch()
        self.lay.insertLayout(2, maintenance)

        self.warn = QPlainTextEdit()
        self.warn.setReadOnly(True)
        self.warn.setFont(QFont(MONO, 10))
        self.warn.setMaximumHeight(90)
        self.lay.addWidget(self.warn)
        self.lay.addStretch()

    # ------------------------------------------------------------ reload ---
    def reload(self):
        for r in self.rows + self.ctrl_cards:
            if isinstance(r, DiskRow):
                # Losing focus during teardown can commit an old editor value.
                # The model may already contain the replacement slot, so an
                # outgoing card must not write its previous assignment back.
                r._loading = True
            self.grid.removeWidget(r)
            r.setParent(None)
            r.deleteLater()
        self.rows = []
        self.ctrl_cards = []


        # Live entries win the name. Built naively this collapses duplicates to
        # whichever came last, which can pair a card with a tombstone and leave
        # the real blockdev unedited.
        by_node = {b.get("node-name"): b for b in self.cfg.blockdevs
                   if not b.get("_disabled") or b.get("_inactive")}
        self._card_groups = []
        # Order: each NVMe controller followed immediately by the namespaces
        # that hang off it, then everything else. A controller sitting apart
        # from its namespaces reads as unrelated, and the pairing is the whole
        # point -- the controller carries the serial the guest sees for them.
        disk_devs = [d for d in self.cfg.devices
                     if (not d.get("_disabled") or d.get("_inactive"))
                     and d.get("driver") in dict(FRONTENDS)
                     and by_node.get(d.get("drive"))]
        inactive_devs = sorted((d for d in disk_devs if d.get("_inactive")),
                               key=lambda d: d["_inactive"])
        disk_devs = [d for d in disk_devs if not d.get("_disabled")]
        # Show actual port/namespace order, including after a removal or slot
        # reuse. Sort only this view: cfg.devices is indexed by emission order.
        disk_devs.sort(key=lambda dev: model.disk_slot(dev) or (("other", ""), 0))

        def disk_card(dev):
            row = DiskRow(self.cfg, by_node[dev["drive"]], dev, self.host_disks,
                          owner=self, host_labels=self.host_labels)
            row.changed.connect(self._on_row_changed)
            row.removed.connect(self.remove_disk)
            row.active_changed.connect(self.set_disk_active)
            self.rows.append(row)
            return row

        placed = set()
        for ctrl in self.nvme_controllers():
            card = self._ctrl_card(ctrl)
            self.ctrl_cards.append(card)
            group = [card]
            for dev in disk_devs:
                if dev.get("driver") == "nvme-ns" and dev.get("bus") == ctrl.get("id"):
                    group.append(disk_card(dev))
                    placed.add(id(dev))
            self._card_groups.append(group)

        other = []
        for dev in disk_devs:
            if id(dev) not in placed:
                other.append(disk_card(dev))
        if other:
            self._card_groups.append(other)
        if inactive_devs:
            self._card_groups.append([disk_card(dev) for dev in inactive_devs])

        self._layout_cards(force=True)
        self._check()
        guard_all(self.grid_host)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_card_groups"):
            self._layout_cards()

    def _layout_cards(self, force=False):
        cards = [card for group in self._card_groups for card in group]
        minimum = max((card.minimumSizeHint().width() for card in cards), default=700)
        columns = 2 if self.viewport().width() >= 2 * minimum + 50 else 1
        if not force and columns == getattr(self, "_columns", None):
            return
        self._columns = columns
        for card in cards:
            self.grid.removeWidget(card)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        # Keep related cards adjacent without leaving an empty half-row at
        # every controller boundary. Inactive cards are already at the end.
        for i, card in enumerate(cards):
            self.grid.addWidget(card, i // columns, i % columns, Qt.AlignmentFlag.AlignTop)

    def _ctrl_card(self, ctrl):
        """An NVMe controller as a card, sized like a disk card."""
        w = QGroupBox(f"{ctrl.get('id','nvme')}   emulated NVMe controller")
        g = QGridLayout(w)
        g.setContentsMargins(8, 2, 8, 6)
        g.setVerticalSpacing(3)
        g.setHorizontalSpacing(6)

        ser = QLineEdit(str(ctrl.get("serial", "")))
        ser.setToolTip("The controller's own serial. This is what the guest shows "
                       "as the NVMe device serial; the namespaces under it have "
                       "no serial of their own.")
        ser.textEdited.connect(lambda t, c=ctrl: self._set_ctrl(c, "serial", t))
        g.addWidget(QLabel("Serial:"), 0, 0)
        g.addWidget(ser, 0, 1, 1, 2)
        rb = QPushButton("Regen")
        rb.setFixedWidth(80)
        rb.clicked.connect(lambda _, c=ctrl, e=ser: self._regen_ctrl(c, e))
        g.addWidget(rb, 0, 3)

        rm = QPushButton("Remove")
        rm.setFixedWidth(70)
        rm.clicked.connect(lambda _, c=ctrl: self._remove_ctrl(c))
        g.addWidget(rm, 0, 4)

        bus = QLineEdit(str(ctrl.get("bus", "")))
        bus.setMinimumWidth(110)
        bus.textEdited.connect(lambda t, c=ctrl: self._set_ctrl(c, "bus", t))
        addr = QLineEdit(str(ctrl.get("addr", "")))
        addr.setFixedWidth(70)
        addr.textEdited.connect(lambda t, c=ctrl: self._set_ctrl(c, "addr", t))
        g.addWidget(QLabel("Bus:"), 1, 0)
        g.addWidget(bus, 1, 1)
        g.addWidget(QLabel("addr:"), 1, 2)
        g.addWidget(addr, 1, 3)

        ns = [d for d in self.cfg.devices if d.get("driver") == "nvme-ns"
              and not d.get("_disabled") and d.get("bus") == ctrl.get("id")]
        ns.sort(key=lambda dev: model.disk_slot(dev) or (("other", ""), 0))
        lbl = QLabel(", ".join(f"{d.get('id')} (ns{d.get('nsid','?')})" for d in ns)
                     or "no namespaces attached")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #888;")
        g.addWidget(QLabel("Namespaces:"), 2, 0)
        g.addWidget(lbl, 2, 1, 1, 4)
        g.setColumnStretch(1, 1)
        return w

    def _set_ctrl(self, ctrl, key, val):
        ctrl[key] = val.strip()
        self._on_row_changed()

    def _regen_ctrl(self, ctrl, edit):
        """New random serial for a controller, same length as the current one."""
        cur = str(ctrl.get("serial", ""))
        v = randomize.serial(len(cur) if cur else 12)
        ctrl["serial"] = v
        edit.setText(v)
        self._on_row_changed()

    def _remove_ctrl(self, ctrl):
        """Removing a controller orphans its namespaces, so say so first."""
        ns = [d for d in self.cfg.devices if d.get("driver") == "nvme-ns"
              and (not d.get("_disabled") or d.get("_inactive")) and d.get("bus") == ctrl.get("id")]
        if ns:
            from PyQt6.QtWidgets import QMessageBox
            if QMessageBox.question(
                    self, "Remove controller",
                    f"{ctrl.get('id')} still has {len(ns)} namespace(s), including inactive disks "
                    f"({', '.join(d.get('id','?') for d in ns)}).\n\n"
                    f"Remove the controller and those disks with it?"
                    ) != QMessageBox.StandardButton.Yes:
                return
            for d in ns:
                d["_disabled"] = True
                d.pop("_inactive", None)
                # Match the LIVE blockdev. A name can also be held by a
                # tombstone, and disabling that one instead leaves the live
                # blockdev emitted with no device behind it.
                bd = next((b for b in self.cfg.blockdevs
                           if b.get("node-name") == d.get("drive")
                           and (not b.get("_disabled") or b.get("_inactive"))), None)
                if bd:
                    bd["_disabled"] = True
                    bd.pop("_inactive", None)
        ctrl["_disabled"] = True
        self.reload()
        self.changed.emit()

    def _rescan(self):
        self.host_disks = hostinfo.block_devices()
        self.host_labels = hostinfo.block_device_labels()
        self.reload()

    def format_mac_disk(self, row):
        if (self.cfg.profile != "macos" or row.dev.get("_disabled")
                or row.dev.get("driver") == "ide-cd" or row.bd.get("read-only")):
            return
        import mac_format
        from mac_format_dialog import MacFormatDialog
        import virtual_gpu
        try:
            if virtual_gpu.service_active():
                raise ValueError("Shut down the running VM first, then open Mac Format again. "
                                 "The formatter needs exclusive access to the selected drive.")
            mac_format.installation_port(self.cfg, row.dev)
            dialog = MacFormatDialog(self.cfg, row.path.currentText().strip(), self)
            dialog.exec()
            if dialog.result_data:
                mac_format.apply_format_result(self.cfg, row.bd, row.dev, dialog.result_data)
                self._rescan()
                self.changed.emit()
            dialog.deleteLater()
        except Exception as error:
            QMessageBox.warning(self, "Mac Format", str(error))

    # ------------------------------------------------------- allocation ---
    def nvme_controllers(self):
        return [d for d in self.cfg.devices
                if d.get("driver") == "nvme" and not d.get("_disabled")]

    def ensure_nvme_controller(self):
        """Return an NVMe controller, creating one if the config has none."""
        ctrls = self.nvme_controllers()
        if ctrls:
            return ctrls[0]
        return self.add_nvme_controller()

    def add_nvme_controller(self):
        """Add an emulated NVMe controller on a free PCI slot."""
        # Only live devices reserve a name. Removal marks rather than deletes,
        # so counting the tombstones too made the numbering climb forever:
        # delete nvme0..nvme3 and the next one added still came back as nvme4.
        used = {d.get("id") for d in self.cfg.devices if not d.get("_disabled")}
        n = 0
        while f"nvme{n}" in used:
            n += 1
        # Find somewhere it actually fits. A pcie-root-port has exactly one
        # downstream slot (device 0); only a pcie-pci-bridge takes several.
        # Putting a second device on a root port produces a QEMU that starts
        # and a guest that never sees the disk.
        taken = {(d.get("bus"), str(d.get("addr", "0x0"))) for d in self.cfg.devices
                 if not d.get("_disabled")}
        occupied_bus = {d.get("bus") for d in self.cfg.devices if not d.get("_disabled")}
        bus, addr = "", "0x0"
        for d in self.cfg.devices:
            if d.get("_disabled"):
                continue
            if d.get("driver") == "pcie-pci-bridge":
                for slot in range(1, 32):
                    if (d["id"], hex(slot)) not in taken:
                        bus, addr = d["id"], hex(slot)
                        break
            elif d.get("driver") == "pcie-root-port" and d["id"] not in occupied_bus:
                bus, addr = d["id"], "0x0"
            if bus:
                break
        ctrl = {"driver": "nvme", "id": f"nvme{n}",
                "serial": _random_serial(12), "bus": bus, "addr": addr}
        self.cfg.devices.append(ctrl)
        return ctrl

    def free_nsid(self, ctrl_id, exclude=None):
        """Lowest namespace id not already used on that controller."""
        used = {d.get("nsid") for d in self.cfg.devices
                if d.get("driver") == "nvme-ns" and not d.get("_disabled")
                and d.get("bus") == ctrl_id and d is not exclude}
        n = 1
        while n in used:
            n += 1
        return n

    def free_ide_port(self, exclude=None):
        """Lowest AHCI port not already occupied.

        q35's built-in ICH9 AHCI exposes six ports; past that the disk needs a
        separate controller, so that limit is surfaced rather than hidden.
        """
        used = {d.get("bus") for d in self.cfg.devices
                if d.get("driver") in ("ide-hd", "ide-cd") and not d.get("_disabled")
                and d is not exclude}
        for n in range(32):
            if f"ide.{n}" not in used:
                return f"ide.{n}"
        return "ide.0"

    def _on_row_changed(self):
        self._check()
        self.changed.emit()

    # --------------------------------------------------------- add/remove ---
    def _next_index(self):
        """First free n for the vmstart2-disk{n} / vmstart2-{n}-storage pair."""
        return model.free_index(self.cfg.blockdevs, self.cfg.devices)

    # Shared with the wizard, which builds the same disks from its own step.
    _claim = staticmethod(model.claim_slot)

    def add_disk(self):
        n = self._next_index()
        bd = {"driver": "host_device", "filename": "", "aio": "threads",
              "node-name": f"vmstart2-{n}-storage", "read-only": False,
              "discard": "unmap", "cache": {"direct": True, "no-flush": False}}
        dev = {"driver": "ide-hd", "bus": self.free_ide_port(),
               "drive": bd["node-name"], "id": f"vmstart2-disk{n}",
               "write-cache": "on", "serial": _random_serial(11)}
        self._claim(self.cfg.blockdevs, "node-name", bd["node-name"], bd)
        self._claim(self.cfg.devices, "id", dev["id"], dev)
        self.reload()
        self.changed.emit()

    def add_iso(self):
        """Attach an .iso as a read-only ide-cd optical drive.

        An ISO is a regular file, so its blockdev uses driver=file (not
        host_device) and read-only=true — the guest sees a CD it cannot write.
        The path is picked up front so the card lands populated rather than
        empty.
        """
        iso, _ = QFileDialog.getOpenFileName(
            self, "Select ISO image", os.path.expanduser("~"),
            "ISO images (*.iso *.img);;All files (*)")
        if not iso:
            return
        n = self._next_index()
        bd = {"driver": "file", "filename": iso,
              "node-name": f"vmstart2-{n}-storage", "read-only": True}
        dev = {"driver": "ide-cd", "bus": self.free_ide_port(),
               "drive": bd["node-name"], "id": f"vmstart2-disk{n}",
               "serial": _random_serial(11)}
        self._claim(self.cfg.blockdevs, "node-name", bd["node-name"], bd)
        self._claim(self.cfg.devices, "id", dev["id"], dev)
        self.reload()
        self.changed.emit()

    def add_controller_with_slot(self):
        """Controller plus one empty namespace hanging off it.

        A bare controller pairs with nothing at layout time, so its row showed
        no place to pick a drive. Creating the first namespace with it puts the
        device picker right next to the controller, which is the arrangement
        the grid is built around.
        """
        ctrl = self.add_nvme_controller()
        n = self._next_index()
        bd = {"driver": "host_device", "filename": "", "aio": "threads",
              "node-name": f"vmstart2-{n}-storage", "read-only": False,
              "discard": "unmap", "cache": {"direct": True, "no-flush": False}}
        dev = {"driver": "nvme-ns", "bus": ctrl["id"],
               "nsid": self.free_nsid(ctrl["id"]),
               "drive": bd["node-name"], "id": f"vmstart2-disk{n}",
               "write-cache": "on", "uuid": randomize.uuid4().lower()}
        self._claim(self.cfg.blockdevs, "node-name", bd["node-name"], bd)
        self._claim(self.cfg.devices, "id", dev["id"], dev)
        self.reload()
        self.changed.emit()

    def remove_disk(self, row):
        # Marked, not deleted: the emitter walks a recorded index order and
        # deleting would repoint every later entry.
        was_active = not row.dev.get("_disabled")
        row.bd["_disabled"] = True
        row.dev["_disabled"] = True
        row.bd.pop("_inactive", None)
        row.dev.pop("_inactive", None)
        if was_active:
            model.fill_removed_disk_slot(self.cfg.devices, row.dev)
        self.reload()
        self.changed.emit()

    def set_disk_active(self, row, active):
        try:
            model.set_disk_active(self.cfg, row.bd, row.dev, active)
        except ValueError as error:
            row._loading = True
            row.active.setChecked(not row.dev.get("_disabled"))
            row._loading = False
            QMessageBox.warning(self, "Cannot activate disk", str(error))
            return
        self.reload()
        self.changed.emit()

    def regen_all_serials(self):
        """Fresh serials for every disk and controller in one go.

        Uniqueness is checked afterwards rather than assumed: two devices
        reporting the same serial is exactly the anomaly this is meant to avoid.
        """
        from PyQt6.QtWidgets import QMessageBox
        n = (len([r for r in self.rows if r.dev.get("driver") in SERIAL_CAPABLE])
             + len(self.nvme_controllers()))
        if QMessageBox.question(
                self, "Regenerate all serials",
                f"Give all {n} devices new random serials?\n\n"
                f"The guest may recognize these disks as new hardware."
                ) != QMessageBox.StandardButton.Yes:
            return
        seen = set()
        for r in self.rows:
            if r.dev.get("driver") not in SERIAL_CAPABLE:
                # A namespace carries a UUID instead; writing serial= here would
                # produce a QEMU that refuses to start.
                if r.dev.get("driver") == "nvme-ns":
                    r.dev["uuid"] = randomize.uuid4().lower()
                    r.dev.pop("serial", None)
                continue
            cur = r.dev.get("serial", "")
            v = randomize.serial(len(cur) if cur else 12)
            while v in seen:
                v = randomize.serial(len(cur) if cur else 12)
            seen.add(v)
            r.dev["serial"] = v
        for c in self.nvme_controllers():
            v = randomize.serial(len(c.get("serial", "")) or 12)
            while v in seen:
                v = randomize.serial(len(c.get("serial", "")) or 12)
            seen.add(v)
            c["serial"] = v
        self.reload()
        self.changed.emit()

    # ------------------------------------------------------------- check ---
    def _check(self):
        msgs = []
        serials, boots, buses, targets, nsids = {}, {}, {}, {}, {}
        for r in self.rows:
            if r.dev.get("_disabled"):
                continue
            did = r.dev.get("id")
            s = r.dev.get("serial")
            if s:
                if s in serials:
                    msgs.append(f"duplicate serial {s}: {serials[s]} and {did}")
                serials[s] = did
            b = r.dev.get("bootindex")
            if b:
                if b in boots:
                    msgs.append(f"duplicate bootindex {b}: {boots[b]} and {did} "
                                f"- QEMU will refuse to start")
                boots[b] = did
            bus = r.dev.get("bus")
            if bus and r.dev.get("driver") in ("ide-hd", "ide-cd"):
                if bus in buses:
                    msgs.append(f"two disks on AHCI port {bus}: {buses[bus]} and {did}")
                buses[bus] = did

            if r.dev.get("serial") and r.dev.get("driver") not in SERIAL_CAPABLE:
                msgs.append(f"{did}: {r.dev.get('driver')} has no 'serial' property; "
                            f"QEMU will refuse to start")

            fn = r.bd.get("filename", "")
            if not fn:
                msgs.append(f"{did}: no host device selected")
            elif not os.path.exists(fn):
                msgs.append(f"{did}: {fn} does not exist")
            else:
                # Two front-ends on one physical disk means both guests write
                # the same blocks. This is the one that eats a filesystem.
                real = os.path.realpath(fn)
                if real in targets:
                    msgs.append(f"DANGER: {targets[real]} and {did} both point at "
                                f"{real}. Two front-ends on one disk will corrupt it.")
                targets[real] = did

            if r.dev.get("driver") == "nvme-ns":
                ctrl_ids = {c.get("id") for c in self.nvme_controllers()}
                if r.dev.get("bus") not in ctrl_ids:
                    msgs.append(f"{did}: bus '{r.dev.get('bus')}' is not an NVMe "
                                f"controller ({', '.join(sorted(ctrl_ids)) or 'none defined'})")
                key = (r.dev.get("bus"), r.dev.get("nsid"))
                if not r.dev.get("nsid"):
                    msgs.append(f"{did}: NVMe namespace needs an nsid")
                elif key in nsids:
                    msgs.append(f"duplicate nsid {key[1]} on {key[0]}: "
                                f"{nsids[key]} and {did}")
                nsids[key] = did

        for c in self.nvme_controllers():
            cs = c.get("serial")
            if cs and cs in serials:
                msgs.append(f"NVMe controller {c.get('id')} serial {cs} is also used "
                            f"by disk {serials[cs]}")
            if not cs:
                msgs.append(f"NVMe controller {c.get('id')} has no serial")

        inactive = sum(bool(row.dev.get("_inactive")) for row in self.rows)
        self.lbl_count.setText(f"{len(self.rows) - inactive} active · {inactive} inactive"
                               if inactive else f"{len(self.rows)} disks")
        self.problems = msgs
        self.warn.setPlainText("\n".join(msgs) if msgs else "No disk problems found.")
        self.warn.setFixedHeight(90 if msgs else self.warn.fontMetrics().lineSpacing() + 14)
