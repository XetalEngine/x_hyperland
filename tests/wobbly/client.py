import json,sys
from PyQt6.QtCore import QSocketNotifier,QTimer,QTime
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QLineEdit
app=QApplication(sys.argv);app.setDesktopFileName("wobbly-test");app.setQuitOnLastWindowClosed(False);windows={}
def add(name):
    w=QWidget();w.setWindowTitle(name);w.resize(620,400)
    w.setStyleSheet('QWidget {background:#132f42;color:#edf5fa;font-size:24px;} QLineEdit {background:#25526d;}')
    layout=QVBoxLayout(w);layout.addWidget(QLabel('TOP — '+name))
    layout.addWidget(QLineEdit('Live text stays editable'));clock=QLabel();layout.addWidget(clock);layout.addStretch();layout.addWidget(QLabel('BOTTOM — original window content'))
    timer=QTimer(w);timer.timeout.connect(lambda:clock.setText(QTime.currentTime().toString('hh:mm:ss.zzz')));timer.start(40)
    windows[name]=w;w.show()
def read(*_):
    line=sys.stdin.readline()
    if not line:app.quit();return
    c=json.loads(line);name=c.get('name','Wobbly test');op=c['op']
    if op=='add':add(name)
    elif op=='close':windows[name].close()
    elif op=='max':windows[name].showMaximized()
    elif op=='restore':windows[name].showNormal()
    elif op=='min':windows[name].showMinimized()
    elif op=='pause':windows[name].findChild(QTimer).stop()
    elif op=='bell':app.beep()
    elif op=='quit':app.quit()
    print('ok',flush=True)
n=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read);n.activated.connect(read);app.exec()
