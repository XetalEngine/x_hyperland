"""Contrasting toolbar/content and bright native marks for readback regressions."""
import json
import sys
from PyQt6.QtCore import QSocketNotifier
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication,QWidget

app=QApplication(sys.argv);app.setDesktopFileName('wobbly-test');app.setQuitOnLastWindowClosed(False)
windows={}
class Window(QWidget):
    color='#334a5a'
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#195b68'))
        p.fillRect(0,0,self.width(),100,QColor(self.color))
        p.fillRect(0,24,self.width(),3,QColor('white'))
        p.fillRect(0,self.height()-100,self.width(),100,QColor('#cbca40'))

def read(*_):
    line=sys.stdin.readline()
    if not line:app.quit();return
    c=json.loads(line);name=c.get('name','Buttons');op=c['op']
    if op=='add':
        w=Window();w.setWindowTitle(name);w.resize(550,650);windows[name]=w;w.show()
    elif op=='color':windows[name].color=c['color'];windows[name].update()
    elif op=='close':windows[name].close()
    elif op=='quit':app.quit()
    print('ok',flush=True)
notifier=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read);notifier.activated.connect(read)
app.exec()
