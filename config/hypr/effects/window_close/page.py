"""Hotkeys dialog; changing the gesture never rewrites keybindings.conf."""
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QCheckBox,
                            QComboBox, QSpinBox, QDialogButtonBox)
from . import model, controller


class Apply(QThread):
    finishedApply = pyqtSignal(object, str)
    def __init__(self, values, token, parent):
        super().__init__(parent); self.values, self.token = values, token
    def run(self):
        try: self.finishedApply.emit(controller.save(self.values, self.token), '')
        except Exception as error: self.finishedApply.emit(None, str(error))


class Dialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Window buttons'); self.setMinimumWidth(460)
        self.values, self.token = model.load(); self.worker = None
        layout = QVBoxLayout(self); layout.setContentsMargins(24,24,24,24); layout.setSpacing(16)
        title = QLabel('Your window controls, one key away')
        title.setStyleSheet('font-size: 19px; font-weight: 700;'); layout.addWidget(title)
        hint = QLabel('Hold the modifier over a window to minimize, maximize or restore, and close. '
                      'Restore turns a tiled window into a floating window at its remembered size, '
                      'fitted to the current screen. Close still lets applications ask you to save.')
        hint.setWordWrap(True); layout.addWidget(hint)
        self.enabled = QCheckBox('Show window buttons'); self.enabled.setChecked(self.values['enabled'])
        layout.addWidget(self.enabled)
        form = QFormLayout(); form.setSpacing(12)
        self.modifier = QComboBox(); self.modifier.addItems(['SUPER', 'ALT', 'SUPER+SHIFT'])
        self.modifier.setCurrentText(self.values['modifier']); form.addRow('Hold to show', self.modifier)
        self.size = QSpinBox(); self.size.setRange(24,64); self.size.setSuffix(' px'); self.size.setValue(self.values['size'])
        form.addRow('Button size', self.size)
        self.inset = QSpinBox(); self.inset.setRange(4,32); self.inset.setSuffix(' px'); self.inset.setValue(self.values['inset'])
        form.addRow('Distance from the corner', self.inset); layout.addLayout(form)
        self.pulse = QCheckBox('Pulse gently in the theme accent'); self.pulse.setChecked(self.values['pulse'])
        layout.addWidget(self.pulse)
        self.status = QLabel(''); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)

    def apply(self):
        self.buttons.setEnabled(False); self.status.setText('Applying…')
        values = dict(enabled=self.enabled.isChecked(), modifier=self.modifier.currentText(),
                      size=self.size.value(), inset=self.inset.value(), pulse=self.pulse.isChecked())
        self.worker = Apply(values, self.token, self)
        self.worker.finishedApply.connect(self.applied); self.worker.start()

    def applied(self, result, error):
        self.buttons.setEnabled(True)
        if error: self.status.setText(error+' Close and reopen to reload the saved settings.')
        else:
            self.values, self.token = result; self.status.setText('Applied to this session and future logins.')

    def reject(self):
        if self.worker and self.worker.isRunning(): return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning(): event.ignore()
        else: super().closeEvent(event)
