"""The terminal welcome, with a live preview and persistent choices."""
import copy
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QCheckBox, QComboBox, QPushButton, QTextBrowser, QApplication)
from . import model
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class TerminalPage(QWidget):
    def __init__(self, async_run):
        super().__init__(); self.async_run = async_run; self.data = {}; self.loading = False
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16)
        title = QLabel('Terminal welcome'); title.setObjectName('brand'); root.addWidget(title)
        note = QLabel('A luminous Arch emblem with anime-inspired facets and light trails, colored by your desktop theme. System information comes from Fastfetch.')
        note.setWordWrap(True); note.setObjectName('muted'); root.addWidget(note)
        row = QHBoxLayout(); self.enabled = QCheckBox('Show when a Fusion terminal opens'); row.addWidget(self.enabled)
        row.addStretch(); row.addWidget(QLabel('Logo'))
        self.logo = QComboBox()
        for caption, value in [('Arch · Neon', 'arch'), ('Arch · Text', 'arch-ascii'), ('Hyper Fusion', 'fusion'), ('Text only', 'none')]: self.logo.addItem(caption, value)
        row.addWidget(self.logo); root.addLayout(row)
        row = QHBoxLayout(); self.user = QCheckBox('Username and hostname'); self.palette = QCheckBox('Color palette')
        row.addWidget(self.user); row.addWidget(self.palette); row.addStretch(); root.addLayout(row)
        grid = QGridLayout(); self.fields = {}
        for i, (key, title) in enumerate(model.FIELDS.items()):
            box = QCheckBox(title); grid.addWidget(box, i // 6, i % 6); self.fields[key] = box
            box.toggled.connect(self.preview)
        root.addLayout(grid)
        preview = QHBoxLayout()
        self.emblem = QLabel(); self.emblem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.emblem.setFixedWidth(250); preview.addWidget(self.emblem)
        self.display = QTextBrowser(); self.display.setMinimumHeight(300); preview.addWidget(self.display, 1)
        root.addLayout(preview, 1)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setObjectName('muted'); root.addWidget(self.status)
        row = QHBoxLayout()
        for text, action in [('Refresh information', self.refresh_data), ('Reset choices', lambda: self.set_value(model.DEFAULTS))]:
            control = QPushButton(text); control.clicked.connect(action); row.addWidget(control)
        row.addStretch(); self.apply = QPushButton('Save terminal'); self.apply.setObjectName('primary')
        self.apply.clicked.connect(self.save); row.addWidget(self.apply); root.addLayout(row)
        for box in (self.enabled, self.user, self.palette): box.toggled.connect(self.preview)
        self.logo.currentIndexChanged.connect(self.preview)
        self.refresh()
        if hasattr(QApplication.instance(),'hypr_theme'):QApplication.instance().hypr_theme.changed.connect(self.preview)
    def value(self):
        return dict(version=1, enabled=self.enabled.isChecked(), logo=self.logo.currentData(),
            show_user=self.user.isChecked(), show_palette=self.palette.isChecked(),
            fields=[key for key, box in self.fields.items() if box.isChecked()])
    def set_value(self, value):
        self.loading = True
        self.enabled.setChecked(value['enabled']); self.user.setChecked(value['show_user']); self.palette.setChecked(value['show_palette'])
        self.logo.setCurrentIndex(self.logo.findData(value['logo']))
        for key, box in self.fields.items(): box.setChecked(key in value['fields'])
        self.loading = False; self.preview()
    @property
    def dirty(self): return self.value() != self.baseline
    def refresh(self):
        if hasattr(self, 'baseline') and self.dirty: return
        try: self.baseline = model.load()
        except (OSError, ValueError) as error:
            self.status.setText(str(error)); self.baseline = copy.deepcopy(model.DEFAULTS)
        self.set_value(self.baseline)
        if not self.data: self.refresh_data()
    def refresh_data(self):
        self.status.setText('Reading system information…')
        self.async_run(model.system_data, self.loaded, lambda message: self.status.setText(message))
    def loaded(self, data):
        self.data = data; self.preview(); self.status.setText('Colors follow your active palette. New terminals use your saved choices.')
    def preview(self, *_):
        if self.loading: return
        value = self.value(); graphic = False
        if value['logo'] == 'arch':
            try:
                from . import artwork
                self.emblem.setPixmap(QPixmap(str(artwork.png(model.runtime.colors()))).scaled(
                    240, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                graphic = True
            except (ImportError, OSError, ValueError): pass
        self.emblem.setVisible(graphic)
        self.display.setHtml(model.render({**value, 'logo':'none'} if graphic else value,
                                         self.data, width=76 if graphic else 108, markup=True))
        self.apply.setEnabled(self.dirty)
    def save(self):
        try:
            if model.load() != self.baseline: raise ValueError('Terminal choices changed elsewhere. Reopen this page before saving.')
            model.save(self.value(),expected=self.baseline); self.baseline = self.value(); self.preview()
            self.status.setText('Saved. Open a new terminal to see your welcome.')
        except (OSError, ValueError) as error: self.status.setText(str(error))
