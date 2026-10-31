"""Minimize controls under Theme → Window effects."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                            QCheckBox, QSpinBox, QComboBox, QPushButton, QMessageBox, QDialog,
                            QColorDialog, QGroupBox, QScrollArea)
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
        description = QLabel('Super + Z minimizes the active window. Click its effect to bring it back. '
                             'Scroll over the left-edge column when it fills up.')
        description.setWordWrap(True); description.setObjectName('muted'); root.addWidget(description)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget(); columns = QHBoxLayout(body); columns.setContentsMargins(0, 12, 8, 12); columns.setSpacing(22)
        general = QGroupBox('Movement & color'); form = QFormLayout(general); form.setSpacing(14)
        self.effect = QComboBox()
        self.effect.addItem('Fireball', 'fireball'); self.effect.addItem('Splat · living slime', 'splat')
        form.addRow('Minimize effect', self.effect)
        self.duration = QSpinBox(); self.duration.setRange(*model.RANGES['duration']); self.duration.setSuffix(' ms')
        self.duration.setKeyboardTracking(False); form.addRow('Travel time', self.duration)
        self.size = QSpinBox(); self.size.setRange(*model.RANGES['size']); self.size.setSuffix(' px')
        self.size.setKeyboardTracking(False); form.addRow('Effect size', self.size)
        self.speed = QSpinBox(); self.speed.setRange(*model.RANGES['speed']); self.speed.setSuffix('%')
        self.speed.setKeyboardTracking(False); form.addRow('Animation speed', self.speed)
        self.follow_theme = QCheckBox('Follow the active theme accent'); form.addRow(self.follow_theme)
        self.color = self.baseline['color']
        self.color_button = QPushButton(); self.color_button.clicked.connect(self.choose_color)
        form.addRow('Custom color', self.color_button)
        columns.addWidget(general, 1)
        details = QGroupBox('Effect details'); right = QVBoxLayout(details)
        self.effect_note = QLabel(); self.effect_note.setWordWrap(True); self.effect_note.setObjectName('muted'); right.addWidget(self.effect_note)
        self.splat_options = QWidget(); self.splat_options.setObjectName("minimizeSplatOptions")
        self.splat_options.setStyleSheet("QWidget#minimizeSplatOptions { background: transparent; }")
        splat = QFormLayout(self.splat_options); splat.setContentsMargins(0, 12, 0, 0); splat.setSpacing(14)
        self.shape = QComboBox()
        for value, title in model.SHAPES.items(): self.shape.addItem(title, value)
        splat.addRow('Silhouette', self.shape)
        self.bubbles = QSpinBox(); self.bubbles.setRange(*model.RANGES['bubbles']); self.bubbles.setSuffix('%')
        self.bubbles.setKeyboardTracking(False); splat.addRow('Boiling intensity', self.bubbles)
        note = QLabel('Random picks a different shape for each window and keeps it until restored. '
                      'Fixed shapes keep their outline while the slime moves and bubbles pop.')
        note.setWordWrap(True); note.setObjectName('muted'); splat.addRow(note)
        right.addWidget(self.splat_options); right.addStretch()
        columns.addWidget(details, 1); columns.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body); root.addWidget(scroll, 1)
        note = QLabel('Your apps stay open. Turning this off restores all minimized windows to their workspaces.')
        note.setWordWrap(True); note.setObjectName('muted'); root.addWidget(note)
        self.status = QLabel(error or 'Choose Fireball or Splat, apply your changes, then try Preview.')
        self.status.setWordWrap(True); self.status.setObjectName('muted'); root.addWidget(self.status)
        row = QHBoxLayout()
        self.defaults = QPushButton('Defaults'); self.defaults.clicked.connect(self.use_defaults); row.addWidget(self.defaults)
        self.preview = QPushButton('Preview'); self.preview.clicked.connect(self.show_preview); row.addWidget(self.preview)
        self.restore = QPushButton('Restore all windows'); self.restore.clicked.connect(self.restore_all); row.addWidget(self.restore)
        row.addStretch()
        self.reload = QPushButton('Reload'); self.reload.clicked.connect(lambda: self.refresh(True)); row.addWidget(self.reload)
        self.discard = QPushButton('Discard'); self.discard.clicked.connect(self.reset); row.addWidget(self.discard)
        self.apply = QPushButton('Apply Minimize'); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); row.addWidget(self.apply)
        root.addLayout(row)
        self.enabled.toggled.connect(self.edited); self.effect.currentIndexChanged.connect(self.edited)
        for field in (self.duration, self.size, self.speed, self.bubbles): field.valueChanged.connect(self.edited)
        self.follow_theme.toggled.connect(self.edited); self.shape.currentIndexChanged.connect(self.edited)
        self.reset()

    def values(self):
        return model.validate(dict(enabled=self.enabled.isChecked(), effect=self.effect.currentData(),
                                   duration=self.duration.value(), size=self.size.value(), follow_theme=self.follow_theme.isChecked(),
                                   color=self.color, shape=self.shape.currentData(), speed=self.speed.value(), bubbles=self.bubbles.value()))

    def reset(self):
        self.fill(self.baseline)

    def use_defaults(self):
        self.fill(model.DEFAULTS)

    def fill(self, values):
        self.loading = True
        self.enabled.setChecked(values['enabled'])
        self.effect.setCurrentIndex(self.effect.findData(values['effect']))
        self.duration.setValue(values['duration']); self.size.setValue(values['size'])
        self.follow_theme.setChecked(values['follow_theme']); self.color = values['color']
        self.shape.setCurrentIndex(self.shape.findData(values['shape']))
        self.speed.setValue(values['speed']); self.bubbles.setValue(values['bubbles'])
        self.loading = False; self.edited()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, 'Minimize effect color')
        if color.isValid(): self.color = color.name(); self.edited()

    def edited(self, *_):
        if self.loading:
            return
        self.dirty = self.values() != self.baseline
        for field in (self.enabled, self.effect, self.duration, self.size, self.speed, self.bubbles, self.follow_theme, self.shape, self.defaults, self.reload, self.restore):
            field.setEnabled(not self.busy)
        self.color_button.setEnabled(not self.busy and not self.follow_theme.isChecked())
        self.color_button.setText('Choose… ' + self.color)
        swatch = QPixmap(18, 18); swatch.fill(QColor(self.color)); self.color_button.setIcon(QIcon(swatch))
        is_splat = self.effect.currentData() == 'splat'; self.splat_options.setVisible(is_splat)
        self.effect_note.setText('Glossy, living slime with rippling skin, swelling bubbles and scattered droplets.' if is_splat else
                                'Soft, rising flames with bright cores and drifting wisps. The fire keeps burning while your window is minimized.')
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
        text = QLabel('Send this window to the left edge. Click its effect to bring it back, or press Super + Z to minimize it.'); text.setWordWrap(True)
        layout.addWidget(text); layout.addStretch()
        minimize = QPushButton('Minimize this window'); minimize.setObjectName('primary'); minimize.clicked.connect(preview.showMinimized)
        layout.addWidget(minimize)
        close = QPushButton('Close preview'); close.clicked.connect(preview.close); layout.addWidget(close)
        self.previews.append(preview)
        preview.destroyed.connect(lambda: self.previews.remove(preview) if preview in self.previews else None)
        preview.show()
