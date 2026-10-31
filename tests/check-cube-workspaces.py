#!/usr/bin/env python3
"""Exercise native cube policy and cursor effects in a disposable compositor only."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'config/hypr'))
from effects.cube import model
from cursors import model as cursors


def main():
    binary=Path(sys.argv[1]).resolve(strict=True)
    root=Path(sys.argv[2]);root.mkdir(parents=True,exist_ok=False)
    profile=root/'profile';config=profile/'effects/cube/settings.json';config.parent.mkdir(parents=True)
    values=model.validate(model.DEFAULTS);values['duration']=450;config.write_text(model.encode(values))
    cursorfile=profile/'cursors/settings.json';cursorfile.parent.mkdir()
    cursorvalues=dict(cursors.DEFAULTS,trail='comet',click_ripple=True)
    cursorfile.write_bytes(cursors.encode(cursorvalues))
    (profile/'cursors/.build').symlink_to(REPO/'config/hypr/cursors/.build',target_is_directory=True)
    conf=root/'hyprland.conf';conf.write_text('''monitor = ,1280x800@60,auto,1
misc {
 disable_hyprland_logo = true
 disable_splash_rendering = true
}
xwayland {
 enabled = false
}
''')
    rule=re.search(r'windowrule \{\n    name = fusion-task-switcher\n.*?\n}',(REPO/'config/hypr/hyprland.conf').read_text(),re.S).group()
    conf.write_text(conf.read_text()+rule+'\n')
    env=dict(os.environ);env.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
    env.update(AQ_BACKENDS=os.environ.get('XETAL_TEST_BACKEND','wayland'),XETAL_CUBE_CONFIG=str(config),GSETTINGS_BACKEND='memory')
    children=[]
    with (root/'compositor.log').open('w') as log:
        comp=subprocess.Popen(['Hyprland','-c',str(conf)],env=env,stdout=log,stderr=log,start_new_session=True);children.append(comp)
        try:
            for _ in range(100):
                if comp.poll() is not None:raise RuntimeError('Nested compositor exited: '+str(root/'compositor.log'))
                instances=json.loads(subprocess.check_output(['hyprctl','-j','instances'],text=True))
                instance=next((i for i in instances if i['pid']==comp.pid),None)
                if instance:
                    env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket']);break
                time.sleep(.1)
            else:raise RuntimeError('No disposable instance')
            def run(*args):
                result=subprocess.run(args,env=env,text=True,capture_output=True,timeout=15)
                if result.returncode:raise RuntimeError(str(args)+result.stdout+result.stderr)
                return result.stdout.strip()
            def ctl(*args):return run('hyprctl',*args)
            def dispatch(*args):
                answer=ctl('dispatch',*args);assert answer=='ok',(args,answer)
            def status():return json.loads(ctl('xetal-cube'))
            def monitors():return json.loads(ctl('-j','monitors'))
            def workspaces():return json.loads(ctl('-j','workspaces'))
            def wait_for(predicate):
                for _ in range(100):
                    if predicate():return
                    time.sleep(.03)
                raise AssertionError('Timed out waiting for native transition')
            time.sleep(.5)
            if not monitors():ctl('output','create','headless','TEST-A')
            ctl('output','create','wayland','TEST-B');time.sleep(.4)
            outputs=monitors();assert len(outputs)>=2,outputs
            a,b=outputs[:2];ctl('keyword','monitor',f"{a['name']},1280x800@60,0x0,1")
            ctl('keyword','monitor',f"{b['name']},1280x800@60,1280x0,1")
            wait_for(lambda:all(m['width']>0 for m in monitors()))
            dispatch('focusmonitor',a['name'])
            for index,n in enumerate((21,22,23,24,25),1):
                dispatch('workspace',str(n))
                child=subprocess.Popen(['kitty','--config','/dev/null','--class','cube-test','-e','sh','-c','sleep 300'],env=env,stdout=log,stderr=log);children.append(child)
                wait_for(lambda:len(json.loads(ctl('-j','clients')))>=index)
            client=next(c for c in json.loads(ctl('-j','clients')) if c['workspace']['id']==24)
            dispatch('focusmonitor',b['name']);dispatch('workspace','name:Research')
            child=subprocess.Popen(['kitty','--config','/dev/null','--class','cube-test','-e','sh','-c','sleep 300'],env=env,stdout=log,stderr=log);children.append(child)
            wait_for(lambda:len(json.loads(ctl('-j','clients')))>=6)
            dispatch('focusmonitor',a['name']);dispatch('workspace','25')
            assert ctl('plugin','load',str(binary))=='ok'
            mapfile=Path(env['XDG_RUNTIME_DIR'])/'hypr'/env['HYPRLAND_INSTANCE_SIGNATURE']/'xetal-cube-faces'
            wait_for(lambda:mapfile.exists() and len(mapfile.read_text().splitlines())==9)
            face_map={int(line.split()[0]):int(line.split()[1]) for line in mapfile.read_text().splitlines()[1:]}
            assignments={m['name']:sorted([w['id'] for w in workspaces() if w['monitor']==m['name'] and w['id'] in face_map]) for m in outputs[:2]}
            assert all(len(ids)==4 for ids in assignments.values()),assignments
            assert {face_map[i] for i in assignments[a['name']]}=={1,2,3,4}
            assert status()['error']=='',status()
            folded=next(c for c in json.loads(ctl('-j','clients')) if c['address']==client['address'])
            assert folded['workspace']['id']!=24,folded['workspace']
            for monitor in (a,b):
                current=next(m for m in monitors() if m['name']==monitor['name'])
                dispatch('movecursor',f"{current['x']+400} {current['y']+400}")
                target=assignments[monitor['name']][1]
                dispatch('xetalcube:workspace','switch 2')
                wait_for(lambda:not status()['active'])
                assert next(m for m in monitors() if m['name']==monitor['name'])['activeWorkspace']['id']==target,(target,monitors(),status())
                before=len(workspaces());dispatch('xetalcube:workspace','switch 9');assert len(workspaces())==before
            dispatch('workspace','name:Research');wait_for(lambda:not status()['active'])
            assert next(m for m in monitors() if m['name']==b['name'])['activeWorkspace']['name']=='Research'
            dispatch('xetalcube:workspace','switch 1');wait_for(lambda:not status()['active'])
            # Taskbar path is the ordinary global-ID dispatcher, also animated.
            target=assignments[a['name']][2];dispatch('workspace',str(target));assert status()['active'];wait_for(lambda:not status()['active'])
            assert next(m for m in monitors() if m['name']==a['name'])['activeWorkspace']['id']==target
            values['workspace_animation']='standard';config.write_text(model.encode(values));dispatch('xetalcube:reload')
            started=status()['started'];dispatch('workspace',str(assignments[a['name']][0]));assert status()['started']==started
            # Trail uses actual compositor movement and becomes idle after its lifetime.
            for x in range(200,600,30):dispatch('movecursor',f'{x} 300');time.sleep(.012)
            assert status()['cursor_marks']>0,status()
            run('grim','-o',a['name'],str(root/'trail.png'))
            from PIL import Image
            pixels=Image.open(root/'trail.png').convert('RGB').crop((180,280,620,320)).getdata()
            assert sum(b>r+15 and g>r+10 for r,g,b in pixels)>10,'Cursor trail did not render visible pixels'
            wait_for(lambda:status()['cursor_marks']==0)
            for style in cursors.STYLES:
                cursorvalues['style']=style;cursorfile.write_bytes(cursors.encode(cursorvalues));dispatch('xetalcube:cursor')
            # Prepare placement before mapping: no centered first-frame flash.
            from switcher import placement
            destination=next(m for m in monitors() if m['name']==b['name'])
            rx,ry=placement.prepare(destination,800,500,ctl)
            code='from PyQt6.QtWidgets import QApplication,QWidget; a=QApplication([]); a.setApplicationName("xetal-switcher"); a.setDesktopFileName("xetal-switcher"); w=QWidget(); w.resize(800,500); w.show(); a.exec()'
            popup=subprocess.Popen(['python3','-c',code],env={**env,'QT_QPA_PLATFORM':'wayland'},stdout=log,stderr=log);children.append(popup)
            seen=[]
            for _ in range(80):
                seen.extend(c for c in json.loads(ctl('-j','clients')) if c['pid']==popup.pid)
                if len(seen)>=5:break
                time.sleep(.02)
            assert seen and all(c['monitor']==destination['id'] and c['at']==[destination['x']+rx,destination['y']+ry] for c in seen),seen
            popup.terminate();popup.wait(timeout=5)
            # Reload does not create extra faces, including repeated enable/disable.
            ctl('reload');time.sleep(.2);assert len(mapfile.read_text().splitlines())==9
            values['enabled']=False;config.write_text(model.encode(values));dispatch('xetalcube:reload')
            assert mapfile.read_text().startswith('disabled')
            restored=next(c for c in json.loads(ctl('-j','clients')) if c['address']==client['address'])
            assert restored['workspace']['id']==24,restored['workspace']
            for effect in ('glow','sparkle','none'):
                cursorvalues['trail']=effect;cursorfile.write_bytes(cursors.encode(cursorvalues));dispatch('xetalcube:cursor')
                for x in range(200,500,25):dispatch('movecursor',f'{x} 300');time.sleep(.012)
                if effect=='none':assert status()['cursor_marks']==0
                else:
                    assert status()['cursor_marks']>0
                    run('grim','-o',a['name'],str(root/('trail-'+effect+'.png')))
                    wait_for(lambda:status()['cursor_marks']==0)
            dispatch('xetalcube:workspace','switch 9');assert any(m['activeWorkspace']['id']==9 for m in monitors())
            values['enabled']=True;config.write_text(model.encode(values));dispatch('xetalcube:reload')
            ctl('output','remove',b['name']);time.sleep(.4)
            assert len(mapfile.read_text().splitlines())==5,mapfile.read_text()
            assert ctl('plugin','unload',str(binary))=='ok'
            assert mapfile.read_text().startswith('disabled')
            print('PASS: four faces/output, local shortcuts, global taskbar rotation, standard animation, overflow restore, cursor styles/trails/idle, reload, hot-unplug, unload.',flush=True)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:child.kill();child.wait()

if __name__=='__main__':main()
