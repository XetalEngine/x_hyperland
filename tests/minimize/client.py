import sys,json
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QPushButton
from PyQt6.QtCore import QSocketNotifier,Qt
app=QApplication([]);app.setQuitOnLastWindowClosed(False);windows={}
def add(name):
 w=QWidget();w.setWindowTitle(name);w.resize(680,420);layout=QVBoxLayout(w)
 w.setStyleSheet('QWidget { background: #123448; color: #def4ff; font-size: 24px; } QPushButton { background: #236b93; padding: 18px; }')
 layout.addWidget(QLabel(name+' — minimize test'));layout.addWidget(QLabel('TOP  12345'));layout.addStretch()
 b=QPushButton('Minimize');b.clicked.connect(w.showMinimized);layout.addWidget(b);layout.addWidget(QLabel('BOTTOM  abcde'));w.show();windows[name]=w
def read(*_):
 line=sys.stdin.readline()
 if not line:app.quit();return
 c=json.loads(line);op=c['op'];name=c.get('name','Test')
 if op=='add':add(name)
 elif op=='min':windows[name].showMinimized()
 elif op=='show':windows[name].showNormal();windows[name].activateWindow()
 elif op=='close':windows[name].close()
 elif op=='full':windows[name].showFullScreen()
 elif op=='quit':app.quit()
 print('ok',flush=True)
n=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read);n.activated.connect(read);app.exec()
