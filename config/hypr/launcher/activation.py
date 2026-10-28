"""Hand keyboard focus from the bar to this newly opened menu, once."""
import os

from PyQt6.QtCore import QObject,QEvent,QProcess,QTimer
from PyQt6.QtWidgets import QApplication


class BarActivation(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.done=False;self.attempts=0
        self.process=QProcess(self)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(lambda *_:self.cancel())
        self.retry=QTimer(self);self.retry.setSingleShot(True)
        self.retry.timeout.connect(self.request)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.cancel)

    def start(self):
        if self.done:return
        QApplication.instance().installEventFilter(self)
        self.deadline.start(700)
        self.retry.start(0)

    def request(self):
        if self.done:return
        if not self.window.isVisible() or self.window.dismissal_protected():
            self.cancel();return
        self.attempts+=1
        # Wayland widget focus does not activate a toplevel opened by a layer
        # surface. Target only this process, never a class shared by other apps.
        self.process.start('hyprctl',['dispatch','focuswindow',f'pid:{os.getpid()}'])

    def finished(self,*_):
        if self.done:return
        reply=bytes(self.process.readAllStandardOutput()).decode(errors='replace').strip().lower()
        # The first frame can still be in flight. Retry only the map race;
        # unavailable IPC and all other errors leave ordinary focus alone.
        if reply in ('window not found','no such window found') and self.attempts<8:
            self.retry.start(25)
        else:self.cancel()

    def cancel(self):
        if self.done:return
        self.done=True;self.retry.stop();self.deadline.stop()
        QApplication.instance().removeEventFilter(self)
        if self.process.state()!=QProcess.ProcessState.NotRunning:self.process.kill()

    def eventFilter(self,watched,event):
        if (event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.KeyPress)
                or watched is self.window and event.type() in (QEvent.Type.Hide,QEvent.Type.Close)):
            self.cancel()
        return False
