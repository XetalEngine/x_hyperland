"""Theme → File Transfer: independent designs, live previews and saved options."""
import copy
import json
from pathlib import Path
import subprocess
import sys

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QFormLayout, QFrame,
    QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

from . import preferences
from .samples import OPERATIONS, sample
from .window import ProgressWindow, theme_runtime


def label(text, name='muted'):
    widget = QLabel(text); widget.setObjectName(name); widget.setWordWrap(True); return widget


class StyleCard(QPushButton):
    def __init__(self, design):
        super().__init__()
        self.design = design; self.setCheckable(True); self.setFixedHeight(105)
        self.setMinimumWidth(180); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(preferences.STYLES[design])
        self.thumbnail = ProgressWindow(sample(), options={**preferences.normalize({}), 'style': design}, preview=True, embedded=True)
        self.thumbnail.setParent(self); self.thumbnail.hide(); self.picture = QPixmap()

    def refresh(self, options, selected):
        choice = copy.deepcopy(options); choice['style'] = self.design
        choice['profiles'][self.design].update(width=448, height=168)
        self.thumbnail.set_options(choice); self.thumbnail.phase = .42
        self.picture = self.thumbnail.grab(); self.setChecked(selected == self.design); self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = theme_runtime.colors(); accent = QColor(theme_runtime.colors(style=self.design)['Accent'])
        p.setBrush(QColor(colors['AlternateBase'])); p.setPen(QPen(accent if self.isChecked() else QColor(colors['Midlight']), 2 if self.isChecked() else 1))
        p.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 12, 12)
        p.setFont(QFont(theme_runtime.ui_font(), 10, QFont.Weight.DemiBold)); p.setPen(QColor(colors['Text']))
        p.drawText(QRectF(12, 6, self.width()-24, 24), Qt.AlignmentFlag.AlignVCenter, preferences.STYLES[self.design])
        if not self.picture.isNull():
            target = self.picture.size().scaled(self.width()-20, 62, Qt.AspectRatioMode.KeepAspectRatio)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap((self.width()-target.width())//2, 35, self.picture.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class PreviewView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame); self.setMinimumSize(270, 100)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setInteractive(False); self.setStyleSheet('QGraphicsView {background:transparent; border:none;}')
        self._scene = QGraphicsScene(self); self.setScene(self._scene)
        self.window = None

    def configure(self, options, operation, state):
        if self.window is not None:
            self._scene.clear(); self.window = None
        self.window = ProgressWindow(sample(operation, state), options=options, preview=True, embedded=True)
        self.window.phase = .37
        self._scene.addWidget(self.window); self.window.show()
        self.fit()
        if not self.isVisible(): self.window.animation.stop()

    def fit(self):
        if self.window is None: return
        area = QRectF(-12, -12, self.window.width()+24, self.window.height()+24)
        self.setSceneRect(area); self.resetTransform()
        factor = min(1., max(.1, self.viewport().width()/area.width()), max(.1, self.viewport().height()/area.height()))
        self.scale(factor, factor); self.centerOn(area.center())

    def resizeEvent(self, event):
        super().resizeEvent(event); self.fit()

    def showEvent(self, event):
        super().showEvent(event); self.fit()
        if self.window: self.window.refresh()

    def hideEvent(self, event):
        if self.window: self.window.animation.stop()
        super().hideEvent(event)


class FileTransferPage(QWidget):
    def __init__(self, async_run):
        super().__init__()
        self.async_run = async_run; self.busy = self.loading = self.dirty = False
        self.fields = {}; self.cards = {}; self.invalid = False
        error = ''
        try: self.baseline, self.token = preferences.load()
        except (OSError, ValueError) as problem:
            self.baseline, self.token = preferences.normalize({}), None
            self.invalid = True; error = str(problem)
        self.draft = copy.deepcopy(self.baseline)
        root = QVBoxLayout(self); root.setContentsMargins(12, 10, 12, 10); root.setSpacing(8)
        heading = QHBoxLayout(); heading.addWidget(label('File Transfer', 'brand')); heading.addStretch()
        self.style = QComboBox(); self.style.setAccessibleName('File Transfer style')
        for value, title in preferences.STYLES.items(): self.style.addItem(title, value)
        heading.addWidget(self.style); root.addLayout(heading)
        outer = QScrollArea(); outer.setWidgetResizable(True); outer.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); body = QVBoxLayout(content); body.setContentsMargins(0, 0, 2, 0); body.setSpacing(12)
        cards = QHBoxLayout(); cards.setSpacing(10)
        for name in preferences.PROFILES:
            card = StyleCard(name); card.clicked.connect(lambda _, value=name: self.select_style(value))
            cards.addWidget(card, 1); self.cards[name] = card
        body.addLayout(cards)
        columns = QHBoxLayout(); columns.setSpacing(14)
        preview_box = QGroupBox('Live preview'); preview_box.setMinimumWidth(300)
        left = QVBoxLayout(preview_box); left.setContentsMargins(10, 14, 10, 12)
        self.preview = PreviewView()
        self.size_hint = label(''); self.size_hint.setWordWrap(False); self.size_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout(); self.operation = QComboBox(); self.operation.setAccessibleName('Preview operation')
        for value, title in OPERATIONS.items(): self.operation.addItem(title, value)
        self.sample_state = QComboBox(); self.sample_state.setAccessibleName('Preview status')
        for value, title in (('running', 'Running'), ('unknown', 'Unknown size'), ('paused', 'Paused'), ('completed', 'Completed'), ('error', 'Error')):
            self.sample_state.addItem(title, value)
        row.addWidget(self.operation, 1); row.addWidget(self.sample_state); left.addLayout(row)
        left.addWidget(self.preview, 1); left.addWidget(self.size_hint)
        self.popup = QPushButton('Preview popup'); self.popup.clicked.connect(self.open_popup)
        preview_note = label('Preview only · no files are changed.'); preview_note.setWordWrap(False)
        left.addWidget(preview_note)
        columns.addWidget(preview_box, 1)
        options_scroll = QScrollArea(); options_scroll.setMinimumWidth(320); options_scroll.setMinimumHeight(220)
        options_scroll.setWidgetResizable(True); options_scroll.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget(); settings = QVBoxLayout(panel); settings.setContentsMargins(0, 0, 2, 0); settings.setSpacing(12)
        self.look_title = QGroupBox('Appearance'); appearance = QFormLayout(self.look_title); appearance.setSpacing(9)
        settings.addWidget(self.look_title)
        for key, title, suffix in (('width', 'Window width', ' px'), ('height', 'Window height', ' px'),
                                   ('radius', 'Corner radius', ' px'), ('border', 'Border width', ' px'),
                                   ('track_height', 'Progress thickness', ' px')):
            self.number(appearance, 'profile', key, title, suffix)
        self.slider(appearance, 'profile', 'opacity', 'Background opacity', '%')
        self.slider(appearance, 'profile', 'glow', 'Glow intensity', '%')
        colors = QHBoxLayout(); self.color = QPushButton('Choose color…'); self.color.clicked.connect(self.choose_color)
        self.theme_color = QPushButton('Theme color'); self.theme_color.clicked.connect(lambda: self.set_accent(''))
        colors.addWidget(self.color, 1); colors.addWidget(self.theme_color); appearance.addRow('Accent color', colors)
        motion = QGroupBox('Animation'); form = QFormLayout(motion); form.setSpacing(9); settings.addWidget(motion)
        self.check(form, 'animation', 'enabled', 'Animate files')
        self.slider(form, 'animation', 'speed', 'Animation speed', '%')
        self.number(form, 'animation', 'density', 'Flying files / packets', '')
        self.check(form, 'animation', 'trails', 'Motion trails')
        self.check(form, 'animation', 'smooth', 'Smooth progress changes')
        info = QGroupBox('Information'); form = QFormLayout(info); form.setSpacing(9); settings.addWidget(info)
        paths = QComboBox()
        for value, title in (('names', 'Folder names'), ('full', 'Full paths'), ('hidden', 'Hidden')): paths.addItem(title, value)
        paths.setAccessibleName('Source and destination'); paths.currentIndexChanged.connect(lambda *_: self.edit('information', 'paths', paths.currentData()))
        self.fields[('information', 'paths')] = paths; form.addRow('Source / destination', paths)
        for key, title in (('percentage', 'Show percentage'), ('amount', 'Show transferred amount'),
                           ('speed', 'Show transfer speed'), ('remaining', 'Show estimated time left')):
            self.check(form, 'information', key, title)
        behavior = QGroupBox('Timing'); form = QFormLayout(behavior); form.setSpacing(9); settings.addWidget(behavior)
        self.number(form, 'behavior', 'show_delay', 'Show after', ' ms')
        self.check(form, 'behavior', 'auto_close', 'Close completed operations automatically')
        self.number(form, 'behavior', 'close_delay', 'Keep completion visible', ' ms')
        form.addRow(label('Errors stay visible until you close them. Pause and Cancel keep controlling the real operation.'))
        settings.addStretch(); options_scroll.setWidget(panel); columns.addWidget(options_scroll, 1); body.addLayout(columns, 1)
        outer.setWidget(content); root.addWidget(outer, 1)
        self.status = label('Choose any transfer style with any desktop theme.'); root.addWidget(self.status)
        actions = QHBoxLayout()
        self.defaults = QPushButton('Reset defaults'); self.defaults.clicked.connect(self.reset_defaults); actions.addWidget(self.defaults)
        actions.addWidget(self.popup)
        actions.addStretch(); self.reload_button = QPushButton('Reload'); self.reload_button.clicked.connect(lambda: self.refresh(True)); actions.addWidget(self.reload_button)
        self.discard = QPushButton('Discard'); self.discard.clicked.connect(self.reset); actions.addWidget(self.discard)
        self.apply = QPushButton('Apply File Transfer'); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); actions.addWidget(self.apply)
        root.addLayout(actions)
        self.style.currentIndexChanged.connect(self.style_changed)
        self.operation.currentIndexChanged.connect(self.preview_changed); self.sample_state.currentIndexChanged.connect(self.preview_changed)
        if hasattr(QApplication.instance(), 'hypr_theme'):
            QApplication.instance().hypr_theme.changed.connect(self.desktop_changed)
        self.reset()
        if error: self.status.setText('Cannot read File Transfer settings: '+error+'. Reload after repairing the file.')

    def number(self, form, section, key, title, suffix):
        field = QSpinBox(); field.setRange(*preferences.RANGES[key]); field.setSuffix(suffix)
        field.setKeyboardTracking(False); field.setAccessibleName(title)
        field.valueChanged.connect(lambda value: self.edit(section, key, value))
        self.fields[(section, key)] = field; form.addRow(title, field)

    def slider(self, form, section, key, title, suffix):
        row = QHBoxLayout(); field = QSlider(Qt.Orientation.Horizontal); field.setRange(*preferences.RANGES[key])
        field.setAccessibleName(title); value = QLabel(); value.setFixedWidth(43); value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        field.valueChanged.connect(lambda n: value.setText(str(n)+suffix))
        field.valueChanged.connect(lambda n: self.edit(section, key, n))
        self.fields[(section, key)] = field; row.addWidget(field, 1); row.addWidget(value); form.addRow(title, row)

    def check(self, form, section, key, title):
        field = QCheckBox(title); field.toggled.connect(lambda value: self.edit(section, key, value))
        self.fields[(section, key)] = field; form.addRow(field)

    def design(self):
        return preferences.selected(self.draft, theme_runtime.design())

    def select_style(self, value):
        self.style.setCurrentIndex(self.style.findData(value)); self.update_preview()

    def style_changed(self):
        if self.loading: return
        self.draft['style'] = self.style.currentData(); self.load_controls(); self.changed()

    def desktop_changed(self):
        self.load_controls(); self.update_preview()

    def edit(self, section, key, value):
        if self.loading: return
        target = self.draft['profiles'][self.design()] if section == 'profile' else self.draft[section]
        target[key] = value; self.changed()

    def load_controls(self):
        self.loading = True
        self.style.setCurrentIndex(self.style.findData(self.draft['style']))
        for (section, key), field in self.fields.items():
            value = (self.draft['profiles'][self.design()] if section == 'profile' else self.draft[section])[key]
            if isinstance(field, QCheckBox): field.setChecked(value)
            elif isinstance(field, QComboBox): field.setCurrentIndex(field.findData(value))
            else: field.setValue(value)
        self.loading = False
        self.look_title.setTitle(preferences.STYLES[self.design()]+' appearance')
        self.update_color()

    def changed(self):
        self.dirty = self.draft != self.baseline
        self.apply.setEnabled(self.dirty and not self.busy and not self.invalid)
        self.discard.setEnabled(self.dirty and not self.busy)
        self.defaults.setEnabled(not self.busy); self.reload_button.setEnabled(not self.busy)
        self.style.setEnabled(not self.busy); self.popup.setEnabled(not self.busy)
        for field in self.fields.values(): field.setEnabled(not self.busy)
        self.fields[('behavior', 'close_delay')].setEnabled(not self.busy and self.draft['behavior']['auto_close'])
        self.color.setEnabled(not self.busy); self.update_color()
        for card in self.cards.values(): card.setEnabled(not self.busy)
        self.update_preview()

    def update_color(self):
        custom = self.draft['profiles'][self.design()]['accent']
        color = QColor(custom or theme_runtime.colors(style=self.design())['Accent'])
        pixmap = QPixmap(18, 18); pixmap.fill(color); self.color.setIcon(QIcon(pixmap))
        self.color.setText(custom.upper() if custom else 'Theme accent'); self.theme_color.setEnabled(bool(custom) and not self.busy)

    def set_accent(self, value):
        self.draft['profiles'][self.design()]['accent'] = value; self.update_color(); self.changed()

    def choose_color(self):
        current = self.draft['profiles'][self.design()]['accent'] or theme_runtime.colors(style=self.design())['Accent']
        chosen = QColorDialog.getColor(QColor(current), self, 'File Transfer accent', QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if chosen.isValid(): self.set_accent(chosen.name())

    def preview_changed(self):
        if not self.loading: self.update_preview()

    def update_preview(self):
        self.preview.configure(self.draft, self.operation.currentData() or 'copy', self.sample_state.currentData() or 'running')
        profile = self.draft['profiles'][self.design()]
        self.size_hint.setText(f"{preferences.STYLES[self.design()]} · {profile['width']} × {profile['height']} px")
        for card in self.cards.values(): card.refresh(self.draft, self.design())

    def reset(self):
        self.draft = copy.deepcopy(self.baseline); self.load_controls(); self.changed()

    def reset_defaults(self):
        self.draft = preferences.normalize({}); self.load_controls(); self.changed()

    def refresh(self, force=False):
        if self.busy or (self.dirty and not force): return
        if self.dirty and QMessageBox.question(self, 'Discard File Transfer edits?', 'Reload the saved settings and discard these edits?',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard: return
        try:
            self.baseline, self.token = preferences.load(); self.invalid = False; self.reset()
        except (OSError, ValueError) as error: self.failed(str(error))

    def save(self):
        if self.busy or not self.dirty or self.invalid: return
        values, token = preferences.normalize(self.draft), self.token
        self.busy = True; self.changed(); self.status.setText('Saving File Transfer settings…')
        self.async_run(lambda: preferences.save(values, token), self.saved, self.failed)

    def saved(self, result):
        self.baseline, self.token = result; self.busy = False; self.reset()
        self.status.setText('Saved. Transfer windows use these choices now and at future logins.')

    def failed(self, message):
        self.busy = False; self.changed(); self.status.setText(str(message))

    def open_popup(self):
        root = Path(__file__).resolve().parents[1]
        try:
            subprocess.Popen([sys.executable, str(root/'theme/run.py'), sys.executable, str(root/'file_jobs/app.py'),
                              '--preview', json.dumps(preferences.normalize(self.draft)), '--operation', self.operation.currentData()])
        except OSError as error: self.status.setText(str(error))
