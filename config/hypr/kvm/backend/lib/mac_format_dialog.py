"""Review and progress UI for native macOS disk preparation."""

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

import mac_format
from uiutil import sudo_command
import virtual_gpu


class MacFormatDialog(QDialog):
    def __init__(self, cfg, filename, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.job = mac_format.prepare_job(cfg, filename, "Macintosh HD")
        self.result_data = None
        self.process = None
        self.work = None
        self.irreversible = False
        self.buffer = ""
        self.last_error = ""
        self.setWindowTitle("Mac Format — prepare installation disk")
        self.setMinimumWidth(620)
        self.resize(720, 640)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QIcon(str(Path(__file__).resolve().parents[1]/"assets/macos.svg")).pixmap(38, 38))
        header.addWidget(icon)
        titles = QVBoxLayout()
        title = QLabel("Prepare this drive for macOS")
        title.setStyleSheet("font-size: 21px; font-weight: 650;")
        titles.addWidget(title)
        subtitle = QLabel("GUID partition map  ·  APFS  ·  Native Apple disk tools")
        subtitle.setObjectName("muted")
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("formatDriveCard")
        card.setStyleSheet("QFrame#formatDriveCard { border: 1px solid #56616a; border-radius: 10px; }")
        form = QFormLayout(card)
        form.setContentsMargins(16, 14, 16, 14)
        target = self.job["target"]
        self.drive_path = QLabel(target["path"])
        self.drive_path.setTextFormat(Qt.TextFormat.PlainText)
        self.drive_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.drive_path.setWordWrap(True)
        form.addRow("Selected drive", self.drive_path)
        def value(text):
            label = QLabel(text)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            return label
        form.addRow("Device", value(f"{target['model']}  ·  {target['size']/1024**3:,.1f} GiB"))
        form.addRow("Serial / location", value(target["serial"] or target["realpath"]))
        form.addRow("Current labels", value(", ".join(target["labels"]) or "No label detected"))
        self.volume_name = QLineEdit("Macintosh HD")
        self.volume_name.setMaxLength(127)
        self.volume_name.textChanged.connect(self._enable_start)
        form.addRow("New volume name", self.volume_name)
        layout.addWidget(card)

        self.warning = QLabel("Formatting erases every partition and file on this drive. "
                              "The temporary Recovery VM will format only the selected drive.")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #f0bd89;")
        layout.addWidget(self.warning)
        self.confirm = QCheckBox("Erase this drive and replace its contents with an empty APFS volume")
        self.confirm.toggled.connect(self._enable_start)
        layout.addWidget(self.confirm)

        steps = QHBoxLayout()
        steps.setSpacing(10)
        self.step_labels = []
        for number, name in enumerate(("Check drive", "Recovery", "Disk tools", "Format", "Verify", "Finish"), 1):
            label = QLabel(f"{number:02}\n{name}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #9da9b5; padding: 9px 3px; border-bottom: 2px solid #48505a;")
            self.step_labels.append(label)
            steps.addWidget(label, 1)
        layout.addLayout(steps)
        self.status = QLabel("Review the drive details before starting.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(800)
        self.log.setMinimumHeight(110)
        self.log.setMaximumHeight(180)
        self.log.setPlaceholderText("Preparation and native disk-tool progress will appear here.")
        layout.addWidget(self.log)

        buttons = QHBoxLayout()
        self.close_button = QPushButton("Cancel")
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        self.elapsed = QLabel("")
        self.elapsed.setObjectName("muted")
        buttons.addWidget(self.elapsed)
        buttons.addStretch()
        self.start_button = QPushButton("Erase and format")
        self.start_button.setStyleSheet("QPushButton { background: #b7433c; color: white; padding: 9px 22px; "
            "border-radius: 6px; font-weight: 650; } QPushButton:hover { background: #cf5148; } "
            "QPushButton:disabled { background: #493e3e; color: #a79797; }")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._elapsed)
        self.started_at = None

    def _elapsed(self):
        if self.started_at is not None:
            seconds = int(time.monotonic() - self.started_at)
            self.elapsed.setText(f"{seconds//60}:{seconds%60:02} elapsed")

    def running(self):
        return self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning

    def _enable_start(self):
        if not hasattr(self, "start_button"):
            return
        try:
            mac_format.validate_name(self.volume_name.text())
            valid = True
        except ValueError:
            valid = False
        self.start_button.setEnabled(valid and self.confirm.isChecked() and not self.running()
                                     and self.result_data is None)

    def _start(self):
        if self.running() or not self.confirm.isChecked():
            return
        try:
            if virtual_gpu.service_active():
                raise ValueError("Shut down the running VM before formatting. Then open Mac Format again.")
            self.job["label"] = mac_format.validate_name(self.volume_name.text())
            mac_format.check_identity(self.job["target"], mac_format.inspect_target(self.job["target"]["path"]))
            runs = Path(self.cfg.root)/"macos/run"
            runs.mkdir(parents=True, exist_ok=True)
            self.work = Path(tempfile.mkdtemp(prefix="mac-format-", dir=runs))
            self.job["confirmed"] = True
            payload = self.work/"job.json"
            payload.write_text(json.dumps(self.job, indent=2)+"\n")
            payload.chmod(0o600)
            command = [sys.executable, "-u", str(Path(mac_format.__file__)), "--submit", str(payload)]
            if os.geteuid() == 0:
                environment, available = dict(os.environ), True
            else:
                command, environment, available = sudo_command(command, "Mac Format needs access to the selected drive")
            if not available:
                raise ValueError("Administrator authentication is unavailable. Install ksshaskpass or configure sudo.")
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            env = QProcessEnvironment()
            for key, val in environment.items():
                env.insert(key, val)
            self.process.setProcessEnvironment(env)
            self.process.readyReadStandardOutput.connect(self._read_output)
            self.process.finished.connect(self._finished)
            self.process.errorOccurred.connect(self._process_error)
            self.volume_name.setEnabled(False)
            self.confirm.setEnabled(False)
            self.start_button.setEnabled(False)
            self.close_button.setText("Cancel preparation")
            self.progress.setRange(0, 0)
            self.status.setText("Checking administrator access and reserving the formatting VM…")
            self.started_at = time.monotonic()
            self.clock.start()
            self.process.start(command[0], command[1:])
        except Exception as error:
            self.status.setText(str(error))
            self.log.appendPlainText(str(error))

    def _read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            try:
                event = json.loads(line)
            except ValueError:
                if line.strip():
                    self.log.appendPlainText(line)
                continue
            if isinstance(event, dict) and "stage" in event:
                self.handle_event(event)

    def handle_event(self, event):
        stage, message = event["stage"], event.get("message", "")
        if message:
            self.log.appendPlainText(message)
            self.status.setText(message)
        if stage in mac_format.PHASES:
            index = mac_format.PHASES.index(stage)
            for n, label in enumerate(self.step_labels):
                color = "#67d99b" if n <= index else "#9da9b5"
                label.setStyleSheet(f"color: {color}; padding: 9px 3px; border-bottom: 2px solid {color};")
            self.progress.setRange(0, 0)
        if event.get("irreversible"):
            self.irreversible = True
            self.close_button.setEnabled(False)
            self.close_button.setText("Formatting…")
            self.warning.setText("Formatting is in progress. Keep the computer powered on until verification finishes.")
        if stage == "detail":
            percentage = re.search(r"(?:^|\s)(\d+(?:\.\d+)?)%", message)
            if percentage and 0 <= float(percentage[1]) <= 100:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(float(percentage[1])))
        elif stage == "error":
            self.last_error = message
        elif stage == "done":
            self.result_data = event.get("result")

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.last_error = self.process.errorString()
            self._finished(1, QProcess.ExitStatus.CrashExit)

    def _finished(self, code, status):
        self.clock.stop()
        self._elapsed()
        self._read_output()
        success = code == 0 and status == QProcess.ExitStatus.NormalExit and self.result_data is not None
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        self.close_button.setEnabled(True)
        self.close_button.setText("Done" if success else "Close")
        self.start_button.setEnabled(False)
        if success:
            self.status.setText(f"{self.result_data['label']} is ready. Start the VM and select it in the macOS installer.")
            self.warning.setText("GUID partition map and APFS volume verified. The selected disk's VM settings will be updated when you close this dialog.")
            self.warning.setStyleSheet("color: #67d99b;")
        else:
            self.result_data = None
            self.status.setText(self.last_error or "Disk preparation did not complete.")
            self.warning.setText("The drive may already have been erased; review the error before trying again."
                                 if self.irreversible else "The formatter did not authorize an erase.")
            if self.work:
                self.log.appendPlainText(f"Diagnostic files: {self.work}")

    def reject(self):
        if self.running():
            if not self.irreversible and self.work:
                (self.work/"cancel").touch()
                self.close_button.setEnabled(False)
                self.status.setText("Cancelling preparation before erasing the drive…")
            return
        if self.result_data:
            self.accept()
        else:
            super().reject()
