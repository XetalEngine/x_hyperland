"""Small validated editors for this session's keyboard, pointer and window settings."""
import html
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QScrollArea,
    QLabel, QLineEdit, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QTextEdit, QMessageBox)
import desktop_settings as settings

INPUT = [
 ('Keyboard','input:kb_layout','Layout codes','text','us · us,ca · gb'),
 ('Keyboard','input:kb_variant','Layout variants','text','Optional, one per layout'),
 ('Keyboard','input:kb_options','Keyboard options','text','Optional XKB options, e.g. caps:escape'),
 ('Keyboard','input:repeat_rate','Repeat rate','int',(1,100,' keys/s')),
 ('Keyboard','input:repeat_delay','Repeat delay','int',(100,2000,' ms')),
 ('Mouse','input:sensitivity','Pointer speed','float',(-1,1,.05)),
 ('Mouse','input:accel_profile','Acceleration','choice',[('System default',''),('Adaptive','adaptive'),('Flat / no acceleration','flat')]),
 ('Mouse','input:natural_scroll','Natural scrolling','bool',None),
 ('Mouse','input:follow_mouse','Window focus','choice',[('Click to focus',0),('Focus follows pointer',1)]),
 ('Touchpad','input:touchpad:tap-to-click','Tap to click','bool',None),
 ('Touchpad','input:touchpad:natural_scroll','Natural scrolling','bool',None),
 ('Touchpad','input:touchpad:disable_while_typing','Disable while typing','bool',None),
]
APPEARANCE = [
 ('Window shape','decoration:rounding','Corner rounding','int',(0,40,' px')),
 ('Window shape','general:border_size','Border width','int',(0,10,' px')),
 ('Window shape','general:gaps_in','Inner gaps','text','One number, or top right bottom left'),
 ('Window shape','general:gaps_out','Outer gaps','text','One number, or top right bottom left'),
 ('Window shape','general:resize_on_border','Resize by dragging borders','bool',None),
 ('Effects','animations:enabled','Animations','bool',None),
 ('Effects','decoration:blur:enabled','Background blur','bool',None),
 ('Effects','decoration:shadow:enabled','Window shadows','bool',None),
 ('Effects','decoration:active_opacity','Focused window opacity','float',(.3,1,.05)),
 ('Effects','decoration:inactive_opacity','Other windows opacity','float',(.3,1,.05)),
]


def validate_values(values):
    for key, value in values.items():
        if key in ('general:gaps_in','general:gaps_out'):
            if not re.fullmatch(r'\d{1,3}(?:\s+\d{1,3}){0,3}', str(value).strip()):
                raise ValueError('Gaps need one to four whole numbers from 0 to 999.')
    if any(key.startswith('input:kb_') for key in values):
        layouts = {node.findtext('configItem/name'): {v.findtext('configItem/name') for v in node.findall('variantList/variant')}
                   for node in ET.parse('/usr/share/X11/xkb/rules/evdev.xml').findall('layoutList/layout')}
        codes = values.get('input:kb_layout','us').split(',')
        if any(code not in layouts for code in codes): raise ValueError('Use valid layout codes, such as us, gb, ca or de. Separate multiple layouts with commas.')
        variants = values.get('input:kb_variant','').split(',')
        if len(variants) > len(codes): raise ValueError('Enter at most one variant per keyboard layout.')
        for code, variant in zip(codes, variants):
            if variant and variant not in layouts[code]: raise ValueError(f'Unknown variant "{variant}" for {code}. Leave variants empty for the standard layout.')


