"""Real Qt archive selection -> GTK desktop drop in the private compositor."""
import hashlib
import json
import sys
import time
import zipfile


def check_archive_drag(root, source, desktop, positions, spawn, ctl, run, gesture, wait, state):
    archive = desktop.parent/'Selection.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('Package/sub/one.txt', 'nested selected file')
        output.writestr('read me # café.txt', 'selected loose file')
        output.writestr('Unselected.txt', 'must stay in the archive')
    original = hashlib.sha256(archive.read_bytes()).hexdigest()
    report = root/'archive-drag.json'
    fixture = root/'archive-drag.py'
    fixture.write_text('''import json,sys
from pathlib import Path
sys.path[:0]=[sys.argv[1]+'/archive_manager',sys.argv[1]]
from PyQt6.QtCore import QTimer,QItemSelectionModel
from PyQt6.QtWidgets import QApplication
from ui import ArchiveBrowser
from tasks import Task
app=QApplication([]);app.setDesktopFileName('fusion-archive-drag-test')
browser=ArchiveBrowser(Path(sys.argv[2]));browser.show()
report=Path(sys.argv[3]);requests=[];results=[];tasks=[];selected=False;point=None
def launch(request):
 requests.append({key:value for key,value in request.items() if key!='password'})
 task=Task(request);tasks.append(task);task.outcome.connect(results.append);task.start()
browser.launch.connect(launch)
def update():
 global selected,point
 if browser.model.db is not None and not selected:
  selection=browser.table.selectionModel();selection.clearSelection()
  for row in range(browser.model.rowCount()):
   index=browser.model.index(row,0)
   if index.data() in ('Package','read me # café.txt'):
    selection.select(index,QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
  selected=bool(browser.selected())
 if selected:
  index=browser.table.selectionModel().selectedRows()[0]
  local=browser.table.viewport().mapTo(browser,browser.table.visualRect(index).center())
  point=[local.x(),local.y()]
 data=dict(point=point,selected=browser.selected(),requests=requests,results=results,status=browser.status.text())
 temporary=report.with_suffix('.tmp');temporary.write_text(json.dumps(data));temporary.replace(report)
timer=QTimer();timer.timeout.connect(update);timer.start(60)
app.exec()
''')
    spawn([sys.executable, str(fixture), str(source), str(archive), str(report)])

    def current():
        try: return json.loads(report.read_text())
        except (ValueError, FileNotFoundError): return {}

    def window():
        return next((c for c in json.loads(ctl('-j', 'clients')) if c['class'] == 'fusion-archive-drag-test'), None)

    wait(window, 'archive browser')
    address = 'address:'+window()['address']
    ctl('dispatch', 'setfloating', address)
    ctl('dispatch', 'resizewindowpixel', 'exact 760 650,'+address)
    ctl('dispatch', 'movewindowpixel', 'exact 500 120,'+address)
    wait(lambda: current().get('point') and len(current()['selected']) == 2, 'two selected archive entries')
    time.sleep(.25)

    def drag(destination, label, folder=None):
        a, b = window()['at']; x, y = current()['point']
        gesture(f'move {a+x} {b+y}'); gesture('button 1')
        gesture(f'move {a+x+18} {b+y+14}')
        gesture(f'move {destination[0]} {destination[1]}', .3)
        gesture(f'move {destination[0]+1} {destination[1]+1}', .2)
        wait(lambda: all(s.get('drop') == folder for s in state()['surfaces']), 'archive destination highlight')
        run('grim', str(root/(label+'.png')))
        gesture('button 0', .25)

    x, y = positions()['A folder']
    drag((x+40, y+26), 'archive-folder-hover', 'A folder')
    wait(lambda: len(current().get('results', [])) == 1, 'archive extraction into desktop folder')
    assert current()['results'][0]['ok'], current()
    assert (desktop/'A folder/Package/sub/one.txt').read_text() == 'nested selected file'
    assert (desktop/'A folder/read me # café.txt').read_text() == 'selected loose file'
    assert not (desktop/'A folder/Unselected.txt').exists()
    assert current()['requests'][0]['destination'] == str(desktop/'A folder'), current()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == original

    # A regular file icon must not turn an archive drop into a background copy.
    x, y = positions()['1 notes # café.txt']
    drag((x+40, y+26), 'archive-file-rejected')
    time.sleep(.3)
    assert len(current()['requests']) == 1, current()
    assert not (desktop/'Package').exists()

    drag((300, 680), 'archive-background')
    wait(lambda: len(current().get('results', [])) == 2, 'archive extraction onto desktop background')
    assert current()['results'][1]['ok'], current()
    assert (desktop/'Package/sub/one.txt').read_text() == 'nested selected file'
    assert (desktop/'read me # café.txt').read_text() == 'selected loose file'
    assert not (desktop/'Unselected.txt').exists()
    assert current()['requests'][1]['destination'] == str(desktop), current()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == original
    wait(lambda: all(s.get('drop') is None for s in state()['surfaces']), 'archive highlight cleared')
    print('PASS: actual Qt archive selection into a GTK desktop folder and background, folder highlighting, rejected file icons, preserved selection and unchanged source archive.')
