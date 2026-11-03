#!/usr/bin/env python3
"""Native drag and close gestures in a disposable compositor, with XWayland off.

Usage: python3 tests/check-file-drag-and-close.py OUTPUT_DIR FILES_BUILD
The browser uses a private profile and local upload fixture; no files leave the machine.
"""
import http.server
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import tarfile
import zipfile
import io
import time

REPO=Path(__file__).resolve().parents[1]


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=False)
    build=Path(sys.argv[2]).resolve()
    plugin=subprocess.check_output([sys.executable,str(REPO/'config/hypr/effects/window_close/build.py')],text=True).strip()
    for name,xml in [('pointer',REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
                     ('keyboard',REPO/'tests/native/virtual-keyboard-unstable-v1.xml')]:
        for mode,suffix in [('client-header','h'),('private-code','c')]:
            subprocess.run(['wayland-scanner',mode,str(xml),str(root/f'virtual-{name}.{suffix}')],check=True)
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True))
    subprocess.run(['cc','-I'+str(root),str(REPO/'tests/native/gesture-input.c'),str(root/'virtual-pointer.c'),
                    str(root/'virtual-keyboard.c'),'-o',str(root/'input'),*flags],check=True)
    runtime=Path(tempfile.mkdtemp(prefix='fusion-gesture-'))
    profile=root/'home/.config/hypr';(profile/'effects/window_close').mkdir(parents=True)
    settings=profile/'effects/window_close/settings.conf'
    shutil.copyfile(REPO/'config/hypr/effects/window_close/settings.conf',settings)
    (profile/'theme').mkdir();(profile/'theme/current.colors').write_text('[Colors:Window]\nDecorationFocus=57,169,255\n')
    source=root/'files';(source/'Destination').mkdir(parents=True)
    filename='photo # 100% café.txt';payload='Native file drag fixture, kept on this computer.\n'
    (source/filename).write_text(payload)
    (root/'preferences.ini').write_text('[General]\npreview=false\n')
    parent=os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'):parent=str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env=dict(os.environ,HOME=str(root/'home'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=parent,
             XDG_CONFIG_HOME=str(root/'home/.config'),XDG_DATA_HOME=str(root/'home/.local/share'),
             XDG_CACHE_HOME=str(root/'home/.cache'),XDG_STATE_HOME=str(root/'home/.local/state'),
             XDG_CURRENT_DESKTOP='Hyprland',GSETTINGS_BACKEND='memory',AQ_BACKENDS='wayland',
             HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',QT_QPA_PLATFORM='wayland',QT_QPA_PLATFORMTHEME='',
             FUSION_FILES_ISOLATED='1',XETAL_FILES_ROOT=str(REPO/'config/hypr'),QT_PLUGIN_PATH='')
    env.pop('HYPRLAND_INSTANCE_SIGNATURE',None);env.pop('DISPLAY',None)
    children=[];logs=[];uploads=[];browser_events=[]
    def spawn(args,**kwargs):
        log=(root/f'process-{len(children)}.log').open('w');logs.append(log)
        process=subprocess.Popen(args,env=env,stdout=log,stderr=log,**kwargs);children.append(process);return process
    def run(*args):
        return subprocess.check_output(args,env=env,text=True,stderr=subprocess.STDOUT,timeout=15).strip()
    def ctl(*args):return run('hyprctl',*args)
    def dispatch(*args):assert ctl('dispatch',*args)=='ok',args
    def wait(predicate,label):
        for _ in range(160):
            if predicate():return
            time.sleep(.05)
        raise AssertionError('Timed out: '+label)
    def clients():return json.loads(ctl('-j','clients'))
    def client(title):return next((c for c in clients() if c['title']==title),None)
    def place(title,x,y,w=650,h=650):
        wait(lambda:client(title),title);c=client(title);address='address:'+c['address']
        dispatch('setfloating',address);dispatch('resizewindowpixel',f'exact {w} {h},'+address)
        dispatch('movewindowpixel',f'exact {x} {y},'+address);time.sleep(.2)
        return client(title)
    def status():return json.loads(ctl('xetal-windowclose'))
    class Upload(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            data=b'''<title>Fusion upload fixture</title><style>body{margin:0;background:#101820;color:#dcefff;font:24px sans-serif;height:100vh;display:grid;place-items:center}#zone{padding:70px;border:2px dashed #39a9ff}</style><div id=zone>Drop a file here</div><script>
            const log=(e)=>fetch('/event',{method:'POST',body:JSON.stringify({event:e.type,types:[...e.dataTransfer.types],files:e.dataTransfer.files.length})});
            addEventListener('dragenter',e=>{e.preventDefault();log(e)});addEventListener('dragover',e=>{e.preventDefault();log(e)});addEventListener('drop',async e=>{e.preventDefault();log(e);let files=[];for(let f of e.dataTransfer.files)files.push({name:f.name,text:await f.text()});await fetch('/result',{method:'POST',body:JSON.stringify(files)});zone.textContent='Received '+files.map(f=>f.name).join(', ');});fetch('/event',{method:'POST',body:JSON.stringify({event:'ready'})});</script>'''
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(data)
        def do_POST(self):
            (uploads if self.path=='/result' else browser_events).append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.end_headers()
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Upload)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    conf=root/'hyprland.conf'
    conf.write_text(f'''monitor=,1400x900@60,auto,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
animations:enabled=false
xwayland:enabled=false
bindm=SUPER,mouse:272,movewindow
plugin={plugin}
''')
    compositor=spawn(['Hyprland','--config',str(conf)],start_new_session=True)
    input_process=None
    try:
        instance=None
        for _ in range(120):
            assert compositor.poll() is None,'Nested compositor exited'
            try:instances=json.loads(run('hyprctl','-j','instances'))
            except json.JSONDecodeError:instances=[]
            instance=next((i for i in instances if i['pid']==compositor.pid),None)
            if instance:break
            time.sleep(.1)
        assert instance,'Nested compositor unavailable'
        env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket'])
        assert ctl('configerrors')=='',ctl('configerrors')
        # D-Bus activation inherits the daemon's environment, not the caller's.
        # Start it here, with the private HOME/runtime and nested display already set.
        bus_log=(root/'dbus.log').open('w');logs.append(bus_log)
        bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],env=env,
                             stdout=subprocess.PIPE,stderr=bus_log,text=True)
        children.append(bus);env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
        assert env['DBUS_SESSION_BUS_ADDRESS'].startswith('unix:'),'Private D-Bus did not start'
        # Disable host-facing devices in this private compositor before adding
        # virtual test input. Parent desktop pointer motion must not interfere.
        devices=json.loads(ctl('-j','devices'))
        (root/'host-devices.json').write_text(json.dumps(devices,indent=2))
        for kind in ('mice','keyboards'):
            for device in devices.get(kind,[]):
                result=ctl('keyword','device['+device['name']+']:enabled','false')
                assert result=='ok',result
        if not json.loads(ctl('-j','monitors')):ctl('output','create','headless','TEST')
        monitor=json.loads(ctl('-j','monitors'))[0]
        ctl('keyword','monitor',monitor['name']+',1700x1000@60,0x0,1');time.sleep(.6)
        monitor=json.loads(ctl('-j','monitors'))[0]
        width=round(monitor['width']/monitor['scale']);height=round(monitor['height']/monitor['scale'])
        input_process=subprocess.Popen([str(root/'input'),str(width),str(height)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def gesture(command,delay=.08):
            input_process.stdin.write(command+'\n');input_process.stdin.flush()
            assert input_process.stdout.readline().strip()=='ok';time.sleep(delay)
        def click():gesture('button 1');gesture('button 0')
        def drag(a,b,control=None):
            gesture(f'move {a[0]} {a[1]}');gesture('button 1')
            for n in range(1,17):
                gesture(f'move {round(a[0]+(b[0]-a[0])*n/16)} {round(a[1]+(b[1]-a[1])*n/16)}',.04)
                if n==10 and control is not None:gesture('key 29 '+str(control))
            time.sleep(.5)
            run('grim','-c',str(root/'drag-feedback.png'))
            gesture('button 0',.3)
        # Run the actual themed JobView UI on this private bus. Its questions
        # expand inside the progress card; no separate overwrite dialog exists.
        transfer_report=root/'transfer-windows.json'
        fixture=root/'transfer-service.py'
        fixture.write_text('''import json,sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
sys.path.insert(0,sys.argv[1])
from file_jobs.app import Windows
from file_jobs.service import Service
from file_jobs.questions import ChoiceButton
from file_jobs import preferences
app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setApplicationName('Fusion transfer probe')
app.setDesktopFileName('fusion-transfer-probe')
service=Service(parent=app);service.start();windows=Windows(service)
windows.options=preferences.normalize({'style':'breakpoint','behavior':{'show_delay':100,'close_delay':500}})
report=Path(sys.argv[2])
def save():
    values=[]
    for window in list(windows.windows.values()):
        if not window.job.question:continue
        buttons={}
        for button in window.question_panel.findChildren(ChoiceButton):
            point=button.mapTo(window,button.rect().center());buttons[button.property('choice')]=[point.x(),point.y()]
        values.append({'title':window.windowTitle(),'kind':window.job.question['kind'],'buttons':buttons,
                       'height':window.height(),'base_height':window.base_height})
    temp=report.with_suffix('.tmp');temp.write_text(json.dumps(values));temp.replace(report)
timer=QTimer(app);timer.timeout.connect(save);timer.start(40);save();app.exec()
''')
        transfer_service=spawn([sys.executable,str(fixture),str(REPO/'config/hypr'),str(transfer_report)])
        wait(transfer_report.exists,'themed transfer service')
        report=root/'positions.json'
        env['WAYLAND_DEBUG']='client'
        spawn([str(build/'files-drag-probe'),str(source),str(report)])
        env.pop('WAYLAND_DEBUG')
        place('Fusion drag probe',20,100)
        browser=shutil.which('google-chrome-stable') or shutil.which('chromium')
        assert browser,'A Chromium browser is needed for this integration check'
        spawn([browser,'--ozone-platform=wayland','--no-first-run','--no-default-browser-check',
               '--disable-background-networking','--disable-sync','--password-store=basic',
               '--user-data-dir='+str(root/'browser'),'--app=http://127.0.0.1:'+str(server.server_port)])
        place('Fusion upload fixture',max(500,width-440),100,430,650)
        wait(lambda:browser_events,'browser JavaScript ready')
        wait(lambda:report.exists() and filename in json.loads(report.read_text()),'file icon')
        def file_point(name):
            c=client('Fusion drag probe');point=json.loads(report.read_text())[name]
            return [c['at'][0]+point[0],c['at'][1]+point[1]]
        (root/'before-drag.json').write_text(json.dumps({'clients':clients(),'point':file_point(filename),'positions':json.loads(report.read_text())},indent=2))
        run('grim',str(root/'before-drag.png'))
        drag(file_point(filename),[width-60,430])
        run('grim',str(root/'after-drag.png'))
        wait(lambda:uploads,'browser upload drop')
        assert uploads[-1]==[{'name':filename,'text':payload}],uploads
        assert (source/filename).exists()
        # Press Ctrl after the drag begins: both the action and badge must change.
        drag(file_point(filename),file_point('Destination'),control=1);gesture('key 29 0')
        shutil.copyfile(root/'drag-feedback.png',root/'copy-drag-feedback.png')
        wait(lambda:(source/'Destination'/filename).exists(),'folder copy')
        assert (source/'Destination'/filename).read_text()==payload
        assert (source/filename).exists()
        run('grim',str(root/'drag.png'))
        print('Real file drag to browser and Ctrl-copy to folder passed',flush=True)
        if '--files-only' in sys.argv:
            # The first collision must wait for an explicit overwrite choice.
            (source/'Destination'/filename).write_text('Previous destination contents')
            gesture('key 29 1')
            drag(file_point(filename),file_point('Destination'),control=0)
            shutil.copyfile(root/'drag-feedback.png',root/'move-drag-feedback.png')
            wait(lambda:bool(json.loads(transfer_report.read_text())),'expanded overwrite question')
            assert (source/filename).exists()
            assert (source/'Destination'/filename).read_text()=='Previous destination contents'
            time.sleep(.3)
            question=json.loads(transfer_report.read_text())[0]
            dialog=next(c for c in clients() if c['pid']==transfer_service.pid and c['title']==question['title'])
            assert question['height']>question['base_height']
            button=question['buttons']['replace']
            run('grim',str(root/'overwrite-question.png'))
            gesture(f"move {dialog['at'][0]+button[0]} {dialog['at'][1]+button[1]}");click()
            wait(lambda:not (source/filename).exists(),'confirmed drop moved source')
            assert (source/'Destination'/filename).read_text()==payload
            assert not (source/'Destination'/'photo # 100% café_copy1.txt').exists()
            print('Plain drop moves after confirming an existing-file overwrite',flush=True)
            point=file_point('_view');gesture(f'move {point[0]} {point[1]}');click()
            run('grim',str(root/'folder-view-menu.png'))
            gesture('key 1 1');gesture('key 1 0')
            for extension in ('tar.gz','zip'):
                member='Archive '+extension+'.txt';content=('Extracted '+extension+' contents').encode()
                archive=root/('sample.'+extension)
                if extension=='zip':
                    with zipfile.ZipFile(archive,'w') as out:out.writestr(member,content)
                else:
                    with tarfile.open(archive,'w:gz') as out:
                        item=tarfile.TarInfo(member);item.size=len(content);out.addfile(item,io.BytesIO(content))
                ark=spawn(['ark',str(archive)])
                wait(lambda:any(c['pid']==ark.pid for c in clients()),'Ark window')
                ark_client=next(c for c in clients() if c['pid']==ark.pid)
                ark_client=place(ark_client['title'],width-720,80,700,700)
                address='address:'+ark_client['address'];dispatch('focuswindow',address)
                time.sleep(.8);run('grim',str(root/('ark-'+extension+'-before.png')))
                # Ark's first archive row, below its two toolbar/header rows.
                a=ark_client['at'];gesture(f'move {a[0]+80} {a[1]+68}');click()
                gesture('key 29 1');gesture('key 30 1');gesture('key 30 0');gesture('key 29 0')
                drag([a[0]+80,a[1]+68],file_point('Destination'))
                run('grim',str(root/('ark-'+extension+'-after.png')))
                wait(lambda:(source/'Destination'/member).exists(),'Ark '+extension+' extraction')
                assert (source/'Destination'/member).read_bytes()==content
                assert archive.exists();dispatch('closewindow',address)
                print('Real Ark '+extension+' drag extraction passed',flush=True)
            return
        # CloseEvent deliberately refuses the first close, like an unsaved-work prompt.
        fixture=root/'close-fixture.py'
        fixture.write_text('''from PyQt6.QtWidgets import QApplication,QWidget,QLabel,QVBoxLayout
from pathlib import Path
import sys
root=Path(sys.argv[1])
class Window(QWidget):
 def closeEvent(self,event):
  (root/'close-requested').write_text('normal close event')
  if (root/'allow-close').exists():event.accept()
  else:event.ignore()
app=QApplication([]);window=Window();window.setWindowTitle('Close fixture');layout=QVBoxLayout(window);layout.addWidget(QLabel('Unsaved work fixture'));window.show();app.exec()
''')
        spawn([sys.executable,str(fixture),str(root)]);place('Close fixture',400,220,400,300)
        gesture('move 550 330');gesture('key 125 1')
        wait(lambda:status()['visible'] and status()['draws']>0,'Super close badge')
        s=status();box=s['box'];point=[round(box[0]+box[2]/2),round(box[1]+box[3]/2)]
        gesture(f'move {point[0]} {point[1]}');run('grim',str(root/'close-button.png'))
        click();wait(lambda:(root/'close-requested').exists(),'normal close event')
        assert client('Close fixture'),'Ignored close request must keep the app alive'
        gesture('key 125 0');wait(lambda:not status()['visible'],'release hides button')
        click();assert status()['closed']==1,'Ordinary clicks must not close'
        # Super-drag away from the button retains the compositor move binding.
        before=client('Close fixture')['at'];gesture('key 125 1')
        drag([before[0]+130,before[1]+140],[before[0]+185,before[1]+180]);gesture('key 125 0')
        assert client('Close fixture')['at']!=before,'Super+drag must still move windows'
        settings.write_text(settings.read_text().replace('enabled=1','enabled=0'))
        dispatch('xetalwindowclose:reload');gesture('key 125 1')
        assert not status()['visible'];gesture('key 125 0')
        settings.write_text(settings.read_text().replace('enabled=0','enabled=1').replace('modifier=SUPER','modifier=ALT'))
        (profile/'theme/current.colors').write_text('[Colors:Window]\nDecorationFocus=239,62,82\n')
        dispatch('xetalwindowclose:reload');gesture('key 56 1')
        wait(lambda:status()['visible'],'configured Alt gesture')
        wait(lambda:abs(status()['color'][0]-239/255)<.001,'live theme accent')
        box=status()['box'];gesture(f'move {round(box[0]+box[2]/2)} {round(box[1]+box[3]/2)}')
        (root/'allow-close').touch();click();gesture('key 56 0')
        wait(lambda:not client('Close fixture'),'accepted normal close')
        results={'browser_drop':uploads[-1], 'folder_copy':True, 'normal_close':True,
                 'super_drag':True, 'disable':True, 'alt_modifier':True, 'theme_reload':True, 'status':status()}
        (root/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results),flush=True)
    finally:
        (root/'browser-events.json').write_text(json.dumps(browser_events,indent=2)+'\n')
        if input_process:
            try:input_process.communicate('quit\n',timeout=3)
            except (OSError,subprocess.TimeoutExpired):input_process.terminate()
        if compositor.poll() is None:
            try:ctl('dispatch','exit')
            except Exception:pass
        for process in reversed(children):
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        # Only helpers tagged with this unique private runtime are eligible.
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():continue
            try:
                if path.stat().st_uid==os.getuid() and ('XDG_RUNTIME_DIR='+str(runtime)).encode() in (path/'environ').read_bytes().split(b'\0'):
                    os.kill(int(path.name),signal.SIGTERM)
            except OSError:pass
        server.shutdown()
        for log in logs:log.close()


if __name__=='__main__':main()
