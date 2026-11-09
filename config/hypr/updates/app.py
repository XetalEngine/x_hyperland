#!/usr/bin/env python3
"""Theme-aware desktop update status and controls."""
from pathlib import Path
import subprocess
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QProcess
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QPlainTextEdit, QProgressBar, QMessageBox)
import service
import update_engine as engine
import release_version
sys.path.insert(0, str(service.ROOT/'theme'))
import runtime as theme_runtime
from window_chrome import window_controls

STYLE = '''
QWidget {background:palette(window); color:palette(text); font-size:13px;}
QLabel#brand {font-size:25px; font-weight:700;}
QLabel#eyebrow {color:palette(accent); font-size:11px; font-weight:600;}
QLabel#message {background:palette(base); padding:16px; border-radius:12px; font-size:15px;}
QLabel#muted {color:palette(placeholder-text);}
QPushButton {background:palette(button); border:1px solid palette(midlight); padding:9px 14px; border-radius:8px;}
QPushButton:hover {border-color:palette(accent);}
QPushButton:disabled {color:palette(placeholder-text);}
QPushButton#primary {background:palette(highlight); color:palette(highlighted-text); font-weight:600;}
QPlainTextEdit {background:palette(base); border:1px solid palette(midlight); border-radius:8px; padding:9px; font-size:12px;}
QProgressBar {background:palette(base); border:0; border-radius:3px; max-height:5px;}
QProgressBar::chunk {background:palette(accent); border-radius:3px;}
'''


