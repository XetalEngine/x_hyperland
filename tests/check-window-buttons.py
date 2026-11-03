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
    # Small theme/config sources only; never adopt the real user's preferences.
    for directory in ('theme','runtime','cursors'):
        destination=home/'.config/hypr'/directory;destination.mkdir(exist_ok=True)
        for source in (REPO/'config/hypr'/directory).iterdir():
            if source.is_file() and source.suffix in ('.py','.json','.colors'):shutil.copy2(source,destination/source.name)
    theme_assets=REPO/'config/hypr/theme/assets'
    if theme_assets.exists():shutil.copytree(theme_assets,home/'.config/hypr/theme/assets')
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
    runtime = Path(tempfile.mkdtemp(prefix='xbuttons-', dir='/tmp'))
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
        assert ctl('plugin', 'load', str(binary)) == 'ok'
        app = spawn([sys.executable, str(REPO / 'tests/wobbly/client.py'), '-name', 'wobbly-test'],
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
                   '--disable-background-networking', '--disable-sync', '--password-store=basic',
                   '--user-data-dir='+str(root/'browser'), fixture.as_uri()], env=chrome_env)
            def chrome(): return next((c for c in clients() if c['class'].startswith(('google-chrome', 'chromium', 'chrome-'))), None)
            c = wait(chrome); addr = 'address:'+c['address']
            dispatch('setfloating', addr); dispatch('resizewindowpixel', 'exact 850 600,'+addr)
            dispatch('movewindowpixel', 'exact 120 100,'+addr); dispatch('focuswindow', addr); time.sleep(.6)
            run('grim', str(root/'chrome-before.png'))
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

        if '--native-only' in sys.argv:
            check_chrome(); return

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
            time.sleep(.3);run('grim',str(root/'gear-settings.png'))
            dispatch('closewindow','address:'+editor['address']);wait(lambda:not any(c['class']=='fusion-window-buttons' for c in clients()))
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

        assert not client()['floating']
        reveal(); assert [b['action'] for b in status()['buttons']] == ['minimize', 'restore', 'close']
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
    finally:
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        for log in logs: log.close()


if __name__ == '__main__': main()
