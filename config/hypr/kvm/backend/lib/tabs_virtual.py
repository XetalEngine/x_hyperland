"""Desktop-friendly launch controls and per-preset virtual display options."""

from pathlib import Path
import time

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                             QSpinBox, QVBoxLayout, QWidget)

import virtual_gpu
import console_window


class VirtualGPUTab(QScrollArea):
    changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._loading = True
        self._auto_open = False
        self._last_output = None
        self._submission_deadline = 0
        self.run = virtual_gpu.current_run()
        self.setWidgetResizable(True)
        content = QWidget()
        self.setWidget(content)
        layout = QVBoxLayout(content)
        opts = virtual_gpu.options(cfg)
        mac = cfg.profile == "macos"

        launch = QGroupBox("Launch")
        body = QVBoxLayout(launch)
        note = QLabel("Run the current preset in a window while Linux keeps its GPU. "
                      "Start and revert scripts are skipped, including host reboot. " +
                      ("Disks, CPU, RAM, OpenCore and private NVRAM are shared with Single GPU." if mac else
                       "Disks, CPU, RAM size, firmware and TPM identity are shared with Single GPU."))
        note.setWordWrap(True)
        body.addWidget(note)
        row = QHBoxLayout()
        self.btn_launch = QPushButton("Launch VM")
        self.btn_launch.setObjectName("accentBig")
        self.btn_launch.setMinimumSize(160, 38)
        self.btn_launch.clicked.connect(self._launch)
        row.addWidget(self.btn_launch)
        preflight = QPushButton("Preflight check")
        preflight.clicked.connect(self._preflight)
        row.addWidget(preflight)
        preview = QPushButton("Preview command")
        preview.clicked.connect(self._preview)
        row.addWidget(preview)
        row.addStretch()
        body.addLayout(row)
        controls = QHBoxLayout()
        self.btn_console = QPushButton("Open console")
        self.btn_console.clicked.connect(self._open_console)
        controls.addWidget(self.btn_console)
        self.btn_shutdown = QPushButton("Shut down guest")
        self.btn_shutdown.clicked.connect(lambda: self._control("system_powerdown"))
        controls.addWidget(self.btn_shutdown)
        self.btn_restart = QPushButton("Restart guest…")
        self.btn_restart.setToolTip("Reset the virtual machine immediately")
        self.btn_restart.clicked.connect(lambda: self._control("system_reset"))
        controls.addWidget(self.btn_restart)
        self.btn_stop = QPushButton("Force off…")
        self.btn_stop.clicked.connect(lambda: self._control("quit"))
        controls.addWidget(self.btn_stop)
        self.state = QLabel("Ready")
        self.state.setObjectName("muted")
        self.state.setWordWrap(True)
        controls.addWidget(self.state, 1)
        body.addLayout(controls)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Monospace", 10))
        self.log.setMinimumHeight(130)
        self.log.setMaximumHeight(180)
        self.log.setPlaceholderText("Virtual GPU preflight checks and launch output appear here.")
        body.addWidget(self.log)
        layout.addWidget(launch)

        self.display_box = QGroupBox("Display and console")
        grid = QGridLayout(self.display_box)
        grid.setHorizontalSpacing(20)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.model = QComboBox()
        for key, (label, tip) in virtual_gpu.MODELS.items():
            if mac and key not in ("VGA", "bochs-display", opts["model"]):
                continue
            self.model.addItem(label, key)
        self.model.setCurrentIndex(max(0, self.model.findData(opts["model"])))
        form.addRow("Graphics card", self.model)
        connection = QHBoxLayout()
        connection.setSpacing(8)
        self.server = QComboBox()
        self.server.addItem("VNC server (display only)", "vnc")
        self.server.addItem("SPICE server", "spice")
        self.server.setCurrentIndex(max(0, self.server.findData(opts["server"])))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(opts["port"]))
        connection.addWidget(self.server, 1)
        connection.addWidget(QLabel("Port"))
        connection.addWidget(self.port)
        form.addRow("Connection", connection)
        resolution = QHBoxLayout()
        resolution.setSpacing(8)
        self.width, self.height = QSpinBox(), QSpinBox()
        for widget, key in ((self.width, "width"), (self.height, "height")):
            widget.setRange(640 if key == "width" else 480, 4096)
            widget.setSingleStep(80)
            widget.setMaximumWidth(115)
            widget.setValue(int(opts[key]))
            resolution.addWidget(widget)
        resolution.insertWidget(1, QLabel("×"))
        resolution.addStretch()
        form.addRow("Preferred resolution", resolution)
        self.uefi_resolution = QCheckBox("Apply preferred size to UEFI (shared firmware)")
        self.uefi_resolution.setChecked(opts["uefi_resolution"])
        self.uefi_resolution.setToolTip("For VGA/Bochs, update OVMF's saved display mode before boot. "
                                       "This preference is shared with Single GPU. A backup is kept; "
                                       "Secure Boot keys and other firmware settings are preserved.")
        form.addRow(self.uefi_resolution)
        self.resolution_note = QLabel()
        self.resolution_note.setWordWrap(True)
        self.resolution_note.setObjectName("muted")
        form.addRow(self.resolution_note)
        self.auto_open = QCheckBox("Open the console after launch")
        self.auto_open.setChecked(opts["auto_open"])
        form.addRow(self.auto_open)
        self.remember_console_size = QCheckBox("Remember console window size")
        self.remember_console_size.setChecked(opts["remember_console_size"])
        reason = console_window.unavailable_reason()
        self.remember_console_size.setEnabled(not reason)
        self.remember_console_size.setToolTip(reason or
            "Automatically saves the last windowed size for each console viewer, even after the launcher closes. "
            "Guest resolution is still controlled by the guest and viewer settings.")
        form.addRow(self.remember_console_size)
        if reason:
            size_note = QLabel(reason)
            size_note.setWordWrap(True)
            size_note.setObjectName("muted")
            form.addRow(size_note)
        self.input = QCheckBox("Virtual keyboard and tablet pointer")
        self.input.setChecked(opts["input"])
        self.input.setToolTip("Control the guest through the viewer without handing over your physical keyboard or mouse")
        form.addRow(self.input)
        grid.addLayout(form, 0, 0)
        self.spice_box = QGroupBox("SPICE integration")
        spice = QVBoxLayout(self.spice_box)
        for key, label in (("clipboard", "Share clipboard"), ("file_transfer", "Allow file transfer"),
                           ("audio", "Guest audio through SPICE")):
            checkbox = QCheckBox(label)
            checkbox.setChecked(opts[key])
            setattr(self, key, checkbox)
            spice.addWidget(checkbox)
            if mac and key in ("clipboard", "file_transfer"):
                checkbox.setChecked(False)
                checkbox.hide()
        if mac:
            self.audio.setText("Virtual HDA audio (requires a macOS driver)")
        agent = QLabel("Clipboard, file transfer and resizing need guest tools installed inside the VM. "
                       "Audio adds a virtual sound card when needed.")
        agent.setWordWrap(True)
        if mac:
            agent.setText("This Mac setup uses viewer keyboard and mouse input. Clipboard sharing, file transfer "
                          "and automatic resizing are unavailable without compatible guest integration. "
                          "GPU acceleration comes from the physical GPU in Single GPU or Dual GPU mode.")
        agent.setObjectName("muted")
        spice.addWidget(agent)
        spice.addStretch()
        grid.addWidget(self.spice_box, 0, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        self.display_note = QLabel()
        self.display_note.setWordWrap(True)
        self.display_note.setObjectName("muted")
        grid.addWidget(self.display_note, 1, 0, 1, 2)
        support = QHBoxLayout()
        mac = cfg.profile == "macos"
        self.btn_spice = QPushButton("Use SPICE + VGA" if mac else "Use SPICE + QXL")
        self.btn_spice.setToolTip("Select Standard VGA, SPICE and the Mac preset's recommended USB input" if mac else
                                 "Select SPICE and QXL, with clipboard and file transfer enabled for the next launch")
        self.btn_spice.clicked.connect(self._use_spice)
        support.addWidget(self.btn_spice)
        setup = QPushButton("Guest setup…")
        setup.clicked.connect(self._guest_setup)
        support.addWidget(setup)
        self.btn_integration = QPushButton("Check guest integration")
        self.btn_integration.clicked.connect(self._check_integration)
        support.addWidget(self.btn_integration)
        if mac:
            self.btn_integration.hide()
        support.addStretch()
        grid.addLayout(support, 2, 0, 1, 2)
        layout.addWidget(self.display_box)

        resources = QGroupBox("Shared preset options")
        details = QVBoxLayout(resources)
        fields = QFormLayout()
        self.memory = QComboBox()
        self.memory.addItem("Preset memory backing (same RAM size)", "preset")
        self.memory.addItem("Ordinary RAM (same size, no hugepages)", "ordinary")
        self.memory.setCurrentIndex(max(0, self.memory.findData(opts["memory"])))
        fields.addRow("Memory", self.memory)
        self.network = QComboBox()
        self.network.addItem("Preset network (private tap on the same bridge)", "preset")
        self.network.addItem("User networking (NAT, no bridge needed)", "user")
        self.network.addItem("Disconnected", "off")
        self.network.setCurrentIndex(max(0, self.network.findData(opts["network"])))
        fields.addRow("Networking", self.network)
        self.input_controller = QComboBox()
        self.input_controller.addItem("USB 3 (XHCI)", "xhci")
        self.input_controller.addItem("USB 2 (EHCI — High Sierra)", "ehci")
        self.input_controller.setCurrentIndex(max(0, self.input_controller.findData(opts["input_controller"])))
        fields.addRow("Keyboard / pointer controller", self.input_controller)
        details.addLayout(fields)
        checks = QGridLayout()
        for i, (key, label, tip) in enumerate((
                ("keep_usb", "Include preset USB passthrough", "Checked devices are taken from Linux while the guest runs"),
                ("keep_pci", "Include non-GPU PCI passthrough", "Only devices already bound to vfio-pci can be included; no drivers are rebound"),
                ("pinning", "Use preset CPU affinity", "Apply the CPU, emulator and I/O thread affinity from CPU pinning"),
                ("realtime", "Use preset thread scheduling", "Apply preset scheduler priorities; the host RT throttling setting stays unchanged"))):
            checkbox = QCheckBox(label)
            checkbox.setToolTip(tip)
            checkbox.setChecked(opts[key])
            setattr(self, key, checkbox)
            checks.addWidget(checkbox, i // 2, i % 2)
        details.addLayout(checks)
        note = QLabel("These options apply to the next Virtual GPU launch and are saved with the preset. "
                      "The hardware editors continue to control the shared configuration.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        details.addWidget(note)
        layout.addWidget(resources)
        layout.addStretch()

        for key in ("model", "server", "memory", "network", "input_controller"):
            getattr(self, key).currentIndexChanged.connect(self._server_changed if key == "server" else self._changed)
        for key in ("port", "width", "height"):
            getattr(self, key).valueChanged.connect(self._changed)
        for key in ("auto_open", "remember_console_size", "input", "clipboard", "file_transfer", "audio", "keep_usb", "keep_pci", "pinning", "realtime", "uefi_resolution"):
            getattr(self, key).toggled.connect(self._changed)
        self._loading = False
        self._update_options()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self._poll()

    def settings(self):
        data = {k: getattr(self, k).currentData() for k in ("model", "server", "memory", "network", "input_controller")}
        data["model"] = data["model"] or "VGA"
        data.update({k: getattr(self, k).value() for k in ("port", "width", "height")})
        data.update({k: getattr(self, k).isChecked() for k in
                     ("auto_open", "remember_console_size", "input", "clipboard", "file_transfer", "audio", "keep_usb", "keep_pci", "pinning", "realtime", "uefi_resolution")})
        return data

    def _changed(self, *_):
        if self._loading:
            return
        self.cfg.data["virtual_gpu"] = self.settings()
        self._update_options()
        self.changed.emit()

    def _server_changed(self, *_):
        if self._loading:
            return
        # Preserve custom ports; swap only the two conventional defaults.
        if self.port.value() in (5901, 5930):
            self.port.setValue(5930 if self.server.currentData() == "spice" else 5901)
        if self.server.currentData() == "vnc" and self.port.value() < 5900:
            self.port.setValue(5901)
        self._changed()

    def _use_spice(self):
        self._loading = True
        mac = self.cfg.profile == "macos"
        self.server.setCurrentIndex(self.server.findData("spice"))
        self.model.setCurrentIndex(self.model.findData("VGA" if mac else "qxl-vga"))
        if self.port.value() == 5901:
            self.port.setValue(5930)
        self.clipboard.setChecked(not mac)
        self.file_transfer.setChecked(not mac)
        if mac:
            self.input_controller.setCurrentIndex(self.input_controller.findData(virtual_gpu.mac_input_controller(self.cfg)))
        self.input.setChecked(True)
        self._loading = False
        self._changed()

    def _update_options(self):
        opts = self.settings()
        self.spice_box.setEnabled(opts["server"] == "spice")
        self.uefi_resolution.setEnabled(opts["model"] in ("VGA", "bochs-display"))
        self.realtime.setEnabled(opts["pinning"])
        label, tip = virtual_gpu.MODELS[opts["model"]]
        viewer = virtual_gpu.viewer_command(opts)
        client = f"Viewer: {Path(viewer[0]).name}." if viewer else "Install " + (
            "vncviewer or remote-viewer" if opts["server"] == "vnc" else
            "virt-viewer (remote-viewer) or spice-gtk (spicy)") + " to open the console."
        integration = "Choose SPICE to enable clipboard, file transfer and audio. " if opts["server"] == "vnc" else ""
        if self.cfg.profile == "macos":
            integration = "Virtual display uses a basic framebuffer; GPU acceleration requires a passed-through GPU and a compatible macOS driver. "
        self.display_note.setText(f"{integration}{tip}  {client}  Local connection: 127.0.0.1:{opts['port']} (no password).")
        self.resolution_note.setText(virtual_gpu.resolution_note(dict(opts, guest_os=self.cfg.profile)))

    def _guest_setup(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Virtual GPU guest setup")
        dialog.resize(650, 410)
        layout = QVBoxLayout(dialog)
        text = QLabel(
            "<p><b>Windows</b><br>Use <b>SPICE + QXL</b>, then install "
            '<a href="https://www.spice-space.org/download.html">SPICE Guest Tools</a> '
            "inside Windows. The SPICE agent, VirtIO Serial driver and QXL display driver are needed. "
            "Restart Windows and sign in. Device Manager should show a QXL display adapter and a "
            "VirtIO Serial controller; the SPICE agent service must be running. "
            "Run Preflight first: custom QEMU builds that change these devices' PCI IDs need "
            "compatible IDs or matching drivers before standard guest tools can work.</p>"
            "<p><b>Linux</b><br>Install <b>spice-vdagent</b> inside the guest and ensure its daemon and "
            "desktop agent are running. Use a supported QXL or VirtIO display driver. "
            "Integration support depends on the guest desktop session.</p>"
            "<p><b>Resolution</b><br>The preferred size is a request to the guest. For an exact size, "
            "select it in the guest's Display settings and turn off automatic guest resizing in the viewer. "
            "With QXL and guest tools, resizing the viewer can resize the guest. "
            "For Windows Basic Display with VGA/Bochs, leave <b>Apply preferred size to UEFI</b> enabled "
            "to update OVMF's saved display mode before launch (requires virt-firmware on the host). "
            "Only the display preference changes; a firmware backup is saved. This setting is shared "
            "with Single GPU. You can also press Esc during boot and set it under "
            "Device Manager → OVMF Platform Configuration.</p>"
            "<p><b>Connection</b><br>VNC does not carry these SPICE features. Use a SPICE viewer: "
            "remote-viewer from virt-viewer, or spicy from spice-gtk. "
            "After boot, use <b>Check guest integration</b> to check the viewer and guest agent channel.</p>")
        text.setWordWrap(True)
        if self.cfg.profile == "macos":
            tahoe = self.cfg.data.get("_meta", {}).get("macos_release") == "tahoe"
            baseline = ("<p><b>Tahoe Recovery</b><br>The Tahoe master provides Skylake-Client / GenuineIntel, "
                        "Apple SMC, USB 3, Standard VGA and a separate firmware directory. Keep RAM at "
                        "<b>16 GiB</b> with the original media; synchronize a changed size in Mac &amp; OpenCore.</p>"
                        if tahoe else
                        "<p><b>High Sierra Recovery</b><br>The High Sierra master provides Penryn / GenuineIntel, "
                        "Apple SMC, USB 2 EHCI, Standard VGA and NAT networking. Keep RAM at <b>6 GiB</b> "
                        "with the original media; synchronize a changed size in Mac &amp; OpenCore.</p>")
            text.setText(
                baseline +
                "<p><b>Console</b><br>Use SPICE with Standard VGA for this profile. The virtual keyboard "
                "and tablet use the preset's USB controller. Clipboard and file transfer are off. "
                "Standard VGA has no Metal acceleration; GPU-dependent features need separate testing.</p>"
                "<p><b>Installation</b><br>The ISO opens macOS Recovery. Add your chosen installation "
                "drive in Disks &amp; storage when ready. Recovery downloads the remaining installer "
                "from Apple, so keep networking enabled. Keep the selected OpenCore boot disk attached. "
                "After installation, the recovery ISO is only needed for recovery or reinstallation.</p>"
                "<p><b>Firmware</b><br>Mac firmware and writable NVRAM live under vmstart_2/macos. "
                "The Windows profile keeps its own settings and firmware paths.</p>")
        text.setOpenExternalLinks(True)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _check_integration(self):
        try:
            checks = virtual_gpu.integration_checks(self.run)
        except Exception as exc:
            checks = [("error", f"Cannot check the running guest: {exc}")]
        self.log.appendPlainText("\n" + "\n".join(f"[{severity.upper():5}] {message}" for severity, message in checks))

    def _preflight(self):
        try:
            checks = virtual_gpu.preflight(virtual_gpu.prepare(self.cfg, self.settings()))
        except Exception as exc:
            checks = [("error", str(exc))]
        self.log.setPlainText("\n".join(f"[{severity.upper():5}] {message}" for severity, message in checks))
        return checks

    def _launch(self):
        if not getattr(self, "before_launch", lambda: True)():
            return
        checks = self._preflight()
        errors = [m for s, m in checks if s == "error"]
        if errors:
            QMessageBox.critical(self, "Cannot launch", "\n\n".join(errors[:8]))
            return
        if self.keep_usb.isChecked() or self.keep_pci.isChecked():
            if QMessageBox.question(self, "Launch with physical devices", "Enabled USB and non-GPU PCI devices "
                    "will be taken from Linux for this run. Launch the guest?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                return
        self.btn_launch.setEnabled(False)
        self._submitting = True
        QApplication.processEvents()
        try:
            self.run = virtual_gpu.launch(self.cfg)
            self._auto_open = self.auto_open.isChecked()
            self._submission_deadline = time.monotonic() + 20
            self._last_output = None
            self.log.appendPlainText("\nLaunch submitted. Waiting for QEMU…")
            self.state.setText("Starting…")
        except Exception as exc:
            self._submission_deadline = 0
            self.btn_launch.setEnabled(True)
            self.log.appendPlainText(f"\nLaunch failed: {exc}")
            QMessageBox.critical(self, "Virtual GPU launch failed", str(exc))
        finally:
            self._submitting = False

    def _poll(self):
        if getattr(self, "_submitting", False):
            return
        state = virtual_gpu.status(self.run)
        if state.get("state") not in (None, "pending"):
            self._submission_deadline = 0
        active = state.get("state") in ("starting", "running", "stopping")
        if active:
            try:
                active = Path(f"/proc/{int(state['pid'])}/stat").read_text().split()[21] == state["process_start"]
            except (OSError, KeyError, ValueError):
                active = False
            if not active:
                state = dict(state="failed", message="VM supervisor is no longer running; check the output below")
        running = active and state.get("state") == "running"
        pending = state.get("state") == "pending" or (not state and time.monotonic() < self._submission_deadline)
        self.btn_launch.setEnabled(not (active or pending))
        for button in (self.btn_console, self.btn_shutdown, self.btn_restart, self.btn_stop, self.btn_integration):
            button.setEnabled(running)
        if state:
            self.state.setText(state.get("message", state.get("state", "")))
            output = virtual_gpu.read_log(self.run)
            if state.get("state") == "failed":
                self._auto_open = False
                output = (output.rstrip() + "\n\n" + state["message"]).lstrip()
            if output != self._last_output:
                self.log.setPlainText(output)
                self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
                self._last_output = output
        if running and self._auto_open:
            self._auto_open = False
            self._open_console()

    def _open_console(self):
        try:
            virtual_gpu.open_viewer(self.run.get("options") or self.settings(),
                                    remember_size=self.remember_console_size.isChecked())
        except Exception as exc:
            QMessageBox.information(self, "Open console", str(exc))

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
            command = virtual_gpu.preview(self.cfg)
        except Exception as exc:
            QMessageBox.warning(self, "Command preview", str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Virtual GPU command")
        dialog.resize(900, 550)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(command)
        editor.setReadOnly(True)
        editor.setFont(QFont("Monospace", 10))
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
