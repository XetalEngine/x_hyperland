"""Dark shortcut and icon editors used only by the Hyprland launcher."""
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QDialogButtonBox, QFileDialog, QListWidget,
    QListWidgetItem, QListView)

import shortcuts
from image_picker import ImagePicker

DIALOG_STYLE = '''
QDialog { background: #131e2c; border: 1px solid #3a5a6b; }
QLabel#dialogTitle { font-size: 23px; font-weight: 700; color: #e9f5ff; }
QLabel#muted { color: #93a9be; }
QLabel#error { color: #f1a3b3; }
QPushButton { background: #24364a; color: #dcebf7; padding: 10px 15px; border-radius: 7px; }
QPushButton:hover { background: #304c61; }
QPushButton#primary { background: #276a6d; color: #efffff; font-weight: 600; }
QPushButton#primary:hover { background: #328489; }
QLineEdit { background: #0d1622; color: #e2edf9; border: 1px solid #344b62; padding: 10px; border-radius: 7px; }
QLineEdit:focus { border-color: #68d6ca; }
QCheckBox { color: #dcebf7; spacing: 10px; padding: 5px 0; }
QCheckBox::indicator { width: 17px; height: 17px; background: #0c1724; border: 1px solid #5f819b; border-radius: 4px; }
QCheckBox::indicator:checked { background: #51b7ad; border-color: #8be6d7; }
QListWidget { background: #101926; border: 1px solid #2b4155; border-radius: 8px; padding: 8px; }
QListWidget::item { border-radius: 6px; padding: 5px; }
QListWidget::item:selected { background: #315768; }
'''


def image_icon(value):
    return QIcon(value) if Path(value).is_absolute() else QIcon.fromTheme(value)


def theme_names():return _theme_names(QIcon.themeName(),tuple(QIcon.themeSearchPaths()))


@lru_cache(maxsize=8)
def _theme_names(theme_name,search_paths):
    names = {'application-x-executable', 'applications-development', 'applications-system',
             'applications-utilities', 'folder', 'utilities-terminal', 'preferences-system'}
    for root in search_paths:
        for theme in dict.fromkeys([theme_name, 'Papirus', 'Papirus-Dark', 'breeze', 'hicolor']):
            for sub in ('scalable','64x64/apps', '48x48/apps', 'scalable/apps', 'apps/48', 'apps/64'):
                directory = Path(root) / theme / sub
                if directory.is_dir():
                    names.update(p.stem for p in directory.iterdir() if p.suffix.lower() in ('.svg', '.png', '.xpm'))
    return sorted(names, key=str.casefold)