class PreferencesPage(QWidget):
    def __init__(self, name, async_run):
        super().__init__(); self.name = name; self.async_run = async_run; self.store = settings.Store(name)
        self.schema = INPUT if name == 'input' else APPEARANCE
        self.fields = {}; self.baseline = {}; self.previous = ''; self.token = ''; self.loading = False; self.busy = False; self.dirty = False
        root = QVBoxLayout(self); root.setContentsMargins(20,16,20,16)
        title = QLabel('Keyboard, mouse & touchpad' if name == 'input' else 'Window shape & effects'); title.setObjectName('brand'); root.addWidget(title)
        description = QLabel('Preferences apply to your Hyprland session and future Hyprland logins.'); description.setObjectName('muted'); root.addWidget(description)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); self.body = QWidget(); body = QVBoxLayout(self.body)
        groups = {}
        for section, key, title, kind, data in self.schema:
            if section not in groups:
                group = QGroupBox(section); form = QFormLayout(group); form.setVerticalSpacing(12); form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
                groups[section] = form; body.addWidget(group)
            if kind == 'bool':
                widget = QCheckBox('Enabled'); widget.toggled.connect(self.edited)
            elif kind in ('int','float'):
                widget = QSpinBox() if kind == 'int' else QDoubleSpinBox(); widget.setRange(data[0],data[1]); widget.setKeyboardTracking(False)
                if kind == 'int': widget.setSuffix(data[2])
                else: widget.setSingleStep(data[2]); widget.setDecimals(2)
                widget.valueChanged.connect(self.edited)
            elif kind == 'choice':
                widget = QComboBox()
                for label,value in data: widget.addItem(label,value)
                widget.currentIndexChanged.connect(self.edited)
            else:
                widget = QLineEdit(); widget.setPlaceholderText(data); widget.textChanged.connect(self.edited)
            widget.setMinimumWidth(280); self.fields[key] = widget; groups[section].addRow(title,widget)
        if name == 'input':
            note = QLabel('Keyboard layouts: us = English (US), gb = English (UK), ca = Canadian, de = German, fr = French.\nDevice-specific overrides in your configuration take precedence.'); note.setWordWrap(True); note.setObjectName('muted'); body.addWidget(note)
        body.addStretch(); scroll.setWidget(self.body); root.addWidget(scroll,1)
        self.changes = QTextEdit(); self.changes.setReadOnly(True); self.changes.setMaximumHeight(135); self.changes.hide(); root.addWidget(self.changes)
        row = QHBoxLayout(); self.status = QLabel('Choose Reload to read current settings.'); self.status.setWordWrap(True); self.status.setObjectName('muted'); row.addWidget(self.status,1)
        self.reload = QPushButton('Reload'); self.reload.clicked.connect(lambda: self.refresh(True)); row.addWidget(self.reload)
        self.discard = QPushButton('Discard'); self.discard.clicked.connect(self.reset); row.addWidget(self.discard)
        self.apply = QPushButton('Apply changes'); self.apply.setObjectName('primary'); self.apply.clicked.connect(self.save); row.addWidget(self.apply); root.addLayout(row)
        self.edited()

    def values(self):
        values = {}
        for section,key,title,kind,data in self.schema:
            field = self.fields[key]
            values[key] = field.isChecked() if kind == 'bool' else field.value() if kind in ('int','float') else field.currentData() if kind == 'choice' else field.text().strip()
        return values

    def refresh(self, force=False):
        if self.busy or (self.dirty and not force): return
        if self.dirty and not self.confirm_discard(): return
        self.busy = True; self.edited(); self.status.setText('Reading current settings…')
        self.async_run(lambda: (settings.read_options(self.fields), self.store.load()), self.loaded, self.failed)

    def loaded(self, result):
        values, (self.previous, self.token) = result; self.baseline = values; self.busy = False; self.reset()
        self.status.setText('Changes are saved only when you choose Apply.')

    def reset(self):
        self.loading = True
        for section,key,title,kind,data in self.schema:
            if key not in self.baseline: continue
            field = self.fields[key]; value = self.baseline[key]
            if kind == 'bool': field.setChecked(bool(value))
            elif kind in ('int','float'): field.setValue(value)
            elif kind == 'choice':
                if field.findData(value)<0: field.addItem('Current: '+str(value),value)
                field.setCurrentIndex(field.findData(value))
            else: field.setText(str(value))
        # Normalize native booleans and numeric values using the actual controls.
        if self.baseline: self.baseline = self.values()
        self.loading = False; self.edited()

    def edited(self, *_):
        if self.loading: return
        current = self.values(); differences = {k:v for k,v in current.items() if self.baseline and self.baseline[k]!=v}
        self.dirty = bool(differences); self.changes.setVisible(self.dirty)
        labels = {key:title for section,key,title,kind,data in self.schema}
        self.changes.setHtml('<b>UNSAVED CHANGES</b><br>'+''.join(f'<br>{html.escape(labels[k])}: {html.escape(str(self.baseline[k]))} → <b>{html.escape(str(v))}</b>' for k,v in differences.items()))
        self.body.setEnabled(not self.busy and bool(self.baseline)); self.reload.setEnabled(not self.busy)
        self.apply.setEnabled(self.dirty and not self.busy); self.discard.setEnabled(self.dirty and not self.busy)

    def save(self):
        if self.busy or not self.dirty: return
        current = self.values()
        try: validate_values(current)
        except ValueError as error: self.status.setText(str(error)); return
        differences = {k:v for k,v in current.items() if self.baseline[k]!=v}
        def work():
            actual = settings.read_options(differences)
            for key, value in actual.items():
                if value != self.baseline[key]: raise ValueError('A setting changed outside this page. Reload before applying.')
            self.store.save(settings.option_config(self.previous,differences), self.token)
            return settings.read_options(self.fields), self.store.load()
        self.busy = True; self.edited(); self.status.setText('Validating and applying…')
        self.async_run(work, self.saved, self.failed)

    def saved(self,result): self.loaded(result); self.status.setText('Applied and saved for future Hyprland logins.')
    def failed(self,message): self.busy = False; self.edited(); self.status.setText(message)
    def confirm_discard(self):
        return QMessageBox.question(self,'Discard edits?', 'Discard your unsaved '+('input' if self.name=='input' else 'window')+' preferences?',
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
