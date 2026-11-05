"""Message-box chimes and asynchronous logout music for Fusion Qt tools."""
import os
from pathlib import Path
import sys
from PyQt6.QtCore import QObject, QEvent, QProcess, QTimer
from PyQt6.QtWidgets import QMessageBox

PLAYER = Path(__file__).resolve().with_name('play.py')


def install(app):
    if app.property('xetalSoundBridge') or not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'): return
    app.setProperty('xetalSoundBridge', True)
    class Chimes(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
                kind = {QMessageBox.Icon.Critical:'error', QMessageBox.Icon.Warning:'warning',
                        QMessageBox.Icon.Information:'info', QMessageBox.Icon.Question:'question'}.get(watched.icon())
                if kind:
                    QProcess.startDetached(sys.executable, [str(PLAYER), kind])
            return False
    app.fusion_sound_bridge = Chimes(app)
    app.installEventFilter(app.fusion_sound_bridge)


def before_exit(parent, callback):
    """Keep the dialog responsive; only the caller's confirmed action follows."""
    process = QProcess(parent); timer = QTimer(process); timer.setSingleShot(True)
    process.setStandardOutputFile(QProcess.nullDevice()); process.setStandardErrorFile(QProcess.nullDevice())
    done = False
    def finish(*_):
        nonlocal done
        if done: return
        done = True; timer.stop()
        if process.state() != QProcess.ProcessState.NotRunning: process.kill()
        callback(); process.deleteLater()
    process.finished.connect(finish); process.errorOccurred.connect(finish)
    timer.timeout.connect(finish); timer.start(5500)
    process.start(sys.executable, [str(PLAYER), 'shutdown'])
    return process
