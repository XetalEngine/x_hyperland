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
        monitor=json.loads(ctl('-j','monitors'))[0]
        width=round(monitor['width']/monitor['scale']);height=round(monitor['height']/monitor['scale'])
        input_process=subprocess.Popen([str(root/'input'),str(width),str(height)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def gesture(command,delay=.08):
            input_process.stdin.write(command+'\n');input_process.stdin.flush()
            assert input_process.stdout.readline().strip()=='ok';time.sleep(delay)
        def click():gesture('button 1');gesture('button 0')
        def drag(a,b):
            gesture(f'move {a[0]} {a[1]}');gesture('button 1')
            for n in range(1,17):gesture(f'move {round(a[0]+(b[0]-a[0])*n/16)} {round(a[1]+(b[1]-a[1])*n/16)}',.04)
            time.sleep(.5)
            gesture('button 0',.3)
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
        gesture('key 29 1') # Ctrl: copy into the destination folder.
        drag(file_point(filename),file_point('Destination'));gesture('key 29 0')
        wait(lambda:(source/'Destination'/filename).exists(),'folder copy')
        assert (source/'Destination'/filename).read_text()==payload
        assert (source/filename).exists()
        run('grim',str(root/'drag.png'))
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