class Window(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Xetal / Desktop updates'); self.resize(630, 510)
        self.queued_action = None; self.restart_process = None; self.restarting = False
        self.check_requested_at = float('inf'); self.check_on_idle = False
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 20, 24, 22); layout.setSpacing(14)
        header = QHBoxLayout(); label = QLabel('XETAL  /  DESKTOP UPDATES'); label.setObjectName('eyebrow')
        header.addWidget(label, 1); header.addWidget(window_controls(self)); layout.addLayout(header)
        self.heading = QLabel('Your desktop, kept current.'); self.heading.setObjectName('brand'); layout.addWidget(self.heading)
        self.version = QLabel(); self.version.setObjectName('muted'); self.version.setWordWrap(True)
        self.version.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(self.version)
        self.message = QLabel(); self.message.setWordWrap(True); self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setObjectName('message'); layout.addWidget(self.message)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setTextVisible(False); layout.addWidget(self.progress)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMinimumHeight(95)
        layout.addWidget(self.details, 1)
        note = QLabel('Opening this window checks for the latest version. Downloads start only when you choose Update!\nYour personal settings are kept. Background checks run every 15 minutes.')
        note.setObjectName('muted'); note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout(); self.check = QPushButton('Check now'); self.check.clicked.connect(lambda:self.action('check'))
        self.prepare = QPushButton('Update!'); self.prepare.setObjectName('primary')
        self.prepare.clicked.connect(self.primary_action)
        self.rollback = QPushButton('Roll back…'); self.rollback.clicked.connect(self.restore)
        row.addWidget(self.check); row.addWidget(self.rollback); row.addStretch(); row.addWidget(self.prepare); layout.addLayout(row)
        QShortcut(QKeySequence('Escape'), self, activated=self.close)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1000); self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if not event.spontaneous():
            self.check_requested_at = time.time(); self.check_on_idle = True
            self.refresh()

    def action(self, action):
        value = service.status()
        if action == 'check': self.check_requested_at = time.time()
        service.request(action)
        # A missing helper is recoverable without a new session. The daemon's
        # lock makes this harmless when the existing helper already owns it.
        service.STATE.mkdir(parents=True, exist_ok=True)
        with (service.STATE/'daemon.log').open('a') as log:
            subprocess.Popen([sys.executable, str(service.ROOT/'updates/service.py'), '--serve'],
                             stdout=log, stderr=log, start_new_session=True)
        self.queued_action = action
        self.queued_status = (value.get('phase', 'current'), value.get('checked'))
        self.queued_at = time.monotonic()
        self.refresh()

    def primary_action(self):
        value = service.status(); pending = engine.json_file(service.STATE/'pending.json')
        if not service.checked_since(value, self.check_requested_at):
            self.action('check'); return
        if service.restart_ready(value, pending):
            self.restart()
        elif value.get('phase') == 'runtime-required':
            self.action('setup')
        elif value.get('phase') in ('available', 'attention', 'ready') and value.get('github', {}).get('relation') == 'ahead':
            self.action('prepare')

    def restart(self):
        if self.restarting: return
        if QMessageBox.question(self, 'Restart to finish updating?',
            'Save your work first. Restart this computer now to finish the update?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        try:
            service.prepare_restart()
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, 'Update not ready', str(error)); self.refresh(); return
        self.restarting = True
        self.restart_process = QProcess(self)
        self.restart_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.restart_process.finished.connect(self.restart_finished)
        self.restart_process.errorOccurred.connect(self.restart_failed)
        self.refresh()
        # Keep normal authorization and shutdown inhibitors; never force reboot.
        self.restart_process.start('systemctl', ['reboot'])

    def restart_finished(self, code, _status):
        if code: self.restart_failed()

    def restart_failed(self, _error=None):
        process = self.restart_process
        if process is None: return
        message = bytes(process.readAllStandardOutput()).decode(errors='replace').strip() or process.errorString()
        self.restart_process = None; self.restarting = False
        process.deleteLater(); self.refresh()
        QMessageBox.warning(self, 'Could not restart', message+'\n\nYour update is still ready. You can try Restart again.')

    def restore(self):
        if QMessageBox.question(self, 'Restore previous desktop?',
            'Queue the previous version for your next Hyprland login?\n\nLater edits are checked before restoring anything.') == QMessageBox.StandardButton.Yes:
            self.action('rollback')

    def refresh(self):
        value = service.status(); phase = value.get('phase', 'current')
        if self.check_on_idle and phase != 'preparing' and not self.restarting:
            self.check_on_idle = False; self.action('check'); return
        if self.queued_action and ((phase, value.get('checked')) != self.queued_status
                                   or time.monotonic()-self.queued_at > 10):
            self.queued_action = None
        current = value.get('current', '')
        current_version = value.get('current_version', '')
        if not current:
            try:
                installed = engine.installed(service.ROOT)
                current = installed['revision']; current_version = installed.get('release_version','')
            except Exception: current = 'unregistered'
        fresh = service.checked_since(value, self.check_requested_at)
        self.version.setText('Installed '+release_version.label(current_version, current)+'   ·   GitHub / main'+
                             ('   ·   '+('Latest ' if fresh else 'Last seen ')+release_version.label(value.get('latest_version'),value['latest']) if value.get('latest') else ''))
        self.version.setToolTip('Installed commit: '+current+('\nLatest commit: '+value['latest'] if value.get('latest') else ''))
        self.message.setText(value.get('message', 'Ready to check for desktop updates.'))
        pending = engine.json_file(service.STATE/'pending.json', {})
        ready = service.restart_ready(value, pending)
        updating = phase == 'preparing' or (self.queued_action in ('prepare', 'setup') and phase != 'checking')
        busy = phase in ('preparing', 'checking') or bool(self.queued_action) or self.restarting
        current = (phase == 'current' and not ready and bool(value.get('latest'))
                   and value.get('current') == value.get('latest'))
        self.progress.setVisible(busy); self.check.setEnabled(not busy)
        self.prepare.setText('Restarting…' if self.restarting else 'Updating…' if updating else 'Restart' if ready else
                             'Update!')
        self.prepare.setToolTip('Restart this computer to finish updating.' if ready else
                               'Open Setup to install the required compositor and desktop.' if phase == 'runtime-required' else
                               'The latest desktop update is already installed.' if current else
                               'Download, build and check the latest desktop update.')
        actionable = ready or phase == 'runtime-required' or (
            phase in ('available', 'attention', 'ready') and pending.get('revision') != value.get('latest')
            and value.get('github', {}).get('relation') == 'ahead')
        self.prepare.setVisible(updating or self.restarting or (fresh and not busy and actionable))
        self.prepare.setEnabled(fresh and not busy and actionable)
        if ready and fresh and phase != 'rollback': self.message.setText(service.READY_MESSAGE)
        if self.queued_action: self.message.setText('Checking GitHub…' if self.queued_action == 'check' else 'Updating…' if updating else 'Request queued…')
        if (not fresh and not busy and not value.get('retry_at')
                and value.get('check_started', 0) < self.check_requested_at):
            self.message.setText('An update notice is saved. Choose Check now to confirm the latest version.'
                                 if value.get('github', {}).get('relation') == 'ahead' else
                                 'Check now to confirm the latest version before updating.')
        if self.restarting: self.message.setText('Restarting…')
        self.rollback.setEnabled(not busy and (service.STATE/'last-backup.json').exists())
        text = value.get('title', 'Updates are published from XetalEngine/x_hyperland on GitHub.')
        if (phase in ('preparing', 'attention', 'ready', 'runtime-required') or ready) and (service.STATE/'update.log').is_file():
            with (service.STATE/'update.log').open('rb') as stream:
                stream.seek(max(0, stream.seek(0, 2)-24000)); text += '\n\n'+stream.read().decode(errors='replace')
        if text != self.details.toPlainText():
            bar = self.details.verticalScrollBar()
            position = bar.value(); follow = position >= bar.maximum()-2
            self.details.setPlainText(text)
            bar.setValue(bar.maximum() if follow else position)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 110 and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(event)


def main():
    app = QApplication(sys.argv); app.setApplicationName('Xetal Updates'); app.setDesktopFileName('xetal-updates')
    live_theme = theme_runtime.install(app, STYLE)
    window = Window(); window.show(); return app.exec()


if __name__ == '__main__': sys.exit(main())
