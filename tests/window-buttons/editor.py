"""Drive the real editor only inside check-window-buttons' private profile."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(sys.argv[1])))
from effects.window_close.window_settings import RuleDialog
from PyQt6.QtCore import QSocketNotifier
from PyQt6.QtWidgets import QApplication
import runtime as theme_runtime

app=QApplication([]);app.setDesktopFileName('fusion-window-buttons')
theme_runtime.install(app)
dialog=RuleDialog(sys.argv[2]);dialog.show()
app.aboutToQuit.connect(dialog.end_preview)

def read(*_):
    line=sys.stdin.readline()
    if not line:app.quit();return
    command=json.loads(line);op=command['op']
    if op=='slider':getattr(dialog,command['key']).slider.setValue(command['value'])
    elif op in ('scope','anchor','mode'):
        control=getattr(dialog,op);control.setCurrentIndex(control.findData(command['value']))
    elif op=='apply':dialog.apply()
    elif op=='reset':dialog.reset.click()
    elif op=='reload':dialog.load()
    elif op=='close':dialog.reject()
    state={'scope':dialog.scope.currentData(),'rule':dialog.values(),'status':dialog.status.text(),'preview':dialog.live.text()}
    print(json.dumps(state),flush=True)

notifier=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read);notifier.activated.connect(read)
app.exec()
