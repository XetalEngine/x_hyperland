"""Desktop drag lifetime while an archive changes the watched directory.

Used by check-desktop-icons.py in its disposable HOME/compositor/private bus.
The external GTK target consumes file URLs like an upload queue; no network or
personal files are used. The archive writer runs independently of either UI.
"""
import json
import sys
import time


def check_drag_refresh(root, desktop, positions, spawn, ctl, gesture, wait, popup, key, state):
    report = root/'target.json'
    target = root/'drop-target.py'
    target.write_text('''import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0')
from gi.repository import Gtk,Gdk
report=Path(sys.argv[1]);state=dict(drops=[],clicks=0)
def save():report.write_text(json.dumps(state))
window=Gtk.Window(title='External upload queue');window.set_default_size(420,300)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.add(box)
drop=Gtk.Label(label='Drop files here');drop.set_size_request(400,200)
drop.drag_dest_set(Gtk.DestDefaults.ALL,[Gtk.TargetEntry.new('text/uri-list',0,0)],Gdk.DragAction.COPY)
def received(widget,context,x,y,data,info,timestamp):
 state['drops'].append(data.get_uris());save();Gtk.drag_finish(context,True,False,timestamp)
drop.connect('drag-data-received',received);box.pack_start(drop,True,True,0)
button=Gtk.Button(label='Click after drop');button.set_size_request(400,90)
def clicked(*_):state['clicks']+=1;save()
button.connect('clicked',clicked);box.pack_end(button,False,False,0)
window.connect('destroy',Gtk.main_quit);window.show_all();save();Gtk.main()
''')
    process = spawn([sys.executable, str(target), str(report)])
    def client():
        return next((c for c in json.loads(ctl('-j','clients')) if c['pid']==process.pid), None)
    def target_state():
        try: return json.loads(report.read_text())
        except (FileNotFoundError,ValueError): return {}
    wait(client,'external GTK drop target')
    address='address:'+client()['address']
    ctl('dispatch','setfloating',address)
    ctl('dispatch','resizewindowpixel','exact 420 300,'+address)
    ctl('dispatch','movewindowpixel','exact 800 160,'+address)
    time.sleep(.3)
    def begin(name):
        a,b=positions()[name]
        gesture(f'move {a+40} {b+26}');gesture('button 1')
        gesture(f'move {a+58} {b+40}')
        assert json.loads(ctl('-j','xetal-file-drag'))['active'], 'Drag did not start'
    def click_target(expected):
        gesture('move 950 400');gesture('button 1');gesture('button 0')
        wait(lambda:target_state().get('clicks')==expected,'external application clickable after drag')
    def desktop_works():
        popup();key(1)
        wait(lambda:not state().get('menus'),'desktop menu clickable and dismissible after drag')
    names=['1 notes # café.txt','2 notes # café.txt']
    for name in names:
        a,b=positions()[name]
        gesture('key 29 1');gesture(f'move {a+40} {b+26}')
        gesture('button 1');gesture('button 0');gesture('key 29 0')
    wait(lambda:set(state()['selected'])==set(names),'two selected source files')
    begin(names[0])
    gesture('move 950 260',.3)
    # An archive is created/updated while its source icon owns a native drag.
    # This is the same directory monitor path as Ark/zip writing on Desktop.
    writer=root/'compress.py'
    writer.write_text('''import os,sys,time,zipfile
from pathlib import Path
root=Path(sys.argv[1]);chunk=os.urandom(65536)
with zipfile.ZipFile(root/'in progress.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
 for name in ('large-a.bin','large-b.bin'):
  with archive.open(name,'w') as entry:
   for _ in range(40):entry.write(chunk);time.sleep(.015)
 time.sleep(.4)
''')
    archive=spawn([sys.executable,str(writer),str(desktop)])
    wait(lambda:'in progress.zip' in positions(),'archive refresh during drag')
    gesture('move 951 261',.3)
    gesture('button 0',.4)
    wait(lambda:target_state().get('drops'),'external target received desktop URLs')
    (root/'after-drop.json').write_text(json.dumps(dict(target=target_state(),
        native=json.loads(ctl('-j','xetal-file-drag'))),indent=2))
    click_target(1);desktop_works()
    assert target_state()['drops']==[[(desktop/name).as_uri() for name in names]],target_state()
    assert archive.wait(timeout=10)==0
    assert all((desktop/name).exists() for name in names)
    # Cancelling a drag after another refresh must release both the toolkit
    # and compositor state without affecting the archive/source files.
    begin(names[0]);gesture('move 950 260',.2)
    (desktop/'after archive.txt').write_text('finished')
    wait(lambda:'after archive.txt' in positions(),'refresh before Escape')
    key(1);gesture('button 0')
    wait(lambda:not json.loads(ctl('-j','xetal-file-drag'))['active'],'cancelled drag')
    click_target(2);desktop_works()
    assert len(target_state()['drops'])==1
    # A source really disappearing must cancel before its widget is destroyed.
    victim='7 notes # café.txt'
    begin(victim);gesture('move 950 260',.2)
    (desktop/victim).unlink()
    wait(lambda:victim not in positions(),'removed source icon')
    gesture('button 0')
    wait(lambda:not json.loads(ctl('-j','xetal-file-drag'))['active'],'removed source released drag')
    click_target(3);desktop_works()
    assert len(target_state()['drops'])==1
    (root/'drag-refresh.json').write_text(json.dumps(dict(result='passed',target=target_state()),indent=2))
    print('PASS: archive refresh during two-file desktop-to-GTK drag, URL delivery, Escape, source removal, and desktop/external-app clicks after each.',flush=True)
