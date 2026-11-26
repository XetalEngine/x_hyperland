#!/usr/bin/env python3
"""Check edge resizing with private input in a seat-isolated Hyprland session.

Usage: check-border-resize.py WINDOW_CONTROLS_PLUGIN CURSOR_PROBE_PLUGIN
       [--memory-plugin WINDOW_MEMORY_PLUGIN] [--wobbly-plugin WOBBLY_PLUGIN]
Requires Hyprland 0.57.2, PyQt6, a C compiler and wayland-scanner.
Results and logs remain in the printed temporary directory.
"""
from pathlib import Path
import argparse, json, os, select, shutil, subprocess, sys, tempfile, time

REPO=Path(__file__).resolve().parents[1]; PROFILE=REPO/'config/hypr'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('plugin',type=Path)
parser.add_argument('cursor_plugin',type=Path)
parser.add_argument('--memory-plugin',type=Path)
parser.add_argument('--wobbly-plugin',type=Path,help='Also check rendered settling in a private Wayland output')
args=parser.parse_args()
plugins=[args.plugin.resolve(strict=True),args.cursor_plugin.resolve(strict=True)]
if args.memory_plugin:plugins.append(args.memory_plugin.resolve(strict=True))
if args.wobbly_plugin:plugins.insert(0,args.wobbly_plugin.resolve(strict=True))
controls_plugin=args.plugin.resolve(strict=True)
sys.path[:0]=[str(REPO/'tests'),str(PROFILE)]
from nested_session import nested_environment,assert_seat_isolated
from effects.window_close import rules
from compat.hypr_compat import call as lua_call
root=Path(tempfile.mkdtemp(prefix='fusion-edge-resize-'))
runtime=Path(tempfile.mkdtemp(prefix='er-'))
(root/'run').symlink_to(runtime,target_is_directory=True)
(root/'compat').symlink_to(PROFILE/'compat',target_is_directory=True)
shutil.copy2(PROFILE/'compat/entry.lua',root/'hyprland.lua')
for name in ('theme','workspaces','window_rules','effects/window_close'):(root/name).mkdir(parents=True,exist_ok=True)
for name in ('settings.conf','kde-rules.json'):shutil.copy2(PROFILE/'effects/window_close'/name,root/'effects/window_close'/name)
(root/'workspaces/rules.json').write_text(json.dumps({'version':1,'default_layout':'kde','workspaces':{}}))
(root/'theme/current.colors').write_text('[Colors:Window]\nBackgroundNormal=14,27,44\nForegroundNormal=239,246,255\nDecorationFocus=32,210,232\n')
(root/'hyprland.conf').write_text(f'''monitor=,1280x900@60,auto,1
monitor=RESIZE,1280x900@60,0x0,1
monitor=WAYLAND-1,640x480@60,4096x0,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
xwayland:enabled=false
source={PROFILE}/control_center/appearance.conf
animations:enabled=false
input:follow_mouse=1
windowrule=match:class ^fusion-resize-test$,float on
''')
if args.wobbly_plugin:
    from effects.wobbly import model as wobbly_model
    (root/'wobbly.json').write_text(wobbly_model.encode(dict(wobbly_model.DEFAULTS,focus_effect=0,map_effect=0,maximize_effect=False)))
    conf=root/'hyprland.conf'
    conf.write_text(conf.read_text().replace('monitor=WAYLAND-1,640x480@60,4096x0,1','monitor=WAYLAND-1,1280x900@60,0x0,1').replace(
        'animations:enabled=false','animations:enabled=true\nanimation=windows,0,1,default\nanimation=fade,0,1,default\nanimation=workspaces,0,1,default'))
for name,xml in [('pointer',REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),('keyboard',REPO/'tests/native/virtual-keyboard-unstable-v1.xml')]:
    for mode,ext in [('client-header','h'),('private-code','c')]:
        subprocess.run(['wayland-scanner',mode,str(xml),str(root/f'virtual-{name}.{ext}')],check=True)
