"""Checkerboard and click counter for a private compositor only."""
import json
from pathlib import Path
import sys
from PyQt6.QtCore import Qt,QEvent,QTimer
from PyQt6.QtGui import QPainter,QColor,QCursor
from PyQt6.QtWidgets import QApplication,QWidget

path=Path(sys.argv[1]);app=QApplication([]);app.setApplicationName('fusion-overlay-target');app.setDesktopFileName('fusion-overlay-target')
class Target(QWidget):
    clicks=0
    events=[]
    def paintEvent(self,event):
        painter=QPainter(self)
        for y in range(0,self.height(),8):
            for x in range(0,self.width(),8):
                painter.fillRect(x,y,8,8,QColor('#202020' if (x//8+y//8)%2 else '#e0e0e0'))
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.clicks+=1;self.save()
    def event(self,event):
        if event.type() in (QEvent.Type.Enter,QEvent.Type.Leave,QEvent.Type.MouseButtonPress,
                            QEvent.Type.MouseButtonRelease,QEvent.Type.WindowActivate,QEvent.Type.WindowDeactivate):
            self.events.append(event.type().name);self.events=self.events[-20:]
        return super().event(event)
    def save(self):
        cursor=QCursor.pos()
        value={'clicks':self.clicks,'platform':app.platformName(),'active':self.isActiveWindow(),
               'visible':self.isVisible(),'under_mouse':self.underMouse(),'pointer':[cursor.x(),cursor.y()],
               'geometry':[self.x(),self.y(),self.width(),self.height()],'events':self.events}
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value));temporary.replace(path)
window=Target();window.setWindowTitle('Overlay input target');window.resize(900,650);window.show();window.save()
timer=QTimer(window);timer.timeout.connect(window.save);timer.start(250)
sys.exit(app.exec())
