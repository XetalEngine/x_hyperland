#!/usr/bin/env python3
"""Render window focus and test saved appearance on a PRIVATE compositor.

Run from a desktop terminal: python3 tests/check-visuals.py REPORT_DIRECTORY
All compositor commands target the new private instance. No host input is sent.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from PIL import Image,ImageStat

REPO=Path(__file__).resolve().parents[1];SOURCE=REPO/'config/hypr'
sys.path.insert(0,str(SOURCE))
from visuals import model
from compat import hypr_compat


def main():
    directory=Path(sys.argv[1]).resolve();directory.mkdir(parents=True,exist_ok=False)
    report={'passed':False,'checks':[]};children=[]
    runtime=Path(tempfile.mkdtemp(prefix='fv-',dir='/tmp'));(directory/'run').symlink_to(runtime)
    home=directory/'home';root=home/'.config/hypr';root.mkdir(parents=True)
    for relative in ('visuals','compat'):
        shutil.copytree(SOURCE/relative,root/relative,ignore=shutil.ignore_patterns('__pycache__','.settings.lock','settings.json'))
    (root/'theme').mkdir();(root/'theme/state.json').write_text('{"design":"raw"}')
    shutil.copy2(SOURCE/'theme/palettes.json',root/'theme/palettes.json')
    (root/'hyprland.conf').write_text('''monitor=,1280x800@60,auto,1
monitor=VISUALS-A,1280x800@60,0x0,1
monitor=WAYLAND-1,640x400@60,1280x0,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
debug:enable_stdout_logs=true
xwayland:enabled=false
animations:enabled=true
windowrule=match:class ^fusion-overlay-target$, workspace 1 silent
windowrule=match:class ^fusion-sample$, workspace 1 silent, float on, center on
workspace=1,monitor:VISUALS-A,default:true,persistent:true
workspace=2,monitor:VISUALS-A,persistent:true
''')
    shutil.copy2(SOURCE/'compat/entry.lua',root/'hyprland.lua')
    env={k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_INSTANCE','XETAL_'))}
    parent=Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute():parent=Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env.update(HOME=str(home),XDG_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),
               XDG_STATE_HOME=str(home/'.local/state'),AQ_BACKENDS='wayland',WAYLAND_DISPLAY=str(parent),
               HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',QT_QPA_PLATFORM='wayland',QT_QPA_PLATFORMTHEME='',
               GSETTINGS_BACKEND='memory',PATH=str(root/'compat/bin')+':/usr/bin:/bin')
    for name in ('DISPLAY','DBUS_SESSION_BUS_ADDRESS'):env.pop(name,None)
    def wait(predicate,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=predicate()
            if value:return value
            if children and children[0].poll() is not None:raise RuntimeError('Private compositor exited; see compositor.log')
            time.sleep(.05)
        raise RuntimeError('Timed out waiting for private visual test state')
    def run(*args):
        process=subprocess.run(args,env=env,capture_output=True,text=True,timeout=40)
        if process.returncode:raise RuntimeError(process.stdout+process.stderr)
        return process.stdout.strip()
    def ctl(*args):return run('/usr/bin/python3',str(root/'compat/bin/hyprctl'),*args)
    def check(name,okay):
        report['checks'].append({'name':name,'passed':bool(okay)})
        print(('PASS ' if okay else 'FAIL ')+name,flush=True)
        if not okay:raise RuntimeError(name)
    with (directory/'compositor.log').open('w') as log,(directory/'apps.log').open('w') as app_log:
        def start(*args):
            child=subprocess.Popen(args,env=env,stdout=app_log,stderr=app_log);children.append(child);return child
        try:
            children.append(subprocess.Popen(['Hyprland','-c',str(root/'hyprland.lua')],env=env,stdout=log,stderr=log,start_new_session=True))
            socket=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None))
            env['HYPRLAND_INSTANCE_SIGNATURE']=socket.parent.name
            env['WAYLAND_DISPLAY']=str(wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None)))
            check('private compositor started',True)
            ctl('output','create','headless','VISUALS-A')
            wait(lambda:any(m['name']=='VISUALS-A' for m in json.loads(ctl('-j','monitors'))))
            ctl('dispatch','focusmonitor','VISUALS-A');ctl('dispatch','workspace','1')
            start(sys.executable,str(REPO/'tests/overlay/target.py'),str(directory/'target.json'))
            wait(lambda:any(c.get('class')=='fusion-overlay-target' and c.get('mapped') for c in json.loads(ctl('-j','clients'))))
            start(sys.executable,str(SOURCE/'visuals/app.py'),'sample')
            wait(lambda:any(c.get('class')=='fusion-sample' and c.get('mapped') for c in json.loads(ctl('-j','clients'))))
            values=deepcopy(model.DEFAULTS);values['focus'].update(enabled=True,shadow=10)
            path=root/'visuals/settings.json';hashes=set()
            for border,glow in ((2,False),(4,True)):
                values['focus'].update(border=border,glow=glow)
                path.write_text(json.dumps(values));ctl('reload');time.sleep(.4)
                check('focus has no configuration error',not ctl('configerrors'))
                check('saved border reaches the compositor',json.loads(ctl('-j','getoption','general:border_size'))['int']==border)
                check('saved glow reaches the compositor',json.loads(ctl('-j','getoption','decoration:glow:enabled'))['bool']==glow)
                image_path=directory/('focus-'+str(border)+'.png');run('grim','-o','VISUALS-A',str(image_path))
                with Image.open(image_path).convert('RGB') as picture:
                    check('focus renders a populated output',picture.size==(1280,800) and max(ImageStat.Stat(picture).stddev)>15)
                    hashes.add(hashlib.sha256(picture.tobytes()).hexdigest())
            check('focus choices change the rendered output',len(hashes)==2)
            before=path.read_bytes()
            (root/'theme/state.json').write_text('{"design":"starcraft","mode":"dark"}');ctl('reload')
            check('changing theme preserves saved focus',path.read_bytes()==before and
                  json.loads(ctl('-j','getoption','general:border_size'))['int']==4 and
                  json.loads(ctl('-j','getoption','decoration:glow:enabled'))['bool'] is True)
            code='''import sys,time,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from visuals import controller,model
root=Path(sys.argv[1]);values=model.load(root)[0];values['focus']['border']=7
controller.preview(values,root,seconds=2)
state=json.loads(controller.ctl('-j','getoption','general:border_size'))
assert state.get('int')==7, 'Preview did not change the border: '+repr(state)
time.sleep(3.2)
assert not (controller.instance()/'fusion-visuals/preview.json').exists()
state=json.loads(controller.ctl('-j','getoption','general:border_size'))
assert state.get('int')==4, 'Preview expiry did not restore the border: '+repr(state)
'''
            run(sys.executable,'-c',code,str(root))
            check('temporary preview restores focus and preserves saved preferences',path.read_bytes()==before)
            report['passed']=True
        except Exception:
            report['error']=traceback.format_exc();print(report['error'],flush=True)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=4)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
            (directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(('PASS' if report['passed'] else 'FAILED')+' — '+str(directory/'result.json'),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
