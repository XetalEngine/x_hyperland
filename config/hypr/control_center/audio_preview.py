"""A short, explicitly requested output test; never changes device settings."""
from pathlib import Path
import sys

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QPushButton
import audio_backend as backend

ROOT = Path(__file__).resolve().parents[1]


class OutputTest(QPushButton):
    def __init__(self, report):
        super().__init__('▶ Test')
        self.report = report
        self.device = None
        self.player = None
        self.setEnabled(False)
        self.setAccessibleName('Test output sound')
        self.setToolTip("Play the current theme's success sound on this output. Output volume and mute are kept.")
        self.clicked.connect(self.toggle)

    def set_device(self, device):
        previous = backend.identity(self.device) if self.device else None
        current = backend.identity(device) if device else None
        if current != previous: self.stop()
        self.device = device
        self.setEnabled(device is not None)

    def toggle(self):
        if self.player:
            self.stop()
            return
        if not self.device: return
        process = QProcess(self)
        self.player = process
        process.setStandardOutputFile(QProcess.nullDevice())
        process.finished.connect(lambda code, _: self.finished(process, code))
        process.errorOccurred.connect(lambda _: self.finished(process, 1))
        self.setText('■ Stop')
        # Preview bypasses disabled event sounds/DND without unmuting a device.
        # A modest clip gain makes Test useful even with system sounds disabled.
        process.start(sys.executable, [str(ROOT / 'sounds/play.py'), 'success', '--preview',
                      '--pack', 'follow', '--volume', '35', '--sink', self.device['name']])

    def finished(self, process, code):
        if self.player is not process: return
        self.player = None
        self.setText('▶ Test')
        if code:
            message = bytes(process.readAllStandardError()).decode(errors='replace').strip()
            self.report(message or 'Could not play the test sound. Check the output device.')
        process.deleteLater()

    def stop(self):
        process, self.player = self.player, None
        self.setText('▶ Test')
        if process:
            process.terminate()
            if not process.waitForFinished(350):
                process.kill()
                process.waitForFinished(150)
            process.deleteLater()

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)
