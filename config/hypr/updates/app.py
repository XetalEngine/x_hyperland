#!/usr/bin/env python3
"""Theme-aware desktop update status and controls."""
from pathlib import Path
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QCheckBox, QPlainTextEdit, QProgressBar, QMessageBox)
import service
import update_engine as engine
sys.path.insert(0, str(service.ROOT/'theme'))
import runtime as theme_runtime
from window_chrome import close_button

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
QCheckBox {spacing:10px;}
QProgressBar {background:palette(base); border:0; border-radius:3px; max-height:5px;}
QProgressBar::chunk {background:palette(accent); border-radius:3px;}
'''


class Window(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Xetal / Desktop updates'); self.resize(630, 510)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 20, 24, 22); layout.setSpacing(14)
        header = QHBoxLayout(); label = QLabel('XETAL  /  DESKTOP UPDATES'); label.setObjectName('eyebrow')
        header.addWidget(label, 1); header.addWidget(close_button(self)); layout.addLayout(header)
        self.heading = QLabel('Your desktop, kept current.'); self.heading.setObjectName('brand'); layout.addWidget(self.heading)
        self.version = QLabel(); self.version.setObjectName('muted'); layout.addWidget(self.version)
        self.message = QLabel(); self.message.setWordWrap(True); self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setObjectName('message'); layout.addWidget(self.message)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setTextVisible(False); layout.addWidget(self.progress)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMinimumHeight(95)
        layout.addWidget(self.details, 1)
        self.automatic = QCheckBox('Automatically prepare and install updates')
        self.automatic.setChecked(service.preferences()['automatic']); self.automatic.toggled.connect(self.preference)
        layout.addWidget(self.automatic)
        note = QLabel('Updates activate at your next Hyprland login. Your apps stay open,\nand personal settings are preserved. Checks run every 15 minutes.')
        note.setObjectName('muted'); note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout(); self.check = QPushButton('Check now'); self.check.clicked.connect(lambda:self.action('check'))
        self.prepare = QPushButton('Prepare update'); self.prepare.setObjectName('primary'); self.prepare.clicked.connect(lambda:self.action('prepare'))
        self.rollback = QPushButton('Roll back…'); self.rollback.clicked.connect(self.restore)
        row.addWidget(self.check); row.addWidget(self.rollback); row.addStretch(); row.addWidget(self.prepare); layout.addLayout(row)
        QShortcut(QKeySequence('Escape'), self, activated=self.close)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1000); self.refresh()

    def preference(self, enabled):
        value = service.preferences(); value['automatic'] = enabled
        engine.write_json(service.STATE/'settings.json', value)

    def action(self, action):
        service.request(action)
        # A missing helper is recoverable without a new session. The daemon's
        # lock makes this harmless when the existing helper already owns it.
        service.STATE.mkdir(parents=True, exist_ok=True)
        with (service.STATE/'daemon.log').open('a') as log:
            subprocess.Popen([sys.executable, str(service.ROOT/'updates/service.py'), '--serve'],
                             stdout=log, stderr=log, start_new_session=True)
        self.message.setText('Checking GitHub…' if action == 'check' else 'Request queued…')

    def restore(self):
        if QMessageBox.question(self, 'Restore previous desktop?',
            'Queue the previous version for your next Hyprland login?\n\nAutomatic updates will pause. Later edits are checked before restoring anything.') == QMessageBox.StandardButton.Yes:
            self.action('rollback')

    def refresh(self):
        value = service.status(); phase = value.get('phase', 'current')
        current = value.get('current', '')
        if not current:
            try: current = engine.installed(service.ROOT)['revision']
            except Exception: current = 'unregistered'
        self.version.setText('Installed '+current[:8]+'   ·   GitHub / main'+('   ·   Latest '+value['latest'][:8] if value.get('latest') else ''))
        self.message.setText(value.get('message', 'Ready to check for desktop updates.'))
        busy = phase in ('preparing', 'checking'); self.progress.setVisible(busy); self.check.setEnabled(not busy)
        self.prepare.setEnabled(not busy and not (service.STATE/'pending.json').exists() and value.get('github', {}).get('relation') == 'ahead')
        self.rollback.setEnabled(not busy and (service.STATE/'last-backup.json').exists())
        self.automatic.blockSignals(True); self.automatic.setChecked(service.preferences()['automatic']); self.automatic.blockSignals(False)
        text = value.get('title', 'Updates are published from XetalEngine/x_hyperland on GitHub.')
        if phase in ('preparing', 'attention', 'ready') and (service.STATE/'update.log').is_file():
            with (service.STATE/'update.log').open('rb') as stream:
                stream.seek(max(0, stream.seek(0, 2)-24000)); text += '\n\n'+stream.read().decode(errors='replace')
        if text != self.details.toPlainText(): self.details.setPlainText(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 110 and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(event)


def main():
    app = QApplication(sys.argv); app.setApplicationName('Xetal Updates'); app.setDesktopFileName('xetal-updates')
    live_theme = theme_runtime.install(app, STYLE)
    window = Window(); window.show(); return app.exec()


if __name__ == '__main__': sys.exit(main())
