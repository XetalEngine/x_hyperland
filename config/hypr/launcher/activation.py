"""Focus and raise the exact window requested from the bar, once."""
import json
import os
import re

from PyQt6.QtCore import QObject,QEvent,QProcess,QTimer
from PyQt6.QtWidgets import QApplication


class BarActivation(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.done=False;self.attempts=0;self.phase='find';self.selector=None
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
        self.phase='find'
        # A resident process can own several windows. Resolve this exact title
        # inside our own process, never another window sharing the app class.
        self.process.start('hyprctl',['-j','clients'])

    def finished(self,code=0,*_):
        if self.done:return
        if code:self.cancel();return
        reply=bytes(self.process.readAllStandardOutput()).decode(errors='replace').strip()
        if self.phase=='find':
            try:
                clients=json.loads(reply)
                if not isinstance(clients,list):raise ValueError('Invalid client list')
                matches=[c for c in clients if c.get('pid')==os.getpid() and c.get('mapped')
                         and c.get('title')==self.window.windowTitle()
                         and re.fullmatch(r'0x[0-9a-fA-F]+',c.get('address',''))]
            except (ValueError,AttributeError,TypeError):self.cancel();return
            if not matches:self.retry_map();return
            if len(matches)!=1:self.cancel();return
            self.selector='address:'+matches[0]['address'];self.phase='focus'
            self.process.start('hyprctl',['dispatch','focuswindow',self.selector])
        elif self.phase=='focus':
            if reply.lower()=='ok':
                # Focus alone permits rendering above a maximized window on
                # this compositor, but leaves the pointer input stack behind.
                # Use the same explicit raise as taskbar and switcher clicks.
                self.phase='raise'
                self.process.start('hyprctl',['dispatch','alterzorder','top,'+self.selector])
            elif reply.lower() in ('window not found','no such window found'):self.retry_map()
            else:self.cancel()
        else:self.cancel() # Minimize's native restore owns a pending raise.

    def retry_map(self):
        # Retry only the map race. Never keep stealing focus after a click.
        if self.attempts<8:self.retry.start(25)
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
