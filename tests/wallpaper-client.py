#!/usr/bin/env python3
"""Drive the real Qt browser inside the disposable test compositor."""
import json
from pathlib import Path
import sys
root=Path(sys.argv[1]); sys.path[:0]=[str(root),str(root/'theme'),str(root/'control_center')]
from PyQt6.QtCore import QSocketNotifier, QTimer, Qt
from PyQt6.QtWidgets import QApplication
from wallpaper.browser import Browser, ScreenPicker, MonitorMap, runtime, STYLE, place, settings

app=QApplication([]); app.setApplicationName('xetal-wallpaper-browser'); app.setDesktopFileName('xetal-wallpaper-browser'); app.setQuitOnLastWindowClosed(False)
runtime.install(app,STYLE); settings.STATE=root/'test-state'; window=Browser(); window.completed=False
def applied(): window.set_busy(False); window.completed=True
window.applied=applied; place(window); window.show()
notifier=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read)
def read():
    line=sys.stdin.readline()
    if not line: app.quit(); return
    try:
        data=json.loads(line); op=data['op']; answer='ok'
        if op=='status':
            answer={'busy':window.busy,'visible':window.isVisible(),'completed':window.completed,'pictures':len(window.pictures),
                    'dialog':type(window.dialog).__name__ if window.dialog else '', 'status':window.status.text(),
                    'monitor':window.monitor_name,'selected':window.carousel.current().path if window.carousel.current() else ''}
        elif op=='choose':
            picture=next(p for p in window.pictures if p.path==data['path']); QTimer.singleShot(0,lambda:window.choose(picture))
        elif op=='select':
            dialog=window.dialog; assert isinstance(dialog,ScreenPicker)
            screen=next(b for b in dialog.findChild(MonitorMap).buttons if b.model['name']==data['name']); screen.click()
        elif op=='cancel': window.dialog.reject()
        elif op=='show': window.completed=False; place(window); window.show()
        elif op=='grab': window.grab().save(data['path'])
        elif op=='grab-dialog': window.dialog.grab().save(data['path'])
        elif op=='quit': app.quit()
        print(json.dumps(answer),flush=True)
    except Exception as error: print(json.dumps({'error':str(error)}),flush=True)
notifier.activated.connect(read)
try: code=app.exec()
finally: window.shutdown()
print('Browser driver event loop exited: '+str(code),file=sys.stderr,flush=True)
raise SystemExit(code)
