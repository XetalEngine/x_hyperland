"""Spare-GPU selection and desktop-preserving guest controls."""

from pathlib import Path
import shutil
import time

from PyQt6.QtCore import QSignalBlocker, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                             QSpinBox, QTextBrowser, QVBoxLayout, QWidget, QListWidget, QListWidgetItem)

import dual_gpu
import dual_devices
import gpu_inventory
import input_devices
import virtual_gpu


class DualGPUTab(QScrollArea):
    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._loading = True
        self._auto_open = False
        self._last_output = None
        self._submission_deadline = 0
        self.run = dual_gpu.current_run()
        opts = dual_gpu.options(cfg)
        mac = cfg.profile == "macos"
        self._identity = opts["gpu_identity"]
        self.setWidgetResizable(True)
        content = QWidget()
        self.setWidget(content)
        layout = QVBoxLayout(content)

        launch = QGroupBox("Launch")
        body = QVBoxLayout(launch)
        note = QLabel("Give Windows an unused physical GPU while Linux keeps its desktop GPU. "
                      "Use the iGPU for lighter work, or a spare graphics card for more performance. "
                      "This uses the same guest disks, CPU, RAM size, firmware and TPM identity.")
        note.setWordWrap(True)
        if mac:
            note.setText("Give macOS an unused physical GPU with a compatible installed macOS driver. "
                         "Linux keeps its desktop GPU. OpenCore, disks and private NVRAM are shared with Single GPU.")
        body.addWidget(note)
        row = QHBoxLayout()
        self.btn_launch = QPushButton("Launch VM")
        self.btn_launch.setObjectName("accentBig")
        self.btn_launch.setMinimumSize(160, 38)
        self.btn_launch.clicked.connect(self._launch)
        row.addWidget(self.btn_launch)
        for title, callback in (("Preflight check", self._preflight), ("Preview command", self._preview),
                                ("Setup guide", self._guide)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        body.addLayout(row)
        row = QHBoxLayout()
        self.btn_viewer = QPushButton("Open viewer")
        self.btn_viewer.clicked.connect(self._open_viewer)
        self.btn_console = QPushButton("Open setup console")
        self.btn_console.clicked.connect(self._open_console)
        self.btn_shutdown = QPushButton("Shut down guest")
        self.btn_shutdown.clicked.connect(lambda: self._control("system_powerdown"))
        self.btn_restart = QPushButton("Restart guest…")
        self.btn_restart.setToolTip("Reset the virtual machine immediately")
        self.btn_restart.clicked.connect(lambda: self._control("system_reset"))
        self.btn_stop = QPushButton("Force off…")
        self.btn_stop.clicked.connect(lambda: self._control("quit"))
        for button in (self.btn_viewer, self.btn_console, self.btn_shutdown, self.btn_restart, self.btn_stop):
            row.addWidget(button)
        row.addStretch()
        body.addLayout(row)
        self.state = QLabel("Ready")
        self.state.setObjectName("muted")
        self.state.setWordWrap(True)
        body.addWidget(self.state)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Monospace", 10))
        self.log.setMinimumHeight(130)
        self.log.setMaximumHeight(180)
        self.log.setPlaceholderText("GPU checks and launch output appear here.")
        body.addWidget(self.log)
        layout.addWidget(launch)

        group = QGroupBox("Guest GPU")
        form = QFormLayout(group)
        row = QHBoxLayout()
        self.gpu = QComboBox()
        self.gpu.setMinimumContentsLength(24)
        self.gpu.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.gpu.setAccessibleName("Unused GPU for the guest")
        row.addWidget(self.gpu, 1)
        self.btn_refresh = QPushButton("Refresh GPUs")
        self.btn_refresh.clicked.connect(lambda: self.refresh_gpus())
        row.addWidget(self.btn_refresh)
        form.addRow("GPU / iGPU", row)
        self.gpu_audio = QCheckBox("Include the GPU's HDMI / DisplayPort audio")
        self.gpu_audio.setChecked(opts["gpu_audio"])
        self.gpu_audio.setToolTip("Optional when audio has a separate IOMMU group. Leave it unchecked "
                                 "to keep Linux audio services on that device. SPICE audio is a separate option.")
        form.addRow(self.gpu_audio)
        audio_note = QLabel("HDMI audio is optional. If WirePlumber holds only the separate audio device, "
                            "leave this unchecked to use the GPU while Linux keeps its audio.")
        audio_note.setWordWrap(True)
        audio_note.setObjectName("muted")
        form.addRow(audio_note)
        self.detected = QLabel()
        self.detected.setWordWrap(True)
        self.detected.setObjectName("muted")
        form.addRow(self.detected)
        self.romfile = QLineEdit(opts["romfile"])
        self.romfile.setPlaceholderText("Optional — a ROM for this selected GPU")
        row = QHBoxLayout()
        row.addWidget(self.romfile, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_rom)
        row.addWidget(browse)
        form.addRow("GPU ROM", row)
        note = QLabel("Detected GPUs stay visible; unavailable entries explain what is using them. "
                      "Only available GPUs can be selected. Active displays, device users and shared IOMMU "
                      "groups are checked again before launch. The selected GPU's original driver is restored "
                      "after shutdown. A GPU disabled in BIOS appears only after enabling it and rebooting.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        form.addRow(note)
        layout.addWidget(group)

        display = QGroupBox("Display and integration")
        form = QFormLayout(display)
        self.viewer = QComboBox()
        for value, label in dual_gpu.VIEWERS.items():
            if mac and value == "looking-glass":
                continue
            self.viewer.addItem(label, value)
        self.viewer.setCurrentIndex(max(0, self.viewer.findData(opts["viewer"])))
        form.addRow("View guest", self.viewer)
        self.auto_open = QCheckBox("Open selected viewer after launch")
        self.auto_open.setChecked(opts["auto_open"])
        form.addRow(self.auto_open)
        row = QHBoxLayout()
        self.width, self.height = QSpinBox(), QSpinBox()
        for widget, key, minimum in ((self.width, "width", 640), (self.height, "height", 480)):
            widget.setRange(minimum, 4096)
            widget.setValue(opts[key])
            widget.setSingleStep(80)
            widget.setMaximumWidth(120)
        row.addWidget(self.width)
        row.addWidget(QLabel("×"))
        row.addWidget(self.height)
        row.addStretch()
        self.resolution_label = QLabel()
        form.addRow(self.resolution_label, row)
        self.resolution_note = QLabel()
        self.resolution_note.setWordWrap(True)
        self.resolution_note.setObjectName("muted")
        form.addRow(self.resolution_note)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(opts["port"])
        self.port_label = QLabel()
        form.addRow(self.port_label, self.port)
        self.clipboard = QCheckBox("Share clipboard")
        self.file_transfer = QCheckBox("Allow file transfer")
        self.audio = QCheckBox("Play guest audio through the viewer")
        for widget, key in ((self.clipboard, "clipboard"), (self.file_transfer, "file_transfer"),
                            (self.audio, "audio")):
            widget.setChecked(opts[key])
            form.addRow(widget)
            if mac and key in ("clipboard", "file_transfer"):
                widget.setChecked(False)
                widget.hide()
        self.audio_mode = QComboBox()
        for value, title in dual_gpu.AUDIO_MODES.items():
            if mac and value == "lg-usb":
                continue
            self.audio_mode.addItem(title, value)
        self.audio_mode.setCurrentIndex(max(0, self.audio_mode.findData(opts["audio_mode"])))
        form.addRow("Audio method", self.audio_mode)
        self.audio_note = QLabel()
        self.audio_note.setWordWrap(True)
        self.audio_note.setObjectName("muted")
        form.addRow(self.audio_note)
        self.viewer_note = QLabel()
        self.viewer_note.setWordWrap(True)
        self.viewer_note.setObjectName("muted")
        form.addRow(self.viewer_note)
        layout.addWidget(display)

        group = QGroupBox("Keyboard and mouse")
        form = QFormLayout(group)
        self.input_mode = QComboBox()
        self.input_mode.addItem("Viewer window", "viewer")
        self.input_mode.addItem("evdev — share a Linux keyboard and mouse", "evdev")
        self.input_mode.setCurrentIndex(max(0, self.input_mode.findData(opts["input_mode"])))
        form.addRow("Input method", self.input_mode)
        self.evdev_keyboard, self.evdev_mouse = QComboBox(), QComboBox()
        for role, combo in (("keyboard", self.evdev_keyboard), ("mouse", self.evdev_mouse)):
            combo.setMinimumContentsLength(24)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setAccessibleName("evdev " + role)
            form.addRow(role.capitalize(), combo)
        self.evdev_toggle = QComboBox()
        for value, title in input_devices.TOGGLES.items():
            self.evdev_toggle.addItem(title, value)
        self.evdev_toggle.setCurrentIndex(max(0, self.evdev_toggle.findData(opts["evdev_toggle"])))
        form.addRow("Switch Linux / macOS" if mac else "Switch Linux / Windows", self.evdev_toggle)
        self.btn_inputs = QPushButton("Refresh input devices")
        self.btn_inputs.clicked.connect(lambda: self.refresh_inputs())
        form.addRow(self.btn_inputs)
        self.lg_capture = QCheckBox("Capture keyboard and mouse when Looking Glass opens")
        self.lg_capture.setChecked(opts["lg_capture"])
        form.addRow(self.lg_capture)
        if mac:
            self.lg_capture.hide()
        self.input_note = QLabel()
        self.input_note.setWordWrap(True)
        self.input_note.setObjectName("muted")
        form.addRow(self.input_note)
        layout.addWidget(group)

        group = QGroupBox("USB / PCI passthrough")
        body = QVBoxLayout(group)
        note = QLabel("Select physical devices for this Dual GPU preset. The guest has exclusive use while "
                      "the VM runs; PCI drivers are restored on shutdown. A USB controller includes all "
                      "devices connected to its ports. For keyboard/mouse sharing, use evdev above instead.")
        note.setWordWrap(True)
        body.addWidget(note)
        self.usb_devices, self.pci_devices = QListWidget(), QListWidget()
        for label, widget in (("Individual USB devices", self.usb_devices),
                              ("PCI devices — onboard audio, USB controllers, unused network/serial cards", self.pci_devices)):
            body.addWidget(QLabel(label))
            widget.setAccessibleName(label)
            widget.setMinimumHeight(130)
            widget.setMaximumHeight(200)
            body.addWidget(widget)
        self.btn_devices = QPushButton("Refresh USB / PCI devices")
        self.btn_devices.clicked.connect(lambda: self.refresh_devices())
        body.addWidget(self.btn_devices)
        note = QLabel("For a USB headset/DAC, select it in the USB list. For motherboard analog/S/PDIF "
                      "outputs, select the onboard audio controller in the PCI list. For HDMI/DisplayPort "
                      "sound, use the Guest GPU audio checkbox. Choose that output in the guest's Sound settings. "
                      "Physical audio does not need viewer audio enabled. Mounted storage, active network "
                      "interfaces, evdev conflicts and shared IOMMU groups are checked before launch.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        body.addWidget(note)
        layout.addWidget(group)

        shared = QGroupBox("Shared preset options")
        form = QFormLayout(shared)
        self.memory = QComboBox()
        self.memory.addItem("Preset memory backing (same RAM size)", "preset")
        self.memory.addItem("Ordinary RAM (same RAM size)", "ordinary")
        self.memory.setCurrentIndex(max(0, self.memory.findData(opts["memory"])))
        form.addRow("Memory", self.memory)
        self.network = QComboBox()
        for label, value in (("Preset network (private tap on the same bridge)", "preset"),
                             ("User networking (NAT)", "user"), ("Disconnected", "off")):
            self.network.addItem(label, value)
        self.network.setCurrentIndex(max(0, self.network.findData(opts["network"])))
        form.addRow("Networking", self.network)
        self.pinning = QCheckBox("Use preset CPU affinity")
        self.pinning.setChecked(opts["pinning"])
        form.addRow(self.pinning)
        note = QLabel("These options are saved with this preset for Dual GPU launches. "
                      "Single GPU start/revert scripts and host reboot are skipped. "
                      "This mode does not apply the Virtual GPU firmware-resolution override.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        form.addRow(note)
        layout.addWidget(shared)
        layout.addStretch()

        self.refresh_gpus(opts["gpu"])
        self.refresh_inputs(opts["evdev_keyboard"], opts["evdev_mouse"])
        self.refresh_devices(opts)
        self.gpu.currentIndexChanged.connect(self._gpu_changed)
        self.gpu_audio.toggled.connect(self._audio_changed)
        self.romfile.textChanged.connect(self._changed)
        for combo in (self.viewer, self.memory, self.network, self.input_mode,
                      self.evdev_keyboard, self.evdev_mouse, self.evdev_toggle, self.audio_mode):
            combo.currentIndexChanged.connect(self._changed)
        for spin in (self.port, self.width, self.height):
            spin.valueChanged.connect(self._changed)
        for check in (self.auto_open, self.clipboard, self.file_transfer, self.audio, self.pinning,
                      self.lg_capture):
            check.toggled.connect(self._changed)
        for widget in (self.usb_devices, self.pci_devices):
            widget.itemChanged.connect(self._device_changed)
        self._loading = False
        self._update_options()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self._poll()

    def refresh_gpus(self, selected=None):
        selected = self.gpu.currentData() if selected is None else selected
        blocker = QSignalBlocker(self.gpu)
        self.gpu.clear()
        self.gpu.addItem("Choose an unused GPU…", "")
        try:
            self.inventory = gpu_inventory.discover(audio=self.gpu_audio.isChecked())
            for gpu in self.inventory:
                suffix = "" if gpu["available"] else (
                    " — HDMI audio busy" if gpu.get("audio_only_busy") else " — unavailable")
                self.gpu.addItem(f"{gpu['name']} — {gpu['slot']}{suffix}", gpu["slot"])
                item = self.gpu.model().item(self.gpu.count() - 1)
                item.setEnabled(gpu["available"])
                item.setToolTip("\n".join(gpu["reasons"]) or "Available; checked again before launch")
            index = self.gpu.findData(selected)
            if selected and index < 0:
                self.gpu.addItem(f"{selected} — unavailable (see below)", selected)
                index = self.gpu.count() - 1
                self.gpu.model().item(index).setEnabled(False)
            self.gpu.setCurrentIndex(max(0, index))
            lines = []
            for gpu in self.inventory:
                state = "; ".join(gpu["reasons"]) if gpu["reasons"] else (
                    "available" if gpu["verified"] else "candidate; full usage check runs before launch")
                lines.append(f"{gpu['name']} ({gpu['slot']}): {state}")
            self.detected.setText("\n".join(lines) or
                                  "No GPUs detected. Enable the iGPU in BIOS, reboot, then refresh.")
        except Exception as exc:
            self.inventory = []
            self.detected.setText(f"Cannot inspect GPUs: {exc}")
        del blocker
        if not self._loading:
            self._poll()

    def refresh_inputs(self, keyboard=None, mouse=None):
        devices = input_devices.discover()
        for role, combo, selected in (("keyboard", self.evdev_keyboard, keyboard),
                                      ("mouse", self.evdev_mouse, mouse)):
            selected = combo.currentData() if selected is None else selected
            with QSignalBlocker(combo):
                combo.clear()
                combo.addItem(f"Choose a {role}…", "")
                for device in devices:
                    if role not in device["roles"]:
                        continue
                    combo.addItem(f"{device['name']} — {Path(device['path']).name}", device["path"])
                    combo.setItemData(combo.count() - 1, device["path"], role=Qt.ItemDataRole.ToolTipRole)
                index = combo.findData(selected)
                if selected and index < 0:
                    combo.addItem(f"{selected} — unavailable", selected)
                    index = combo.count() - 1
                    combo.model().item(index).setEnabled(False)
                combo.setCurrentIndex(max(0, index))
        if not self._loading:
            self._changed()

    def settings(self):
        opts = dual_gpu.options(self.cfg)
        opts.update(gpu=self.gpu.currentData() or "", gpu_identity=self._identity,
                    gpu_audio=self.gpu_audio.isChecked(), romfile=self.romfile.text().strip(),
                    viewer=self.viewer.currentData(), port=self.port.value(), width=self.width.value(),
                    height=self.height.value(), memory=self.memory.currentData(),
                    network=self.network.currentData(), input_mode=self.input_mode.currentData(),
                    evdev_keyboard=self.evdev_keyboard.currentData() or "",
                    evdev_mouse=self.evdev_mouse.currentData() or "",
                    evdev_toggle=self.evdev_toggle.currentData(), audio_mode=self.audio_mode.currentData(),
                    usb_devices=self._selected_devices(self.usb_devices),
                    pci_devices=self._selected_devices(self.pci_devices))
        for key in ("auto_open", "clipboard", "file_transfer", "audio", "pinning", "lg_capture"):
            opts[key] = getattr(self, key).isChecked()
        return opts

    @staticmethod
    def _selected_devices(widget):
        return [widget.item(n).data(Qt.ItemDataRole.UserRole) for n in range(widget.count())
                if widget.item(n).checkState() == Qt.CheckState.Checked]

    def refresh_devices(self, opts=None):
        opts = opts or dict(usb_devices=self._selected_devices(self.usb_devices),
                            pci_devices=self._selected_devices(self.pci_devices))
        for key, widget, identify, discover in (
                ("usb_devices", self.usb_devices, "port", dual_devices.discover_usb),
                ("pci_devices", self.pci_devices, "slot", dual_devices.discover_pci)):
            saved = {d[identify]: d for d in opts[key]}
            with QSignalBlocker(widget):
                widget.clear()
                try:
                    devices = discover()
                except (OSError, ValueError) as exc:
                    devices = []
                    item = QListWidgetItem(f"Cannot scan devices: {exc}", widget)
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                for dev in devices:
                    address = dev[identify]
                    current = {identify: address, "identity": dev["identity"]}
                    selected = saved.pop(address, None)
                    title = f"{dev['name']} — {address}"
                    if identify == "slot":
                        title += f" · group {dev['group'] or '?'} · {dev['driver'] or 'unbound'}"
                    elif dev["hub"]:
                        title += " (hub — choose its devices individually)"
                    if selected and selected["identity"] != current["identity"]:
                        title += " (device changed; uncheck and reselect)"
                    item = QListWidgetItem(title, widget)
                    item.setToolTip(title)
                    item.setData(Qt.ItemDataRole.UserRole, selected or current)
                    item.setData(Qt.ItemDataRole.UserRole + 1, current)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
                    if dev.get("hub") and not selected:
                        item.setFlags(Qt.ItemFlag.NoItemFlags)
                for address, selected in saved.items():
                    item = QListWidgetItem(f"{address} — disconnected / unavailable (uncheck to remove)", widget)
                    item.setData(Qt.ItemDataRole.UserRole, selected)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)

    def _device_changed(self, item):
        current = item.data(Qt.ItemDataRole.UserRole + 1)
        if item.checkState() == Qt.CheckState.Checked and current:
            with QSignalBlocker(item.listWidget()):
                item.setData(Qt.ItemDataRole.UserRole, current)
        self._changed()

    def _gpu_changed(self, *_):
        selected = next((g for g in self.inventory if g["slot"] == self.gpu.currentData()), None)
        self._identity = selected["identity"] if selected else {}
        # A ROM belongs to a particular GPU, not whichever device is chosen next.
        with QSignalBlocker(self.romfile):
            self.romfile.clear()
        self._changed()
        self._poll()

    def _audio_changed(self, *_):
        self.refresh_gpus()
        self._changed()

    def _changed(self, *_):
        if self._loading:
            return
        self._update_options()
        self.cfg.data["dual_gpu"] = self.settings()
        self.changed.emit()

    def _update_options(self):
        mac = self.cfg.profile == "macos"
        guest = "macOS" if mac else "Windows"
        viewer = self.viewer.currentData()
        looking_glass = viewer == "looking-glass"
        evdev = self.input_mode.currentData() == "evdev"
        for widget in (self.evdev_keyboard, self.evdev_mouse, self.evdev_toggle, self.btn_inputs):
            widget.setEnabled(evdev)
        self.lg_capture.setEnabled(looking_glass and not evdev)
        if evdev:
            shortcut = self.evdev_toggle.currentText().lower()
            self.input_note.setText(
                f"The selected devices control {guest} when the VM starts. Press {shortcut} together, "
                f"then release them, to switch both devices between {guest} and Linux. "
                "Closing the viewer does not release the devices; the switch shortcut or stopping the VM does. "
                + ("No physical USB passthrough is needed." if mac else
                   "Keep Looking Glass uncaptured in this mode. No physical USB passthrough is needed."))
        elif looking_glass:
            self.input_note.setText(
                "Press Scroll Lock in Looking Glass to capture or release keyboard and mouse. "
                "The matching Windows IDD supports input directly; the setup fallback uses SPICE. "
                "No physical USB passthrough is needed.")
        else:
            self.input_note.setText(
                "Use the console window for keyboard and mouse, or choose evdev to switch "
                "a Linux keyboard and mouse between the host and guest.")
        self.auto_open.setEnabled(viewer != "physical")
        self.auto_open.setText("Open selected viewer after launch" if not looking_glass else
                               "Open Looking Glass after launch (setup console if the client is missing)")
        for check in (self.clipboard, self.file_transfer, self.audio):
            check.setEnabled(viewer != "vnc")
            check.setToolTip("Requires SPICE and compatible guest tools" if viewer == "vnc" else "")
        item = self.audio_mode.model().item(self.audio_mode.findData("lg-usb"))
        if item is not None:
            item.setEnabled(looking_glass)
        if viewer == "vnc":
            with QSignalBlocker(self.audio):
                self.audio.setChecked(False)
        if not looking_glass and self.audio_mode.currentData() == "lg-usb":
            with QSignalBlocker(self.audio_mode):
                self.audio_mode.setCurrentIndex(self.audio_mode.findData("spice"))
        self.audio_mode.setEnabled(self.audio.isChecked() and viewer != "vnc")
        if self.audio_mode.currentData() == "lg-usb":
            text = ("Open Looking Glass, then choose Looking Glass USB Audio in Windows Sound settings. "
                    "This adds a virtual USB sound card; it does not take a physical Linux USB device. "
                    "Requires a Looking Glass client built with USB audio support.")
        else:
            text = ("Choose the virtual High Definition Audio output in Windows Sound settings. "
                    "Looking Glass uses the classic SPICE audio path for this choice. "
                    "Looking Glass USB audio is an alternative if classic audio is silent.")
        if viewer == "vnc":
            text = "VNC has no audio. Use a physical USB/PCI sound device below, or select a SPICE/Looking Glass viewer."
        elif viewer == "physical":
            text += " Open the setup console for viewer audio, or use a physical sound device below."
        self.audio_note.setText(text)
        if mac:
            self.audio_note.setText("Select the output in macOS System Settings > Sound. "
                                   "Virtual HDA needs a compatible macOS driver. Physical USB or GPU audio can be selected below. "
                                   "VNC carries display and input only.")
        self.port_label.setText("Local VNC port" if viewer == "vnc" else "Local SPICE port")
        self.resolution_label.setText("Size frame buffer for" if looking_glass else "Console preferred size")
        size = dual_gpu.shared_memory_size(self.width.value(), self.height.value()) // 1024**2
        prefix = f"Looking Glass frame buffer: {size} MiB. " if looking_glass else ""
        guest = "macOS" if self.cfg.profile == "macos" else "Windows"
        self.resolution_note.setText(prefix + f"Set the actual desktop resolution inside {guest}. "
                                     "This does not change OVMF's saved display preference.")
        if viewer in ("spice", "vnc"):
            text = (f"{viewer.upper()} shows the separate virtual VGA display, not the passed-through GPU's output. "
                    f"{guest} needs a compatible driver for the GPU. To view that GPU's display, "
                    f"use physical GPU output or a remote desktop service inside {guest}.")
            if viewer == "spice" and not mac:
                text += " Clipboard and file transfer require compatible SPICE guest drivers and tools."
            elif viewer == "vnc":
                text += " VNC has no SPICE sharing features; use a port of 5900 or higher."
        elif viewer == "physical":
            text = ("Use a monitor connected to the guest GPU. "
                    "The setup console remains available as a separate virtual display.")
            if not mac:
                text += " Looking Glass is not required."
        else:
            text = ("Looking Glass needs matching Linux and Windows components plus the guest GPU driver. "
                    "The setup console remains available for installation and recovery. "
                    "Clipboard and file transfer also need compatible SPICE guest drivers and tools.")
        self.viewer_note.setText(text)

    def _browse_rom(self):
        path, _ = QFileDialog.getOpenFileName(self, "GPU ROM", "", "ROM files (*.rom *.bin);;All files (*)")
        if path:
            self.romfile.setText(path)

    def _preflight(self):
        try:
            checks = dual_gpu.preflight(dual_gpu.prepare(self.cfg, self.settings()))
        except Exception as exc:
            checks = [("error", str(exc))]
        self.log.setPlainText("\n".join(f"[{s.upper():5}] {m}" for s, m in checks))
        return checks

    def _launch(self):
        if not getattr(self, "before_launch", lambda: True)():
            return
        checks = self._preflight()
        errors = [message for severity, message in checks if severity == "error"]
        if errors:
            QMessageBox.critical(self, "Cannot launch", "\n\n".join(errors[:8]))
            return
        self.btn_launch.setEnabled(False)
        self._submitting = True
        QApplication.processEvents()
        try:
            self.run = dual_gpu.launch(self.cfg)
            self._auto_open = self.auto_open.isChecked() and self.viewer.currentData() != "physical"
            self._submission_deadline = time.monotonic() + 20
            self._last_output = None
            self.state.setText("Starting…")
            self.log.appendPlainText("\nLaunch submitted. Checking GPU ownership…")
        except Exception as exc:
            self._submission_deadline = 0
            self.btn_launch.setEnabled(True)
            self.log.appendPlainText(f"\nLaunch failed: {exc}")
            QMessageBox.critical(self, "Dual GPU launch failed", str(exc))
        finally:
            self._submitting = False

    def _poll(self):
        state = virtual_gpu.status(self.run)
        active = state.get("state") in ("starting", "running", "stopping")
        if active:
            try:
                active = Path(f"/proc/{int(state['pid'])}/stat").read_text().split()[21] == state["process_start"]
            except (OSError, KeyError, ValueError):
                active = False
            if not active:
                state = dict(state="failed", message="VM supervisor exited; check the log and GPU binding record")
        pending = not state and time.monotonic() < self._submission_deadline
        running = active and state.get("state") == "running"
        selected = next((g for g in self.inventory if g["slot"] == self.gpu.currentData()), None)
        self.btn_launch.setEnabled(not (active or pending) and bool(selected and selected["available"]))
        for button in (self.btn_console, self.btn_shutdown, self.btn_restart, self.btn_stop):
            button.setEnabled(running)
        viewer = self.run.get("options", {}).get("viewer", "looking-glass")
        self.btn_viewer.setEnabled(running and viewer != "physical")
        self.btn_viewer.setText("Open Looking Glass" if running and viewer == "looking-glass" else "Open viewer")
        if state:
            self.state.setText(state.get("message", state.get("state", "")))
            output = virtual_gpu.read_log(self.run)
            if output != self._last_output:
                self.log.setPlainText(output)
                self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
                self._last_output = output
        if running and self._auto_open:
            self._auto_open = False
            if viewer == "looking-glass" and not dual_gpu.viewer_command(self.run):
                self._open_console()
            else:
                self._open_viewer()

    def _open_viewer(self):
        try:
            dual_gpu.open_viewer(self.run)
        except Exception as exc:
            QMessageBox.information(self, "Open viewer", str(exc))

    def _open_console(self):
        try:
            opts = self.run.get("options")
            if not opts:
                opts = self.settings()
                opts["server"] = "vnc" if opts["viewer"] == "vnc" else "spice"
            virtual_gpu.open_viewer(opts)
        except Exception as exc:
            QMessageBox.information(self, "Setup console", str(exc))

    def _control(self, command):
        if command == "system_reset" and QMessageBox.warning(self, "Restart guest",
                "Restart the virtual machine now? This immediately resets the guest, so unsaved "
                "work may be lost. For a normal shutdown and restart, use Restart inside the guest.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        if command == "quit" and QMessageBox.warning(self, "Force off guest",
                "This immediately cuts power to the guest. Unsaved guest work may be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        try:
            virtual_gpu.control(self.run, command)
            self.state.setText({"system_powerdown": "Shutdown requested…",
                                "system_reset": "Restart requested…", "quit": "Stopping…"}[command])
        except Exception as exc:
            QMessageBox.warning(self, "Guest control", str(exc))

    def _preview(self):
        try:
            text = dual_gpu.preview(self.cfg)
        except Exception as exc:
            QMessageBox.warning(self, "Command preview", str(exc))
            return
        self._dialog("Dual GPU command", text)

    def _dialog(self, title, text, rich=False):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(900, 560)
        layout = QVBoxLayout(dialog)
        editor = QTextBrowser() if rich else QPlainTextEdit()
        if rich:
            editor.setOpenExternalLinks(True)
            editor.setHtml(text)
        else:
            editor.setPlainText(text)
            editor.setReadOnly(True)
            editor.setFont(QFont("Monospace", 10))
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _guide(self):
        if self.cfg.profile == "macos":
            self._dialog("Mac Dual GPU setup", """
<h3>Keep Linux on one GPU; give macOS the other</h3>
<ol><li>Keep the Linux desktop on its current GPU and choose an unused GPU for macOS.</li>
<li>The guest GPU needs a compatible macOS driver and a usable IOMMU group. Keep the working OpenCore boot disk attached.</li>
<li>Use physical GPU output to see the accelerated desktop. SPICE/VNC shows the separate virtual display for setup.</li>
<li>Choose viewer input, evdev sharing, or individual USB passthrough. Do not assign the same device by two methods.</li>
<li>Choose audio devices with a compatible macOS driver and select the output in System Settings &gt; Sound.</li>
<li>Run Preflight check, then Launch VM. Linux keeps its desktop; Single GPU start/revert hooks are skipped.</li></ol>
<p>Boot settings, identity and security are edited in Mac &amp; OpenCore. Its validated versions include a rollback preset.</p>
""", rich=True)
            return
        self._dialog("Dual GPU setup", """
<h3>Keep Linux on one GPU; give Windows the other</h3>
<ol>
<li>Enable the iGPU in your motherboard BIOS and reboot. Keep your Linux display
connected to the GPU you want Linux to retain.</li>
<li>Refresh GPUs and select the spare device. If it is busy, close its applications
or configure the Linux desktop to use only the host GPU and disable its outputs
on the spare GPU. If only HDMI/DP audio is held by WirePlumber and it is in a
separate IOMMU group, leave Include the GPU's HDMI / DisplayPort audio unchecked.
This keeps the audio device with Linux. This mode will not stop the display manager.</li>
<li>Run Preflight check. The spare GPU needs its own usable IOMMU group.
Shared USB, storage and security devices are never detached automatically.</li>
<li>Launch and open the setup console. Install the selected physical GPU's Windows
driver. Some AMD iGPUs need a matching GPU ROM and may not reset reliably.</li>
<li>Choose SPICE or VNC for a virtual console, or physical GPU output for a monitor
connected to the guest GPU. These choices do not require Looking Glass.
SPICE/VNC display the emulated VGA device, not the passed-through GPU's output.
A remote desktop service configured inside Windows is another way to access the guest.</li>
<li>For an optional Looking Glass window, install matching client and Windows
components from the <a href="https://looking-glass.io/downloads">official downloads</a>.
Current IDD builds can create a virtual monitor. Legacy B7 Host builds need an
active guest display, often a monitor or dummy plug.</li>
<li>Select the Looking Glass display and the desired resolution inside Windows.
The setup console is a separate virtual display, so it does not show the passed GPU's output.</li>
<li>For viewer sound, enable Play guest audio and choose an audio method. Looking Glass USB audio
adds the required SPICE USB channel; after opening Looking Glass, select Looking Glass USB Audio
in Windows Sound settings. Classic SPICE uses the virtual High Definition Audio output instead.</li>
<li>For physical devices, select USB devices or PCI controllers in USB / PCI passthrough.
These choices are independent of Single GPU. A sound card's outputs belong to Windows until
shutdown. A full USB controller includes every device attached to it; do not also select its
children or the same keyboard/mouse for evdev.</li>
</ol>
<p>Preflight checks your QEMU's IVSHMEM PCI ID. A custom ID requires a matching
Windows driver; standard Looking Glass drivers expect 1af4:1110. Clipboard also
needs compatible VirtIO Serial and SPICE guest tools. This page does not change
QEMU, OVMF, or your Single GPU hooks to resolve driver incompatibilities.</p>
<p>The launcher creates private shared memory for each run. This works without
installing a KVMFR kernel module, but frame copies can cost more CPU time.</p>
<p>After shutdown, the launcher restores the original GPU bindings. Errors and the
original bindings are retained in the run log and gpu-bindings.json. If the GPU
cannot reset, resolve the hardware/driver issue before trying another launch mode.</p>
<p><a href="https://looking-glass.io/docs/bleeding/requirements/">Looking Glass requirements</a>
 · <a href="https://looking-glass.io/docs/bleeding/quickstart/">Installation guide</a></p>
""", rich=True)
