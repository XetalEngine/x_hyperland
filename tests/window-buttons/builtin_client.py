"""Load a real Fusion window inside the integration test's disposable profile."""
import json
from pathlib import Path
import runpy
import sys
from PyQt6.QtCore import QEvent,QPoint,QSocketNotifier
from PyQt6.QtWidgets import QApplication,QToolButton

root=Path(sys.argv[1]).resolve();kind=sys.argv[2]
assert root.is_relative_to(Path('/tmp'))
directory={'settings':'control_center','theme':'wallpaper','kvm':'kvm'}[kind]
sys.path[:0]=[str(root/directory),str(root/'theme'),str(root)]
namespace=runpy.run_path(str(root/directory/'app.py'),run_name='builtin_fixture')
if kind=='kvm':namespace['portable'].prepare()
app=QApplication([]);app.setDesktopFileName('builtin-'+kind);app.setQuitOnLastWindowClosed(False)
import runtime
runtime.install(app,namespace.get('STYLE',''))
if kind=='settings':window=namespace['Window'](visible=False)
elif kind=='theme':window=namespace['ThemeWindow']()
else:window=namespace['KVMSettings']()
window.show()
def read(*_):
    if not sys.stdin.readline():app.quit();return
    result={}
    for name in ('windowMinimize','windowMaximize','windowClose'):
        button=window.findChild(QToolButton,name);point=button.mapTo(window,QPoint())
        result[name]={'box':[point.x(),point.y(),button.width(),button.height()],'caption':button.accessibleName()}
    print(json.dumps(result),flush=True)
notifier=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read);notifier.activated.connect(read)
app.exec()
window.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
