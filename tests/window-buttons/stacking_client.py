"""Solid-color windows with actual pointer counters for stacking checks."""
import json
import sys
from PyQt6.QtCore import QSocketNotifier, Qt
from PyQt6.QtWidgets import QApplication, QWidget

app=QApplication(sys.argv)
app.setDesktopFileName('wobbly-test')
app.setQuitOnLastWindowClosed(False)
windows={}


class Window(QWidget):
    def __init__(self,name):
        super().__init__()
        self.clicks=0
        self.setWindowTitle(name)
        self.resize(620,400)
        self.setStyleSheet('background:'+('#205080' if name=='Buttons' else '#d08020')+';')

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.clicks+=1
        super().mousePressEvent(event)


def read(*_):
    line=sys.stdin.readline()
    if not line:app.quit();return
    request=json.loads(line);name=request.get('name','Buttons');op=request['op']
    if op=='add':
        windows[name]=Window(name);windows[name].show()
    elif op=='max':windows[name].showMaximized()
    elif op=='full':windows[name].showFullScreen()
    elif op=='restore':windows[name].showNormal()
    elif op=='close':windows[name].close()
    elif op=='counts':
        print(json.dumps({name:w.clicks for name,w in windows.items()}),flush=True);return
    print('ok',flush=True)


notifier=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read)
notifier.activated.connect(read)
app.exec()
