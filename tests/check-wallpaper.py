#!/usr/bin/env python3
"""Exercise GPU transitions, real hyprpaper and Qt selection in a nested session.

Usage: python3 tests/check-wallpaper.py /tmp/new-wallpaper-test-directory
Never changes the parent compositor's wallpapers or user preferences.
"""
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from PIL import Image

REPO=Path(__file__).resolve().parents[1]


def main():
    root=Path(sys.argv[1]); root.mkdir(parents=True,exist_ok=False)
    profile=root/'hypr'; shutil.copytree(REPO/'config/hypr',profile,ignore=shutil.ignore_patterns('.build','__pycache__','qt5','qt6','gtk3','qt-settings','cache','state'))
    runtime=Path(tempfile.mkdtemp(prefix='wp-',dir='/tmp'))
    parent=os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'): parent=str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=parent,GSETTINGS_BACKEND='memory',QT_QPA_PLATFORM='wayland',PYTHONFAULTHANDLER='1')
    env.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
    config=root/'hyprland.conf'
    config.write_text('''monitor = ,1280x800@60,auto,1
misc {
 disable_hyprland_logo = true
 disable_splash_rendering = true
}
animations {
 enabled = false
}
windowrule {
 name = fusion-wallpaper-browser
 match:class = ^(xetal-wallpaper-browser)$
 match:title = ^Wallpapers$
 float = on
 border_size = 0
 no_anim = on
 size = 1200 720
 center = on
}
windowrule {
 name = fusion-wallpaper-overlay
 match:class = ^(xetal-wallpaper-browser)$
 match:title = ^Wallpapers · Floating cards$
 float = on
 border_size = 0
 rounding = 0
 no_blur = on
 no_shadow = on
 no_anim = on
 size = 1200 720
 center = on
}
layerrule = no_anim on, match:namespace ^xetal-wallpaper-transition$
''')
    pictures=root/'pictures'; pictures.mkdir()
    for name,color in [('red','#c03040'),('blue','#2040d0'),('green','#30b070')]: Image.new('RGB',(1280,800),color).save(pictures/(name+'.png'))
    (profile/'wallpaper/state').mkdir(); (profile/'wallpaper/state/browser.json').write_text(json.dumps({'version':1,'folders':[str(pictures)],'bundled':True,'transition':'random'}))
    (profile/'wallpaper/selection.json').write_text('{}\n')
    paper_config=root/'hyprpaper.conf'; paper_config.write_text(f'ipc = true\nsplash = false\nwallpaper {{\n monitor =\n path = {pictures/"red.png"}\n fit_mode = cover\n}}\n')
    children=[]; logs=[]
    def spawn(args,**kwargs):
        p=subprocess.Popen(args,**kwargs); children.append(p); return p
    def run(*args):
        r=subprocess.run(args,env=env,text=True,capture_output=True,timeout=15)
        if r.returncode: raise RuntimeError(str(args)+': '+r.stdout+r.stderr)
        return r.stdout.strip()
    def ctl(*args): return run('hyprctl',*args)
    def wait(predicate,timeout=8):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.04)
        raise AssertionError('Timed out')
    def shot(name,output):
        path=root/(name+'.png'); run('grim','-o',output,str(path)); return Image.open(path).convert('RGB')
    def ready(child,token,timeout=7):
        assert select.select([child.stdout],[],[],timeout)[0], 'helper timeout'
        assert child.stdout.readline().strip()==token,(token,child.poll())
    def helper(monitor,style='bloom'):
        w,h=monitor['width'],monitor['height']
        if monitor.get('transform',0)%2:w,h=h,w
        scale=monitor.get('scale',1)
        log=(root/('transition-'+style+'.log')).open('a');logs.append(log)
        child=spawn([binary,str(monitor['x']),str(monitor['y']),str(round(w/scale)),str(round(h/scale)),str(pictures/'red.png'),'cover',str(pictures/'blue.png'),'cover',style],
                    env=dict(env,GDK_BACKEND='wayland'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log)
        ready(child,b'READY');return child
    try:
        log=(root/'compositor.log').open('w');logs.append(log)
        compositor=spawn(['Hyprland','-c',str(config)],env=env,stdout=log,stderr=log,start_new_session=True)
        for _ in range(100):
            assert compositor.poll() is None
            try: instance=next((i for i in json.loads(run('hyprctl','-j','instances')) if i['pid']==compositor.pid),None)
            except (ValueError,RuntimeError): instance=None
            if instance and (runtime/'hypr'/instance['instance']/'.socket.sock').exists():
                env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket']);break
            time.sleep(.1)
        else: raise RuntimeError('No nested compositor')
        time.sleep(1)
        first=json.loads(ctl('-j','monitors'))[0]; name=first['name']
        log=(root/'hyprpaper.log').open('w');logs.append(log)
        paper=spawn(['hyprpaper','-c',str(paper_config)],env=env,stdout=log,stderr=log)
        time.sleep(1); assert paper.poll() is None
        binary=run(sys.executable,str(profile/'wallpaper/build.py'))
        assert not ctl('configerrors').strip()
        for style in ('bloom','fade','sweep','ripple','iris','glide'):
            ctl('hyprpaper','wallpaper',f'{name},{pictures/"red.png"},cover'); time.sleep(.2)
            child=helper(first,style)
            before=shot(style+'-before',name); point=(before.width//2,before.height//2)
            assert before.getpixel(point)[0]>150,before.getpixel(point)
            ctl('hyprpaper','wallpaper',f'{name},{pictures/"blue.png"},cover')
            # The overlay must cover the persistent update until GO.
            assert shot(style+'-held',name).getpixel(point)[0]>150
            child.stdin.write(b'GO\n');child.stdin.flush();time.sleep(.35)
            middle=shot(style+'-middle',name);ready(child,b'DONE')
            child.stdin.close();child.wait(timeout=2);time.sleep(.1)
            after=shot(style+'-after',name);assert after.getpixel(point)[2]>150,after.getpixel(point)
            assert middle.tobytes()!=before.tobytes() and middle.tobytes()!=after.tobytes()
        print('All six GPU transitions: real intermediate frames and seamless hyprpaper handoff passed',flush=True)
        # EOF/crash cleanup removes only the temporary layer.
        child=helper(first); child.stdin.close();child.wait(timeout=2)
        assert 'xetal-wallpaper-transition' not in ctl('-j','layers')
        ctl('keyword','animations:enabled','true')
        log=(root/'browser.log').open('w');logs.append(log)
        browser=spawn([sys.executable,str(REPO/'tests/wallpaper-client.py'),str(profile)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
        def command(op,**args):
            assert browser.poll() is None, ('Browser exited',browser.returncode,op)
            browser.stdin.write(json.dumps({'op':op,**args})+'\n');browser.stdin.flush()
            assert select.select([browser.stdout],[],[],10)[0], 'UI timeout'
            reply=json.loads(browser.stdout.readline());assert not isinstance(reply,dict) or 'error' not in reply,reply;return reply
        wait(lambda:command('status')['pictures']==15)
        assert command('status')['selected']==str(pictures/'blue.png')
        assert command('status')['monitor']==name
        time.sleep(.8)
        command('grab',path=str(root/'browser.png'))
        command('choose',path=str(pictures/'green.png'));wait(lambda:command('status')['completed'])
        saved=json.loads((profile/'wallpaper/selection.json').read_text());assert saved[name]['original']==str(pictures/'green.png')
        assert command('status')['dialog']==''
        print('Single-display selection applied directly and persisted: passed',flush=True)
        ctl('output','create','wayland');wait(lambda:len(json.loads(ctl('-j','monitors')))==2)
        second=next(m for m in json.loads(ctl('-j','monitors')) if m['name']!=name)
        ctl('keyword','monitor',f'{second["name"]},800x600@60,{first["width"]}x0,1');time.sleep(.7)
        command('show');command('choose',path=str(pictures/'blue.png'));wait(lambda:command('status')['dialog']=='ScreenPicker')
        command('grab-dialog',path=str(root/'monitor-picker.png'));command('cancel')
        assert json.loads((profile/'wallpaper/selection.json').read_text())==saved
        command('choose',path=str(pictures/'blue.png'));wait(lambda:command('status')['dialog']=='ScreenPicker')
        command('select',name=second['name']);wait(lambda:command('status')['completed'])
        saved2=json.loads((profile/'wallpaper/selection.json').read_text());assert saved2[name]==saved[name];assert saved2[second['name']]['original']==str(pictures/'blue.png')
        print('Two-display arrangement, cancel, apply only clicked output: passed',flush=True)
        # Each fresh opening follows the hosting output, including cached sources.
        for monitor,expected in ((first,'green'),(second,'blue')):
            command('quit');assert browser.wait(timeout=5)==0
            monitor=next(m for m in json.loads(ctl('-j','monitors')) if m['name']==monitor['name'])
            ctl('dispatch','movecursor',str(monitor['x']+100),str(monitor['y']+100))
            browser=spawn([sys.executable,str(REPO/'tests/wallpaper-client.py'),str(profile)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
            wait(lambda:command('status')['pictures']==15)
            assert command('status')['monitor']==monitor['name'],command('status')
            assert command('status')['selected']==str(pictures/(expected+'.png')),command('status')
            client=next(c for c in json.loads(ctl('-j','clients')) if c['class']=='xetal-wallpaper-browser')
            assert client['monitor']==monitor['id'],client
        print('Current wallpaper centered independently on both hosting displays: passed',flush=True)
        # Reject a stale target without replacing either saved choice.
        command('show');command('choose',path=str(pictures/'red.png'));wait(lambda:command('status')['dialog']=='ScreenPicker')
        ctl('output','remove',second['name']);command('select',name=second['name']);wait(lambda:not command('status')['busy'])
        assert 'disconnected' in command('status')['status'];assert json.loads((profile/'wallpaper/selection.json').read_text())==saved2
        print('Disconnected monitor rejected without changing saved wallpapers: passed',flush=True)
        command('quit');assert browser.wait(timeout=5)==0
        # Real layer-shell matching on a fractional-scale portrait output.
        ctl('keyword','monitor',f'{name},1000x750@60,0x0,1.25,transform,1');time.sleep(.7)
        rotated=json.loads(ctl('-j','monitors'))[0]
        assert rotated['scale']==1.25 and rotated['transform']==1
        child=helper(rotated);child.stdin.close();assert child.wait(timeout=3)==0
        ctl('keyword','monitor',f'{name},1280x800@60,0x0,1,transform,0');time.sleep(.7)
        print('Fractional-scale portrait output transition: passed',flush=True)
        # App-level single-instance toggle with the actual launcher and lifetime socket.
        log=(root/'singleton.log').open('w');logs.append(log)
        for style in ('window','overlay'):
            preferences=profile/'wallpaper/state/browser.json'
            options=json.loads(preferences.read_text());options['style']=style;preferences.write_text(json.dumps(options))
            desktop=shot('desktop-'+style,name)
            app=spawn([sys.executable,str(profile/'wallpaper/launch.py')],env=env,stdout=log,stderr=log)
            wait(lambda:any(c['class']=='xetal-wallpaper-browser' for c in json.loads(ctl('-j','clients'))))
            time.sleep(.5)
            client=next(c for c in json.loads(ctl('-j','clients')) if c['class']=='xetal-wallpaper-browser')
            assert client['floating'],client
            view=shot('selector-'+style,name);x,y=client['at'];point=(x+2,y+2)
            assert (view.getpixel(point)==desktop.getpixel(point))==(style=='overlay'), (style,point)
            run(sys.executable,str(profile/'wallpaper/launch.py'),'--show');assert app.poll() is None
            # Settings can switch an open selector without toggling it closed.
            options['style']='window' if style=='overlay' else 'overlay';preferences.write_text(json.dumps(options))
            run(sys.executable,str(profile/'wallpaper/launch.py'),'--show')
            title='Wallpapers' if options['style']=='window' else 'Wallpapers · Floating cards'
            wait(lambda:any(c['title']==title for c in json.loads(ctl('-j','clients'))))
            assert app.poll() is None
            assert len([c for c in json.loads(ctl('-j','clients')) if c['class']=='xetal-wallpaper-browser'])==1
            run(sys.executable,str(profile/'wallpaper/launch.py'));assert app.wait(timeout=5)==0
            assert not any(c['class']=='xetal-wallpaper-browser' for c in json.loads(ctl('-j','clients')))
        print('Both styles, transparent desktop, Settings show/switch, singleton toggle and clean exit: passed',flush=True)
        print('WALLPAPER INTEGRATION PASS',flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None: child.terminate()
        for child in reversed(children):
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        for log in logs:log.close()


if __name__=='__main__':main()
