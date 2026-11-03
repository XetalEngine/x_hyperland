#!/usr/bin/env python3
"""Exercise real Compiz deformation in a disposable nested Hyprland session.

Usage: check-wobbly.py /path/to/xetal-wobbly.so /tmp/new-test-directory
Never loads a plugin into the parent compositor or modifies its configuration.
"""
import json,os,shlex,subprocess,sys,tempfile,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'config/hypr'))
from effects.wobbly import model
from effects.window_close import build as close_build, model as close_model
from effects.cube import model as cube_model, build as cube_build
from effects.burn import model as burn_model, build as burn_build
from effects.minimize import model as minimize_model, build as minimize_build
from cursors import model as cursor_model,effects as mouse_effects,build as cursor_build


def main():
    binary=Path(sys.argv[1]).resolve(strict=True);root=Path(sys.argv[2]);root.mkdir(parents=True,exist_ok=False)
    home=root/'home';home.mkdir();config=root/'wobbly.json'
    close_settings=home/'.config/hypr/effects/window_close/settings.conf';close_settings.parent.mkdir(parents=True)
    close_settings.write_text(close_model.encode(close_model.DEFAULTS))
    values=dict(model.DEFAULTS,enabled=True);config.write_text(model.encode(values))
    cube=root/'cube.json';cube.write_text(cube_model.encode(dict(cube_model.DEFAULTS,enabled=True)))
    burn=root/'burn.conf';burn.write_text(burn_model.encode(dict(burn_model.DEFAULTS,enabled=True)))
    minimize=root/'minimize.conf';minimize.write_text(minimize_model.encode(minimize_model.DEFAULTS))
    cursor_config=home/'.config/hypr/cursors/settings.json';cursor_config.parent.mkdir(parents=True)
    cursor_values=dict(cursor_model.DEFAULTS,trail='none');cursor_config.write_bytes(cursor_model.encode(cursor_values))
    cursor_data=cursor_config.parent/'.build';cursor_data.mkdir()
    (cursor_data/'data').symlink_to(cursor_build.build(),target_is_directory=True)
    cursor_build.register_themes(cursor_data/'data',home/'.local/share/icons')
    theme_state=home/'.config/hypr/theme/state.json';theme_state.parent.mkdir();theme_state.write_text('{"design":"tidalglass"}')
    sources=[]
    for name,protocol in [('virtual-pointer',REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
                          ('virtual-keyboard',REPO/'tests/native/virtual-keyboard-unstable-v1.xml'),
                          ('system-bell',Path('/usr/share/wayland-protocols/staging/xdg-system-bell/xdg-system-bell-v1.xml'))]:
        subprocess.run(['wayland-scanner','client-header',str(protocol),str(root/(name+'.h'))],check=True)
        source=root/(name+'.c');sources.append(str(source))
        subprocess.run(['wayland-scanner','private-code',str(protocol),str(source)],check=True)
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True))
    pointer_path=root/'pointer';subprocess.run(['cc','-I'+str(root),str(REPO/'tests/wobbly/pointer.c'),*sources,'-o',str(pointer_path),*flags],check=True)
    conf=root/'hyprland.conf';conf.write_text('''monitor=,1280x900@60,auto,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
debug:disable_scale_checks=true
debug:disable_logs=false
input:follow_mouse=0
animations:enabled=true
general:border_size=3
general:col.active_border=rgba(65dcedff)
decoration:rounding=15
decoration:blur:enabled=true
bindm=,mouse:272,movewindow
bindm=,mouse:273,resizewindow
bindm=SUPER,mouse:272,movewindow
bindm=SUPER,mouse:273,resizewindow
windowrule=match:class ^wobbly-test$,float on
''')
    verify=subprocess.run(['Hyprland','--verify-config','--config',str(conf)],capture_output=True,text=True)
    assert verify.returncode==0,verify.stdout+verify.stderr
    runtime=Path(tempfile.mkdtemp(prefix='xw-',dir='/tmp'))
    parent=os.environ.get('WAYLAND_DISPLAY','wayland-0')
    if not parent.startswith('/'):parent=str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),XDG_DATA_HOME=str(home/'.local/share'),
             XDG_STATE_HOME=str(home/'.local/state'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=parent,AQ_BACKENDS='wayland',
             HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',XETAL_WOBBLY_CONFIG=str(config),QT_QPA_PLATFORM='wayland',QT_QPA_PLATFORMTHEME='',
             QT_WAYLAND_DISABLE_WINDOWDECORATION='1',QT_PLUGIN_PATH='',GSETTINGS_BACKEND='memory',XETAL_CUBE_CONFIG=str(cube),XETAL_BURN_CONFIG=str(burn),XETAL_MINIMIZE_CONFIG=str(minimize),XETAL_CURSOR_CONFIG=str(cursor_config))
    for k in ('HYPRLAND_INSTANCE_SIGNATURE','DISPLAY','DBUS_SESSION_BUS_ADDRESS'):env.pop(k,None)
    children=[];logs=[]
    def spawn(args,**kwargs):
        log=(root/f'child-{len(children)}.log').open('w');logs.append(log)
        p=subprocess.Popen(args,env=kwargs.pop('env',env),stderr=log,stdout=kwargs.pop('stdout',log),**kwargs);children.append(p);return p
    def run(*args):
        r=subprocess.run(args,env=env,capture_output=True,text=True,timeout=15)
        if r.returncode:raise RuntimeError(str(args)+r.stdout+r.stderr)
        return r.stdout.strip()
    def ctl(*args):return run('hyprctl',*args)
    def dispatch(*args):
        result=ctl('dispatch',*args);assert result=='ok',(args,result)
    def wait(predicate,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=predicate()
            if value:return value
            time.sleep(.04)
        raise AssertionError('Timed out: '+str(predicate))
    def clients():return json.loads(ctl('-j','clients'))
    def client(name='Wayland wobble'):return next((c for c in clients() if c['title']==name),None)
    def status():return json.loads(ctl('xetal-wobbly'))
    def screenshot(name):run('grim',str(root/(name+'.png')))
    def save(**changes):values.update(changes);config.write_text(model.encode(values));dispatch('xetalwobbly:reload')
    try:
        compositor=spawn(['Hyprland','--config',str(conf)],start_new_session=True)
        def instance():
            if compositor.poll() is not None:raise AssertionError('Nested compositor exited')
            try:return next((i for i in json.loads(ctl('-j','instances')) if i['pid']==compositor.pid),None)
            except ValueError:return None
        i=wait(instance);env.update(HYPRLAND_INSTANCE_SIGNATURE=i['instance'],WAYLAND_DISPLAY=i['wl_socket'])
        def size_output(name, w, h):
            # Only touch windows belonging to this disposable compositor. The
            # parent must not tile/resize its output behind the virtual pointer.
            def parent_clients():
                return json.loads(subprocess.check_output(['hyprctl','-j','clients'],env=os.environ,text=True))
            surface=wait(lambda:next((c for c in parent_clients() if c['pid']==compositor.pid and name in c['title']),None))
            target='address:'+surface['address']
            for action,arg in [('setfloating',target),('resizewindowpixel',f'exact {w} {h},'+target)]:
                subprocess.run(['hyprctl','dispatch',action,arg],env=os.environ,check=True,capture_output=True)
            wait(lambda:next(o for o in json.loads(ctl('-j','monitors')) if o['name']==name)['width']==w)
        primary=wait(lambda:next(iter(json.loads(ctl('-j','monitors'))),None))
        size_output(primary['name'],1280,900)
        time.sleep(1.5)
        assert ctl('plugin','load',str(binary))=='ok'
        assert ctl('plugin','load',str(close_build.build()))=='ok'
        app=spawn([sys.executable,str(REPO/'tests/wobbly/client.py'),'-name','wobbly-test'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def command(op,name='Wayland wobble'):
            app.stdin.write(json.dumps(dict(op=op,name=name))+'\n');app.stdin.flush();assert app.stdout.readline().strip()=='ok'
        command('add');wait(lambda:client());w=client();address='address:'+w['address']
        dispatch('setfloating',address);dispatch('resizewindowpixel','exact 620 400,'+address);dispatch('movewindowpixel','exact 170 150,'+address)
        time.sleep(.5);dispatch('focuswindow',address)
        m=json.loads(ctl('-j','monitors'))[0];width=m['width'];height=m['height']
        pointer=spawn([str(pointer_path),str(width),str(height)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def point(line):pointer.stdin.write(line+'\n');pointer.stdin.flush();assert pointer.stdout.readline().strip()=='ok'
        point('move 250 190');point('down 272');time.sleep(.04)
        for x in (280,320,360,400,440,480):point(f'move {x} 250');time.sleep(.025)
        screenshot('drag');s=status();assert s['grabs']>=1 and s['active']==1 and s['draws']>0,s
        point('up 272')
        wait(lambda:status()['active']==0);screenshot('settled')
        assert not status()['error'];assert client()['floating']
        stats=status();assert stats['damage_ratio']<.5,stats
        assert stats['mesh_builds']<=stats['steps']+1,stats
        print('Live Wayland drag passed; damage ratio:',stats['damage_ratio'],'mesh builds/draws:',stats['mesh_builds'],stats['draws'],flush=True)
        # Static content must keep animating without client redraws or a timer.
        command('pause');time.sleep(.2);before=status()['steps'];dispatch('xetalwobbly:shiver')
        wait(lambda:status()['steps']>before+10);wait(lambda:status()['active']==0)
        counters=(status()['draws'],status()['steps']);time.sleep(.2)
        assert (status()['draws'],status()['steps'])==counters
        print('Static window schedules its own presentation frames and stops when settled',flush=True)
        # The undeformed rectangle crosses the output edge first. Its trailing
        # border must remain visible wherever the spring lattice is onscreen.
        # Sampling the actual rendered boundary catches monitor-clipped source
        # textures even when physics and draw counters are perfectly healthy.
        from PIL import Image
        for edge in ('left','right','top','bottom'):
            dispatch('resizewindowpixel','exact 620 400,'+address)
            x=100 if edge=='left' else width-820 if edge=='right' else 250
            y=100 if edge=='top' else height-500 if edge=='bottom' else 200
            dispatch('movewindowpixel',f'exact {x} {y},'+address);time.sleep(.4)
            px=x+(500 if edge=='left' else 80);py=y+(300 if edge=='top' else 50)
            dx=-280 if edge=='left' else 380 if edge=='right' else 0
            dy=-280 if edge=='top' else 280 if edge=='bottom' else 0
            point(f'move {px} {py}');point('down 272');time.sleep(.02)
            assert status()['active']==1 and status()['windows'][0]['grabbed'],(edge,status())
            for fraction in (.25,.5,.75,1):
                point(f'move {round(px+dx*fraction)} {round(py+dy*fraction)}');time.sleep(.008)
            screenshot('edge-'+edge)
            actual=client();ax,ay=actual['at'];aw,ah=actual['size']
            crosses={'left':ax<0,'right':ax+aw>width,'top':ay<0,'bottom':ay+ah>height}
            assert crosses[edge],(edge,actual)
            point('up 272');wait(lambda:status()['active']==0)
            picture=Image.open(root/('edge-'+edge+'.png')).convert('RGB')
            horizontal=edge in ('left','right');reverse=edge in ('right','bottom')
            extent=picture.width if horizontal else picture.height
            slices=range(y+80,y+320,8) if horizontal else range(x+80,x+540,8)
            visible=bordered=0
            for row in slices:
                pixels=[picture.getpixel((col,row) if horizontal else (row,col)) for col in range(extent)]
                colored=[col for col,(r,g,b) in enumerate(pixels) if b>r+18 and g>r+10]
                if not colored:continue
                boundary=colored[-1] if reverse else colored[0]
                if boundary<12 or boundary>extent-12:continue
                visible+=1
                bordered+=any(g>140 and b>160 and g>r+40 for r,g,b in pixels[max(0,boundary-4):boundary+5])
            assert visible>=8 and bordered>=visible*.8,(edge,visible,bordered,'Window source was clipped before deformation')
        dispatch('movewindowpixel','exact 170 150,'+address);time.sleep(.4)
        print('Fast drags preserve the full window border at all four output edges',flush=True)
        def close_status():return json.loads(ctl('xetal-windowclose'))
        # The artificial close button is suppressed for native move AND resize,
        # even if Wobbly is disabled. Releasing the drag restores Super-hover.
        for effect_enabled in (True,False):
            save(enabled=effect_enabled)
            for mouse in (272,273):
                c=client();x=c['at'][0]+100;y=c['at'][1]+50
                point(f'move {x} {y}');point('key 125 1');wait(lambda:close_status()['visible'])
                point(f'down {mouse}');wait(lambda:not close_status()['visible'])
                for delta in (10,20,30):point(f'move {x+delta} {y+delta}');time.sleep(.02)
                assert not close_status()['visible'];assert close_status()['closed']==0
                point(f'up {mouse}');wait(lambda:close_status()['visible']);point('key 125 0')
                wait(lambda:not close_status()['visible']);wait(lambda:status()['active']==0)
        save(enabled=True)
        print('Close button hides throughout move/resize and returns on release, with and without Wobbly',flush=True)
        # Resize uses the same original spring model with new rest lengths.
        c=client();x=c['at'][0]+c['size'][0]-25;y=c['at'][1]+c['size'][1]-25
        point(f'move {x} {y}');point('down 273');time.sleep(.04)
        for d in (20,40,60):point(f'move {x+d} {y+d}');time.sleep(.03)
        assert status()['active']==1;point('up 273');wait(lambda:status()['active']==0)
        # Hold/release the original Shift snap modifier, and its inverted mode.
        for inverted in (False,True):
            save(snap_inverted=inverted);c=client();x=c['at'][0]+80;y=c['at'][1]+30
            point(f'move {x} {y}');point('down 272');wait(lambda:status()['active']==1)
            wait(lambda:status()['windows'][0]['snapping']==inverted)
            point('key 42 1');wait(lambda:status()['windows'][0]['snapping']!=inverted)
            point('key 42 0');wait(lambda:status()['windows'][0]['snapping']==inverted)
            point('up 272');wait(lambda:status()['active']==0)
        save(snap_inverted=False,shiver=True)
        before=status()['shivers'];point('bell');wait(lambda:status()['shivers']>before);wait(lambda:status()['active']==0)
        # Maximization, focus/map filtering and disabling restore normal input.
        before=status()['started'];dispatch('fullscreen','1');wait(lambda:status()['started']>before);wait(lambda:status()['active']==0)
        assert client()['fullscreen']==1,client()
        dispatch('fullscreen','1');wait(lambda:status()['active']==0)
        save(focus_effect=1,focus_window_match='class=does-not-match',map_effect=1,map_window_match='Normal')
        before=status()['shivers'];command('add','Map shiver');wait(lambda:status()['shivers']>before);wait(lambda:status()['active']==0)
        before=status()['shivers'];dispatch('focuswindow',address);time.sleep(.2);assert status()['shivers']==before
        save(focus_effect=1,focus_window_match='Normal');dispatch('focuswindow','title:^Map shiver$');wait(lambda:status()['active']>0)
        save(enabled=False);assert status()['active']==0 and not status()['enabled'];screenshot('disabled')
        before=status()['started']
        point('move 260 200');point('down 272');point('move 360 250');point('up 272');time.sleep(.2);assert status()['started']==before
        save(enabled=True,map_effect=0,focus_effect=0);dispatch('focuswindow',address);dispatch('xetalwobbly:shiver');wait(lambda:status()['active']>0)
        command('close');wait(lambda:status()['active']==0);assert compositor.poll() is None
        print('Resize, maximize/restore, map/focus matching, disable and close cleanup passed',flush=True)
        # XWayland uses its original window types and XKB bell notifications.
        display_file=root/'display'
        dispatch('exec','sh -c '+shlex.quote('printf "%s" "$DISPLAY" > '+shlex.quote(str(display_file))))
        wait(lambda:display_file.exists() and display_file.read_text())
        xenv=dict(env,DISPLAY=display_file.read_text(),QT_QPA_PLATFORM='xcb')
        xapp=spawn([sys.executable,str(REPO/'tests/wobbly/client.py'),'-name','wobbly-test'],env=xenv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def xcommand(op):
            xapp.stdin.write(json.dumps(dict(op=op,name='XWayland wobble'))+'\n');xapp.stdin.flush();assert xapp.stdout.readline().strip()=='ok'
        xcommand('add');wait(lambda:client('XWayland wobble'));c=client('XWayland wobble');assert c['xwayland']
        xa='address:'+c['address'];dispatch('setfloating',xa);dispatch('movewindowpixel','exact 130 180,'+xa);time.sleep(.4)
        before=status()['grabs'];point('move 230 220');point('down 272');point('move 370 300');wait(lambda:status()['grabs']>before)
        screenshot('xwayland-drag');point('up 272');wait(lambda:status()['active']==0)
        before=status()['started'];xcommand('max');wait(lambda:status()['started']>before);wait(lambda:status()['active']==0)
        xcommand('restore');wait(lambda:status()['active']==0)
        save(shiver=True);assert status()['x11_bell'] and status()['wayland_bell'],status()
        before=status()['shivers'];xcommand('bell');wait(lambda:status()['shivers']>before);wait(lambda:status()['active']==0)
        print('XWayland drag and XKB bell passed',flush=True)
        # All native effects must load together, regardless of hook installation order.
        for effect in (cube_build,burn_build,minimize_build):assert ctl('plugin','load',str(effect.build()))=='ok'
        def mouse_status():return json.loads(ctl('xetal-cube'))
        def mouse_style(style):
            cursor_values['trail']=style
            if style in mouse_effects.STYLES:cursor_values['color']=mouse_effects.STYLES[style][2]
            cursor_config.write_bytes(cursor_model.encode(cursor_values));dispatch('xetalcube:cursor')
        import math
        for style in mouse_effects.STYLES:
            mouse_style(style);before=mouse_status()['cursor_frames']
            for step in range(70):point(f'move {250+step*8} {int(320+math.sin(step*.15)*40)}');time.sleep(.006)
            screenshot('mouse-'+style);s=mouse_status()
            assert s['cursor_effect']==style and s['cursor_frames']>before and s['cursor_marks']>0,s
            wait(lambda:mouse_status()['cursor_marks']==0);frames=mouse_status()['cursor_frames'];time.sleep(.15)
            assert mouse_status()['cursor_frames']==frames,'Mouse effect rendered while idle'
        mouse_style('follow');assert mouse_status()['cursor_effect']=='tidal'
        theme_state.write_text('{"design":"binaryknife"}');dispatch('xetalcube:cursor');assert mouse_status()['cursor_effect']=='circuit'
        mouse_style('ink');theme_state.write_text('{"design":"raw"}');dispatch('xetalcube:cursor');assert mouse_status()['cursor_effect']=='ink'
        mouse_style('none');point('move 500 300');assert mouse_status()['cursor_marks']==0
        print('All themed native mouse trails, theme following, independent mixing, disabling and idle suspension passed',flush=True)
        dispatch('focuswindow',xa);dispatch('xetalwobbly:shiver');dispatch('xetalcube:preview')
        wait(lambda:json.loads(ctl('xetal-cube'))['active']);dispatch('xetalcube:turn','25 12');time.sleep(.2)
        screenshot('cube-with-wobbly');dispatch('xetalcube:finish','cancel');wait(lambda:not json.loads(ctl('xetal-cube'))['active'])
        assert not json.loads(ctl('xetal-cube'))['error'];wait(lambda:status()['active']==0)
        dispatch('focuswindow',xa);dispatch('xetalwobbly:shiver');wait(lambda:status()['active']>0)
        xcommand('min');wait(lambda:status()['active']==0);wait(lambda:json.loads(ctl('xetal-minimize'))['active']==1)
        dispatch('xetalminimize:restoreall');wait(lambda:json.loads(ctl('xetal-minimize'))['active']==0)
        dispatch('xetalwobbly:shiver');xcommand('close');wait(lambda:status()['active']==0)
        dispatch('focuswindow','title:^Map shiver$');dispatch('xetalwobbly:shiver')
        dispatch('workspace','2');wait(lambda:status()['active']==0);dispatch('workspace','1');time.sleep(.4)
        assert not status()['error'];assert compositor.poll() is None
        print('Cube/Burn/Minimize coexistence, minimize, close and workspace cleanup passed',flush=True)
        command('add','Close button check');wait(lambda:client('Close button check'));time.sleep(.4)
        c=client('Close button check');point(f"move {c['at'][0]+80} {c['at'][1]+50}");point('key 125 1');wait(lambda:close_status()['visible'])
        b=close_status()['box'];point(f'move {int(b[0]+b[2]/2)} {int(b[1]+b[3]/2)}');point('down 272');point('up 272')
        wait(lambda:not client('Close button check'));point('key 125 0');assert close_status()['closed']==1
        print('Normal Super-click close still works',flush=True)
        # A cached mesh must use each output's viewport, including rotated and
        # fractional-scale neighbors. Damage must reach both halves of a window.
        address='address:'+client('Map shiver')['address'];command('pause','Map shiver')
        m=json.loads(ctl('-j','monitors'))[0];width=m['width']
        assert ctl('keyword','monitor',f'{m["name"]},{m["width"]}x{m["height"]}@60,0x0,1')=='ok'
        ctl('output','create','wayland');wait(lambda:len(json.loads(ctl('-j','monitors')))==2)
        second=next(output for output in json.loads(ctl('-j','monitors')) if output['name']!=m['name'])
        size_output(second['name'],1000,800)
        assert ctl('keyword','monitor',f'{second["name"]},1000x800@144,{width}x0,1.25,transform,1')=='ok'
        # A mode request can make the nested backend request maximization in
        # its parent again. Restore only these two test surfaces afterward.
        size_output(m['name'],width,900)
        size_output(second['name'],1000,800)
        wait(lambda:all(o['width']>0 and o['height']>0 for o in json.loads(ctl('-j','monitors'))))
        time.sleep(1)
        outputs=json.loads(ctl('-j','monitors'))
        assert next(o for o in outputs if o['name']==second['name'])['scale']==1.25,outputs
        m=next(o for o in outputs if o['name']==m['name']);width=m['width']
        right=max(o['x']+(o['height'] if o['transform']%2 else o['width'])/o['scale'] for o in outputs)
        dispatch('movewindowpixel',f'exact {width-350} 180,'+address);time.sleep(.5)
        assert client('Map shiver')['monitor']==m['id'];dispatch('focuswindow',address)
        # Wait for the compositor's placement animation as well as the springs
        # before taking a reference, so text comparison measures orientation.
        dispatch('xetalwobbly:shiver');wait(lambda:status()['active']==0)
        screenshot('spanning-reference')
        before=status();dispatch('xetalwobbly:shiver');time.sleep(.18);screenshot('spanning-scaled-portrait')
        wait(lambda:status()['active']==0);after=status();screenshot('spanning-settled')
        prior={o['id']:o['steps'] for o in before['outputs']}
        assert all(o['steps']-prior.get(o['id'],0)>10 for o in after['outputs']),(before,after)
        assert not after['error']
        from PIL import Image,ImageFilter
        with Image.open(root/'spanning-reference.png') as reference, Image.open(root/'spanning-scaled-portrait.png') as animated:
            ratio=reference.width/right
            pixel=(round((width+80)*ratio),round(380*ratio))
            expected=reference.convert('RGB').getpixel(pixel);actual=animated.convert('RGB').getpixel(pixel)
            assert max(expected)-min(expected)>20,expected
            assert max(abs(a-b) for a,b in zip(expected,actual))<15,(expected,actual)
            # Text remains upright and in place on both sides of the seam. A
            # solid-color sample alone would miss a rotated/flipped workbuffer.
            c=client('Map shiver');x,y=c['at'];cw,ch=c['size']
            for area in ((x+15,y+12,width-12,y+55),(width+12,y+ch-55,x+cw-12,y+ch-12)):
                crop=tuple(round(value*ratio) for value in area)
                glyphs=reference.crop(crop).convert('L').tobytes()
                nearby=animated.crop(crop).convert('L').filter(ImageFilter.MaxFilter(11)).tobytes()
                bright=sum(v>180 for v in glyphs)
                assert bright>50 and sum(a>180 and b>180 for a,b in zip(glyphs,nearby))>.8*bright,area
        # Cross the seam while held. Neither transfer may recreate or drop the
        # lattice, and status must report the destination output's refresh rate.
        save(map_effect=0,focus_effect=0)
        outputs=json.loads(ctl('-j','monitors'))
        right=max(o['x']+(o['height'] if o['transform']%2 else o['width'])/o['scale'] for o in outputs)
        bottom=max(o['y']+(o['width'] if o['transform']%2 else o['height'])/o['scale'] for o in outputs)
        point(f'extent {round(right)} {round(bottom)}')
        dispatch('movewindowpixel',f'exact {width-650} 180,'+address);time.sleep(.4)
        point(f'move {width-350} 240');point('key 125 1');point('down 272')
        wait(lambda:status()['active']==1);started=status()['started']
        for x in range(width-330,width+310,20):point(f'move {x} 240');time.sleep(.012)
        wait(lambda:client('Map shiver')['monitor']==second['id'])
        s=status();assert s['active']==1 and s['started']==started and s['windows'][0]['grabbed'],s
        target=next(o for o in json.loads(ctl('-j','monitors')) if o['id']==second['id'])
        assert s['windows'][0]['monitor']==target['id'] and abs(s['windows'][0]['refresh_hz']-target['refreshRate'])<.1,s
        for x in range(width+300,width-350,-20):point(f'move {x} 240');time.sleep(.012)
        wait(lambda:client('Map shiver')['monitor']==m['id'])
        assert status()['active']==1 and status()['started']==started,status()
        point('up 272');point('key 125 0');wait(lambda:status()['active']==0)
        (root/'monitor-timing.json').write_text(json.dumps({'outputs':outputs,'transferred':s},indent=2))
        print('Held drag transfer preserves the spring lattice; actual output rates:',[o['refreshRate'] for o in outputs],flush=True)
        # Nested Wayland outputs may report 60 Hz regardless of requested mode.
        # Rate invariance (60/120/144/240 Hz and rate changes) is also checked by
        # native/test_engine.cpp; this checks actual per-output callbacks/transfer.
        ctl('output','remove',second['name'])
        dispatch('movewindowpixel','exact 170 150,'+address);time.sleep(.3)
        print('Window spanning a rotated fractional-scale output animates on both displays',flush=True)
        # In-flight unload must detach every transformer before its code unloads.
        dispatch('focuswindow','title:^Map shiver$');dispatch('xetalwobbly:shiver');assert ctl('plugin','unload',str(binary))=='ok'
        time.sleep(.3);assert compositor.poll() is None;assert ctl('configerrors')==''
        print('In-flight plugin unload passed',flush=True)
        assert ctl('plugin','load',str(binary))=='ok'
        dispatch('xetalwobbly:shiver');wait(lambda:status()['active']==0)
        counters=(status()['draws'],status()['steps']);time.sleep(.3)
        assert (status()['draws'],status()['steps'])==counters
        assert ctl('plugin','unload',str(binary))=='ok'
        print('Reload alongside existing effects and idle timer suspension passed',flush=True)
    except Exception:
        for name,args in [('status',('xetal-wobbly',)),('monitors',('-j','monitors')),('clients',('-j','clients'))]:
            try:(root/('failure-'+name+'.json')).write_text(ctl(*args))
            except Exception:pass
        raise
    finally:
        for p in reversed(children):
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()


if __name__=='__main__':main()
