"""Create a new guest disk or attach an existing raw image."""

from pathlib import Path

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                            QLineEdit, QProgressBar, QPushButton, QSpinBox, QTabBar, QVBoxLayout, QWidget)

from uiutil import guard_all
import virtual_disk


class ImageJob(QThread):
    def __init__(self, operation, arguments, parent=None):
        super().__init__(parent)
        self.operation, self.arguments = operation, arguments
        self.path, self.error = None, ""

    def run(self):
        try:
            self.path = self.operation(*self.arguments)
        except Exception as error:
            self.error = str(error)


class VirtualDiskDialog(QDialog):
    def __init__(self, parent=None, *, attached_paths=()):
        super().__init__(parent)
        self.selected_path = None
        self.attached_paths = tuple(attached_paths)
        self.job = None
        self.busy = False
        self.setWindowTitle("Add Virtual Disk")
        self.setMinimumWidth(560)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        title = QLabel("Add a virtual disk")
        title.setStyleSheet("font-size: 20px; font-weight: 650;")
        layout.addWidget(title)
        description = QLabel("Create a blank disk or attach a disk image you already have.")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.fields = QWidget()
        fields_layout = QVBoxLayout(self.fields)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(16)
        self.mode = QTabBar()
        self.mode.addTab("Create new")
        self.mode.addTab("Use existing")
        self.mode.setExpanding(False)
        self.mode.setAccessibleName("Virtual disk source")
        fields_layout.addWidget(self.mode)
        self.new_fields = QWidget()
        form = QFormLayout(self.new_fields)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        folder = QHBoxLayout()
        self.location = QLineEdit(str(Path.home()/"VirtualMachines"))
        self.location.setAccessibleName("Virtual disk folder")
        folder.addWidget(self.location, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        folder.addWidget(browse)
        form.addRow("Location", folder)
        self.filename = QLineEdit("virtual-disk.img")
        self.filename.setAccessibleName("Virtual disk filename")
        form.addRow("Filename", self.filename)
        self.capacity = QSpinBox()
        self.capacity.setRange(1, virtual_disk.MAX_GIB)
        self.capacity.setValue(64)
        self.capacity.setSuffix(" GiB")
        self.capacity.setGroupSeparatorShown(True)
        form.addRow("Size", self.capacity)
        fields_layout.addWidget(self.new_fields)

        self.existing_fields = QWidget()
        existing_form = QFormLayout(self.existing_fields)
        existing_form.setContentsMargins(0, 0, 0, 0)
        existing_row = QHBoxLayout()
        self.existing_path = QLineEdit()
        self.existing_path.setAccessibleName("Existing disk image")
        self.existing_path.setPlaceholderText("Choose an existing .img or .raw file…")
        existing_row.addWidget(self.existing_path, 1)
        browse_existing = QPushButton("Browse…")
        browse_existing.clicked.connect(self.browse_existing)
        existing_row.addWidget(browse_existing)
        existing_form.addRow("Disk image", existing_row)
        fields_layout.addWidget(self.existing_fields)
        layout.addWidget(self.fields)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setObjectName("muted")
        layout.addWidget(self.hint)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.hide()
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self.reject)
        buttons.addWidget(self.cancel)
        self.create = QPushButton("Create and add")
        self.create.setObjectName("accent")
        self.create.setDefault(True)
        self.create.clicked.connect(self.start)
        buttons.addWidget(self.create)
        layout.addLayout(buttons)
        self.mode.currentChanged.connect(self.set_mode)
        self.set_mode(0)
        guard_all(self)
        self.filename.selectAll()
        self.filename.setFocus()

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose virtual disk folder", self.location.text())
        if folder:
            self.location.setText(folder)

    def browse_existing(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose existing virtual disk", self.existing_path.text() or self.location.text(),
            "Raw disk images (*.img *.raw);;All files (*)")
        if path:
            self.existing_path.setText(path)
            self.status.hide()

    def set_mode(self, index):
        existing = index == 1
        self.new_fields.setVisible(not existing)
        self.existing_fields.setVisible(existing)
        self.create.setText("Add disk" if existing else "Create and add")
        self.status.hide()
        self.hint.setText(
            "Attach a raw disk image (.img or .raw). Its existing size and contents are kept."
            if existing else
            "Creates a blank raw disk (.img or .raw). Host storage is used as the guest writes data, up to this capacity.")
        if existing:
            if not self.existing_path.text():
                try:
                    self.existing_path.setText(str(virtual_disk.image_path(self.location.text(), self.filename.text())))
                except ValueError:
                    pass
            self.existing_path.setFocus()
        else:
            self.filename.setFocus()

    def running(self):
        return self.busy

    def start(self):
        if self.running():
            return
        self.busy = True
        self.fields.setEnabled(False)
        self.create.setEnabled(False)
        self.cancel.setEnabled(False)
        existing = self.mode.currentIndex() == 1
        self.status.setText("Checking the existing disk…" if existing else "Creating the virtual disk…")
        self.status.show()
        self.progress.show()
        operation = virtual_disk.existing_image if existing else virtual_disk.create_image
        arguments = ((self.existing_path.text(), self.attached_paths) if existing else
                     (self.location.text(), self.filename.text(), self.capacity.value()))
        self.job = ImageJob(operation, arguments, self)
        self.job.finished.connect(self.finished_operation)
        self.job.start()

    def finished_operation(self):
        self.busy = False
        job, self.job = self.job, None
        job.deleteLater()
        self.progress.hide()
        if job.path is not None:
            self.selected_path = job.path
            self.accept()
            return
        self.fields.setEnabled(True)
        self.create.setEnabled(True)
        self.cancel.setEnabled(True)
        prefix = "Could not add the disk: " if self.mode.currentIndex() == 1 else "Could not create the disk: "
        self.status.setText(prefix + job.error)

    def reject(self):
        if not self.running():
            super().reject()

    def closeEvent(self, event):
        if self.running():
            event.ignore()
        else:
            super().closeEvent(event)