class IconPicker(QDialog):
    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Choose shortcut icon')
        self.setStyleSheet(shortcuts.theme_runtime.stylesheet(DIALOG_STYLE,style=shortcuts.theme_runtime.launcher_design()))
        self.resize(710, 570)
        self.value = current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        title = QLabel('Give it a new look'); title.setObjectName('dialogTitle')
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search installed icons…')
        layout.addWidget(self.search)
        self.grid = QListWidget()
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setIconSize(QSize(40, 40))
        self.grid.setGridSize(QSize(120, 84))
        self.grid.setWordWrap(True)
        self.grid.itemDoubleClicked.connect(lambda _item: self.choose())
        layout.addWidget(self.grid, 1)
        self.count = QLabel(); self.count.setObjectName('muted'); layout.addWidget(self.count)
        bottom = QHBoxLayout()
        browse = QPushButton('Choose image file…'); browse.clicked.connect(self.browse)
        bottom.addWidget(browse); bottom.addStretch()
        cancel = QPushButton('Cancel'); cancel.clicked.connect(self.reject); bottom.addWidget(cancel)
        use = QPushButton('Use icon'); use.setObjectName('primary'); use.clicked.connect(self.choose)
        bottom.addWidget(use); layout.addLayout(bottom)
        self.search.textChanged.connect(self.populate)
        self.populate()

    def populate(self):
        query = self.search.text().strip().casefold()
        matches = [name for name in theme_names() if all(t in name.casefold() for t in query.split())]
        self.grid.clear()
        for name in matches[:180]:
            item = QListWidgetItem(QIcon.fromTheme(name), name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(name)
            self.grid.addItem(item)
        self.count.setText(f'{len(matches)} matching icons' + (' · Type to narrow the first 180' if len(matches) > 180 else ''))
        if self.grid.count():
            self.grid.setCurrentRow(0)

    def choose(self):
        item = self.grid.currentItem()
        if item:
            self.value = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def browse(self):
        filename = ImagePicker.choose(self, 'Choose shortcut icon', str(Path.home() / 'Pictures'),
            'Images (*.svg *.png *.webp *.jpg *.jpeg *.ico *.xpm)')
        if filename and not QIcon(filename).isNull():
            self.value = filename
            self.accept()


class ShortcutEditor(QDialog):
    def __init__(self, entry=None, parent=None, duplicate=False):
        super().__init__(parent)
        self.entry, self.duplicate = entry, duplicate
        self.setWindowTitle('New favorite shortcut' if duplicate or entry is None else 'Properties')
        self.setStyleSheet(shortcuts.theme_runtime.stylesheet(DIALOG_STYLE,style=shortcuts.theme_runtime.launcher_design()))
        self.resize(730, 670)
        self.fields = dict(entry.fields) if entry else {
            'name': '', 'command': '', 'icon': 'application-x-executable', 'directory': '',
            'description': '', 'terminal': False, 'keep_open': True, 'floating': False, 'administrator': False}
        if duplicate:
            self.fields['name'] += ' (copy)'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)
        heading = QHBoxLayout()
        self.preview = QLabel(); self.preview.setFixedSize(64, 64); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(self.preview)
        titles = QVBoxLayout()
        title = QLabel('Make this shortcut yours'); title.setObjectName('dialogTitle')
        titles.addWidget(title)
        subtitle = QLabel('Changes apply to this Hyprland menu.'); subtitle.setObjectName('muted')
        titles.addWidget(subtitle); heading.addLayout(titles, 1); layout.addLayout(heading)
        form = QFormLayout(); form.setVerticalSpacing(13)
        self.inputs = {}
        for key, label, placeholder in [('name', 'Name', 'Shortcut name'),
                ('command', 'Command', 'Program and arguments'),
                ('directory', 'Working folder', 'Use the default working folder'),
                ('icon', 'Icon', 'An installed icon name or image file'),
                ('description', 'Description', 'Optional description')]:
            field = QLineEdit(self.fields[key]); field.setPlaceholderText(placeholder)
            field.setClearButtonEnabled(True)
            field.setCursorPosition(0)
            self.inputs[key] = field
            if key in ('command', 'directory', 'icon'):
                row = QHBoxLayout(); row.addWidget(field, 1)
                select = QPushButton('Choose…' if key == 'icon' else 'Browse…')
                select.clicked.connect(lambda checked=False, k=key: self.browse(k))
                row.addWidget(select); form.addRow(label, row)
            else:
                form.addRow(label, field)
        layout.addLayout(form)
        hint = QLabel('Quote program paths or arguments that contain spaces. Existing %U and %F placeholders are supported.')
        hint.setObjectName('muted'); hint.setWordWrap(True); layout.addWidget(hint)
        self.terminal = QCheckBox('Always open this shortcut in a terminal')
        self.terminal.setChecked(self.fields['terminal']); layout.addWidget(self.terminal)
        self.keep_open = QCheckBox('Keep the terminal open after the command exits')
        self.keep_open.setChecked(self.fields['keep_open'])
        self.keep_open.setEnabled(self.terminal.isChecked())
        self.terminal.toggled.connect(self.keep_open.setEnabled); layout.addWidget(self.keep_open)
        self.floating=QCheckBox('Always start this shortcut floating')
        self.floating.setChecked(self.fields['floating'])
        self.floating.setToolTip('Open floating from Favorites, Apps, search, bar pins and launch hotkeys, just like Ctrl-click. Other shortcuts keep their own setting.')
        layout.addWidget(self.floating)
        self.administrator = QCheckBox('Run as administrator')
        self.administrator.setChecked(self.fields.get('administrator', False))
        self.administrator.setToolTip('Ask for authentication when needed and allow the app to use this display until it exits.')
        layout.addWidget(self.administrator)
        admin_hint = QLabel('Use the program itself in Command; authentication and display access are handled for you.')
        admin_hint.setObjectName('muted'); admin_hint.setWordWrap(True)
        layout.addWidget(admin_hint)
        self.error = QLabel(); self.error.setObjectName('error'); self.error.setWordWrap(True)
        layout.addWidget(self.error); layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName('primary')
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Save to Favorites' if duplicate or entry is None else 'Save shortcut')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.inputs['icon'].textChanged.connect(self.update_icon)
        self.update_icon()
        self.inputs['name'].setFocus()

    def update_icon(self):
        self.preview.setPixmap(image_icon(self.inputs['icon'].text()).pixmap(54, 54))

    def browse(self, field):
        if field == 'icon':
            picker = IconPicker(self.inputs['icon'].text(), self)
            if picker.exec() == QDialog.DialogCode.Accepted:
                self.inputs['icon'].setText(picker.value)
            return
        if field == 'directory':
            path = QFileDialog.getExistingDirectory(self, 'Choose working folder',
                self.inputs[field].text() or str(Path.home()), options=QFileDialog.Option.DontUseNativeDialog)
        else:
            path, _ = QFileDialog.getOpenFileName(self, 'Choose program or script', str(Path.home()),
                'All files (*)', options=QFileDialog.Option.DontUseNativeDialog)
            if path:
                path = '"' + path.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
        if path:
            self.inputs[field].setText(path)

    def accept(self):
        try:
            values = {key: field.text() for key, field in self.inputs.items()}
            values.update(terminal=self.terminal.isChecked(), keep_open=self.keep_open.isChecked(),
                          floating=self.floating.isChecked(), administrator=self.administrator.isChecked())
            self.fields = shortcuts.validate(values)
            icon = self.fields['icon']
            if icon and image_icon(icon).isNull():
                raise ValueError('Choose an icon that can be displayed, or leave the icon empty.')
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc))
            return
        super().accept()
