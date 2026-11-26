#!/usr/bin/python3
"""Pixel checks on private headless outputs of a nested Hyprland 0.57 session.

Usage: check-cube-render.py PLUGIN DIRECTORY
Never loads plugins or changes settings in the working desktop. All images,
configuration and logs remain in DIRECTORY. Needs Hyprland, grim, GTK layer
shell and Pillow. Run outside a sandbox that forbids Wayland/IPC sockets.
"""
from nested_session import nested_environment
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback
from PIL import Image, ImageChops, ImageStat

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'config/hypr'), str(REPO/'config/hypr/compat')]
from effects.cube import model
from effects.window_close import model as buttons_model, rules as buttons_rules
from effects.minimize import model as minimize_model
import hypr_compat

COLORS = ((230,35,45), (30,210,65), (40,75,230), (235,205,30))


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    root = Path(sys.argv[2]).resolve(); root.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'plugin': str(binary), 'checks': [], 'failures': []}
    children = []
    home = root/'home'; home.mkdir()
    # AF_UNIX paths are limited to 108 bytes, including Hyprland's instance ID.
    runtime = Path(tempfile.mkdtemp(prefix='fc-',dir='/tmp'))
    (root/'run').symlink_to(runtime,target_is_directory=True)
    report['runtime']=str(runtime)
    cube = home/'.config/hypr/effects/cube'; cube.mkdir(parents=True)
    picture = Image.new('RGB', (1280,800))
    picture.putdata([(30+x*180//1280,30+y*180//800,50+(x//37+y//29)%2*130)
                     for y in range(800) for x in range(1280)])
    picture.save(root/'sky.png')
    values = dict(model.DEFAULTS, duration=0, sky_motion=False, sky_speed=0,
                  windows_3d=False, top_image='', bottom_image='', zoom=.64, wall_opacity=1)
    values['sky_image'] = model.import_image(root/'sky.png',cube)
    model.prepare_images(values,cube)
    settings = cube/'settings.json'; settings.write_text(model.encode(values))
    controls=home/'.config/hypr/effects/window_close';controls.mkdir(parents=True)
    (controls/'settings.conf').write_text(buttons_model.encode(buttons_model.DEFAULTS))
    (controls/'rules.json').write_text(buttons_rules.encode({'version':1,'apps':{
        'wobbly-test':dict(buttons_rules.DEFAULTS,mode='always')}}))
    minimize=home/'.config/hypr/effects/minimize/settings.conf';minimize.parent.mkdir(parents=True)
    minimize.write_text(minimize_model.encode(dict(minimize_model.DEFAULTS,auto_hide=False)))
    conf = root/'hyprland.conf'
    conf.write_text('''monitor = ,1920x1080@60,auto,1
monitor = WAYLAND-1,800x450@60,3840x1440,1
monitor = CUBE-A,1920x1080@60,0x0,1
monitor = CUBE-B,2560x1440@60,1920x0,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
misc:disable_hyprland_guiutils_check = true
misc:background_color = rgb(181c26)
xwayland:enabled = false
animations:enabled = false
debug:disable_logs = false
debug:enable_stdout_logs = true
''')
    lua = root/'hyprland.lua'; lua.write_text(hypr_compat.Renderer(root).render())
    env = nested_environment({k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_INSTANCE','XETAL_'))})
    parent=Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute():parent=Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(home/'.config'),
               XDG_CACHE_HOME=str(home/'.cache'), XDG_STATE_HOME=str(home/'.local/state'),
               AQ_BACKENDS='wayland', WAYLAND_DISPLAY=str(parent), HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1',
               XETAL_CUBE_CONFIG=str(settings), GDK_BACKEND='wayland', GSETTINGS_BACKEND='memory',
               QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='')
    env.pop('DISPLAY',None);env.pop('DBUS_SESSION_BUS_ADDRESS',None)
    def wait(predicate):
        end = time.monotonic()+15
        while time.monotonic()<end:
            result = predicate()
            if result: return result
            if children and children[0].poll() is not None:
                raise RuntimeError('Test compositor exited; see compositor.log')
            time.sleep(.05)
        raise RuntimeError('Timed out waiting for isolated compositor state')
    def run(*args):
        p = subprocess.run(args,env=env,capture_output=True,text=True,timeout=20)
        if p.returncode: raise RuntimeError(str(args)+': '+p.stdout+p.stderr)
        return p.stdout.strip()
    def ctl(*args): return run('/usr/bin/hyprctl',*args)
    def dispatch(name,args=''):
        answer=ctl('dispatch',hypr_compat.dispatcher(name,args))
        if answer!='ok': raise RuntimeError(name+': '+answer)
    def state(): return json.loads(ctl('xetal-cube'))
    def keyword(key,value):
        answer=ctl('eval',hypr_compat.keyword(key,value))
        if answer!='ok': raise RuntimeError(answer)
    def shot(name,monitor):
        path=root/(name+'.png');run('grim','-o',monitor,str(path))
        return Image.open(path).convert('RGB')
    def check(name,okay,detail):
        report['checks'].append({'name':name,'passed':bool(okay),'detail':detail})
        if not okay: report['failures'].append(name)
        print(('PASS ' if okay else 'FAIL ')+name+' '+str(detail),flush=True)
    def finish():
        dispatch('xetalcube:finish','cancel');wait(lambda:not state()['active'])
    def configure(**changes):
        values.update(changes);settings.write_text(model.encode(values));dispatch('xetalcube:reload')
    def preview(monitor):
        previous=state()['draws'];dispatch('xetalcube:preview',monitor)
        wait(lambda:state()['draws']>previous+3)
        # Preview deliberately starts tilted. Face pixel checks need the front
        # face square to the camera, using the public input-delta dispatcher.
        dispatch('xetalcube:turn',f'{-math.degrees(state()["yaw"])/values["sensitivity"]} {math.degrees(.26)/values["sensitivity"]}')
        previous=state()['draws'];wait(lambda:state()['draws']>previous+3)
    def colors(image):
        w,h=image.size
        return [tuple(round(c) for c in ImageStat.Stat(image.crop((int(x*w)-3,int(y*h)-3,int(x*w)+4,int(y*h)+4))).mean)
                for x,y in ((.25,.25),(.75,.25),(.25,.75),(.75,.75))]
    def color_error(found): return max(abs(a-b) for color,expected in zip(found,COLORS) for a,b in zip(color,expected))
    def coverage_error(image):
        # Check each quadrant out to its edges. Four center probes alone miss
        # the original 20% right/bottom clipping on a 1920-pixel output.
        w,h=image.size
        return max(abs(a-b) for y in (.06,.25,.44,.56,.75,.94) for x in (.06,.25,.44,.56,.75,.94)
                   for a,b in zip(image.getpixel((round(x*(w-1)),round(y*(h-1)))),COLORS[int(x>.5)+2*int(y>.5)]))
    with (root/'compositor.log').open('w') as log:
        try:
            comp=subprocess.Popen(['/usr/bin/Hyprland','-c',str(lua)],env=env,stdout=log,stderr=log,start_new_session=True)
            children.append(comp)
            socket=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None))
            env['HYPRLAND_INSTANCE_SIGNATURE']=socket.parent.name
            env['WAYLAND_DISPLAY']=str(wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None)))
            ctl('output','create','headless','CUBE-A')
            ctl('output','create','headless','CUBE-B')
            def test_outputs():
                outputs=[m for m in json.loads(ctl('-j','monitors')) if m['name'] in ('CUBE-A','CUBE-B')]
                return sorted(outputs,key=lambda m:m['name']) if len(outputs)==2 else None
            monitors=wait(test_outputs)
            time.sleep(.3)
            wallpaper=subprocess.Popen(['/usr/bin/python3',str(REPO/'tests/cube/wallpaper.py')],env=env,stdout=log,stderr=log)
            children.append(wallpaper);time.sleep(.6)
            if wallpaper.poll() is not None:raise RuntimeError('Wallpaper fixture exited; see compositor.log')
            assert ctl('plugin','load',str(binary))=='ok'
            for m in monitors:
                name=m['name']
                normal=shot(name+'-desktop',name)
                expected=(1920,1080) if name=='CUBE-A' else (2560,1440)
                check(name+' output resolution',normal.size==expected,normal.size)
                check(name+' fixture fills output',coverage_error(normal)<15,coverage_error(normal))
                preview(name)
                image=shot(name+'-cube-front',name)
                # An unrotated face is centered; recover its screen bounds from
                # the projection, independently of the capture implementation.
                scale=values['zoom'];w,h=image.size
                face=image.crop((round(w*(1-scale)/2),round(h*(1-scale)/2),round(w*(1+scale)/2),round(h*(1+scale)/2)))
                error=coverage_error(face);check(name+' wallpaper fills face including edges',error<25,error)
                dispatch('xetalcube:turn','130 -50');time.sleep(.2)
                shot(name+'-cube-turned',name);finish()
                for mode in ('image','sky'):
                    configure(zoom=.25,wall_opacity=0,sky_mode=mode,sky_motion=False)
                    preview(name);a=shot(name+'-'+mode,name)
                    box=(30,30,220,150)
                    detail=ImageStat.Stat(a.crop(box))
                    check(name+' '+mode+' background has image detail',max(detail.stddev)>8,detail.stddev)
                    dispatch('xetalcube:turn','140 -85');time.sleep(.2)
                    b=shot(name+'-'+mode+'-turned',name)
                    difference=sum(ImageStat.Stat(ImageChops.difference(a.crop(box),b.crop(box))).mean)/3
                    check(name+' '+mode+' fixed background stays fixed',difference<.3,difference)
                    finish()
                configure(zoom=.64,wall_opacity=1,sky_mode='image',sky_motion=False)
            check('cube reports no error',not state()['error'],state()['error'])
            if len(sys.argv)>3:
                assert ctl('plugin','load',str(Path(sys.argv[3]).resolve(strict=True)))=='ok'
                # The nested backend's small visible output can stop receiving
                # frames when covered. Keep sampling on a private test output.
                dispatch('focusmonitor','CUBE-A')
                client=subprocess.Popen(['/usr/bin/python3',str(REPO/'tests/window-buttons/background_client.py')],
                                        env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
                children.append(client)
                def app(**command):
                    client.stdin.write(json.dumps(command)+'\n');client.stdin.flush()
                    assert client.stdout.readline().strip()=='ok'
                app(op='add',name='Sampler regression')
                window=wait(lambda:next((c for c in json.loads(ctl('-j','clients')) if c['pid']==client.pid),None))
                dispatch('setfloating','address:'+window['address'])
                dispatch('resizewindowpixel','exact 550 650,address:'+window['address'])
                dispatch('movewindowpixel','exact 300 150,address:'+window['address'])
                def info():
                    for identity in json.loads(ctl('xetal-windowbuttons'))['windows']:
                        result=json.loads(ctl('xetal-windowbuttons',identity))
                        if result.get('address')==window['address']:return result
                    return None
                wait(info)
                for color in ('#334a5a','#75402c','#294c37'):
                    app(op='color',name='Sampler regression',color=color)
                    def matched():
                        current=info()['auto_background'];actual=current['color']
                        return current['ready'] and max(abs(int(actual[i:i+2],16)-int(color[i:i+2],16)) for i in (1,3,5))<=4
                    wait(matched)
                    check('window controls sample '+color,True,info()['auto_background'])
                if len(sys.argv)>4:
                    assert ctl('plugin','load',str(Path(sys.argv[4]).resolve(strict=True)))=='ok'
                    dispatch('resizewindowpixel','exact 1500 900,address:'+window['address'])
                    dispatch('movewindowpixel','exact 100 100,address:'+window['address'])
                    time.sleep(.4)
                    # Cross the 1024-pixel preview limit so the downsampling
                    # framebuffer path is exercised before another cube draw.
                    for cycle in range(2):
                        dispatch('xetalminimize:minimize','address:'+window['address'])
                        wait(lambda:json.loads(ctl('xetal-minimize'))['active']==1)
                        time.sleep(.4);shot('minimize-'+str(cycle),'CUBE-A')
                        dispatch('xetalminimize:restoreall')
                        wait(lambda:json.loads(ctl('xetal-minimize'))['active']==0)
                        time.sleep(.2)
                    preview('CUBE-A');shot('cube-after-minimize','CUBE-A');finish()
                    check('large window snapshots, minimize, restore and cube coexist',True,
                          json.loads(ctl('xetal-minimize'))['restored'])
                app(op='close',name='Sampler regression')
                check('window controls survive sampling and window close',True,ctl('xetal-windowclose'))
            report['passed']=not report['failures']
        except BaseException:
            report['error']=traceback.format_exc();print(report['error'],flush=True)
            if children and children[0].poll() is None:
                try:
                    report['monitors']=json.loads(ctl('-j','monitors'))
                    report['clients']=json.loads(ctl('-j','clients'))
                    report['window_controls']=ctl('xetal-windowbuttons')
                    for m in report['monitors']:shot('failure-'+m['name'],m['name'])
                except Exception:pass
        finally:
            for child in reversed(children):
                if child.poll() is None: child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: child.kill();child.wait()
            (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(('PASS' if report['passed'] else 'FAILED')+' — '+str(root/'result.json'),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
