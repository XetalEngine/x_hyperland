#!/usr/bin/env python3
"""Exercise text selection and floating header dragging in a private compositor.

Usage: python3 tests/check-floating-text-drag.py NEW_OUTPUT_DIRECTORY
No test input reaches the parent session; XWayland is disabled in the fixture.
"""
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'config/hypr'))
from effects.wobbly import model as wobble_model,build as wobble_build


def main():
    root = Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=False)
    plugin = subprocess.check_output([sys.executable,str(REPO/'config/hypr/runtime/cursor_probe/build.py')],text=True).strip()
    for name, xml in [('pointer',REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
                      ('keyboard',REPO/'tests/native/virtual-keyboard-unstable-v1.xml')]:
        for mode,suffix in [('client-header','h'),('private-code','c')]:
            subprocess.run(['wayland-scanner',mode,str(xml),str(root/f'virtual-{name}.{suffix}')],check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True))
    subprocess.run(['cc','-I'+str(root),str(REPO/'tests/native/gesture-input.c'),str(root/'virtual-pointer.c'),
                    str(root/'virtual-keyboard.c'),'-o',str(root/'input'),*flags],check=True)
    runtime = Path(tempfile.mkdtemp(prefix='ft-'))
    home = root/'home';home.mkdir()
    wobble=root/'wobbly.json';wobble_values=dict(wobble_model.DEFAULTS);wobble.write_text(wobble_model.encode(wobble_values))
    parent = os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'): parent = str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=parent,
               XDG_CONFIG_HOME=str(home/'.config'), XDG_DATA_HOME=str(home/'.local/share'),
               XDG_CACHE_HOME=str(home/'.cache'), XDG_STATE_HOME=str(home/'.local/state'),
               AQ_BACKENDS='wayland', HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1',
               QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='', QT_PLUGIN_PATH='',
               QT_WAYLAND_DISABLE_WINDOWDECORATION='1', GSETTINGS_BACKEND='memory',
               XCURSOR_THEME='Adwaita', XCURSOR_SIZE='24',XETAL_WOBBLY_CONFIG=str(wobble))
    for key in ('HYPRLAND_INSTANCE_SIGNATURE','DISPLAY','DBUS_SESSION_BUS_ADDRESS'): env.pop(key,None)
    children=[];logs=[];input_process=None;results=[]
    def spawn(args,**kwargs):
        log=(root/f'process-{len(children)}.log').open('w');logs.append(log)
        process=subprocess.Popen(args,env=env,stdout=log,stderr=log,**kwargs);children.append(process);return process
    def ctl(*args):
        return subprocess.check_output(['hyprctl',*args],env=env,text=True,stderr=subprocess.STDOUT,timeout=10).strip()
    def dispatch(*args): assert ctl('dispatch',*args)=='ok',args
    def wait(predicate,label):
        for _ in range(100):
            if predicate(): return
            time.sleep(.05)
        raise AssertionError('Timed out: '+label)
    def client(): return next((c for c in json.loads(ctl('-j','clients')) if c['title']=='Text drag fixture'),None)
    def cursor(): return json.loads(ctl('xetal-cursor'))
    conf=root/'hyprland.conf'
    conf.write_text(f'''monitor=,1100x700@60,auto,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
animations:enabled=false
xwayland:enabled=false
bindm=SUPER,mouse:272,movewindow
bindn=,mouse:272,event,xetal-floating-drag-press
bindinr=,mouse:272,event,xetal-floating-drag-release
windowrule=match:tag ^xetal-title-drag$,no_anim on
plugin={plugin}
''')
    compositor=spawn(['Hyprland','--config',str(conf)],start_new_session=True)
    try:
        instance=None
        for _ in range(100):
            assert compositor.poll() is None,'Nested compositor exited'
            try: instances=json.loads(ctl('-j','instances'))
            except json.JSONDecodeError: instances=[]
            instance=next((i for i in instances if i['pid']==compositor.pid),None)
            if instance: break
            time.sleep(.1)
        assert instance
        env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket'])
        assert not ctl('configerrors'),ctl('configerrors')
        assert ctl('plugin','load',str(wobble_build.build()))=='ok'
        log=(root/'dbus.log').open('w');logs.append(log)
        bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],env=env,stdout=subprocess.PIPE,stderr=log,text=True)
        children.append(bus);env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
        assert env['DBUS_SESSION_BUS_ADDRESS'].startswith('unix:')
        monitor=json.loads(ctl('-j','monitors'))[0]
        input_process=subprocess.Popen([str(root/'input'),str(round(monitor['width']/monitor['scale'])),str(round(monitor['height']/monitor['scale']))],
                                       env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def gesture(command,delay=.1):
            input_process.stdin.write(command+'\n');input_process.stdin.flush()
            assert input_process.stdout.readline().strip()=='ok';time.sleep(delay)
        def drag(start,end):
            gesture(f'move {start[0]} {start[1]}',.2)
            initial=cursor();gesture('button 1')
            pressed=cursor()
            for n in range(1,13): gesture(f'move {round(start[0]+(end[0]-start[0])*n/12)} {round(start[1]+(end[1]-start[1])*n/12)}',.04)
            gesture('button 0',.2)
            return {'hover':initial,'press':pressed}
        fixture=root/'fixture.py'
        fixture.write_text('''from PyQt6.QtWidgets import QApplication,QWidget,QLineEdit,QLabel
from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtGui import QImage,QPixmap,QCursor
from pathlib import Path
import json,struct,sys
root=Path(sys.argv[1]);app=QApplication([])
window=QWidget();window.setWindowFlags(Qt.WindowType.FramelessWindowHint);window.setWindowTitle('Text drag fixture');window.resize(650,350)
edit=QLineEdit('https://example.test/select-this-address',window);edit.setGeometry(80,6,280,24)
label=QLabel('Drag the empty header; select the address text.',window);label.move(80,90)
def bitmap(name):
 data=Path('/usr/share/icons/Adwaita/cursors/'+name).read_bytes();header=struct.unpack_from('<4I',data)
 for n in range(header[3]):
  kind,size,offset=struct.unpack_from('<3I',data,header[1]+n*12)
  if kind!=0xfffd0002 or size!=24:continue
  h,t,s,v,w,height,x,y,d=struct.unpack_from('<9I',data,offset)
  image=QImage(data[offset+h:offset+h+w*height*4],w,height,w*4,QImage.Format.Format_ARGB32_Premultiplied).copy()
  return QCursor(QPixmap.fromImage(image),x,y)
 raise RuntimeError('Missing fixture cursor')
mode=''
def update():
 global mode
 new=(root/'mode').read_text() if (root/'mode').exists() else 'named'
 if new!=mode:
  mode=new
  window.setCursor(bitmap('left_ptr') if mode=='bitmap' else Qt.CursorShape.ArrowCursor)
  edit.setCursor(bitmap('xterm') if mode=='bitmap' else Qt.CursorShape.IBeamCursor)
 (root/'selection.tmp').write_text(json.dumps(dict(mode=mode,selection=edit.selectedText())))
 (root/'selection.tmp').replace(root/'selection.json')
timer=QTimer();timer.timeout.connect(update);timer.start(30)
window.show();app.exec()
''')
        helper=spawn([sys.executable,str(REPO/'config/hypr/scripts/floating-drag.py')])
        spawn([sys.executable,str(fixture),str(root)])
        wait(client,'fixture');address='address:'+client()['address']
        dispatch('setfloating',address);dispatch('resizewindowpixel','exact 650 350,'+address)
        dispatch('movewindowpixel','exact 80 100,'+address)
        wait(lambda:(root/'selection.json').exists(),'selection report')
        assert helper.poll() is None,'Drag helper did not start'
        def selection(): return json.loads((root/'selection.json').read_text())
        for mode in ('named','bitmap'):
            (root/'mode').write_text(mode);wait(lambda:selection()['mode']==mode,'cursor mode')
            x,y=client()['at'];before=[x,y]
            observed=drag([x+280,y+18],[x+100,y+18])
            (root/f'{mode}-text.json').write_text(json.dumps(dict(observed=observed,client=client(),selection=selection()),indent=2))
            subprocess.run(['grim',str(root/f'{mode}-text.png')],env=env,check=True)
            assert client()['at']==before,('Text drag moved window',mode,observed,client()['at'])
            assert selection()['selection'],('Text was not selected',mode)
            # Crossing from text into empty header must still select, not move.
            observed['leaving_field']=drag([x+200,y+18],[x+470,y+18])
            assert client()['at']==before,('Leaving text moved window',mode)
            observed['header']=drag([x+460,y+20],[x+500,y+60])
            assert client()['at']!=before,('Empty header no longer drags',mode,observed)
            results.append(dict(mode=mode,text_selection=True,window_stayed=True,header_moves=True,cursors=observed))
        before=client()['at'];gesture('key 125 1')
        drag([before[0]+200,before[1]+140],[before[0]+240,before[1]+180]);gesture('key 125 0')
        assert client()['at']!=before,'Super-drag must still work'
        assert ctl('keyword','animations:enabled','true')=='ok'
        def wobble_status():return json.loads(ctl('xetal-wobbly'))
        for normal,hotkey in ((True,False),(False,True)):
            wobble_values.update(normal_drag=normal,hotkey_drag=hotkey);wobble.write_text(wobble_model.encode(wobble_values));dispatch('xetalwobbly:reload')
            dispatch('movewindowpixel','exact 80 100,'+address);time.sleep(.4)
            x,y=client()['at'];grabs=wobble_status()['grabs'];before=[x,y]
            drag([x+460,y+20],[x+500,y+60])
            assert client()['at']!=before,('Normal drag must move with either toggle',normal,client(),cursor(),wobble_status())
            assert wobble_status()['grabs']-grabs==int(normal),('Normal drag switch',normal,wobble_status())
            wait(lambda:wobble_status()['active']==0,'normal wobble settles')
            x,y=client()['at'];grabs=wobble_status()['grabs'];before=[x,y];gesture('key 125 1')
            drag([x+150,y+100],[x+185,y+135]);gesture('key 125 0')
            assert client()['at']!=before,'Hotkey drag must move with either toggle'
            assert wobble_status()['grabs']-grabs==int(hotkey),('Hotkey drag switch',hotkey,wobble_status())
            wait(lambda:wobble_status()['active']==0,'hotkey wobble settles')
        print('Wobbly recognizes the text-safe native top grip; both drag switches act independently',flush=True)
        assert helper.poll() is None,'Drag helper crashed'
        (root/'results.json').write_text(json.dumps({'checks':results,'super_drag':True},indent=2)+'\n')
        print(json.dumps({'modes':[r['mode'] for r in results],'text_selection':True,'header_drag':True,'super_drag':True}),flush=True)
    finally:
        if input_process:
            try: input_process.communicate('quit\n',timeout=3)
            except (OSError,subprocess.TimeoutExpired): input_process.terminate()
        if compositor.poll() is None:
            try: ctl('dispatch','exit')
            except Exception: pass
        for process in reversed(children):
            if process.poll() is None: process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        for path in Path('/proc').iterdir():
            if not path.name.isdigit(): continue
            try:
                if path.stat().st_uid==os.getuid() and ('XDG_RUNTIME_DIR='+str(runtime)).encode() in (path/'environ').read_bytes().split(b'\0'):
                    os.kill(int(path.name),signal.SIGTERM)
            except OSError: pass
        for log in logs:log.close()


if __name__=='__main__': main()
