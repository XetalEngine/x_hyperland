"""Minimize controls under Theme → Window effects."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                            QCheckBox, QSpinBox, QComboBox, QPushButton, QMessageBox, QDialog)
from . import model, controller


class MinimizePage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run
        self.busy = self.dirty = self.loading = False
        self.previews = []
        error = ''
        try:
            self.baseline, self.token = model.load()
        except (OSError, ValueError) as exc:
            self.baseline, self.token = dict(model.DEFAULTS), None
            error = f'Cannot read Minimize settings: {exc}. Repair effects/minimize/settings.conf, then Reload.'
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        heading = QHBoxLayout()
        title = QLabel('Minimize'); title.setObjectName('brand'); heading.addWidget(title)
        heading.addStretch()
        self.enabled = QCheckBox('Enable minimizing'); heading.addWidget(self.enabled)
        root.addLayout(heading)
        description = QLabel('Minimize a window to a burning fireball on the left edge of its screen. '
                             'Click the fireball to bring the window back. Scroll over the column when it fills up.')
        description.setWordWrap(True); description.setObjectName('muted'); root.addWidget(description)
        form = QFormLayout(); form.setSpacing(14)
        self.effect = QComboBox(); self.effect.addItem('Fireball', 'fireball'); form.addRow('Effect', self.effect)
        self.duration = QSpinBox(); self.duration.setRange(*model.RANGES['duration']); self.duration.setSuffix(' ms')
        self.duration.setKeyboardTracking(False); form.addRow('Travel time', self.duration)
        self.size = QSpinBox(); self.size.setRange(*model.RANGES['size']); self.size.setSuffix(' px')
        self.size.setKeyboardTracking(False); form.addRow('Fireball size', self.size)
        root.addLayout(form)
        note = QLabel('Your apps stay open. Turning this off restores all minimized windows to their workspaces.')
        note.setWordWrap(True); note.setObjectName('muted'); root.addWidget(note); root.addStretch()
        self.status = QLabel(error or 'Minimize using an app’s own button. This effect is separate from Burn when closing windows.')
        self.status.setWordWrap(True); self.status.setObjectName('muted'); root.addWidget(self.status)
        row = QHBoxLayout()
        self.preview = QPushButton('Preview'); self.preview.clicked.connect(self.show_preview); row.addWidget(self.preview)
        self.restore = QPushButton('Restore all windows'); self.restore.clicked.connect(self.restore_all); row.addWidget(self.restore)
        row.addStretch()
        self.reload = QPushButton('Reload'); self.reload.clicked.connect(lambda: self.refresh(True)); row.addWidget(self.reload)
        self.discard = QPushButton('Discard'); self.discard.clicked.connect(self.reset); row.addWidget(self.discard)
        self.apply = QPushButton('Apply Minimize'); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); row.addWidget(self.apply)
        root.addLayout(row)
        self.enabled.toggled.connect(self.edited); self.effect.currentIndexChanged.connect(self.edited)
        self.duration.valueChanged.connect(self.edited); self.size.valueChanged.connect(self.edited)
        self.reset()

    def values(self):
        return model.validate(dict(enabled=self.enabled.isChecked(), effect=self.effect.currentData(),
                                   duration=self.duration.value(), size=self.size.value()))

    def reset(self):
        self.loading = True
        self.enabled.setChecked(self.baseline['enabled'])
        self.effect.setCurrentIndex(self.effect.findData(self.baseline['effect']))
        self.duration.setValue(self.baseline['duration']); self.size.setValue(self.baseline['size'])
        self.loading = False; self.edited()

    def edited(self, *_):
        if self.loading:
            return
        self.dirty = self.values() != self.baseline
        for field in (self.enabled, self.effect, self.duration, self.size, self.reload, self.restore):
            field.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy and self.token is not None)
        self.discard.setEnabled(self.dirty and not self.busy)
        self.preview.setEnabled(not self.busy and not self.dirty and self.baseline['enabled'] and self.token is not None)

    def refresh(self, force=False):
        if self.busy or (self.dirty and not force):
            return
        if self.dirty and QMessageBox.question(self, 'Discard Minimize edits?', 'Reload saved settings and discard these edits?',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:
            return
        try:
            self.baseline, self.token = model.load(); self.reset()
        except (OSError, ValueError) as exc:
            self.failed(str(exc))

    def save(self):
        if self.busy or not self.dirty:
            return
        values = self.values(); self.busy = True; self.edited(); self.status.setText('Applying Minimize…')
        self.async_run(lambda: controller.save(values, self.token), self.saved, self.failed)

    def saved(self, result):
        self.baseline, self.token = result; self.busy = False; self.reset()
        self.status.setText('Minimize is on and saved for future logins.' if self.baseline['enabled'] else
                            'Minimize is off. Your windows have been restored.')

    def failed(self, message):
        self.busy = False; self.edited(); self.status.setText(str(message))

    def restore_all(self):
        if self.busy:
            return
        self.busy = True; self.edited()
        def done(_):
            self.busy = False; self.edited(); self.status.setText('All minimized windows returned to their workspaces.')
        self.async_run(lambda: controller.hypr('dispatch', 'xetalminimize:restoreall'), done, self.failed)

    def show_preview(self):
        if self.busy:
            return
        self.busy = True; self.edited()
        self.async_run(lambda: controller.activate(self.baseline), self.preview_ready, self.failed)

    def preview_ready(self, _):
        self.busy = False; self.edited()
        preview = QDialog(self.window()); preview.setWindowTitle('Minimize preview'); preview.setModal(False)
        preview.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose); preview.resize(520, 300)
        layout = QVBoxLayout(preview); layout.setContentsMargins(28, 24, 28, 24)
        text = QLabel('Send this window to the left edge. Click its fireball to bring it back.'); text.setWordWrap(True)
        layout.addWidget(text); layout.addStretch()
        minimize = QPushButton('Minimize this window'); minimize.setObjectName('primary'); minimize.clicked.connect(preview.showMinimized)
        layout.addWidget(minimize)
        close = QPushButton('Close preview'); close.clicked.connect(preview.close); layout.addWidget(close)
        self.previews.append(preview)
        preview.destroyed.connect(lambda: self.previews.remove(preview) if preview in self.previews else None)
        preview.show()