flags=subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True).split()
subprocess.run(['cc','-I'+str(root),str(REPO/'tests/native/gesture-input.c'),str(root/'virtual-pointer.c'),str(root/'virtual-keyboard.c'),'-o',str(root/'input'),*flags],check=True)
(root/'fixture.py').write_text('''import sys\nfrom PyQt6.QtWidgets import QApplication,QWidget,QPushButton
from PyQt6.QtCore import Qt
app=QApplication([]);app.setDesktopFileName(sys.argv[1] if len(sys.argv)>1 else 'fusion-resize-test')
w=QWidget();w.setWindowTitle('Edge resize fixture');w.setWindowFlags(Qt.WindowType.FramelessWindowHint);w.resize(600,400)
b=QPushButton('Content button',w);b.setGeometry(440,160,150,35)
b.clicked.connect(lambda:w.setWindowTitle('Content clicked'))\nw.show();app.exec()
''')
parent=Path(os.environ['WAYLAND_DISPLAY'])
if not parent.is_absolute():parent=Path(os.environ['XDG_RUNTIME_DIR'])/parent
env=nested_environment({k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_','XETAL_'))})
env.update(XDG_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(root/'config'),XDG_CACHE_HOME=str(root/'cache'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'),WAYLAND_DISPLAY=str(parent),QT_QPA_PLATFORM='wayland',QT_QPA_PLATFORMTHEME='',QT_WAYLAND_DISABLE_WINDOWDECORATION='1',QT_PLUGIN_PATH='',GSETTINGS_BACKEND='memory',XETAL_WINDOW_CONTROLS_ROOT=str(root),XETAL_WORKSPACE_RULES=str(root/'workspaces/rules.json'))
env.pop('DISPLAY',None);env.pop('DBUS_SESSION_BUS_ADDRESS',None)
if args.wobbly_plugin:env['XETAL_WOBBLY_CONFIG']=str(root/'wobbly.json')
children=[];report={'passed':False,'checks':[],'directory':str(root)}
log=(root/'session.log').open('w')
def spawn(args,**kw):
    kw.setdefault('stdout',log);kw.setdefault('stderr',log)
    p=subprocess.Popen(args,env=env,**kw);children.append(p);return p
def wait(f,label):
    end=time.monotonic()+8
    while time.monotonic()<end:
        value=f()
        if value:return value
        assert compositor.poll() is None,'Nested compositor stopped'
        time.sleep(.04)
    raise AssertionError('Timed out: '+label)
def ctl(*args):
    p=subprocess.run([str(PROFILE/'compat/bin/hyprctl'),*args],env=env,text=True,capture_output=True,timeout=6)
    assert p.returncode==0,(args,p.stdout,p.stderr)
    return p.stdout.strip()
def dispatch(*args):assert ctl('dispatch',*args)=='ok',args
def check(name,okay,detail):
    report['checks'].append(dict(name=name,passed=bool(okay),detail=detail))
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert okay,(name,'See '+str(root/'result.json'))
    print('PASS:',name,flush=True)
try:
    compositor=spawn(['Hyprland','--config',str(root/'hyprland.lua')],start_new_session=True)
    sock=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None),'IPC socket')
    display=wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None),'Wayland socket')
    env.update(HYPRLAND_INSTANCE_SIGNATURE=sock.parent.name,WAYLAND_DISPLAY=str(display))
    assert_seat_isolated(compositor.pid,sock.parent/'hyprland.log')
    if args.wobbly_plugin:
        # Keep an actual presentation output for the spring/render checks.
        # Only resize this test compositor's own surface in the parent session.
        def host(*args):
            return subprocess.check_output([str(PROFILE/'compat/bin/hyprctl'),*args],text=True,timeout=6).strip()
        output=json.loads(ctl('-j','monitors'))[0]['name']
        surface=wait(lambda:next((c for c in json.loads(host('-j','clients')) if c['pid']==compositor.pid and output in c['title']),None),'nested output surface')
        address='address:'+surface['address']
        assert host('dispatch','setfloating',address)=='ok'
        assert host('dispatch','resizewindowpixel','exact 1280 900,'+address)=='ok'
        wait(lambda:json.loads(ctl('-j','monitors'))[0]['width']==1280,'output dimensions')
        # Parent input must never interfere with the private virtual pointer.
        devices=json.loads(ctl('-j','devices'))
        for group in ('mice','keyboards'):
            for device in devices[group]:assert ctl('eval',lua_call('device',{'name':device['name'],'enabled':False}))=='ok'
    else:
        assert ctl('output','create','headless','RESIZE')=='ok'
        wait(lambda:any(m['name']=='RESIZE' for m in json.loads(ctl('-j','monitors'))),'headless output')
        for m in json.loads(ctl('-j','monitors')):
            if m['name']!='RESIZE':assert ctl('output','remove',m['name'])=='ok'
        wait(lambda:len(json.loads(ctl('-j','monitors')))==1,'private output only')
        output='RESIZE'
    dispatch('focusmonitor',output);assert not ctl('configerrors'),ctl('configerrors')
    for p in plugins:assert ctl('plugin','load',str(p))=='ok'
    app=spawn([sys.executable,str(root/'fixture.py')])
    def client():return next((c for c in json.loads(ctl('-j','clients')) if c['pid']==app.pid),None)
    wait(client,'fixture')
    pointer=spawn([str(root/'input'),'1280','900'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    def point(cmd,delay=.025):
        pointer.stdin.write(cmd+'\n');pointer.stdin.flush()
        assert select.select([pointer.stdout],[],[],4)[0],cmd
        assert pointer.stdout.readline().strip()=='ok',cmd
        time.sleep(delay)
    def info():
        return next(v for v in (json.loads(ctl('xetal-windowbuttons',i)) for i in json.loads(ctl('xetal-windowbuttons'))['windows']) if v['address']==client()['address'])
    def normal():
        if args.wobbly_plugin:wait(lambda:not json.loads(ctl('xetal-wobbly'))['active'],'springs settled')
        if client()['fullscreen']:dispatch('fullscreen','1' if client()['fullscreen']==1 else '0')
        address='address:'+client()['address'];dispatch('focuswindow',address)
        dispatch('resizewindowpixel','exact 600 400,'+address);dispatch('movewindowpixel','exact 340 260,'+address)
        wait(lambda:client()['size']==[600,400] and client()['at']==[340,260],'reset geometry');time.sleep(.1)
    last_settle={}
    def drag(start,end):
        last_settle.clear()
        point(f'move {start[0]} {start[1]}',.15)
        before=client();hover=json.loads(ctl('xetal-cursor'));point('button 1',.08)
        for n in range(1,9):point(f'move {round(start[0]+(end[0]-start[0])*n/8)} {round(start[1]+(end[1]-start[1])*n/8)}',.035)
        if args.wobbly_plugin:
            held=json.loads(ctl('xetal-wobbly'))
            point('button 0',.01)
            samples=[];deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                state=json.loads(ctl('xetal-wobbly'))
                assert not state['error'],state
                if not state['active']:break
                assert not any(w['grabbed'] for w in state['windows']),state
                samples.append(state);time.sleep(.008)
            assert not state['active'],'Springs did not finish settling'
            last_settle.update(held=held,samples=samples,finished=state)
        else:point('button 0',.2)
        return before,client(),hover
    for titlebar in (False,True):
        normal()
        data=json.loads((root/'effects/window_close/kde-rules.json').read_text())
        data['apps']['fusion-resize-test']=dict(rules.DEFAULTS,mode='off' if not titlebar else 'auto',titlebar=titlebar)
        (root/'effects/window_close/kde-rules.json').write_text(rules.encode(data));dispatch('xetalwindowclose:reload')
        wait(lambda:bool(info()['titlebar']['enabled'])==titlebar,'title bar state')
        for direction in ('left','right','top','bottom','top-left','top-right','bottom-left','bottom-right'):
            normal();c=client();x,y=c['at'];w,h=c['size'];bar=info()['titlebar']
            top=min(y,bar['box'][1]) if titlebar else y
            sx=x-10 if 'left' in direction else x+w+10 if 'right' in direction else x+w//2
            sy=top-10 if 'top' in direction else y+h+10 if 'bottom' in direction else y+h//2
            dx=(-96 if args.wobbly_plugin else -48) if 'left' in direction else (96 if args.wobbly_plugin else 48) if 'right' in direction else 0
            dy=(-72 if args.wobbly_plugin else -40) if 'top' in direction else (72 if args.wobbly_plugin else 40) if 'bottom' in direction else 0
            before,after,hover=drag((sx,sy),(sx+dx,sy+dy))
            okay=hover['current']['kind']=='other' and (after['size'][0]>before['size'][0]+20 if dx else after['size'][0]==before['size'][0]) and (after['size'][1]>before['size'][1]+20 if dy else after['size'][1]==before['size'][1])
            check(('title bar' if titlebar else 'own chrome')+' '+direction,okay,dict(before=before['size'],after=after['size'],before_at=before['at'],after_at=after['at'],hover=hover,start=[sx,sy]))
            if args.wobbly_plugin:
                held,samples,done=last_settle['held'],last_settle['samples'],last_settle['finished']
                residual=max(w['deviation'] for w in samples[-1]['windows']) if samples else None
                okay=held['active']==1 and len(samples)>2 and done['draws']>held['draws']+2 and residual<3
                check(('title bar' if titlebar else 'own chrome')+' '+direction+' settles without a jump',okay,
                    dict(held=held,samples=samples,finished=done,residual=residual))
        for mode,label in [('1','maximized'),('0','fullscreen')]:
            normal();dispatch('fullscreen',mode);time.sleep(.3);c=client();x,y=c['at'];w,h=c['size']
            start=(max(1,min(1278,x-1)),max(1,min(898,y+h//2)))
            before,after,hover=drag(start,(start[0]+55,start[1]+35))
            check(('title bar' if titlebar else 'own chrome')+' '+label+' stays fixed',before['at']==after['at'] and before['size']==after['size'] and before['fullscreen']==after['fullscreen'],dict(before=before['size'],after=after['size'],state=after['fullscreen']))

    normal()
    def same(before,after):
        return all(before[key]==after[key] for key in ('at','size','fullscreen'))
    def top_point(offset=10):
        c=client();return (c['at'][0]+c['size'][0]//2,info()['titlebar']['box'][1]-offset)
    def keyword(name,value):
        assert ctl('keyword','general:'+name,str(value))=='ok'
        time.sleep(.15)
    # The target follows the user's setting, including an explicit off switch.
    for name,value,label in [('extend_border_grab_area',0,'zero extra margin'),('resize_on_border','false','border resize disabled')]:
        normal();keyword(name,value);start=top_point()
        before,after,hover=drag(start,(start[0],start[1]-40))
        check(label,same(before,after) and hover['current']['kind']!='other',dict(before=before['size'],after=after['size'],hover=hover))
        keyword(name,15 if name=='extend_border_grab_area' else 'true')
    normal();start=top_point(14)
    before,after,hover=drag(start,(start[0],start[1]-40))
    check('14 pixel target with thin borders',after['size'][1]>before['size'][1]+20,after['size'])
    normal();keyword('border_size',0);start=top_point(14)
    before,after,hover=drag(start,(start[0],start[1]-40))
    check('borderless title bar has a grab area',after['size'][1]>before['size'][1]+20,after['size'])
    keyword('border_size',2)
    normal();start=top_point();keyword('hover_icon_on_border','false')
    point(f'move {start[0]} {start[1]}',.2)
    cursor=json.loads(ctl('xetal-cursor'))['current']
    check('resize cursor off switch',cursor['kind']!='other',cursor)
    keyword('hover_icon_on_border','true')
    point(f'move {start[0]} {start[1]-1}',.2)
    cursor=json.loads(ctl('xetal-cursor'))['current']
    check('resize cursor restored',cursor['kind']=='other',cursor)
    # A press/release intercepted by the decoration must not leave a held
    # button behind or steal the application's next click.
    c=client();point(f"move {c['at'][0]+500} {c['at'][1]+175}",.2)
    check('cursor returns to app',json.loads(ctl('xetal-cursor'))['current']['kind']=='arrow',json.loads(ctl('xetal-cursor')))
    point('button 1');point('button 0',.2)
    check('application click after resizing',client()['title']=='Content clicked',client()['title'])
    normal();b=info()['titlebar']['box'];start=(b[0]+100,b[1]+b[3]//2)
    before,after,hover=drag(start,(start[0]+60,start[1]+40))
    check('title bar still moves without resizing',before['size']==after['size'] and before['at']!=after['at'],dict(before=before['at'],after=after['at']))
    normal()
    for label,state in [('maximize',1),('restore',0)]:
        b=info()['titlebar']['buttons'][2]
        point(f'move {round(b[0]+b[2]/2)} {round(b[1]+b[3]/2)}',.15)
        point('button 1');point('button 0',.3)
        check('title bar '+label+' button',client()['fullscreen']==state,client()['fullscreen'])
    normal();start=top_point()
    cover=spawn([sys.executable,str(root/'fixture.py'),'fusion-resize-cover'])
    def cover_client():return next((c for c in json.loads(ctl('-j','clients')) if c['pid']==cover.pid),None)
    wait(cover_client,'cover window')
    addr='address:'+cover_client()['address']
    if not cover_client()['floating']:dispatch('togglefloating',addr)
    dispatch('resizewindowpixel','exact 300 160,'+addr);dispatch('movewindowpixel','exact 500 150,'+addr)
    dispatch('focuswindow',addr);time.sleep(.2)
    covered=cover_client()
    before,after,hover=drag(start,(start[0],start[1]-15))
    check('overlapping window keeps its input',same(before,after) and same(covered,cover_client()),dict(before=before['size'],after=after['size']))
    cover.terminate();cover.wait(timeout=5);wait(lambda:not cover_client(),'cover closed')
    normal();start=top_point();point(f'move {start[0]} {start[1]}',.2)
    assert ctl('plugin','unload',str(controls_plugin))=='ok'
    point('move 640 100',.2)
    check('unload clears resize cursor',json.loads(ctl('xetal-cursor'))['current']['kind']!='other',json.loads(ctl('xetal-cursor')))
    assert ctl('plugin','load',str(controls_plugin))=='ok'
    wait(lambda:info()['titlebar']['enabled'],'title bar after reload')
    normal();start=top_point()
    before,after,hover=drag(start,(start[0],start[1]-40))
    check('resize after plugin reload',after['size'][1]>before['size'][1]+20,after['size'])
    assert_seat_isolated(compositor.pid,sock.parent/'hyprland.log')
    report['passed']=True
finally:
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
    log.close()
    print('RESULT:',root/'result.json',flush=True)

