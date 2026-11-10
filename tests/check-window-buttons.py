#!/usr/bin/env python3
"""Exercise Super window buttons using private virtual input in nested Hyprland.

Usage: check-window-buttons.py PLUGIN OUTPUT_DIR
Only the disposable compositor's output window is resized in the parent.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'config/hypr'))
from effects.window_close import model, rules
from effects.minimize import build as minimize_build, model as minimize_model


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    root = Path(sys.argv[2]).resolve()
    assert root.is_relative_to(Path('/tmp')) and root != Path('/tmp'), 'Tests require a new directory under /tmp'
    root.mkdir(parents=True, exist_ok=False)
    home = root / 'home'; home.mkdir()
    settings = home / '.config/hypr/effects/window_close/settings.conf'
    settings.parent.mkdir(parents=True); settings.write_text(model.encode(model.DEFAULTS))
    for source in (REPO/'config/hypr/effects/window_close').glob('*.py'):
        shutil.copy2(source,settings.parent/source.name)
    shutil.copy2(REPO/'config/hypr/effects/native_toolchain.py',settings.parent.parent/'native_toolchain.py')
    workspace_dir=home/'.config/hypr/workspaces';workspace_dir.mkdir(parents=True)
    for source in (REPO/'config/hypr/workspaces').glob('*.py'):
        shutil.copy2(source,workspace_dir/source.name)
    # Small theme/config sources only; never adopt the real user's preferences.
    for directory in ('theme','runtime','cursors','window_rules','icon_themes','sounds'):
        destination=home/'.config/hypr'/directory;destination.mkdir(exist_ok=True)
        for source in (REPO/'config/hypr'/directory).iterdir():
            if source.is_file() and source.suffix in ('.py','.json','.colors'):shutil.copy2(source,destination/source.name)
    theme_assets=REPO/'config/hypr/theme/assets'
    if theme_assets.exists():shutil.copytree(theme_assets,home/'.config/hypr/theme/assets')
    if '--builtin-only' in sys.argv or '--launch-only' in sys.argv:
        # All writable app/preferences paths belong to this private HOME. Copy
        # sources/configs only; compiled binaries stay in the build tree.
        for directory,subdirs,names in os.walk(REPO/'config/hypr'):
            subdirs[:]=[d for d in subdirs if not d.startswith('.') and d not in ('__pycache__','node_modules','wallpapers','assets','qt5','qt6','gtk3')]
            for name in names:
                source=Path(directory)/name
                if source.suffix not in ('.py','.json','.conf','.colors','.css','.svg','.sh','.txt','.desktop'):continue
                destination=home/'.config/hypr'/source.relative_to(REPO/'config/hypr')
                destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
    minimize = root / 'minimize.conf'
    minimize_values = dict(minimize_model.DEFAULTS)
    minimize.write_text(minimize_model.encode(minimize_values))
    sources = []
    for name, protocol in [
        ('virtual-pointer', REPO / 'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
        ('virtual-keyboard', REPO / 'tests/native/virtual-keyboard-unstable-v1.xml'),
        ('system-bell', Path('/usr/share/wayland-protocols/staging/xdg-system-bell/xdg-system-bell-v1.xml')),
    ]:
        subprocess.run(['wayland-scanner', 'client-header', str(protocol), str(root / (name + '.h'))], check=True)
        source = root / (name + '.c'); sources.append(str(source))
        subprocess.run(['wayland-scanner', 'private-code', str(protocol), str(source)], check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'wayland-client', 'xkbcommon'], text=True))
    pointer_path = root / 'pointer'
    subprocess.run(['cc', '-I' + str(root), str(REPO / 'tests/wobbly/pointer.c'), *sources, '-o', str(pointer_path), *flags], check=True)
    conf = root / 'hyprland.conf'
    conf.write_text('''monitor=,1280x900@60,auto,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
debug:disable_logs=false
input:follow_mouse=0
animations:enabled=false
general:border_size=3
bindm=SUPER,mouse:272,movewindow
bindm=SUPER,mouse:273,resizewindow
''')
    verify = subprocess.run(['Hyprland', '--verify-config', '--config', str(conf)], capture_output=True, text=True)
    assert verify.returncode == 0, verify.stdout + verify.stderr
    runtime = Path(tempfile.mkdtemp(prefix='wb-', dir='/tmp'))
    parent = os.environ.get('WAYLAND_DISPLAY', 'wayland-0')
    if not parent.startswith('/'): parent = str(Path(os.environ['XDG_RUNTIME_DIR']) / parent)
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), XDG_CACHE_HOME=str(home / '.cache'),
               XDG_DATA_HOME=str(home / '.local/share'), XDG_STATE_HOME=str(home / '.local/state'), XDG_RUNTIME_DIR=str(runtime),
               WAYLAND_DISPLAY=parent, AQ_BACKENDS='wayland', HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1',
               QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='', QT_WAYLAND_DISABLE_WINDOWDECORATION='1',
               QT_PLUGIN_PATH='', GSETTINGS_BACKEND='memory', XETAL_MINIMIZE_CONFIG=str(minimize))
    for key in ('HYPRLAND_INSTANCE_SIGNATURE', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'): env.pop(key, None)
    children, logs = [], []

    def spawn(args, **kwargs):
        log = (root / f'child-{len(children)}.log').open('w'); logs.append(log)
        p = subprocess.Popen(args, env=kwargs.pop('env', env), stderr=log, stdout=kwargs.pop('stdout', log), **kwargs)
        children.append(p); return p

    def run(*args):
        p = subprocess.run(args, env=env, capture_output=True, text=True, timeout=15)
        assert p.returncode == 0, (args, p.stdout, p.stderr)
        return p.stdout.strip()

    def ctl(*args): return run('hyprctl', *args)
    def dispatch(*args): assert ctl('dispatch', *args) == 'ok', args
    def wait(predicate, seconds=8):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            value = predicate()
            if value: return value
            time.sleep(.04)
        raise AssertionError('Timed out: ' + str(predicate))
    def clients(): return json.loads(ctl('-j', 'clients'))
    def client(name='Buttons'): return next((c for c in clients() if c['title'] == name), None)
    def status(): return json.loads(ctl('xetal-windowclose'))
    def min_status(): return json.loads(ctl('xetal-minimize'))
    def address(name='Buttons'): return 'address:' + client(name)['address']
    def geometry(name='Buttons'):
        c = client(name); return [*c['at'], *c['size']]

    try:
        compositor = spawn(['Hyprland', '--config', str(conf)], start_new_session=True)
        def instance():
            assert compositor.poll() is None, 'Nested compositor exited'
            try: return next((i for i in json.loads(ctl('-j', 'instances')) if i['pid'] == compositor.pid), None)
            except ValueError: return None
        i = wait(instance); env.update(HYPRLAND_INSTANCE_SIGNATURE=i['instance'], WAYLAND_DISPLAY=i['wl_socket'])
        def size_output(w, h):
            def parent_clients():
                return json.loads(subprocess.check_output(['hyprctl', '-j', 'clients'], env=os.environ, text=True))
            surface = wait(lambda: next((c for c in parent_clients() if c['pid'] == compositor.pid), None))
            target = 'address:' + surface['address']
            for action, arg in [('setfloating', target), ('resizewindowpixel', f'exact {w} {h},' + target)]:
                subprocess.run(['hyprctl', 'dispatch', action, arg], env=os.environ, capture_output=True, check=True)
            wait(lambda: json.loads(ctl('-j', 'monitors'))[0]['width'] == w)
            time.sleep(.3)
        wait(lambda: json.loads(ctl('-j', 'monitors'))); size_output(1280, 900)
        # Parent pointer motion must not interrupt a virtual double-click.
        # Disable only the nested backend's devices, before creating test input.
        devices=json.loads(ctl('-j','devices'))
        for group in ('mice','keyboards'):
            for device in devices[group]:
                assert ctl('keyword',f'device[{device["name"]}]:enabled','false')=='ok'
        minimize_binary = sys.argv[sys.argv.index('--minimize-plugin')+1] if '--minimize-plugin' in sys.argv else str(minimize_build.build())
        assert ctl('plugin', 'load', minimize_binary) == 'ok'
        memory_binary=subprocess.check_output([sys.executable,str(REPO/'config/hypr/runtime/window_memory/build.py')],text=True).strip()
        assert ctl('plugin','load',memory_binary)=='ok'
        assert ctl('plugin', 'load', str(binary)) == 'ok'
        if '--launch-only' in sys.argv:
            bus=spawn(['dbus-daemon','--session','--nofork','--print-address=1'],stdout=subprocess.PIPE,text=True)
            env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
            assert env['DBUS_SESSION_BUS_ADDRESS'].startswith('unix:')
        fixture='tests/window-buttons/background_client.py' if '--background-only' in sys.argv else 'tests/wobbly/client.py'
        if '--stacking-only' in sys.argv:fixture='tests/window-buttons/stacking_client.py'
        app = spawn([sys.executable, str(REPO / fixture), '-name', 'wobbly-test'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        def command(op, name='Buttons', process=app):
            process.stdin.write(json.dumps(dict(op=op, name=name)) + '\n'); process.stdin.flush()
            assert process.stdout.readline().strip() == 'ok'
        command('add'); wait(lambda: client())
        pointer = spawn([str(pointer_path), '1280', '900'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        def point(line):
            pointer.stdin.write(line + '\n'); pointer.stdin.flush(); assert pointer.stdout.readline().strip() == 'ok'
        def reveal(name='Buttons'):
            c = client(name); point(f"move {max(0, c['at'][0]) + 100} {max(0, c['at'][1]) + 70}")
            point('key 125 1'); wait(lambda: status()['visible'])
        def aim(index):
            b = status()['buttons'][index]['box']; point(f'move {round(b[0]+b[2]/2)} {round(b[1]+b[3]/2)}')
        def click(index, name='Buttons'):
            reveal(name); aim(index); point('down 272'); point('up 272'); time.sleep(.15); point('key 125 0')
        def fits(name='Buttons'):
            c = client(name); m = json.loads(ctl('-j', 'monitors'))[0]
            x, y = c['at']; w, h = c['size']; left, top, right, bottom = m['reserved']
            assert x >= left + 3 and y >= top + 3 and x+w <= m['width']-right-3 and y+h <= m['height']-bottom-3, (c, m)

        if '--stacking-only' in sys.argv:
            from PIL import Image
            workspace=client()['workspace']['id'];controller_path=workspace_dir/'controller.py'
            def policy(mode):
                run(sys.executable,str(controller_path),'--workspace',str(workspace),'--layout',mode)
            def counts():
                app.stdin.write('{"op":"counts"}\n');app.stdin.flush()
                return json.loads(app.stdout.readline())
            def tap(x,y):
                point(f'move {x} {y}');point('down 272');point('up 272')
            def visible_color(label,expected):
                image=root/(label+'.png');run('grim',str(image))
                with Image.open(image) as shot:
                    actual=shot.convert('RGB').getpixel((450,470))
                assert max(abs(a-b) for a,b in zip(actual,expected))<8,(label,actual,expected)
            command('add','Media');wait(lambda:client('Media'))
            for mode in ('floating','kde'):
                policy(mode)
                assert all(c['floating'] for c in clients())
                for operation,fullscreen in (('max',1),('full',2)):
                    command(operation);wait(lambda:client()['fullscreen']==fullscreen)
                    dispatch('resizewindowpixel','exact 400 260,'+address('Media'))
                    dispatch('movewindowpixel','exact 400 250,'+address('Media'))
                    for repeat in range(3):
                        dispatch('focuswindow',address('Media'))
                        wait(lambda:client('Media')['allowedOverFullscreen'] and client('Media')['acceptsInput'])
                        visible_color(f'{mode}-{operation}-{repeat}-media',(208,128,32))
                        before=counts();tap(450,470)
                        wait(lambda:counts()['Media']>before['Media'])
                        tap(80,760) # exposed browser content, outside Media
                        wait(lambda:json.loads(ctl('-j','activewindow'))['title']=='Buttons')
                        assert not client('Media')['allowedOverFullscreen'],clients()
                        visible_color(f'{mode}-{operation}-{repeat}-browser',(32,80,128))
                        before=counts();tap(450,470) # former overlay rectangle
                        wait(lambda:counts()['Buttons']>before['Buttons'])
                        assert counts()['Media']==before['Media']
                    dispatch('workspace','2');dispatch('workspace',str(workspace))
                    assert not client('Media')['allowedOverFullscreen']
                    visible_color(f'{mode}-{operation}-roundtrip',(32,80,128))
                    # Normal restore keeps both windows accessible again.
                    command('restore');wait(lambda:client()['fullscreen']==0)
                    dispatch('focuswindow',address('Media'))
                    assert client('Media')['acceptsInput']
            policy('off')
            dispatch('settiled',address());command('max');wait(lambda:client()['fullscreen']==1)
            dispatch('focuswindow',address('Media'));tap(80,760)
            assert client('Media')['allowedOverFullscreen'] # normal floating-over-tiling policy
            print('PASS: Force floating/KDE render and click order, maximize/fullscreen, workspace return and Individual isolation.',flush=True)
            return

        if '--kde-only' in sys.argv:
            workspace=client()['workspace']['id'];controller_path=workspace_dir/'controller.py'
            def policy(**values):
                args=[sys.executable,str(controller_path),'--workspace',str(workspace)]
                for key,value in values.items():args.extend(['--'+key,value])
                run(*args)
            def info(name='Missing controls'):
                ids=json.loads(ctl('xetal-windowbuttons'))['windows']
                return next(v for v in (json.loads(ctl('xetal-windowbuttons',i)) for i in ids) if v['address']==client(name)['address'])
            binary_fixture=root/'decorations'
            gtk_flags=shlex.split(run('pkg-config','--cflags','--libs','gtk+-3.0'))
            run('cc',str(REPO/'tests/window-buttons/decorations.c'),'-o',str(binary_fixture),'-lglfw','-lGL',*gtk_flags)
            missing=spawn([str(binary_fixture)]);wait(lambda:client('Missing controls'))
            # Preserve old choices even when workspace controls were forced Off.
            policy(layout='kde',controls='off')
            wait(lambda:client('Missing controls')['floating'] and client()['floating'])
            assert info()['control_profile']=='kde' and info()['rule']['mode']=='auto',info()
            assert info()['decoration_hint']=='server',info()
            dispatch('settiled',address('Missing controls'));assert client('Missing controls')['floating']
            def hover(name='Missing controls'):
                dispatch('focuswindow',address(name))
                dispatch('alterzorder','top,'+address(name))
                c=client(name);point(f"move {c['at'][0]+100} {c['at'][1]+70}");point('key 125 0')
                time.sleep(.15)
            def action(index):
                hover();wait(lambda:status()['visible']);aim(index)
                point('down 272');point('up 272');time.sleep(.15)
            hover();wait(lambda:status()['visible'])
            assert status()['gear_visible'] and status()['buttons'][3]['box']==[0,0,0,0],status()
            settings.write_text(model.encode(dict(model.DEFAULTS,enabled=False)));dispatch('xetalwindowclose:reload')
            hover();wait(lambda:status()['visible']);assert not status()['enabled']
            settings.write_text(model.encode(model.DEFAULTS));dispatch('xetalwindowclose:reload')
            initial=geometry('Missing controls');action(1);wait(lambda:client('Missing controls')['fullscreen']==1)
            maximized=geometry('Missing controls')
            assert ctl('plugin','unload',memory_binary)=='ok'
            assert ctl('plugin','load',memory_binary)=='ok'
            assert client('Missing controls')['fullscreen']==1 and geometry('Missing controls')==maximized
            action(1);wait(lambda:client('Missing controls')['fullscreen']==0 and geometry('Missing controls')==initial)
            assert ctl('xetal-window-state',client('Missing controls')['address'],'2','2')=='ok'
            wait(lambda:client('Missing controls')['fullscreen']==2);hover();wait(lambda:not status()['visible'])
            assert ctl('xetal-window-state',client('Missing controls')['address'],'0','0')=='ok'
            hover();wait(lambda:status()['visible'])
            action(0);wait(lambda:min_status()['active']==1)
            dispatch('xetalminimize:restoreall')
            wait(lambda:min_status()['active']==0);hover();wait(lambda:status()['visible'])
            run('grim',str(root/'kde-controls.png'))
            print('PASS: KDE floats existing windows; missing controls, no tile, no-modifier maximize/restore/minimize.',flush=True)
            # An actual GTK headerbar must keep its own buttons, while retaining
            # a Super gear for correcting inaccurate decoration hints.
            csd=spawn([str(binary_fixture),'gtk'],env=dict(env,GDK_BACKEND='wayland'))
            wait(lambda:client('Wayland client frame'))
            assert client('Wayland client frame')['floating']
            assert info('Wayland client frame')['decoration_hint']=='client',info('Wayland client frame')
            hover('Wayland client frame');assert not status()['visible']
            point('key 125 1');wait(lambda:status()['gear_visible']);point('key 125 0')
            # Use the real gear without Super on a fallback row.
            hover();wait(lambda:status()['gear_visible']);g=status()['gear']
            point(f'move {round(g[0]+g[2]/2)} {round(g[1]+g[3]/2)}');point('down 272');point('up 272')
            real_editor=wait(lambda:next((c for c in clients() if c['class']=='fusion-window-buttons'),None))
            dispatch('closewindow','address:'+real_editor['address']);wait(lambda:not any(c['class']=='fusion-window-buttons' for c in clients()))
            wait(lambda:not info()['preview'])
            window_id=info()['id'];app_key=info()['app']
            standard=settings.with_name('rules.json');standard_rule=dict(rules.DEFAULTS,mode='nearby',size=34)
            standard.write_text(rules.encode({'version':1,'apps':{app_key:standard_rule}}));before=standard.read_bytes()
            dispatch('xetalwindowclose:reload')
            editor=spawn([sys.executable,str(REPO/'tests/window-buttons/editor.py'),str(home/'.config/hypr'),window_id],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            wait(lambda:any(c['pid']==editor.pid for c in clients()))
            def edit(op,**values):
                editor.stdin.write(json.dumps(dict(op=op,**values))+'\n');editor.stdin.flush();return json.loads(editor.stdout.readline())
            assert edit('state')['rule']['mode']=='auto'
            wait(lambda:info()['preview'])
            assert info()['preview_boxes'][3]==[0,0,0,0]
            edit('mode',value='off');saved=edit('apply');assert saved['status'].startswith('Applied.'),saved
            assert info()['rule']['mode']=='off' and standard.read_bytes()==before
            policy(layout='floating',controls='individual')
            assert info()['rule']==standard_rule and not info()['preview']
            rejected=edit('apply');assert 'mode changed' in rejected['status'],rejected
            edit('reload');assert edit('state')['rule']==standard_rule
            policy(layout='kde');edit('reload');assert edit('state')['rule']['mode']=='off'
            edit('scope',value='window');edit('mode',value='always');assert edit('apply')['status'].startswith('Applied.')
            edit('close');editor.wait(timeout=5);hover();wait(lambda:status()['visible'])
            assert info()['window_override'] and standard.read_bytes()==before
            print('PASS: live KDE gear preview, separate app/window saves, mode isolation, stale-editor rejection and inherited standard choices.',flush=True)
            # Real XWayland hints, polled without blocking the compositor.
            display=root/'x-display'
            dispatch('exec','sh -c '+shlex.quote('printf "%s" "$DISPLAY" > '+shlex.quote(str(display))))
            wait(lambda:display.exists() and display.read_text())
            xenv=dict(env,DISPLAY=display.read_text())
            xserver=spawn([str(binary_fixture),'x11'],env=xenv);wait(lambda:client('X11 controls'))
            hover('X11 controls');wait(lambda:info('X11 controls')['decoration_hint']=='server')
            wait(lambda:status()['visible']);assert not status()['buttons'][3]['box'][2]
            xclient=spawn([str(binary_fixture),'x11','client'],env=xenv);wait(lambda:client('Client frame'))
            hover('Client frame');wait(lambda:info('Client frame')['decoration_hint']=='client')
            time.sleep(.15);assert not status()['visible']
            # Close disposes cached hints and the session override, new windows
            # retain only the persistent KDE app choice.
            assert info()['rule']['mode']=='always' and info()['window_override'],info()
            hover();action(2);missing.wait(timeout=5);wait(lambda:not client('Missing controls'))
            missing=spawn([str(binary_fixture)]);wait(lambda:client('Missing controls'))
            assert info()['id']!=window_id and not info()['window_override'] and info()['rule']['mode']=='off'
            assert ctl('plugin','unload',str(binary))=='ok'
            assert ctl('plugin','load',str(binary))=='ok'
            assert info()['rule']['mode']=='off' and info()['control_profile']=='kde'
            print('PASS: X11 server/client hints, window lifetime, persisted KDE choice and safe plugin reload.',flush=True)
            for expected in ('off','tile','floating','kde'):
                run(sys.executable,str(controller_path),'--workspace',str(workspace),'--cycle-layout')
                assert info()['workspace_layout']==expected
            return

        if '--workspaces-only' in sys.argv:
            workspace=client()['workspace']['id']
            controller_path=workspace_dir/'controller.py'
            def policy(number=workspace,**values):
                args=[sys.executable,str(controller_path),'--workspace',str(number)]
                for key,value in values.items():args.extend(['--'+key,value])
                run(*args)
            def info(name='Buttons'):
                ids=json.loads(ctl('xetal-windowbuttons'))['windows']
                return next(v for v in (json.loads(ctl('xetal-windowbuttons',i)) for i in ids) if v['address']==client(name)['address'])
            command('add','Other');wait(lambda:client('Other'))
            policy(layout='floating');wait(lambda:client()['floating'] and client('Other')['floating']);fits();fits('Other')
            dispatch('settiled',address());assert client()['floating']
            command('add','New floating');wait(lambda:client('New floating'))
            assert client('New floating')['floating'];fits('New floating')
            command('close','New floating');wait(lambda:not client('New floating'))
            policy(layout='tile');wait(lambda:not client()['floating'] and not client('Other')['floating'])
            dispatch('setfloating',address());assert not client()['floating']
            assert client()['size'][0]*client()['size'][1] < 1280*900*.75,'Windows must share the tiled layout'
            reveal();point('down 272');point('move 700 350');point('up 272');point('key 125 0')
            wait(lambda:not client()['floating']);time.sleep(.1)
            assert not client()['floating'] and client()['size'][0]*client()['size'][1] < 1280*900*.75
            # A contradictory launch rule must not produce tile/float jumps.
            dispatch('focuswindow',address())
            assert ctl('keyword','windowrule','match:class ^wobbly-test$,float on')=='ok'
            command('add','New tiled');wait(lambda:client('New tiled'))
            for _ in range(6):assert not client('New tiled')['floating'];time.sleep(.03)
            command('close','New tiled');wait(lambda:not client('New tiled'))
            assert ctl('keyword','windowrule','match:class ^wobbly-test$,float off')=='ok'
            policy(2,layout='floating')
            dispatch('movetoworkspacesilent','2,'+address('Other'));wait(lambda:client('Other')['floating'])
            dispatch('movetoworkspacesilent',str(workspace)+','+address('Other'));wait(lambda:not client('Other')['floating'])
            policy(layout='off');dispatch('setfloating',address());assert client()['floating']
            dispatch('settiled',address());assert not client()['floating']
            print('PASS: existing/new/moved windows obey workspace layouts; Off restores normal mode changes.',flush=True)

            # User rules can target an app plus a title, and later matches win.
            # Workspace overrides remain stronger than every user rule.
            from window_rules import model as window_rules
            rule_path=home/'.config/hypr/window_rules/rules.json'
            matched=dict(rules.DEFAULTS,mode='always',size=35)
            specific=dict(rules.DEFAULTS,mode='nearby',size=19)
            document=window_rules.validate({'version':1,'rules':[
                dict(window_rules.DEFAULT, id='a'*32, name='App buttons', app='wobbly-*', controls=matched),
                dict(window_rules.DEFAULT, id='b'*32, name='Title buttons', app='wobbly-*', title='But*', controls=specific),
            ]})
            rule_path.write_text(json.dumps(document));dispatch('xetalwindowclose:reload')
            assert info()['rule']==specific and info('Other')['rule']==matched
            policy(controls='on');assert info()['rule']==info('Other')['rule'] and info()['rule']['mode']=='always'
            policy(controls='off');point('key 125 1');time.sleep(.1)
            assert not status()['visible'];point('key 125 0')
            policy(controls='individual');assert info()['rule']==specific and info('Other')['rule']==matched
            rule_path.write_text('{"version":1,"rules":[]}');dispatch('xetalwindowclose:reload')
            print('PASS: app/title window rules, last-match order, and workspace On/Off/Individual priority.',flush=True)

            behavior=dict(window_rules.DEFAULT,id='c'*32,name='Window geometry',app='wobbly-*',
                          title='User positioned',layout='floating',width=640,height=400,position='center')
            rule_conf=rule_path.with_suffix('.conf')
            rule_conf.write_text(window_rules.render({'version':1,'rules':[behavior]}))
            conf.write_text(conf.read_text()+'source = '+str(rule_conf)+'\n')
            assert ctl('reload')=='ok';assert not ctl('configerrors')
            command('add','User positioned');wait(lambda:client('User positioned'))
            positioned=client('User positioned')
            assert positioned['floating'] and positioned['size']==[640,400],positioned
            assert 'fusion-managed-rule' in [tag.removesuffix('*') for tag in positioned['tags']],positioned
            fits('User positioned')
            policy(layout='tile');wait(lambda:not client('User positioned')['floating'])
            dispatch('setfloating',address('User positioned'));assert not client('User positioned')['floating']
            command('close','User positioned');wait(lambda:not client('User positioned'))
            rule_conf.write_text(window_rules.render({'version':1,'rules':[]}));assert ctl('reload')=='ok'
            policy(layout='off')
            print('PASS: generated app/title behavior applies floating geometry on first map; workspace tile still wins.',flush=True)

            app_rules=settings.with_name('rules.json');app_key=info()['app']
            individual=dict(rules.DEFAULTS,mode='nearby',size=42,x=20)
            app_rules.write_text(rules.encode({'version':1,'apps':{app_key:individual}}));dispatch('xetalwindowclose:reload')
            original=app_rules.read_bytes()
            policy(controls='on')
            assert info()['rule']['mode']=='always' and info('Other')['rule']==info()['rule']
            reveal();point('key 125 0');wait(lambda:status()['visible']);assert not status()['gear_visible']
            window_id=info()['id']
            editor=spawn([sys.executable,str(REPO/'tests/window-buttons/editor.py'),str(home/'.config/hypr'),window_id],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            editor_client=wait(lambda:next((c for c in clients() if c['pid']==editor.pid),None))
            dispatch('setfloating','address:'+editor_client['address'])
            def edit(op,**values):
                editor.stdin.write(json.dumps(dict(op=op,**values))+'\n');editor.stdin.flush();return json.loads(editor.stdout.readline())
            state=edit('state');assert state['scope']=='workspace',state
            wait(lambda:info()['preview'] and info('Other')['preview'])
            edit('slider',key='size',value=24);edit('slider',key='x',value=31)
            wait(lambda:info()['preview_rule']['size']==24 and info('Other')['preview_rule']['x']==31)
            assert info()['rule']['size']!=24 and app_rules.read_bytes()==original
            state=edit('apply');assert state['status'].startswith('Applied.'),state
            assert info()['rule']['size']==24 and info('Other')['rule']['size']==24
            run('grim',str(root/'shared-workspace-preview.png'))
            # A stale editor must never override workspace Off, even under Super.
            policy(controls='off');point('key 125 1');time.sleep(.1)
            assert not info()['preview'] and not info('Other')['preview']
            assert not status()['visible'] and not status()['gear_visible']
            edit('close');editor.wait(timeout=5);point('key 125 0')
            policy(controls='individual');assert info()['rule']==individual and app_rules.read_bytes()==original
            # The taskbar editor has a workspace identity even with controls
            # Off or no windows. Applying shared dimensions never enables it.
            editor=spawn([sys.executable,str(REPO/'tests/window-buttons/editor.py'),str(home/'.config/hypr'),'workspace:9'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            wait(lambda:next((c for c in clients() if c['pid']==editor.pid),None))
            state=edit('state');assert state['scope']=='workspace',state
            edit('slider',key='size',value=18)
            state=edit('apply');assert state['status'].startswith('Applied.'),state
            entry=json.loads((workspace_dir/'rules.json').read_text())['workspaces']['9']
            assert entry['controls']=='individual' and entry['rule']['size']==18 and entry['layout']=='off',entry
            edit('close');editor.wait(timeout=5)
            policy(controls='off')
            editor=spawn([sys.executable,str(REPO/'tests/window-buttons/editor.py'),str(home/'.config/hypr'),f'workspace:{workspace}'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            wait(lambda:next((c for c in clients() if c['pid']==editor.pid),None))
            state=edit('state');assert state['rule']['size']==24,state
            edit('slider',key='size',value=20);state=edit('apply');assert state['status'].startswith('Applied.'),state
            point('key 125 1');time.sleep(.1);assert not status()['visible'];point('key 125 0')
            assert info()['workspace_controls']=='off'
            edit('close');editor.wait(timeout=5)
            policy(controls='on')
            editor=spawn([sys.executable,str(REPO/'tests/window-buttons/editor.py'),str(home/'.config/hypr'),f'workspace:{workspace}'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            wait(lambda:next((c for c in clients() if c['pid']==editor.pid),None))
            state=edit('state');assert state['rule']['size']==20,state
            edit('slider',key='size',value=24)
            wait(lambda:info()['preview_rule']['size']==24 and info('Other')['preview_rule']['size']==24)
            state=edit('apply');assert state['status'].startswith('Applied.'),state
            edit('close');editor.wait(timeout=5)
            print('PASS: workspace Settings edits empty/Off workspaces, preserves visibility, and previews shared settings while On.',flush=True)
            policy(controls='on');assert info()['rule']['size']==24
            settings.write_text(model.encode(dict(model.DEFAULTS,enabled=False)));dispatch('xetalwindowclose:reload')
            reveal();point('key 125 0');wait(lambda:status()['visible'])
            settings.write_text(model.encode(model.DEFAULTS));dispatch('xetalwindowclose:reload')
            assert ctl('plugin','unload',str(binary))=='ok';assert ctl('plugin','load',str(binary))=='ok'
            assert info()['rule']['size']==24 and info()['workspace_controls']=='on'
            policy(layout='tile')
            click(1);wait(lambda:client()['fullscreen']==1);assert not client()['floating']
            click(1);wait(lambda:client()['fullscreen']==0);assert not client()['floating']
            click(0);wait(lambda:min_status()['active']==1)
            dispatch('xetalminimize:restoreall');wait(lambda:min_status()['active']==0)
            wait(lambda:not client()['floating'] and client()['workspace']['id']==workspace)
            assert ctl('plugin','unload',memory_binary)=='ok';assert ctl('plugin','load',memory_binary)=='ok'
            dispatch('setfloating',address());assert not client()['floating']
            print('PASS: shared gear editor/live preview, persistence, Individual restoration, Off under Super, and native maximize/restore.',flush=True)
            run(sys.executable,str(REPO/'config/hypr/waybar/options/test_options.py'),'--native')
            assert not ctl('configerrors')
            return

        def check_chrome():
            browser = shutil.which('google-chrome-stable') or shutil.which('chromium')
            assert browser, 'Chrome or Chromium is required for the native title-bar regression'
            fixture = root / 'native.html'
            fixture.write_text('<title>Native window controls</title><body style="background:#163144;color:white">Native controls regression</body>')
            profile=root/'browser/Default';profile.mkdir(parents=True)
            (profile/'Preferences').write_text(json.dumps({'browser':{'custom_chrome_frame':True}}))
            for toolkit in ('gtk-3.0','gtk-4.0'):
                config=home/'.config'/toolkit;config.mkdir(parents=True,exist_ok=True)
                (config/'settings.ini').write_text('[Settings]\ngtk-decoration-layout=:minimize,maximize,close\n')
            chrome_env=dict(env,WAYLAND_DEBUG='client',GSETTINGS_BACKEND='keyfile')
            # gsettings uses this private keyfile backend, never the user's
            # D-Bus/dconf service. Assert every writable config path before it
            # runs; this test is forbidden from targeting the real profile.
            for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):
                assert Path(chrome_env[key]).resolve().is_relative_to(root), (key,chrome_env[key])
            assert 'DBUS_SESSION_BUS_ADDRESS' not in chrome_env
            assert Path(chrome_env['HOME']) != Path.home()
            print('Isolated GTK preferences:',chrome_env['XDG_CONFIG_HOME'],'backend:',chrome_env['GSETTINGS_BACKEND'],flush=True)
            subprocess.run(['gsettings','set','org.gnome.desktop.wm.preferences','button-layout',':minimize,maximize,close'],env=chrome_env,check=True)
            spawn([browser, '--ozone-platform=wayland', '--no-first-run', '--no-default-browser-check',
                   '--disable-background-networking', '--disable-sync', '--password-store=basic', '--disable-component-update',
                   '--remote-debugging-port=0', '--user-data-dir='+str(root/'browser'), fixture.as_uri()], env=chrome_env)
            def chrome(): return next((c for c in clients() if c['class'].startswith(('google-chrome', 'chromium', 'chrome-'))), None)
            c = wait(chrome); addr = 'address:'+c['address']
            dispatch('setfloating', addr); dispatch('resizewindowpixel', 'exact 850 600,'+addr)
            dispatch('movewindowpixel', 'exact 120 100,'+addr); dispatch('focuswindow', addr); time.sleep(.6)
            run('grim', str(root/'chrome-before.png'))
            if '--tabs-only' in sys.argv:
                import urllib.request
                probe=subprocess.check_output([sys.executable,str(REPO/'config/hypr/runtime/cursor_probe/build.py')],text=True).strip()
                assert ctl('plugin','load',probe)=='ok'
                assert ctl('keyword','bindn',',mouse:272,event,xetal-floating-drag-press')=='ok'
                assert ctl('keyword','bindinr',',mouse:272,event,xetal-floating-drag-release')=='ok'
                spawn([sys.executable,str(REPO/'config/hypr/scripts/floating-drag.py')])
                port_file=root/'browser/DevToolsActivePort';wait(port_file.exists)
                endpoint='http://127.0.0.1:'+port_file.read_text().splitlines()[0]
                def pages():
                    with urllib.request.urlopen(endpoint+'/json/list',timeout=3) as response:
                        return [page for page in json.load(response) if page['type']=='page']
                def add_tab():
                    request=urllib.request.Request(endpoint+'/json/new?about:blank',method='PUT')
                    with urllib.request.urlopen(request,timeout=3) as response:json.load(response)
                    time.sleep(.5)
                # Deliberately use only this throwaway profile's blank tabs.
                add_tab();run('grim',str(root/'chrome-tabs.png'))
                print('Chrome tab baseline',chrome()['at'],chrome()['size'],len(pages()),flush=True)
                # Upper, center and lower parts of the *visible* X. Before
                # the geometry fix, only the lower part received a click.
                for dx,dy in ((254,16),(256,20),(258,24)):
                    c=chrome();before=len(pages())
                    point(f"move {c['at'][0]+dx} {c['at'][1]+dy}");time.sleep(.5)
                    point('down 272');time.sleep(.04)
                    # A one-pixel held motion takes the compositor's implicit
                    # grab path; it must retain the same surface origin.
                    point(f"move {c['at'][0]+dx+1} {c['at'][1]+dy}");point('up 272');time.sleep(.4)
                    after=len(pages());assert after==before-1,('Tab X missed',dx,dy,before,after)
                    add_tab()
                print('Chrome tab X accepts upper, center, lower and held-motion clicks',flush=True)
                before=(chrome()['at'],chrome()['size'])
                assert ctl('plugin','unload',memory_binary)=='ok'
                assert ctl('plugin','load',memory_binary)=='ok'
                assert (chrome()['at'],chrome()['size'])==before
                assert json.loads(ctl('xetal-windows'))
                print('Input adapter reload keeps live windows and metadata intact',flush=True)
                return
            for gesture in ('button', 'double-click'):
                for cycle in range(4):
                    c = chrome(); expected = 0 if c['fullscreen'] == 1 else 1
                    print('Chrome',gesture,cycle,'requesting',expected,flush=True)
                    x = c['at'][0] + (c['size'][0]-48 if gesture == 'button' else c['size'][0]/2)
                    y = c['at'][1]+20
                    point(f'move {round(x)} {round(y)}')
                    for _ in range(2 if gesture == 'double-click' else 1):
                        point('down 272'); point('up 272'); time.sleep(.06)
                    wait(lambda: chrome()['fullscreen'] == expected)
                    time.sleep(.25)
                print('Chrome native '+gesture+' repeatedly maximizes/restores without minimizing', flush=True)
            dispatch('closewindow', addr); wait(lambda: not chrome())

        if '--native-only' in sys.argv or '--tabs-only' in sys.argv:
            check_chrome(); return

        if '--launch-only' in sys.argv:
            profile=home/'.config/hypr'
            memory=spawn([sys.executable,str(REPO/'config/hypr/runtime/window_memory/service.py'),'--state',str(root/'windows.json')])
            wait(lambda:any(p['name']=='Xetal Window Memory' for p in json.loads(ctl('-j','plugin','list'))))
            # A desktop entry goes through the real launcher path, including
            # first-map rules, size memory, and a private D-Bus for Kate.
            driver=root/'launch.py'
            driver.write_text('''import sys
sys.path.insert(0,sys.argv[1]+'/launcher')
from gi.repository import Gio
from shortcuts import Entry
entry=Entry('org.kde.kate.desktop',Gio.DesktopAppInfo.new_from_filename(sys.argv[2]))
entry.launch(floating=sys.argv[3]=='float')
''')
            desktop=root/'kate.desktop'
            desktop.write_text('[Desktop Entry]\nType=Application\nName=Kate fixture\nExec=kate --new --startanon\nTerminal=false\n')
            def kate():return next((c for c in clients() if c['class']=='org.kde.kate'),None)
            def launch_kate(mode):
                p=spawn([sys.executable,str(driver),str(profile),str(desktop),mode]);assert p.wait(timeout=10)==0
                c=wait(kate,seconds=15)
                snapshots=[]
                for _ in range(50):
                    c=kate();snapshots.append(dict(floating=c['floating'],fullscreen=c['fullscreen'],size=c['size'],at=c['at']))
                    assert c['floating']==(mode=='float') and c['fullscreen']==0 and c['fullscreenClient']==0,(mode,c)
                    time.sleep(.04)
                (root/(mode+'-launch.json')).write_text(json.dumps(snapshots,indent=2))
                return 'address:'+c['address']
            addr=launch_kate('float');dispatch('resizewindowpixel','exact 710 490,'+addr);dispatch('movewindowpixel','exact 150 170,'+addr)
            time.sleep(1.3);dispatch('focuswindow',addr);dispatch('fullscreenstate','1 1');time.sleep(1.3)
            assert kate()['fullscreen']==1
            dispatch('closewindow',addr);wait(lambda:not kate());time.sleep(.4)
            addr=launch_kate('tile')
            assert not client()['floating'] and client()['size'][0]>300 and kate()['size'][0]>300
            assert abs(client()['size'][0]-kate()['size'][0])<80,(client(),kate())
            dispatch('closewindow',addr);wait(lambda:not kate());time.sleep(.4)
            addr=launch_kate('float')
            assert kate()['size']==[710,490],kate()
            assert all(abs(a-b)<=3 for a,b in zip(kate()['at'],[150,170])),kate()
            assert memory.poll() is None
            print('Kate: maximized history → stable tiled launch; Ctrl launch restores normal size and position',flush=True)
            return

        if '--builtin-only' in sys.argv:
            command('close');wait(lambda:not client())
            profile=home/'.config/hypr'
            app_env=dict(env,XETAL_FILES_ROOT=str(profile),XETAL_HYPR_ROOT=str(profile),XETAL_KVM_DATA=str(root/'kvm-data'))
            for kind in ('files','panel','settings','theme','kvm'):
                python=kind not in ('files','panel')
                if python:
                    process=spawn([sys.executable,str(REPO/'tests/window-buttons/builtin_client.py'),str(profile),kind],env=app_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
                else:
                    executable=REPO/('config/hypr/file_manager/.build/xetal-files' if kind=='files' else 'config/hypr/control_panel/.build/xetal-control-panel')
                    process=spawn([str(executable),*(['--this-pc'] if kind=='files' else [])],env=app_env)
                def current():return next((c for c in clients() if c['pid']==process.pid),None)
                c=wait(current,seconds=40);addr='address:'+c['address']
                dispatch('setfloating',addr);dispatch('resizewindowpixel','exact 1220 760,'+addr);dispatch('movewindowpixel','exact 25 80,'+addr)
                def controls():
                    if python:
                        process.stdin.write('state\n');process.stdin.flush();return json.loads(process.stdout.readline())
                    w=current()['size'][0]
                    offset,y=(20,18) if kind=='files' else (34,33)
                    return {name:{'box':[w-offset-step*34-16,y-16,32,32]} for step,name in enumerate(('windowClose','windowMaximize','windowMinimize'))}
                def native_click(name):
                    x,y,w,h=controls()[name]['box'];c=current()
                    point(f"move {round(c['at'][0]+x+w/2)} {round(c['at'][1]+y+h/2)}");point('down 272');point('up 272')
                time.sleep(.6);run('grim',str(root/(kind+'-buttons.png')))
                for cycle in range(3):
                    native_click('windowMaximize');wait(lambda:current()['fullscreen']==1)
                    if python:assert controls()['windowMaximize']['caption']=='Restore'
                    native_click('windowMaximize');wait(lambda:current()['fullscreen']==0)
                    if python:assert controls()['windowMaximize']['caption']=='Maximize'
                geometry_before=[*current()['at'],*current()['size']]
                native_click('windowMinimize');wait(lambda:min_status()['active']==1)
                assert process.poll() is None
                dispatch('xetalminimize:restoreall');wait(lambda:min_status()['active']==0)
                wait(lambda:[*current()['at'],*current()['size']]==geometry_before)
                native_click('windowClose');wait(lambda:not current())
                if process.poll() is None:process.terminate();process.wait(timeout=8)
                print(kind+': native minimize/restore, repeated maximize/restore, and close passed',flush=True)
            assert not ctl('configerrors')
            return

        if '--background-only' in sys.argv:
            from PIL import Image
            dispatch('setfloating',address());dispatch('resizewindowpixel','exact 550 650,'+address())
            dispatch('movewindowpixel','exact 700 110,'+address());point('move 800 300')
            window_id=next(i for i in json.loads(ctl('xetal-windowbuttons'))['windows'] if json.loads(ctl('xetal-windowbuttons',i))['address']==client()['address'])
            def info():return json.loads(ctl('xetal-windowbuttons',window_id))
            def screenshot(name):
                path=root/(name+'.png');run('grim',str(path));return Image.open(path).convert('RGB')
            def same_color(actual,expected):
                return all(abs(int(actual[i:i+2],16)-int(expected[i:i+2],16))<=3 for i in (1,3,5))
            original=screenshot('background-before')
            editor=spawn([sys.executable,str(REPO/'tests/window-buttons/editor.py'),str(home/'.config/hypr'),window_id],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            ed=wait(lambda:next((c for c in clients() if c['pid']==editor.pid),None))
            dispatch('setfloating','address:'+ed['address']);dispatch('movewindowpixel','exact 30 60,address:'+ed['address'])
            def edit(op,**values):
                editor.stdin.write(json.dumps(dict(op=op,**values))+'\n');editor.stdin.flush()
                return json.loads(editor.stdout.readline())
            wait(lambda:info()['preview'] and len(info()['preview_boxes'])==5)
            wait(lambda:info()['auto_background']['ready'])
            actual=info()['auto_background']['color'];assert same_color(actual,'#334a5a'),info()
            boxes=info()['preview_boxes'];x=round((boxes[0][0]+boxes[0][2]+boxes[1][0])/2);y=client()['at'][1]+25
            assert min(original.getpixel((x,y)))>245,(x,y,original.getpixel((x,y)))
            matched=screenshot('background-auto')
            assert max(matched.getpixel((x,y)))<200,matched.getpixel((x,y))
            time.sleep(.7);assert same_color(info()['auto_background']['color'],'#334a5a'),'Auto sampled its own backing'
            app.stdin.write(json.dumps(dict(op='color',name='Buttons',color='#75402c'))+'\n');app.stdin.flush();assert app.stdout.readline().strip()=='ok'
            wait(lambda:same_color(info()['auto_background']['color'],'#75402c'))
            screenshot('background-auto-updated')
            print('Auto samples the toolbar, ignores bright native marks, covers gaps, and follows content without feedback',flush=True)
            output=json.loads(ctl('-j','monitors'))[0]['name']
            for scale,transform,color in [('1.25',0,'#4e375a'),('1',1,'#294c37'),('1',0,'#75402c')]:
                assert ctl('keyword','monitor',f'{output},preferred,auto,{scale},transform,{transform}')=='ok'
                time.sleep(.3)
                dispatch('resizewindowpixel','exact 450 550,'+address());dispatch('movewindowpixel','exact 420 110,'+address())
                app.stdin.write(json.dumps(dict(op='color',name='Buttons',color=color))+'\n');app.stdin.flush();assert app.stdout.readline().strip()=='ok'
                try:wait(lambda:same_color(info()['auto_background']['color'],color))
                except AssertionError:
                    screenshot('background-transform-failure');print('Transform failure:',scale,transform,color,info(),client(),ctl('-j','monitors'),flush=True);raise
            dispatch('resizewindowpixel','exact 550 650,'+address());dispatch('movewindowpixel','exact 700 110,'+address())
            print('Auto matches on fractional-scale and rotated outputs',flush=True)
            edit('background',value='manual');edit('color',value='#654321')
            wait(lambda:info()['preview_rule']['background_color']=='#654321' and info()['preview_rule']['background']=='manual')
            assert info()['rule']['background']=='auto','Draft was persisted'
            image=screenshot('background-manual');assert max(image.getpixel((x,y)))<200,image.getpixel((x,y))
            edit('pick');time.sleep(.7);screenshot('background-picker-active')
            point('move 950 350');point('down 272');point('up 272')
            try:wait(lambda:edit('state')['rule']['background_color']=='#195b68')
            except AssertionError:
                print('Picker state:',edit('state'),flush=True);raise
            wait(lambda:info()['preview_rule']['background_color']=='#195b68')
            screenshot('background-picked')
            picked=edit('apply');assert picked['status'].startswith('Applied.'),picked
            assert info()['rule']['background_color']=='#195b68' and info()['rule']['background']=='manual'
            # Escape cancels a desktop pick without overwriting the chosen color.
            edit('pick');time.sleep(.5);point('key 1 1');point('key 1 0');time.sleep(.3)
            assert edit('state')['rule']['background_color']=='#195b68'
            print('Manual live preview, real desktop eyedropper, Apply and picker cancellation passed',flush=True)
            edit('pick-fallback');time.sleep(.4);point('move 950 720');point('down 272');point('up 272')
            wait(lambda:edit('state')['rule']['background_color']=='#cbca40')
            print('Desktop eyedropper fallback works with slurp and grim, without hyprpicker',flush=True)
            edit('background',value='auto');wait(lambda:info()['preview_rule']['background']=='auto')
            wait(lambda:same_color(info()['auto_background']['color'],'#75402c'))
            edit('close');editor.wait(timeout=5);wait(lambda:not info()['preview'])
            assert info()['rule']['background']=='manual'
            hidden=screenshot('background-hidden');assert min(hidden.getpixel((x,y)))>245,hidden.getpixel((x,y))
            assert ctl('plugin','unload',str(binary))=='ok';assert ctl('plugin','load',str(binary))=='ok'
            assert info()['rule']['background_color']=='#195b68'
            assert not ctl('configerrors')
            print('Close discards Auto draft, restores native toolbar, and saved background survives plugin reload',flush=True)
            return

        def check_rules():
            def info(name='Buttons'):
                ids=json.loads(ctl('xetal-windowbuttons'))['windows']
                return next(v for v in (json.loads(ctl('xetal-windowbuttons',i)) for i in ids) if v['address']==client(name)['address'])
            window_id=info()['id']
            def save(scope,value,name='Buttons'):
                ident=info(name)['id']
                code='import sys,json;sys.path.insert(0,sys.argv[1]);from effects.window_close import controller,rules;path,section=controller.rule_file(sys.argv[3]);_,token=rules.load(path,section);controller.save_rule(sys.argv[2],sys.argv[3],json.loads(sys.argv[4]),token)'
                run(sys.executable,'-c',code,str(home/'.config/hypr'),ident,scope,json.dumps(value))
            point('key 125 0')
            always=dict(rules.DEFAULTS,mode='always')
            save('app',always);reveal();point('key 125 0');wait(lambda:status()['visible'])
            assert not status()['gear_visible']
            for expected in (1,0):
                aim(1);point('down 272');point('up 272');wait(lambda:client()['fullscreen']==expected)
                reveal();point('key 125 0');wait(lambda:status()['visible'])
            aim(0);point('down 272');point('up 272');wait(lambda:min_status()['active']==1)
            dispatch('xetalminimize:restoreall');wait(lambda:min_status()['active']==0)
            reveal();point('key 125 0');wait(lambda:status()['visible'])
            save('window',dict(always,mode='off'));wait(lambda:not status()['visible'])
            reveal_gear=lambda: point('key 125 1')
            reveal_gear();wait(lambda:status()['gear_visible']);assert not status()['visible']
            gear=status()['gear'];point(f'move {round(gear[0]+gear[2]/2)} {round(gear[1]+gear[3]/2)}')
            point('down 272');point('up 272');wait(lambda:status()['settings_opened']==1);point('key 125 0')
            editor=wait(lambda:next((c for c in clients() if c['class']=='fusion-window-buttons'),None),12)
            wait(lambda:info()['preview'] and len(info()['preview_boxes'])==5)
            assert all(b[2]>0 for b in info()['preview_boxes'])
            time.sleep(.3);run('grim',str(root/'gear-settings.png'))
            dispatch('closewindow','address:'+editor['address']);wait(lambda:not any(c['class']=='fusion-window-buttons' for c in clients()))
            wait(lambda:not info()['preview'])
            assert info()['rule']['mode']=='off'
            dispatch('focuswindow',address());save('window',dict(always,mode='nearby',anchor='bottom-left',size=48,x=20,y=20,proximity=40))
            c=client();point(f"move {c['at'][0]+c['size'][0]//2} {c['at'][1]+c['size'][1]//2}")
            wait(lambda:not status()['visible']);point('key 125 1');wait(lambda:status()['visible'])
            b=status()['buttons'][0]['box'];assert b[2]==48
            point(f'move {round(b[0]+b[2]/2)} {round(b[1]+b[3]/2)}');point('key 125 0');wait(lambda:status()['visible'])
            assert not status()['gear_visible'];run('grim',str(root/'nearby-buttons.png'))
            point(f"move {c['at'][0]+c['size'][0]//2} {c['at'][1]+c['size'][1]//2}");wait(lambda:not status()['visible'])
            save('window',dict(always,size=64,x=4000,y=4000,anchor='bottom-right'))
            reveal();point('key 125 0');wait(lambda:status()['visible'])
            c=client()
            for b in status()['buttons']:
                x,y,w,h=b['box'];assert c['at'][0]<=x and c['at'][1]<=y and x+w<=c['at'][0]+c['size'][0] and y+h<=c['at'][1]+c['size'][1]
            assert ctl('plugin','unload',str(binary))=='ok';assert ctl('plugin','load',str(binary))=='ok'
            assert info()['rule']['size']==64 and info()['window_override']
            save('window',None);assert info()['rule']==always and not info()['window_override']
            command('add','New app window');wait(lambda:client('New app window'))
            assert info('New app window')['rule']==always
            save('window',dict(always,mode='off'),'New app window');old_id=info('New app window')['id']
            command('close','New app window');wait(lambda:not client('New app window'))
            command('add','Replacement window');wait(lambda:client('Replacement window'))
            assert info('Replacement window')['id']!=old_id and info('Replacement window')['rule']==always
            command('close','Replacement window');save('app',None);dispatch('focuswindow',address())
            assert info()['rule']['mode']=='super'
            print('Gear, nearby/always/off, window/app inheritance, position bounds, reload and window lifetime passed',flush=True)

        if '--rules-only' in sys.argv:
            click(1);wait(lambda:client()['floating']);check_rules();return

        if '--preview-only' in sys.argv:
            click(1);wait(lambda:client()['floating']);point('key 125 0')
            dispatch('resizewindowpixel','exact 550 650,'+address());dispatch('movewindowpixel','exact 700 110,'+address())
            window_id=next(i for i in json.loads(ctl('xetal-windowbuttons'))['windows'] if json.loads(ctl('xetal-windowbuttons',i))['address']==client()['address'])
            def info():return json.loads(ctl('xetal-windowbuttons',window_id))
            app_rules=settings.with_name('rules.json');app_key=info()['app']
            app_choice=dict(rules.DEFAULTS,mode='nearby',size=40)
            window_choice=dict(rules.DEFAULTS,mode='off',size=48,x=28,y=32)
            app_rules.write_text(rules.encode({'version':1,'apps':{app_key:app_choice}}))
            window_rules=runtime/'hypr'/env['HYPRLAND_INSTANCE_SIGNATURE']/'xetal-windowbuttons-rules.json'
            window_rules.write_text(rules.encode({'version':1,'windows':{window_id:window_choice}},'windows'))
            dispatch('xetalwindowclose:reload')
            def start_editor():
                process=spawn([sys.executable,str(REPO/'tests/window-buttons/editor.py'),str(home/'.config/hypr'),window_id],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
                editor=wait(lambda:next((c for c in clients() if c['pid']==process.pid),None))
                dispatch('setfloating','address:'+editor['address']);dispatch('movewindowpixel','exact 30 110,address:'+editor['address'])
                wait(lambda:info()['preview'] and len(info()['preview_boxes'])==5)
                return process
            def edit(process,op,**values):
                process.stdin.write(json.dumps(dict(op=op,**values))+'\n');process.stdin.flush()
                return json.loads(process.stdout.readline())
            original=(app_rules.read_bytes(),window_rules.read_bytes())
            editor=start_editor();state=edit(editor,'state')
            assert state['scope']=='app' and state['rule']==window_choice,state
            point('move 80 180');assert not status()['held']
            assert all(b[2]>0 for b in info()['preview_boxes'])
            edit(editor,'slider',key='x',value=96);edit(editor,'slider',key='y',value=84);edit(editor,'slider',key='size',value=56)
            wait(lambda:info()['preview_rule']['x']==96 and info()['preview_rule']['y']==84 and info()['preview_rule']['size']==56)
            assert info()['rule']==window_choice and (app_rules.read_bytes(),window_rules.read_bytes())==original
            run('grim',str(root/'live-preview.png'))
            edit(editor,'close');editor.wait(timeout=5);wait(lambda:not info()['preview'])
            assert (app_rules.read_bytes(),window_rules.read_bytes())==original
            print('Current settings, remembered-app default, five live buttons, sliders and discard passed',flush=True)
            editor=start_editor();edit(editor,'slider',key='size',value=52);edit(editor,'mode',value='always')
            state=edit(editor,'apply');assert state['status'].startswith('Applied.'),state
            saved=info()['rule'];assert saved['size']==52 and saved['mode']=='always' and not info()['window_override']
            command('add','Same app');wait(lambda:client('Same app'))
            ids=json.loads(ctl('xetal-windowbuttons'))['windows']
            other=next(json.loads(ctl('xetal-windowbuttons',i)) for i in ids if json.loads(ctl('xetal-windowbuttons',i))['address']==client('Same app')['address'])
            assert other['rule']==saved;command('close','Same app')
            state=edit(editor,'reset');assert state['scope']=='window' and state['rule']==rules.DEFAULTS
            assert info()['rule']==saved,'Reset should remain a draft until Apply'
            edit(editor,'apply');assert info()['rule']==rules.DEFAULTS and info()['window_override']
            assert json.loads(app_rules.read_text())['apps'][app_key]==saved
            edit(editor,'close');editor.wait(timeout=5);wait(lambda:not info()['preview'])
            print('App Apply replaces this window override; reset affects only this window after Apply',flush=True)
            editor=start_editor();editor.kill();editor.wait(timeout=5);wait(lambda:not info()['preview'])
            assert info()['rule']==rules.DEFAULTS
            # A missing heartbeat expires even while the owning process lives.
            token='f'*32
            dispatch('xetalwindowclose:preview',json.dumps(dict(action='update',id=window_id,token=token,owner=os.getpid(),rule=window_choice)))
            wait(lambda:info()['preview']);wait(lambda:not info()['preview'],seconds=6)
            assert info()['rule']==rules.DEFAULTS
            editor=start_editor();command('close');wait(lambda:not client())
            edit(editor,'close');editor.wait(timeout=5)
            assert not ctl('configerrors')
            print('Editor crash, expired preview and closing target window clean up without saving drafts',flush=True)
            return

        assert not client()['floating']
        reveal(); assert [b['action'] for b in status()['buttons']] == ['minimize', 'restore', 'close', 'tile']
        run('grim', str(root / 'tiled-buttons.png')); point('key 125 0')
        click(1); wait(lambda: client()['floating']); fits()
        assert client()['size'][0] < 1200 and client()['size'][1] < 840, client()
        # Native buttons and title-bar double clicks issue explicit state
        # requests. They must keep working without a minimize/remap reset.
        for cycle in range(3):
            command('restore'); time.sleep(.15)
            command('max'); wait(lambda: client()['fullscreen'] == 1)
            command('restore'); wait(lambda: client()['fullscreen'] == 0)
        print('Repeated native maximize/restore needs no minimize reset', flush=True)
        first_float = geometry(); click(1); wait(lambda: client()['fullscreen'] == 1)
        click(1); wait(lambda: client()['fullscreen'] == 0 and geometry() == first_float)
        dispatch('resizewindowpixel', 'exact 710 490,' + address()); dispatch('movewindowpixel', 'exact 130 140,' + address())
        wait(lambda: client()['size'] == [710, 490]); dispatch('settiled', address())
        wait(lambda: not client()['floating']); click(1)
        wait(lambda: client()['floating'] and client()['size'] == [710, 490]); fits()
        saved = geometry(); click(1); wait(lambda: client()['fullscreen'] == 1)
        reveal(); assert status()['buttons'][1]['action'] == 'restore'; point('key 125 0')
        click(1); wait(lambda: client()['fullscreen'] == 0 and geometry() == saved)
        command('restore'); time.sleep(.2); command('max')
        wait(lambda: client()['fullscreen'] == 1); click(1)
        wait(lambda: client()['fullscreen'] == 0 and geometry() == saved)
        print('Tiled → remembered float → maximize → restore, including application maximize, passed', flush=True)

        command('add','Tile sibling');wait(lambda:client('Tile sibling'))
        dispatch('settiled',address('Tile sibling'));click(3)
        wait(lambda:not client()['floating'] and client()['fullscreen']==0)
        assert not client('Tile sibling')['floating']
        assert abs(client()['size'][0]-client('Tile sibling')['size'][0])<80,(client(),client('Tile sibling'))
        click(3);assert not client()['floating'],'Tile is idempotent'
        click(1);wait(lambda:client()['floating'] and client()['size']==[710,490])
        click(1);wait(lambda:client()['fullscreen']==1);click(3)
        wait(lambda:not client()['floating'] and client()['fullscreen']==0)
        click(1);wait(lambda:client()['floating'] and client()['size']==[710,490])
        command('close','Tile sibling');wait(lambda:not client('Tile sibling'))
        settings.write_text(model.encode(dict(model.DEFAULTS,size=10)));dispatch('xetalwindowclose:reload')
        reveal();assert all(b['box'][2]==10 for b in status()['buttons']),status()
        run('grim',str(root/'ten-pixel-buttons.png'));point('key 125 0')
        click(3);wait(lambda:not client()['floating'])
        settings.write_text(model.encode(model.DEFAULTS));dispatch('xetalwindowclose:reload');click(1)
        wait(lambda:client()['floating'])
        print('Tile joins the layout, keeps normal floating size, and all controls work down to 10px',flush=True)

        dispatch('resizewindowpixel', 'exact 1150 780,' + address()); wait(lambda: client()['size'] == [1150, 780])
        dispatch('settiled', address()); wait(lambda: not client()['floating'])
        size_output(850, 700); point('extent 850 700'); click(1)
        wait(lambda: client()['floating']); fits()
        assert client()['size'][0] < 850 and client()['size'][1] < 700, client()
        run('grim', str(root / 'smaller-display.png'))
        print('A remembered size from a larger display fits completely inside the smaller display', flush=True)

        # Both windows remain reachable, but the target is deliberately unfocused.
        size_output(1280, 900); point('extent 1280 900')
        dispatch('resizewindowpixel', 'exact 620 400,' + address()); dispatch('movewindowpixel', 'exact 70 180,' + address())
        command('add', 'Other'); wait(lambda: client('Other'))
        dispatch('setfloating', address('Other')); dispatch('resizewindowpixel', 'exact 530 400,' + address('Other'))
        dispatch('movewindowpixel', 'exact 730 150,' + address('Other')); dispatch('focuswindow', address('Other'))
        def activate(name):
            process=spawn([sys.executable,str(REPO/'config/hypr/scripts/activate-window.py'),client(name)['address']]);assert process.wait(timeout=5)==0
            wait(lambda:client(name)['focusHistoryID']==0)
            ordered=[c['address'] for c in clients()]
            assert ordered.index(client(name)['address'])>ordered.index(client('Other' if name=='Buttons' else 'Buttons')['address'])
        activate('Buttons');activate('Other')
        dispatch('xetalminimize:minimize',address());wait(lambda:min_status()['active']==1)
        activate('Buttons');wait(lambda:min_status()['active']==0)
        activate('Other')
        print('Workspace icon activation focuses, raises and restores the addressed window',flush=True)
        saved = geometry(); click(0)
        wait(lambda: min_status()['active'] == 1)
        assert client('Other')['workspace']['id'] > 0 and client()['workspace']['id'] < 0
        dispatch('xetalminimize:restoreall'); wait(lambda: min_status()['active'] == 0)
        wait(lambda: geometry() == saved)
        minimize_values['enabled'] = False; minimize.write_text(minimize_model.encode(minimize_values)); dispatch('xetalminimize:reload')
        before = status()['minimized']; click(0)
        assert not min_status()['enabled'] and min_status()['active'] == 0 and status()['minimized'] == before
        minimize_values['enabled'] = True; minimize.write_text(minimize_model.encode(minimize_values)); dispatch('xetalminimize:reload')
        print('Minimize targets the hovered window, restores its geometry, and respects disabling', flush=True)

        # A consumed press must not turn into another action when released.
        before = {k: status()[k] for k in ('closed', 'minimized', 'maximized', 'restored', 'floated')}
        reveal(); aim(0); point('down 272'); aim(2); point('up 272'); point('key 125 0'); time.sleep(.15)
        assert before == {k: status()[k] for k in before}
        reveal(); aim(2); point('down 272'); point('key 125 0'); point('up 272'); time.sleep(.15)
        assert before == {k: status()[k] for k in before} and client()
        for button in (272, 273):
            reveal(); point(f'down {button}'); wait(lambda: not status()['visible'])
            point('move 200 280'); assert not status()['visible']; point(f'up {button}')
            wait(lambda: status()['visible']); point('key 125 0'); wait(lambda: not status()['visible'])
        print('Cancelled clicks and move/resize hide-and-return behavior passed', flush=True)

        # Check the same restoration through the XWayland client path.
        display = root / 'display'
        dispatch('exec', 'sh -c ' + shlex.quote('printf "%s" "$DISPLAY" > ' + shlex.quote(str(display))))
        wait(lambda: display.exists() and display.read_text())
        xapp = spawn([sys.executable, str(REPO / 'tests/wobbly/client.py'), '-name', 'wobbly-test'],
                     env=dict(env, DISPLAY=display.read_text(), QT_QPA_PLATFORM='xcb'),
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        command('add', 'X11 buttons', xapp); wait(lambda: client('X11 buttons'))
        assert client('X11 buttons')['xwayland']; click(1, 'X11 buttons'); wait(lambda: client('X11 buttons')['floating']); fits('X11 buttons')
        old = geometry('X11 buttons'); click(1, 'X11 buttons'); wait(lambda: client('X11 buttons')['fullscreen'] == 1)
        click(1, 'X11 buttons'); wait(lambda: geometry('X11 buttons') == old)
        click(2, 'X11 buttons'); wait(lambda: not client('X11 buttons'))
        dispatch('focuswindow', address()); click(2); wait(lambda: not client())
        assert status()['closed'] == 2
        assert ctl('plugin', 'unload', str(binary)) == 'ok'
        assert ctl('plugin', 'load', str(binary)) == 'ok' and status()['enabled']
        assert not ctl('configerrors') and compositor.poll() is None
        print('Wayland/XWayland close, XWayland maximize/restore and safe plugin reload passed', flush=True)
    except Exception:
        try:
            diagnostic={'clients':clients(),'buttons':status()}
            if 'initial' in locals():diagnostic['initial']=initial
            (root/'failure.json').write_text(json.dumps(diagnostic,indent=2))
            run('grim',str(root/'failure.png'))
        except Exception:pass
        raise
    finally:
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        # Exec-launched apps and the size-memory watcher also belong only to
        # this disposable compositor. Never signal any parent-session helper.
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():continue
            try:
                if path.stat().st_uid==os.getuid() and ('XDG_RUNTIME_DIR='+str(runtime)).encode() in (path/'environ').read_bytes().split(b'\0'):
                    os.kill(int(path.name),signal.SIGTERM)
            except OSError:pass
        for log in logs: log.close()


if __name__ == '__main__': main()
