"""Shared, theme-aware About dialog for Hyper Fusion's Python apps."""
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMenu, QPushButton, QStyle, QToolButton, QVBoxLayout,
)


def _identity():
    defaults = {'author': 'Xetal — Thiago Costa', 'discord': 'xetal', 'echo': 'xetal'}
    try:
        data = json.loads(Path(__file__).with_name('about.json').read_text())
    except (OSError, ValueError):
        return defaults
    if isinstance(data, dict):
        for key in defaults:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                defaults[key] = value.strip()
    return defaults


class AboutDialog(QDialog):
    def __init__(self, parent, app_name, description, credits=''):
        super().__init__(parent)
        self.setObjectName('fusionAboutDialog')
        self.setWindowTitle('About ' + app_name)
        self.setWindowIcon(parent.windowIcon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(440)
        self.setStyleSheet('''
            QDialog#fusionAboutDialog { background: palette(window); color: palette(window-text); }
            QDialog#fusionAboutDialog QLabel { background: transparent; color: palette(window-text); border: none; padding: 0; }
            QLabel#aboutAppName { font-size: 23px; font-weight: 700; }
            QLabel#aboutBrand { color: palette(highlight); font-weight: 700; letter-spacing: 2px; }
            QLabel#aboutAuthor { font-size: 17px; font-weight: 600; }
            QFrame#aboutIdentity { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
            QDialog#fusionAboutDialog QPushButton { min-height: 22px; padding: 5px 14px; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        header = QHBoxLayout()
        header.setSpacing(16)
        app_icon = parent.windowIcon()
        if app_icon.isNull():
            app_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        icon = QLabel(self)
        icon.setFixedSize(48, 48)
        icon.setPixmap(app_icon.pixmap(48, 48))
        header.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(self._label('HYPER FUSION', 'aboutBrand'))
        titles.addWidget(self._label(app_name, 'aboutAppName'))
        header.addLayout(titles, 1)
        layout.addLayout(header)
        layout.addWidget(self._label(description))

        identity = _identity()
        card = QFrame(self)
        card.setObjectName('aboutIdentity')
        details = QVBoxLayout(card)
        details.setContentsMargins(18, 16, 18, 16)
        details.setSpacing(10)
        details.addWidget(self._label('Author'))
        details.addWidget(self._label(identity['author'], 'aboutAuthor'))
        details.addSpacing(8)
        contacts = QGridLayout()
        contacts.setHorizontalSpacing(18)
        contacts.setVerticalSpacing(10)
        contacts.setColumnStretch(1, 1)
        for row, service in enumerate(('Discord', 'Echo')):
            username = identity[service.lower()]
            contacts.addWidget(self._label(service), row, 0)
            contacts.addWidget(self._label(username, 'about' + service), row, 1)
            copy = QPushButton('Copy', card)
            copy.setObjectName('copy' + service + 'Username')
            copy.setAccessibleName('Copy ' + service + ' username')
            copy.setToolTip('Copy ' + service + ' username')
            copy.setAutoDefault(False)
            copy.setMinimumWidth(86)
            reset = QTimer(copy)
            reset.setSingleShot(True)
            reset.timeout.connect(lambda button=copy: button.setText('Copy'))
            copy.clicked.connect(lambda checked=False, button=copy, timer=reset, text=username:
                                 self._copy(button, timer, text))
            contacts.addWidget(copy, row, 2)
        details.addLayout(contacts)
        layout.addWidget(card)
        if credits:
            layout.addWidget(self._label(credits, 'aboutCredits'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        close.setDefault(True)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(480, self.sizeHint().height())
        close.setFocus()

    def _label(self, text, name=''):
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                      Qt.TextInteractionFlag.TextSelectableByKeyboard)
        return label

    @staticmethod
    def _copy(button, timer, username):
        QApplication.clipboard().setText(username)
        button.setText('Copied')
        timer.start(1600)


def show_about(parent, app_name, description, credits=''):
    dialog = parent.findChild(AboutDialog, 'fusionAboutDialog')
    if dialog is not None:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    else:
        dialog = AboutDialog(parent, app_name, description, credits)
        dialog.open()
    return dialog


def about_menu(parent, app_name, description, credits=''):
    button = QToolButton(parent)
    button.setObjectName('applicationAboutMenu')
    button.setText('⋯')
    button.setFixedSize(34, 32)
    button.setAccessibleName(app_name + ' menu')
    button.setToolTip(app_name + ' menu')
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(button)
    action = menu.addAction('About ' + app_name + '…')
    action.setObjectName('aboutApplicationAction')
    action.triggered.connect(lambda checked=False: show_about(parent, app_name, description, credits))
    button.setMenu(menu)
    return button
