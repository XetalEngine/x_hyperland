"""Echo account controls shared by every KVM Settings page."""
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
                             QDialog, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox)
import portable
from packages import SITE


class AccountHeader(QWidget):
    login_requested=pyqtSignal()
    logout_requested=pyqtSignal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFixedWidth(224)
        layout=QVBoxLayout(self);layout.setContentsMargins(8,0,8,0);layout.setSpacing(2)
        title=QHBoxLayout();title.setSpacing(5)
        logo=QLabel();logo.setPixmap(QIcon(str(portable.ROOT/'echo.svg')).pixmap(16,16))
        title.addWidget(logo)
        self.status=QLabel();self.status.setTextFormat(Qt.TextFormat.PlainText)
        title.addWidget(self.status,1);layout.addLayout(title)
        actions=QHBoxLayout();actions.setSpacing(4)
        self.download=QPushButton('Download Echo')
        self.download.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(SITE+'/#download')))
        self.login=QPushButton('Login');self.login.clicked.connect(self.login_requested.emit)
        self.logout=QPushButton('Logout');self.logout.clicked.connect(self.logout_requested.emit)
        for button in (self.download,self.login,self.logout):
            button.setFlat(True)
            button.setStyleSheet('padding: 1px 5px; margin: 0; min-height: 18px; font-size: 11px;')
            actions.addWidget(button)
        actions.addStretch();layout.addLayout(actions)

    def refresh(self,account,*,busy=False):
        signed_in=bool(account.token)
        text='Logged in as '+account.user.get('username','Echo user') if signed_in else 'Echo · Not logged in'
        self.status.setText(self.status.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,187))
        self.status.setToolTip(text);self.status.setAccessibleName(text)
        self.login.setVisible(not signed_in);self.logout.setVisible(signed_in)
        self.login.setEnabled(not busy);self.logout.setEnabled(not busy)


class LoginDialog(QDialog):
    def __init__(self,credentials,can_remember,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Login to Echo')
        self.setMinimumWidth(440)
        form=QFormLayout(self)
        note=QLabel('Log in each time you open KVM Settings. A saved password only fills in this form.')
        note.setWordWrap(True);form.addRow(note)
        self.login=QLineEdit(credentials.get('login',''))
        self.password=QLineEdit(credentials.get('password',''));self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.totp=QLineEdit();self.totp.setPlaceholderText('If enabled on your account')
        self.remember=QCheckBox('Save password in the system password wallet')
        self.remember.setEnabled(can_remember);self.remember.setChecked(bool(credentials) and can_remember)
        if not can_remember:self.remember.setToolTip('Install secret-tool and unlock a system password wallet to save passwords.')
        form.addRow('Username or email',self.login);form.addRow('Password',self.password)
        form.addRow('Authentication code',self.totp);form.addRow(self.remember)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Login')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)

    def values(self):
        return (self.login.text().strip(),self.password.text(),self.totp.text().strip(),self.remember.isChecked())

    def clear_secrets(self):
        self.password.clear();self.totp.clear()
