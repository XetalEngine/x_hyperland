"""Shared, theme-aware About dialog for Hyper Fusion's Python apps."""
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame,
    QHBoxLayout, QLabel, QLayout, QMenu, QPushButton, QToolButton, QVBoxLayout,
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
        self.setMinimumWidth(400)
        theme = Path(__file__).parent
        try:
            self.setStyleSheet((theme / 'about.qss').read_text())
        except OSError:
            pass
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content = self
        body = layout
        brand = QHBoxLayout()
        brand.addWidget(self._label('HYPER FUSION', 'aboutBrand'), 1)
        try:
            version = (theme.parent / 'VERSION').read_text().strip()
        except OSError:
            version = ''
        if version:
            brand.addWidget(self._label(version, 'aboutVersion'))
        body.addLayout(brand)
        logo = QLabel(content)
        logo.setObjectName('aboutEngineLogo')
        logo.setAccessibleName('Xetal Engine')
        pixmap = QPixmap(str(theme / 'assets/xetal-engine.png'))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(330, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText('XETAL ENGINE')
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(68)
        body.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(6)
        app_label = self._label(app_name, 'aboutAppName')
        app_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titles.addWidget(app_label)
        description_label = self._label(description, 'aboutDescription')
        description_label.setProperty('aboutMuted', True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titles.addWidget(description_label)
        body.addLayout(titles)

        identity = _identity()
        card = QFrame(content)
        card.setObjectName('aboutIdentity')
        details = QVBoxLayout(card)
        details.setContentsMargins(18, 16, 18, 16)
        details.setSpacing(8)
        caption = self._label('CREATED BY')
        caption.setProperty('aboutCaption', True)
        caption.setProperty('aboutMuted', True)
        details.addWidget(caption)
        details.addWidget(self._label(identity['author'], 'aboutAuthor'))
        details.addSpacing(4)
        contacts = QHBoxLayout()
        contacts.setSpacing(12)
        for service in ('Discord', 'Echo'):
            username = identity[service.lower()]
            contact = QFrame(card)
            contact.setProperty('aboutContact', True)
            row = QHBoxLayout(contact)
            row.setContentsMargins(14, 12, 14, 12)
            row.setSpacing(10)
            column = QVBoxLayout()
            column.setSpacing(4)
            row.addLayout(column, 1)
            service_label = self._label(service)
            service_label.setProperty('aboutMuted', True)
            column.addWidget(service_label)
            handle = self._label(username, 'about' + service)
            handle.setProperty('aboutHandle', True)
            column.addWidget(handle)
            copy = QPushButton('Copy', contact)
            copy.setObjectName('copy' + service + 'Username')
            copy.setAccessibleName('Copy ' + service + ' username')
            copy.setToolTip('Copy ' + service + ' username')
            copy.setAutoDefault(False)
            reset = QTimer(copy)
            reset.setSingleShot(True)
            reset.timeout.connect(lambda button=copy: button.setText('Copy'))
            copy.clicked.connect(lambda checked=False, button=copy, timer=reset, text=username:
                                 self._copy(button, timer, text))
            row.addWidget(copy)
            contacts.addWidget(contact, 1)
        details.addLayout(contacts)
        body.addWidget(card)
        if credits:
            credit_label = self._label(credits, 'aboutCredits')
            credit_label.setProperty('aboutMuted', True)
            body.addWidget(credit_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        close.setDefault(True)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self._fit_contents)
        self._fit_contents()
        close.setFocus()

    def _fit_contents(self):
        self.ensurePolished()
        available = self.screen().availableGeometry()
        layout = self.layout()
        width = max(layout.minimumSize().width(), min(580, available.width() - 40))
        height = max(layout.minimumSize().height(), layout.totalHeightForWidth(width))
        # Widen first on shorter displays so all text stays visible at its
        # normal font size. The layout's minimum protects against saved tiny
        # window sizes and compositor resize requests.
        if height > available.height() - 72:
            width = max(width, min(720, available.width() - 40))
            height = max(layout.minimumSize().height(), layout.totalHeightForWidth(width))
        self.setMinimumSize(width, height)
        self.resize(width, height)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_timer.start(0)

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
