"""Fusion Settings → Theme → Task Switcher, with safe draft previews."""
import copy

from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget)

from . import preferences, overlay
from .scene import Scene, sample_clients, sample_pictures, theme_runtime


def label(text, name='muted'):
    result = QLabel(text); result.setObjectName(name); result.setWordWrap(True); return result


class PreviewDialog(QDialog):
    def __init__(self, options, parent):
        super().__init__(parent)
        self.setWindowTitle('Task Switcher · Preview'); self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        overlay.configure(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        self.scene = Scene(); self.scene.configure(options, sample_clients())
        self.scene.pictures = sample_pictures(self.scene.clients) if options['live_previews'] else {}
        self.scene.activated.connect(lambda i: self.scene.select(i)); self.scene.stepped.connect(self.step)
        self.scene.dismissed.connect(self.close)
        self.scene.setAccessibleDescription('Example windows. Tab or arrows to explore. Escape or click empty space to close.')
        root.addWidget(self.scene, 1)
        for obj in (self, self.scene): obj.installEventFilter(self)
        available = self.screen().availableGeometry()
        self.resize(min(1100, available.width()-40), min(650, available.height()-60))
        self.scene.setFocus()

    def step(self, direction): self.scene.select(self.scene.selected+direction)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape: self.close(); return True
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Left, Qt.Key.Key_Right):
                self.step(-1 if key in (Qt.Key.Key_Backtab, Qt.Key.Key_Left) or event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
                return True
        return super().eventFilter(obj, event)


class TaskSwitcherPage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run; self.busy = self.dirty = self.loading = self.invalid = False
        self.fields = {}; self.profile_fields = {}; self.dialogs = []
        error = ''
        try: self.baseline, self.token = preferences.load()
        except (OSError, ValueError) as problem:
            self.baseline, self.token = preferences.normalize({}), None
            self.invalid = True; error = str(problem)
        self.draft = copy.deepcopy(self.baseline)
        root = QVBoxLayout(self); root.setContentsMargins(12, 10, 12, 10); root.setSpacing(8)
        header = QHBoxLayout(); header.addWidget(label('Task Switcher', 'brand')); header.addStretch()
        header.addWidget(label('Super + Tab'))
        self.style = QComboBox(); self.style.setAccessibleName('Task Switcher style')
        for key, title in preferences.STYLES.items(): self.style.addItem(title, key)
        header.addWidget(self.style); root.addLayout(header)
        self.description = label(''); root.addWidget(self.description)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); body = QVBoxLayout(content); body.setContentsMargins(0, 0, 6, 0)
        preview_box = QGroupBox('Animated preview · example windows'); preview_layout = QVBoxLayout(preview_box)
        self.preview = Scene(interactive=False); self.preview.setFixedHeight(210)
        self.preview.configure(self.draft, sample_clients()); self.examples = sample_pictures(self.preview.clients)
        self.preview.pictures = self.examples
        preview_layout.addWidget(self.preview)
        row = QHBoxLayout()
        self.previous = QPushButton('← Previous'); self.previous.clicked.connect(lambda: self.step(-1)); row.addWidget(self.previous)
        self.next = QPushButton('Next →'); self.next.clicked.connect(lambda: self.step(1)); row.addWidget(self.next)
        self.play = QCheckBox('Animate preview'); self.play.setChecked(True); self.play.toggled.connect(self.update_timer); row.addWidget(self.play)
        row.addStretch(); self.popup = QPushButton('Larger preview'); self.popup.clicked.connect(self.open_preview); row.addWidget(self.popup)
        self.popup.setToolTip('Preview floating cards over your desktop. Press Esc or click empty space to close.')
        preview_layout.addLayout(row); body.addWidget(preview_box)
        columns = QHBoxLayout(); columns.setSpacing(16)
        general = QGroupBox('Behavior and appearance'); form = QFormLayout(general); form.setSpacing(8)
        self.scope = QComboBox(); self.scope.setAccessibleName('Windows to include')
        for key, title in preferences.SCOPES.items(): self.scope.addItem(title, key)
        self.scope.currentIndexChanged.connect(lambda: self.edit('scope', self.scope.currentData()))
        form.addRow('Windows to include', self.scope)
        for key, title, suffix in [('duration', 'Animation duration', ' ms'), ('size', 'Switcher size', '%'),
                                    ('inactive_opacity', 'Inactive windows', '%')]:
            self.add_number(form, key, title, suffix)
        for key, title in [('live_previews', 'Live window previews'), ('show_titles', 'Show window titles'), ('show_icons', 'Show app icons')]:
            self.add_check(form, key, title)
        form.addRow(label('Cards float directly over the desktop. Release Super to select; Esc or click empty space to cancel. Duration 0 disables motion.'))
        columns.addWidget(general, 1)
        self.specific = QGroupBox(); self.specific_form = QFormLayout(self.specific); self.specific_form.setSpacing(8)
        columns.addWidget(self.specific, 1); body.addLayout(columns); body.addStretch()
        scroll.setWidget(content); root.addWidget(scroll, 1)
        self.status = label('Choose a switcher for any desktop theme. Apply keeps your choice for future logins.'); root.addWidget(self.status)
        actions = QHBoxLayout()
        self.defaults = QPushButton('Style defaults'); self.defaults.clicked.connect(self.reset_style); actions.addWidget(self.defaults)
        actions.addStretch(); self.reload_button = QPushButton('Reload'); self.reload_button.clicked.connect(lambda: self.refresh(True)); actions.addWidget(self.reload_button)
        self.discard = QPushButton('Discard'); self.discard.clicked.connect(self.reset); actions.addWidget(self.discard)
        self.apply = QPushButton('Apply Task Switcher'); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); actions.addWidget(self.apply)
        root.addLayout(actions)
        self.timer = QTimer(self); self.timer.setInterval(1600); self.timer.timeout.connect(lambda: self.step(1))
        self.style.currentIndexChanged.connect(self.style_changed)
        if hasattr(QApplication.instance(), 'hypr_theme'):
            QApplication.instance().hypr_theme.changed.connect(self.theme_changed)
        self.reset()
        if error: self.status.setText('Cannot read Task Switcher settings: '+error+'. Reload after repairing the file.')

    def add_number(self, form, key, title, suffix='', profile=False):
        field = QSpinBox(); field.setRange(*preferences.RANGES[key]); field.setSuffix(suffix)
        field.setKeyboardTracking(False); field.setAccessibleName(title)
        field.valueChanged.connect(lambda value: self.edit(key, value, profile))
        (self.profile_fields if profile else self.fields)[key] = field; form.addRow(title, field)

    def add_check(self, form, key, title, profile=False):
        field = QCheckBox(title); field.setAccessibleName(title); field.toggled.connect(lambda value: self.edit(key, value, profile))
        (self.profile_fields if profile else self.fields)[key] = field; form.addRow(field)

    def build_specific(self):
        while self.specific_form.rowCount(): self.specific_form.removeRow(0)
        self.profile_fields = {}; style = self.draft['style']; self.specific.setTitle(preferences.STYLES[style]+' options')
        names = dict(columns=('Columns', ''), thumb_width=('Preview width', ' px'), thumb_height=('Preview height', ' px'),
                     ring_width=('Ring width', '%'), ring_height=('Ring height', '%'), min_scale=('Back window size', '%'),
                     min_brightness=('Back window brightness', '%'), size=('Window size', '%'), cover_offset=('Cover offset', '%'),
                     reflection_intensity=('Reflection intensity', '%'), flip_rotation=('Flip angle', '°'), tilt=('Stack tilt', '°'), spacing=('Window spacing', ' px'))
        checks = dict(icon_only='Icons only', clockwise='Rotate clockwise', reflection='Show reflections', inactive_rotate='Tilt inactive windows')
        for key, value in self.draft['profiles'][style].items():
            if type(value) is bool: self.add_check(self.specific_form, key, checks[key], True)
            else: self.add_number(self.specific_form, key, *names[key], profile=True)
        if style in ('fusion', 'static', 'scale'):
            self.specific_form.addRow(label('Larger window lists continue onto the next page as you cycle.'))
        self.specific_form.addRow(label('Colors follow your desktop theme. These controls are remembered separately for each switcher.'))

    def style_changed(self):
        if self.loading: return
        self.draft['style'] = self.style.currentData(); self.load_controls(); self.changed()
        self.preview.select(0, False)

    def edit(self, key, value, profile=False):
        if self.loading: return
        target = self.draft['profiles'][self.draft['style']] if profile else self.draft
        target[key] = value; self.changed()

    def load_controls(self):
        self.loading = True
        self.style.setCurrentIndex(self.style.findData(self.draft['style']))
        self.scope.setCurrentIndex(self.scope.findData(self.draft['scope']))
        self.build_specific()
        for fields, values in ((self.fields, self.draft), (self.profile_fields, self.draft['profiles'][self.draft['style']])):
            for key, field in fields.items():
                if isinstance(field, QCheckBox): field.setChecked(values[key])
                else: field.setValue(values[key])
        self.loading = False
        self.description.setText(preferences.DESCRIPTIONS[self.draft['style']])

    def changed(self):
        self.dirty = self.draft != self.baseline
        self.apply.setEnabled(self.dirty and not self.busy and not self.invalid)
        self.discard.setEnabled(self.dirty and not self.busy)
        for field in [self.style, self.scope, self.defaults, self.reload_button, *self.fields.values(), *self.profile_fields.values()]:
            field.setEnabled(not self.busy)
        cfg = self.draft['profiles'][self.draft['style']]
        self.fields['live_previews'].setEnabled(not self.busy and self.draft['style'] != 'fusion')
        if 'reflection_intensity' in self.profile_fields:
            self.profile_fields['reflection_intensity'].setEnabled(not self.busy and cfg['reflection'])
        self.preview.configure(self.draft)
        self.preview.pictures = self.examples if self.draft['live_previews'] else {}

    def step(self, direction): self.preview.select(self.preview.selected+direction)

    def update_timer(self):
        if self.isVisible() and self.play.isChecked(): self.timer.start()
        else: self.timer.stop()

    def showEvent(self, event): super().showEvent(event); self.update_timer()
    def hideEvent(self, event): self.timer.stop(); super().hideEvent(event)

    def theme_changed(self):
        self.examples = sample_pictures(self.preview.clients)
        self.preview.pictures = self.examples if self.draft['live_previews'] else {}; self.preview.update()
        for dialog in self.dialogs:
            dialog.scene.pictures = sample_pictures(dialog.scene.clients) if dialog.scene.options['live_previews'] else {}; dialog.scene.update()

    def open_preview(self):
        dialog = PreviewDialog(copy.deepcopy(self.draft), self)
        self.dialogs.append(dialog); dialog.finished.connect(lambda _: self.dialogs.remove(dialog))
        dialog.show(); dialog.scene.setFocus()

    def reset_style(self):
        style = self.draft['style']; self.draft['profiles'][style] = copy.deepcopy(preferences.PROFILES[style])
        self.load_controls(); self.changed()

    def reset(self):
        self.draft = copy.deepcopy(self.baseline); self.load_controls(); self.changed()

    def refresh(self, force=False):
        if self.busy or (self.dirty and not force): return
        if self.dirty and QMessageBox.question(self, 'Discard Task Switcher edits?', 'Reload saved settings and discard these edits?',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard: return
        try:
            self.baseline, self.token = preferences.load(); self.invalid = False; self.reset()
        except (OSError, ValueError) as error: self.failed(str(error))

    def save(self):
        if self.busy or not self.dirty or self.invalid: return
        values, token = preferences.normalize(self.draft), self.token
        self.busy = True; self.changed(); self.status.setText('Saving Task Switcher settings…')
        self.async_run(lambda: preferences.save(values, token), self.saved, self.failed)

    def saved(self, result):
        self.baseline, self.token = result; self.busy = False; self.reset()
        self.status.setText('Saved. Hold Super and press Tab to try it. Your windows keep their monitors and workspaces.')

    def failed(self, message):
        self.busy = False; self.changed(); self.status.setText(str(message))
