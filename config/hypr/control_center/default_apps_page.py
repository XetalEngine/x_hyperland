"""Settings entry point for the same app associations used by Control Panel."""
import json
from pathlib import Path
import subprocess
import sys

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QPushButton, QScrollArea, QDialog, QDialogButtonBox, QLineEdit,
    QListWidget, QListWidgetItem,
)

ROOT = Path(__file__).resolve().parents[1]


def request(action='snapshot', data=None):
    result = subprocess.run(
        [sys.executable, str(ROOT/'control_panel/default_apps.py'), action],
        input=json.dumps(data or {}), text=True, capture_output=True, timeout=30)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('Default apps could not be loaded. Please try Refresh.')
    if result.returncode or value.get('error'):
        raise RuntimeError(value.get('error', 'The app preference could not be saved.'))
    return value


def text(value, name=''):
    label = QLabel(value)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setObjectName(name)
    return label


def app_icon(name):
    return QIcon(name) if name.startswith('/') else QIcon.fromTheme(name, QIcon.fromTheme('application-x-executable'))


class DefaultAppsPage(QWidget):
    def __init__(self, async_run, launch):
        super().__init__()
        self.async_run, self.launch = async_run, launch
        self.busy = False
        self.data = {}
        self.undo_token = ''
        self.cards = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(text('Default apps', 'section'))
        titles.addWidget(text('Choose what opens your folders, files and links across the desktop.', 'muted'))
        heading.addLayout(titles, 1)
        self.refresh_button = QPushButton('Refresh')
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        layout.addLayout(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.grid = QGridLayout(body)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        advanced = QPushButton('File types & advanced defaults…')
        advanced.clicked.connect(lambda: self.launch([str(ROOT/'scripts/control-panel.sh'), '--section', 'default-apps']))
        footer.addWidget(advanced)
        footer.addStretch()
        self.undo_button = QPushButton('Undo last change')
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo)
        footer.addWidget(self.undo_button)
        layout.addLayout(footer)
        self.status = text('Screenshot and recording notifications use your File manager choice.', 'muted')
        layout.addWidget(self.status)

    def set_busy(self, value):
        self.busy = value
        self.refresh_button.setEnabled(not value)
        self.undo_button.setEnabled(not value and bool(self.undo_token))
        for card in self.cards:
            card.setEnabled(not value)

    def refresh(self):
        if self.busy:
            return
        self.set_busy(True)
        self.async_run(request, self.loaded, self.failed)

    def loaded(self, data):
        self.data = data
        while self.grid.count():
            self.grid.takeAt(0).widget().deleteLater()
        self.cards = []
        apps = {app['id']: app for app in data['apps']}
        for role in data['roles']:
            app = apps.get(role['default'], {})
            card = QFrame()
            card.setObjectName('modernCard')
            content = QVBoxLayout(card)
            content.setContentsMargins(16, 14, 16, 14)
            content.setSpacing(8)
            title = QHBoxLayout()
            icon = QLabel()
            icon.setPixmap(app_icon(role['icon']).pixmap(26, 26))
            title.addWidget(icon)
            title.addWidget(text(role['title'], 'section'), 1)
            content.addLayout(title)
            description = text(role['description'], 'muted')
            description.setMinimumHeight(32)
            content.addWidget(description)
            choice = QPushButton(app_icon(app.get('icon', role['icon'])), app.get('name', 'Choose an app')+'  ▾')
            choice.setIconSize(QSize(24, 24))
            choice.setMinimumHeight(40)
            choice.setAccessibleName(role['title']+': '+app.get('name', 'Choose an app'))
            choice.clicked.connect(lambda _, selected=role: self.choose(selected))
            content.addWidget(choice)
            self.cards.append(card)
        self.arrange()
        self.set_busy(False)

    def arrange(self):
        columns = 3 if self.width() >= 900 else 2
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index//columns, index % columns)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def failed(self, message):
        self.set_busy(False)
        self.status.setText(message)

    def choose(self, role):
        if self.busy:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Choose '+role['title'].lower())
        dialog.resize(550, 550)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(text(role['title'], 'section'))
        layout.addWidget(text(role['description']+'. This updates the defaults for your account.', 'muted'))
        search = QLineEdit()
        search.setPlaceholderText('Find an installed app…')
        search.setClearButtonEnabled(True)
        layout.addWidget(search)
        apps = QListWidget()
        apps.setIconSize(QSize(32, 32))
        apps.setSpacing(3)
        layout.addWidget(apps, 1)
        types = set(role['types'])
        for app in sorted(self.data['apps'], key=lambda item: (
                not bool(types.intersection(item.get('types', []))), item['name'].casefold())):
            entry = QListWidgetItem(app_icon(app['icon']), app['name'], apps)
            entry.setData(Qt.ItemDataRole.UserRole, app['id'])
            entry.setToolTip(app.get('description', ''))
            entry.setSizeHint(QSize(0, 46))
            if app['id'] == role['default']:
                apps.setCurrentItem(entry)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        apply = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply.setText('Use this app')
        apply.setObjectName('primary')
        apply.setEnabled(apps.currentItem() is not None)
        apps.currentItemChanged.connect(lambda current, _: apply.setEnabled(current is not None and not current.isHidden()))
        def filter_apps(value):
            for index in range(apps.count()):
                item = apps.item(index)
                item.setHidden(value.casefold() not in item.text().casefold())
            apply.setEnabled(apps.currentItem() is not None and not apps.currentItem().isHidden())
        search.textChanged.connect(filter_apps)
        apply.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        search.setFocus()
        if dialog.exec() == QDialog.DialogCode.Accepted and apps.currentItem():
            payload = {'role': role['id'], 'app': apps.currentItem().data(Qt.ItemDataRole.UserRole),
                       'revision': self.data['revision']}
            self.set_busy(True)
            self.async_run(lambda: request('apply', payload), self.applied, self.failed)
        dialog.deleteLater()

    def applied(self, result):
        self.undo_token = result.get('undo', '')
        self.status.setText(result.get('message', 'Default app saved.'))
        self.set_busy(False)
        self.refresh()

    def undo(self):
        if self.busy or not self.undo_token:
            return
        token = self.undo_token
        self.set_busy(True)
        self.async_run(lambda: request('undo', {'token': token}), self.applied, self.failed)
