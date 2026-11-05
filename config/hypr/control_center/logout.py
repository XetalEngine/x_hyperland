#!/usr/bin/env python3
"""Confirm logout without changing the session until Log out is selected."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'theme'))
import runtime
from window_chrome import close_button
from sounds.qt import before_exit

STYLE = '''
QWidget {background:#171c24; color:#e3ecf8; font-family:"Noto Sans"; font-size:13px;}
QLabel {background:transparent;}
QLabel#eyebrow {color:#69d8ce; font-size:10px; letter-spacing:3px;}
QLabel#title {font-size:26px; font-weight:700;}
QLabel#message {color:#b1c0d1; font-size:14px;}
QLabel#error {color:#f4adba;}
QPushButton {background:#253342; border:1px solid #3b5063; border-radius:7px; padding:10px 22px;}
QPushButton:hover {background:#324a59; border-color:#6ccfc5;}
QPushButton:focus {border:2px solid #73d8cf; padding:9px 21px;}
QPushButton#logout {background:#4b2935; color:#ffe0e6; border-color:#8d4f61;}
QPushButton#logout:hover {background:#683747; border-color:#dc8c9f;}
QPushButton#logout:focus {border:2px solid #f4adba;}
'''


class LogoutDialog(QDialog):
    def __init__(self, runner=None, exit_sound=None):
        super().__init__()
        self.runner = runner or subprocess.run
        self.exit_sound = exit_sound or before_exit
        self.submitted = False
        self.setWindowTitle('Confirm logout')
        self.setMinimumWidth(440)
        self.resize(470, 270)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 20, 26, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        brand = QLabel('XETAL  /  SESSION')
        brand.setObjectName('eyebrow')
        header.addWidget(brand, 1)
        self.close_control = close_button(self, callback=self.reject)
        header.addWidget(self.close_control)
        layout.addLayout(header)
        title = QLabel('Are you sure?')
        title.setObjectName('title')
        layout.addWidget(title)
        message = QLabel('Log out of your desktop?\nYour open applications will close.')
        message.setObjectName('message')
        message.setWordWrap(True)
        layout.addWidget(message)
        self.error = QLabel()
        self.error.setObjectName('error')
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        layout.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel = QPushButton('Cancel')
        self.cancel.setDefault(True)
        self.cancel.clicked.connect(self.reject)
        actions.addWidget(self.cancel)
        self.logout = QPushButton('Log out')
        self.logout.setObjectName('logout')
        self.logout.setAutoDefault(False)
        self.logout.clicked.connect(self.confirm_logout)
        actions.addWidget(self.logout)
        layout.addLayout(actions)
        self.cancel.setFocus()

    def present(self):
        self.show()
        self.cancel.setFocus()
        self.raise_()
        self.activateWindow()

    def confirm_logout(self):
        if self.submitted:
            return
        self.submitted = True
        self.logout.setEnabled(False)
        self.cancel.setEnabled(False)
        self.close_control.setEnabled(False)
        self.exit_sound(self, self.finish_logout)

    def reject(self):
        if not self.submitted: super().reject()

    def finish_logout(self):
        try:
            result = self.runner(['hyprctl', 'dispatch', 'exit'], capture_output=True,
                                 text=True, timeout=4)
            if result.returncode or result.stdout.strip() != 'ok':
                raise RuntimeError((result.stderr or result.stdout or 'No response from Hyprland.').strip())
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            self.error.setText('Could not log out: ' + str(exc)[:500])
            self.error.show()
            self.submitted = False
            self.logout.setEnabled(True)
            self.cancel.setEnabled(True)
            self.close_control.setEnabled(True)
            self.cancel.setFocus()
            return
        self.accept()


def focus_existing(address):
    connection = QLocalSocket()
    connection.connectToServer(address)
    if not connection.waitForConnected(100):
        return False
    connection.write(b'show')
    connection.waitForBytesWritten(300)
    connection.disconnectFromServer()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', help='Render the dialog to PNG without logging out')
    args = parser.parse_args()
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    directory = os.environ.get('XDG_RUNTIME_DIR')
    if not args.preview and (not signature or not directory):
        print('Open this dialog from your Hyprland session.', file=sys.stderr)
        return 1
    app = QApplication(sys.argv[:1])
    app.setApplicationName('xetal-logout')
    app.setDesktopFileName('xetal-logout')
    runtime.install(app, STYLE)
    window = LogoutDialog()
    if args.preview:
        window.logout.setEnabled(False)
        window.present()
        QTimer.singleShot(150, lambda: (window.grab().save(args.preview), app.quit()))
        return app.exec()
    instance = Path(directory) / 'hypr' / signature
    address = str(instance / 'logout-confirmation.sock')
    with (instance / 'logout-confirmation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            for _ in range(10):
                if focus_existing(address):
                    return 0
                time.sleep(.05)
            return 1
        QLocalServer.removeServer(address)
        server = QLocalServer()
        if not server.listen(address):
            raise RuntimeError(server.errorString())
        def incoming():
            connection = server.nextPendingConnection()
            window.present()
            subprocess.Popen(['hyprctl', 'dispatch', 'focuswindow', 'class:^(xetal-logout)$'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            connection.disconnected.connect(connection.deleteLater)
            connection.disconnectFromServer()
        server.newConnection.connect(incoming)
        lifetime = QLocalSocket(app)
        lifetime.readyRead.connect(lambda: lifetime.readAll())
        lifetime.disconnected.connect(app.quit)
        lifetime.errorOccurred.connect(app.quit)
        lifetime.connectToServer(str(instance / '.socket2.sock'))
        if not lifetime.waitForConnected(1000):
            server.close()
            return 1
        window.present()
        try:
            return app.exec()
        finally:
            server.close()
            lifetime.abort()


if __name__ == '__main__':
    raise SystemExit(main())
