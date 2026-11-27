"""Shared application appearance and navigation preferences, kept in private state."""
import copy
import json
import os
from pathlib import Path
import tempfile

from PyQt6.QtCore import Qt, QSize, QSignalBlocker
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget)


def read_preferences(path, default_hidden=()):
    # Existing installations keep their headers. Setup explicitly seeds the
    # new fresh-install choices; factory reset supplies those same choices.
    defaults = dict(version=1, show_window_controls=True, hidden_pages=list(default_hidden))
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return defaults
    if not isinstance(value, dict):
        return defaults
    result = dict(value)
    result['show_window_controls'] = value.get('show_window_controls', True)
    if type(result['show_window_controls']) is not bool:
        result['show_window_controls'] = True
    hidden = value.get('hidden_pages', list(default_hidden))
    result['hidden_pages'] = sorted({name for name in hidden if isinstance(name, str)}) if isinstance(hidden, list) else list(default_hidden)
    return result


def write_preferences(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(values, stream, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class InterfaceSettingsDialog(QDialog):
    """entries are (stable page id, caption, icon, description)."""
    def __init__(self, title, path, entries, apply, parent=None, default_hidden=()):
        super().__init__(parent)
        self.setObjectName('interfaceSettingsDialog')
        self.setWindowTitle(title + ' · Settings')
        self.setMinimumSize(680, 480)
        available = self.screen().availableGeometry()
        self.resize(min(960, available.width() - 40), min(700, available.height() - 60))
        self.path, self.entries, self.apply = Path(path), list(entries), apply
        self.default_hidden = tuple(default_hidden)
        self.saved = read_preferences(self.path, self.default_hidden)
        root = QVBoxLayout(self); root.setContentsMargins(22, 20, 22, 16); root.setSpacing(16)
        heading = QLabel(title + ' · Settings'); heading.setObjectName('brand'); root.addWidget(heading)
        body = QHBoxLayout(); body.setSpacing(20)
        self.navigation = QListWidget(); self.navigation.setObjectName('interfaceCategories')
        self.navigation.setFixedWidth(160)
        for label in ('Appearance', 'Workspace'):
            item = QListWidgetItem(label, self.navigation); item.setSizeHint(QSize(140, 42))
        body.addWidget(self.navigation)
        self.pages = QStackedWidget(); body.addWidget(self.pages, 1); root.addLayout(body, 1)
        appearance = QWidget(); form = QVBoxLayout(appearance); form.setSpacing(14)
        self.buttons = QCheckBox('Show window buttons (minimize, maximize/restore, close)')
        self.buttons.setObjectName('showWindowControls'); form.addWidget(self.buttons)
        for text in ('The header makes room automatically. Settings stays available when the buttons are hidden.',
                     "In KDE mode, use the window's gear menu to add a title bar above the app. Hold Super to reach the gear when the title bar and overlay controls are off."):
            hint = QLabel(text); hint.setWordWrap(True); hint.setObjectName('muted'); form.addWidget(hint)
        form.addStretch(); self.pages.addWidget(appearance)
        workspace = QWidget(); layout = QVBoxLayout(workspace); layout.setSpacing(12)
        hint = QLabel('Select pages, then use the arrows to move them between Shown and Hidden. The header Settings button is always available.')
        hint.setWordWrap(True); layout.addWidget(hint)
        actions = QHBoxLayout(); self.count = QLabel(); actions.addWidget(self.count, 1)
        show_all = QPushButton('Show all'); show_all.setObjectName('showAllPages'); actions.addWidget(show_all); layout.addLayout(actions)
        lists = QHBoxLayout()
        def pane(title, name):
            column = QVBoxLayout(); caption = QLabel(title); column.addWidget(caption)
            widget = QListWidget(); widget.setObjectName(name); widget.setAccessibleName(title)
            widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            widget.setTextElideMode(Qt.TextElideMode.ElideRight); widget.setSortingEnabled(True)
            widget.setIconSize(QSize(22, 22)); widget.setSpacing(3); widget.setMinimumWidth(0)
            column.addWidget(widget, 1); lists.addLayout(column, 1)
            return caption, widget
        self.shown_count, self.shown = pane('Shown', 'shownPages')
        arrows = QVBoxLayout(); arrows.addStretch()
        self.hide_button = QPushButton('→'); self.show_button = QPushButton('←')
        for control, name, hint in ((self.hide_button, 'hidePages', 'Hide selected pages'), (self.show_button, 'showPages', 'Show selected pages')):
            control.setObjectName(name); control.setFixedSize(40, 36); control.setAutoDefault(False)
            control.setToolTip(hint); control.setAccessibleName(hint); arrows.addWidget(control)
        arrows.addStretch(); lists.addLayout(arrows)
        self.hidden_count, self.hidden = pane('Hidden', 'hiddenPages'); layout.addLayout(lists, 1)
        self.pages.addWidget(workspace)
        footer = QHBoxLayout(); reset = QPushButton('Reset page'); reset.setObjectName('resetInterfacePage')
        footer.addWidget(reset); self.status = QLabel('Changes save automatically.'); self.status.setWordWrap(True); footer.addWidget(self.status, 1)
        done = QPushButton('Done'); done.clicked.connect(self.accept); footer.addWidget(done); root.addLayout(footer)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex); self.navigation.setCurrentRow(0)
        self.buttons.toggled.connect(lambda checked: self.change(show_window_controls=checked))
        self.shown.itemSelectionChanged.connect(lambda: self.hide_button.setEnabled(bool(self.shown.selectedItems())))
        self.hidden.itemSelectionChanged.connect(lambda: self.show_button.setEnabled(bool(self.hidden.selectedItems())))
        self.hide_button.clicked.connect(lambda: self.move(False)); self.show_button.clicked.connect(lambda: self.move(True))
        show_all.clicked.connect(self.show_all); reset.clicked.connect(self.reset_page)
        self.load_widgets()

    def load_widgets(self):
        with QSignalBlocker(self.buttons): self.buttons.setChecked(self.saved['show_window_controls'])
        self.shown.clear(); self.hidden.clear()
        hidden = set(self.saved['hidden_pages'])
        for key, title, icon, description in self.entries:
            item = QListWidgetItem(icon, title, self.hidden if key in hidden else self.shown)
            item.setData(Qt.ItemDataRole.UserRole, key); item.setToolTip(description or title)
            item.setSizeHint(QSize(0, 36))
        self.shown_count.setText(f'Shown · {self.shown.count()}'); self.hidden_count.setText(f'Hidden · {self.hidden.count()}')
        self.count.setText(f'{self.shown.count()} of {len(self.entries)} pages shown')
        self.hide_button.setEnabled(False); self.show_button.setEnabled(False)

    def change(self, **changes):
        # Re-read before saving so independent/unknown preferences survive.
        updated = read_preferences(self.path, self.default_hidden); updated.update(changes)
        try:
            write_preferences(self.path, updated)
        except (OSError, ValueError) as error:
            self.status.setText('Could not save: ' + str(error)); self.load_widgets(); return
        self.saved = updated; self.apply(copy.deepcopy(updated)); self.load_widgets()
        self.status.setText('Changes saved.')

    def move(self, show):
        source = self.hidden if show else self.shown
        chosen = {item.data(Qt.ItemDataRole.UserRole) for item in source.selectedItems()}
        hidden = set(self.saved['hidden_pages'])
        self.change(hidden_pages=sorted(hidden - chosen if show else hidden | chosen))

    def show_all(self):
        self.change(hidden_pages=sorted(set(self.saved['hidden_pages']) - {key for key, *_ in self.entries}))

    def reset_page(self):
        if self.pages.currentIndex() == 0:
            self.change(show_window_controls=False)
        else:
            self.change(hidden_pages=list(self.default_hidden))
