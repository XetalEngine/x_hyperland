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
from effects.cube import model as cube_model, build as cube_build
from effects.burn import model as burn_model, build as burn_build
from effects.minimize import model as minimize_model, build as minimize_build


def main():
    binary=Path(sys.argv[1]).resolve(strict=True);root=Path(sys.argv[2]);root.mkdir(parents=True,exist_ok=False)
    home=root/'home';home.mkdir();config=root/'wobbly.json'
    values=dict(model.DEFAULTS,enabled=True);config.write_text(model.encode(values))
    cube=root/'cube.json';cube.write_text(cube_model.encode(dict(cube_model.DEFAULTS,enabled=True)))
    burn=root/'burn.conf';burn.write_text(burn_model.encode(dict(burn_model.DEFAULTS,enabled=True)))
    minimize=root/'minimize.conf';minimize.write_text(minimize_model.encode(minimize_model.DEFAULTS))
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
debug:disable_logs=false
input:follow_mouse=0
animations:enabled=true
general:border_size=3
general:col.active_border=rgba(65dcedff)
decoration:rounding=15
decoration:blur:enabled=true
bindm=,mouse:272,movewindow
bindm=,mouse:273,resizewindow
windowrule=match:class ^wobbly-test$,float on
''')
    verify=subprocess.run(['Hyprland','--verify-config','--config',str(conf)],capture_output=True,text=True)
    assert verify.returncode==0,verify.stdout+verify.stderr
    runtime=Path(tempfile.mkdtemp(prefix='xw-',dir='/tmp'))
    parent=os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'):parent=str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),XDG_DATA_HOME=str(home/'.local/share'),
             XDG_STATE_HOME=str(home/'.local/state'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=parent,AQ_BACKENDS='wayland',
             HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',XETAL_WOBBLY_CONFIG=str(config),QT_QPA_PLATFORM='wayland',QT_QPA_PLATFORMTHEME='',
             QT_WAYLAND_DISABLE_WINDOWDECORATION='1',QT_PLUGIN_PATH='',GSETTINGS_BACKEND='memory',XETAL_CUBE_CONFIG=str(cube),XETAL_BURN_CONFIG=str(burn),XETAL_MINIMIZE_CONFIG=str(minimize))
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
        i=wait(instance);env.update(HYPRLAND_INSTANCE_SIGNATURE=i['instance'],WAYLAND_DISPLAY=i['wl_socket']);time.sleep(1.5)
        assert ctl('plugin','load',str(binary))=='ok'
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
        print('Live Wayland drag, deformation and settling passed',flush=True)
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
    finally:
        for p in reversed(children):
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()


if __name__=='__main__':main()
