#!/usr/bin/env python3
"""Check Echo-shaped ARGB overlays on a private nested Hyprland session.

Usage: check-echo-overlay.py OUTPUT_DIRECTORY
Only synthetic pixels and clicks are used. Never launches or modifies Echo.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import traceback
from PIL import Image,ImageChops,ImageStat

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'config/hypr/compat'))
import hypr_compat


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=False)
    home=root/'home';home.mkdir();runtime=Path(tempfile.mkdtemp(prefix='ovl-',dir='/tmp'))
    (root/'run').symlink_to(runtime,target_is_directory=True)
    report={'passed':False,'checks':[],'runtime':str(runtime)};children=[];logs=[];comp=None
    rule=re.search(r'windowrule \{\n    name = hyperfusion-echo-overlay\n.*?\n\}',(REPO/'config/hypr/hyprland.conf').read_text(),re.S).group()
    baseline='''monitor = ,1024x768@60,auto,1
monitor = WAYLAND-1,800x450@60,1024x0,1
monitor = OVERLAY,1024x768@60,0x0,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
misc:disable_hyprland_guiutils_check = true
animations:enabled = false
decoration:blur:enabled = true
decoration:blur:size = 8
decoration:blur:passes = 3
decoration:blur:ignore_opacity = true
general:border_size = 0
decoration:rounding = 0
windowrule = match:title ^Overlay input target$, float on, monitor OVERLAY, size 900 650, move 60 100
debug:enable_stdout_logs = true
debug:disable_logs = false
'''
    config=root/'hyprland.conf';config.write_text(baseline)
    lua=root/'hyprland.lua';lua.write_text(hypr_compat.Renderer(root).render())
    parent=Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute():parent=Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env={k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_INSTANCE','XETAL_'))}
    env.update(HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),
        XDG_STATE_HOME=str(home/'.local/state'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=str(parent),
        AQ_BACKENDS='wayland',HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',
        QT_QPA_PLATFORMTHEME='',QT_QPA_PLATFORM='wayland',PATH='/usr/bin:/bin')
    env.pop('DBUS_SESSION_BUS_ADDRESS',None);env.pop('DISPLAY',None)
    def run(*args):
        p=subprocess.run(args,env=env,capture_output=True,text=True,timeout=20)
        if p.returncode:raise RuntimeError(str(args)+': '+p.stdout+p.stderr)
        return p.stdout.strip()
    def spawn(args,label,extra=None):
        log=(root/(label+'.log')).open('w');logs.append(log)
        child=subprocess.Popen(args,env={**env,**(extra or {})},stdout=log,stderr=log,start_new_session=True)
        children.append(child);return child
    def stop(child):
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=4)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=4)
    def wait(predicate,seconds=15):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if comp and comp.poll() is not None:raise RuntimeError('Private compositor exited; see compositor.log')
            value=predicate()
            if value:return value
            time.sleep(.05)
        raise RuntimeError('Timed out waiting for private overlay test state')
    def ctl(*args):return run('/usr/bin/hyprctl',*args)
    def dispatch(action,argument=''):return ctl('dispatch',hypr_compat.dispatcher(action,argument))
    def clients():return json.loads(ctl('-j','-a','clients'))
    def target():return next((w for w in clients() if w.get('title')=='Overlay input target' and w.get('mapped')),None)
    def overlay():return next((w for w in clients() if w.get('title')=='Echo Overlay'),None)
    def click_count():
        try:return json.loads((root/'clicks.json').read_text())['clicks']
        except (OSError,ValueError,KeyError):return -1
    def click():
        window=target();x,y=window['at'];w,h=window['size']
        run(str(root/'pointer'),'OVERLAY',str(round(x+w/2)),str(round(y+h/2)),'1024','768')
    def capture(name):
        path=root/(name+'.png');run('grim','-o','OVERLAY',str(path));return Image.open(path).convert('RGB')
    def difference(before,after):
        # Avoid the roster, window edges and pointer. Compare only the
        # synthetic checkerboard seen through transparent overlay pixels.
        return max(ImageStat.Stat(ImageChops.difference(before.crop((250,250,450,450)),after.crop((250,250,450,450)))).mean)
    def check(name,okay,detail=None):
        report['checks'].append({'name':name,'passed':bool(okay),'detail':detail})
        print(('PASS ' if okay else 'FAIL ')+name,flush=True)
        if not okay:raise RuntimeError(name)
    def snapshot(name):
        result={}
        for command in ('clients','monitors','activewindow','cursorpos'):
            try:result[command]=json.loads(ctl('-j',command))
            except Exception as error:result[command]={'error':str(error)}
        try:result['target']=json.loads((root/'clicks.json').read_text())
        except (OSError,ValueError):pass
        report.setdefault('states',{})[name]=result
        return result
    try:
        # Build standalone fixtures only, with no Echo/application dependencies.
        run('cc','-Wall','-Wextra','-Werror',str(REPO/'tests/overlay/surface.c'),'-o',str(root/'surface'),'-lX11','-lXfixes','-lXrender')
        xml=REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'
        run('wayland-scanner','client-header',str(xml),str(root/'virtual-pointer.h'))
        run('wayland-scanner','private-code',str(xml),str(root/'virtual-pointer.c'))
        run('cc','-Wall','-Wextra','-Werror','-I'+str(root),str(REPO/'tests/overlay/pointer.c'),str(root/'virtual-pointer.c'),'-o',str(root/'pointer'),'-lwayland-client')
        comp=spawn(['/usr/bin/Hyprland','-c',str(lua)],'compositor')
        endpoint=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None))
        env['HYPRLAND_INSTANCE_SIGNATURE']=endpoint.parent.name
        env['WAYLAND_DISPLAY']=str(wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None)))
        ctl('output','create','headless','OVERLAY')
        wait(lambda:any(m['name']=='OVERLAY' for m in json.loads(ctl('-j','monitors'))))
        dispatch('focusmonitor','OVERLAY')
        xdisplay=root/'xdisplay'
        ctl('dispatch',hypr_compat.dispatcher('exec','sh -c '+shlex.quote('printf "%s" "$DISPLAY" > '+shlex.quote(str(xdisplay)))))
        wait(lambda:xdisplay.exists() and xdisplay.read_text());env['DISPLAY']=xdisplay.read_text()
        for platform in ('wayland','xcb'):
            config.write_text(baseline);lua.write_text(hypr_compat.Renderer(root).render());ctl('reload')
            dispatch('focusmonitor','OVERLAY')
            (root/'clicks.json').unlink(missing_ok=True)
            client=spawn([sys.executable,str(REPO/'tests/overlay/target.py'),str(root/'clicks.json')],platform+'-target',{'QT_QPA_PLATFORM':platform})
            window=wait(target);dispatch('focuswindow','address:'+window['address'])
            wait(lambda:json.loads(ctl('-j','activewindow')).get('address')==window['address'])
            time.sleep(.4);snapshot(platform+'-before-click');capture(platform+'-before-click')
            click();wait(lambda:click_count()==1,seconds=4)
            check(platform+' ordinary window receives baseline click',True,snapshot(platform+'-baseline-click')['target'])
            clean=capture(platform+'-clean')
            helper=spawn([str(root/'surface')],platform+'-overlay');wait(overlay);time.sleep(.5)
            unfixed=capture(platform+'-baseline');count=click_count();click();time.sleep(.3)
            report.setdefault('baseline',{})[platform]={'blur_difference':difference(clean,unfixed),'click_passed':click_count()>count}
            config.write_text(baseline+'\n'+rule+'\n');lua.write_text(hypr_compat.Renderer(root).render());ctl('reload');time.sleep(.4)
            check(platform+' overlay rule reload has no configuration errors',not ctl('configerrors'))
            fixed=capture(platform+'-fixed');delta=difference(clean,fixed)
            check(platform+' transparent overlay does not blur the desktop',delta<3,delta)
            pixel=fixed.getpixel((60,45));check(platform+' overlay remains visible',pixel[0]>200 and pixel[1]<120,pixel)
            count=click_count();click();time.sleep(.3)
            check(platform+' clicks reach the window under the existing overlay',click_count()==count+1)
            stop(helper);wait(lambda:not overlay());helper=spawn([str(root/'surface')],platform+'-reopened-overlay');wait(overlay);time.sleep(.3)
            count=click_count();click();time.sleep(.3)
            check(platform+' newly opened overlay remains click-through',click_count()==count+1)
            stop(helper);wait(lambda:not overlay());count=click_count();click();time.sleep(.3)
            check(platform+' ordinary window remains interactive after overlay closes',click_count()==count+1)
            stop(client);wait(lambda:not target())
        report['passed']=True
    except Exception as error:
        report['error']=str(error);traceback.print_exc()
        if comp and comp.poll() is None:
            snapshot('failure')
            try:capture('failure')
            except Exception:pass
    finally:
        for child in reversed(children):stop(child)
        for log in logs:log.close()
        (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(('PASS' if report['passed'] else 'FAILED')+' — '+str(root/'result.json'),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
