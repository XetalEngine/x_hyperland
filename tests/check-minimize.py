#!/usr/bin/env python3
"""Real Wayland/X11 requests, pointer input and recovery in a disposable compositor.

Usage: check-minimize.py /absolute/path/xetal-minimize.so /tmp/new-test-directory
Add --upgrade-from /absolute/path/previous.so to exercise an in-session upgrade.
Requires a parent Wayland session, PyQt6, grim, wayland-scanner and a C compiler.
It never loads the plugin into the parent compositor or launches a real VM.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from effects.minimize import model

# Keep the established edge-stack checks; the dock gets its own live scenarios.
DEFAULTS = dict(model.DEFAULTS, presentation="stack")
from effects.cube import model as cube_model, build as cube_build
from effects.burn import model as burn_model, build as burn_build


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    upgrade_from = (Path(sys.argv[sys.argv.index('--upgrade-from')+1]).resolve(strict=True)
                    if '--upgrade-from' in sys.argv[3:] else None)
    root = Path(sys.argv[2]); root.mkdir(parents=True, exist_ok=False)
    config = root/'minimize.conf'; config.write_text(model.encode(DEFAULTS))
    palette = root/'current.colors'; palette.write_text('[Colors:Window]\nDecorationFocus=57,169,255\n')
    cube = root/'cube.json'; cube.write_text(cube_model.encode(dict(cube_model.DEFAULTS, enabled=True)))
    burn = root/'burn.conf'; burn.write_text(burn_model.encode(dict(burn_model.DEFAULTS, enabled=True)))
    protocol = REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'
    subprocess.run(['wayland-scanner', 'client-header', str(protocol), str(root/'virtual-pointer.h')], check=True)
    subprocess.run(['wayland-scanner', 'private-code', str(protocol), str(root/'virtual-pointer.c')], check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'wayland-client'], text=True))
    pointer = root/'pointer'
    subprocess.run(['cc', '-I'+str(root), str(REPO/'tests/minimize/pointer.c'), str(root/'virtual-pointer.c'), '-o', str(pointer), *flags], check=True)
    conf = root/'hyprland.conf'
    conf.write_text('''monitor = ,1280x800@60,auto,1
misc {
 disable_hyprland_logo = true
 disable_splash_rendering = true
 focus_on_activate = true
}
input {
 follow_mouse = 1
}
debug {
 disable_logs = false
}
''')
    runtime = Path(tempfile.mkdtemp(prefix='xm-', dir='/tmp'))
    parent = os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'):
        parent = str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=parent,
               GSETTINGS_BACKEND='memory', XETAL_MINIMIZE_CONFIG=str(config), XETAL_MINIMIZE_COLORS=str(palette),
               XETAL_CUBE_CONFIG=str(cube), XETAL_BURN_CONFIG=str(burn))
    env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
    children = []
    logs = []

    def spawn(args, **kwargs):
        process = subprocess.Popen(args, **kwargs); children.append(process); return process

    def run(*args):
        result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError(str(args)+': '+result.stdout+result.stderr)
        return result.stdout.strip()

    def ctl(*args): return run('hyprctl', *args)
    def dispatch(*args):
        answer = ctl('dispatch', *args); assert answer == 'ok', (args, answer)
    def status(): return json.loads(ctl('xetal-minimize'))
    def clients(): return json.loads(ctl('-j', 'clients'))
    def client(name): return next(c for c in clients() if c['title'] == name)
    def wait(predicate):
        for _ in range(120):
            if predicate(): return
            time.sleep(.04)
        raise AssertionError('Timed out waiting for transition')
    def begin_app(platform):
        logs.append((root/(platform+'.log')).open('w'))
        child_env = dict(env, QT_QPA_PLATFORM=platform)
        if platform == 'xcb':
            # Ask a child of the nested compositor for its own X server.
            display_file = root/'display'
            dispatch('exec', 'sh -c '+shlex.quote('printf "%s" "$DISPLAY" > '+shlex.quote(str(display_file))))
            wait(lambda: display_file.exists() and bool(display_file.read_text()))
            child_env['DISPLAY'] = display_file.read_text()
        app = spawn([sys.executable, str(REPO/'tests/minimize/client.py')], env=child_env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logs[-1], text=True)
        def command(op, name):
            app.stdin.write(json.dumps(dict(op=op, name=name))+'\n'); app.stdin.flush()
            assert app.stdout.readline().strip() == 'ok', (op, name)
        return command
    def click_or_scroll(item, kind='click'):
        b = item['box']; monitors = json.loads(ctl('-j', 'monitors')); m = monitors[0]
        run(str(pointer), str(int(b[0]+b[2]/2)), str(int(b[1]+b[3]/2)),
            str(m['width']), str(m['height']), kind)
    def restored(name, ws):
        c = client(name); return c['workspace']['id'] == ws and not c['hidden'] and c['mapped']

    try:
        logs.append((root/'compositor.log').open('w'))
        compositor = spawn(['Hyprland', '-c', str(conf)], env=env, stdout=logs[-1], stderr=logs[-1], start_new_session=True)
        for _ in range(100):
            assert compositor.poll() is None, 'Nested compositor exited'
            try:
                instance = next((i for i in json.loads(run('hyprctl', '-j', 'instances')) if i['pid'] == compositor.pid), None)
            except ValueError:
                instance = None
            if instance and (runtime/'hypr'/instance['instance']/'.socket.sock').exists():
                env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'], WAYLAND_DISPLAY=instance['wl_socket']); break
            time.sleep(.1)
        else:
            raise RuntimeError('No disposable compositor')
        time.sleep(.6)
        # Use the Wayland backend: a headless output needs a GBM allocator that
        # is not available on every host. Let the parent's initial resize settle.
        time.sleep(1)
        output = json.loads(ctl('-j', 'monitors'))[0]
        output_name = output['name']
        dispatch('focusmonitor', output_name); dispatch('workspace', '1')
        for path in (cube_build.build(), burn_build.build(), upgrade_from or binary):
            assert ctl('plugin', 'load', str(path)) == 'ok', path
        print('Cube, Burn and Minimize loaded together', flush=True)
        wayland = begin_app('wayland')
        if upgrade_from:
            wayland('add', 'Upgrade recovery'); wait(lambda: any(c['title'] == 'Upgrade recovery' for c in clients()))
            before = client('Upgrade recovery')
            wayland('min', 'Upgrade recovery'); wait(lambda: status()['active'] == 1)
            assert ctl('plugin', 'unload', str(upgrade_from)) == 'ok'
            wait(lambda: restored('Upgrade recovery', before['workspace']['id']))
            answer = ctl('plugin', 'load', str(binary)); assert answer == 'ok', answer
            # GNU-unique inline data can survive dlclose. Merely checking the
            # new plugin's version missed an old dock-design table being reused.
            config.write_text(model.encode(dict(model.DEFAULTS, dock_style='gildedhollow')))
            dispatch('xetalminimize:reload'); assert status()['dock_style'] == 10
            palette.write_text('[General]\nColorScheme=XetalGildedHollowDark\n[Colors:Window]\nDecorationFocus=235,187,94\n')
            config.write_text(model.encode(model.DEFAULTS))
            dispatch('xetalminimize:reload'); assert status()['dock_style'] == 10
            config.write_text(model.encode(DEFAULTS))
            palette.write_text('[Colors:Window]\nDecorationFocus=57,169,255\n')
            dispatch('xetalminimize:reload')
            wayland('close', 'Upgrade recovery'); wait(lambda: not clients())
            print('Live upgrade restores windows and accepts the new dock design: passed', flush=True)
        if '--dock-only' in sys.argv[3:]:
            from minimize.dock_checks import check as check_dock
            check_dock(root,env,ctl,dispatch,status,clients,client,wait,wayland,run,spawn,
                       pointer,output,model,config,palette)
            assert ctl('plugin','unload',str(binary))=='ok'
            print('PASS',flush=True)
            return
        wayland('add', 'Wayland'); wait(lambda: any(c['title'] == 'Wayland' for c in clients()))
        dispatch('setfloating', 'address:'+client('Wayland')['address'])
        dispatch('resizewindowpixel', 'exact 680 420,address:'+client('Wayland')['address'])
        dispatch('movewindowpixel', 'exact 220 160,address:'+client('Wayland')['address'])
        time.sleep(.6); before = client('Wayland'); ws = before['workspace']['id']
        wayland('min', 'Wayland'); wait(lambda: status()['active'] == 1)
        time.sleep(.15); run('grim', '-o', output_name, str(root/'flying.png'))
        time.sleep(.6); run('grim', '-o', output_name, str(root/'fireball.png'))
        # Change effects on an already minimized window, including palette-only
        # reloads. No restore/re-minimize is allowed during these changes.
        from PIL import Image, ImageDraw
        # Unknown applications retain the window preview. A real cached icon
        # is picked up without restoring/re-minimizing the window.
        from effects.minimize.icons import key as icon_key
        assert status()['windows'][0]['icon'] is False
        icon_dir = runtime/'hypr'/env['HYPRLAND_INSTANCE_SIGNATURE']/'xetal-minimize-icons'
        icon_dir.mkdir(mode=0o700)
        icon_path = icon_dir/icon_key(before['class'])
        Image.new('RGBA', (128,128), (20,235,95,255)).save(icon_path)
        wait(lambda: status()['windows'][0]['icon'] is True)
        time.sleep(.2)
        run('grim', '-o', output_name, str(root/'fireball-app-icon.png'))
        b = status()['windows'][0]['box']; x,y,w,h = map(int,b)
        pixels = Image.open(root/'fireball-app-icon.png').crop((x,y,x+w,y+h)).convert('RGB')
        assert sum(g>180 and r<60 and blue<150 for r,g,blue in pixels.getdata()) > 100, 'App icon was not rendered'
        icon_path.unlink()
        wait(lambda: status()['windows'][0]['icon'] is False)
        shots = []
        def shot(label):
            path = root/(label+'.png'); run('grim', '-o', output_name, str(path))
            b = status()['windows'][0]['box']; x,y,w,h = map(int,b)
            picture = Image.open(path).crop((max(0,x-8),max(0,y-8),x+w+8,y+h+8)).convert('RGB')
            shots.append((label,picture))
        for effect in ('fireball',):
            config.write_text(model.encode(dict(DEFAULTS, effect=effect, size=160)))
            dispatch('xetalminimize:reload'); time.sleep(.4)
            assert status()['active']==1 and status()['effect']==effect
            for i,rgb in enumerate(((57,169,255),(225,72,33),(101,224,118))):
                palette.write_text('[Colors:Window]\nDecorationFocus='+','.join(map(str,rgb))+'\n')
                dispatch('xetalminimize:reload'); time.sleep(.4)
                assert all(abs(a-b/255)<.001 for a,b in zip(status()['color'],rgb))
                shot(effect+'-'+str(i))
        config.write_text(model.encode(dict(DEFAULTS,follow_theme=False,color='#c939ce')))
        dispatch('xetalminimize:reload')
        assert all(abs(a-b/255)<.001 for a,b in zip(status()['color'],(201,57,206)))
        run('grim','-o',output_name,str(root/'fireball-a.png'));time.sleep(.3)
        run('grim','-o',output_name,str(root/'fireball-b.png'))
        assert (root/'fireball-a.png').read_bytes()!=(root/'fireball-b.png').read_bytes()
        # Malformed live preferences must not strand or recolor a window.
        config.write_text(model.encode(DEFAULTS)+'shape=invalid\n')
        assert 'Duplicate' in ctl('dispatch','xetalminimize:reload')
        assert status()['effect']=='fireball' and status()['active']==1
        config.write_text(model.encode(DEFAULTS));dispatch('xetalminimize:reload')
        print('Live Fireball, palette-follow, custom color and rejected reload: passed',flush=True)
        click_or_scroll(status()['windows'][0]); wait(lambda: status()['active'] == 0)
        wait(lambda: restored('Wayland', ws))
        after = client('Wayland'); assert after['at'] == before['at'] and after['size'] == before['size'], (before, after)
        print('Wayland minimize button, pointer restore, geometry: passed', flush=True)
        # Minimize a particular Qt window while a separate viewer has focus.
        # This is the same native request used by KVM Settings after launch.
        wayland('add', 'Viewer'); wait(lambda: any(c['title'] == 'Viewer' for c in clients()))
        dispatch('setfloating', 'address:'+client('Viewer')['address'])
        dispatch('resizewindowpixel', 'exact 420 260,address:'+client('Viewer')['address'])
        dispatch('centerwindow')
        dispatch('focuswindow', 'address:'+client('Viewer')['address'])
        wayland('min', 'Wayland'); wait(lambda: status()['active'] == 1)
        assert restored('Viewer', ws)
        assert client('Wayland')['workspace']['name'].startswith('special:xetal-minimized-ws-')
        # An ordinary underlying window must still receive pointer input when
        # effects are hidden, and rendering must stop for the effect.
        wayland('add', 'Underlay'); wait(lambda: any(c['title'] == 'Underlay' for c in clients()))
        dispatch('fullscreen', '1')
        for effect in ('fireball',):
            config.write_text(model.encode(dict(DEFAULTS, effect=effect)))
            dispatch('xetalminimize:reload'); time.sleep(.6)
            item = status()['windows'][0]
            dispatch('focuswindow', 'address:'+client('Viewer')['address'])
            dispatch('xetalminimize:togglevisibility'); time.sleep(.15)
            hidden = status(); assert hidden['hidden'] and not hidden['windows'][0]['visible']
            run('grim', '-o', output_name, str(root/(effect+'-hidden.png')))
            time.sleep(.2); assert status()['draws'] == hidden['draws']
            click_or_scroll(item)
            click_or_scroll(item, '1')
            assert status()['active'] == 1  # Hidden effects cannot steal input.
            assert json.loads(ctl('-j','activewindow'))['title'] == 'Underlay'
            dispatch('xetalminimize:togglevisibility')
            wait(lambda: status()['draws'] > hidden['draws'])
            assert status()['windows'][0]['visible']
        dispatch('xetalminimize:togglevisibility')
        wayland('min', 'Viewer'); wait(lambda: status()['active'] == 2)
        assert all(not item['visible'] for item in status()['windows'])
        dispatch('focuswindow', 'address:'+client('Viewer')['address'])
        wait(lambda: status()['active'] == 1)
        assert restored('Viewer', ws) and status()['hidden']
        dispatch('xetalminimize:restoreall'); wait(lambda: status()['active'] == 0)
        assert restored('Wayland', ws)
        dispatch('xetalminimize:togglevisibility')
        wayland('close', 'Viewer'); wayland('close', 'Underlay')
        config.write_text(model.encode(DEFAULTS)); dispatch('xetalminimize:reload')
        print('Targeted Qt minimize; Fireball hide, render pause, pointer pass-through and hidden restore: passed', flush=True)
        wayland('min', 'Wayland'); wait(lambda: status()['active'] == 1)
        config.write_text(model.encode(dict(DEFAULTS, enabled=False)))
        dispatch('xetalminimize:reload'); wait(lambda: status()['active'] == 0)
        assert restored('Wayland', ws)
        config.write_text(model.encode(DEFAULTS)); dispatch('xetalminimize:reload')
        wayland('min', 'Wayland'); wait(lambda: status()['active'] == 1)
        wayland('close', 'Wayland'); wait(lambda: status()['active'] == 0)
        print('Repeated minimize, disable recovery, closing minimized app: passed', flush=True)

        homes={}
        for name,workspace in (('Home3A',3),('Home3B',3),('Home4',4)):
            dispatch('workspace',str(workspace));wayland('add',name)
            wait(lambda:any(c['title']==name for c in clients()));time.sleep(.1)
            homes[name]=client(name)['workspace']['id'];wayland('min',name)
            wait(lambda:client(name)['workspace']['name'].startswith('special:xetal-minimized-ws-'))
            assert client(name)['workspace']['name']=='special:xetal-minimized-ws-'+str(homes[name])
        assert client('Home3A')['workspace']['id']==client('Home3B')['workspace']['id']
        assert client('Home3A')['workspace']['id']!=client('Home4')['workspace']['id']
        # App-icon focus restores only that app, not all the windows in its group.
        dispatch('focuswindow','address:'+client('Home3A')['address'])
        wait(lambda:status()['active']==2);assert restored('Home3A',homes['Home3A'])
        dispatch('xetalminimize:restoreall');wait(lambda:status()['active']==0)
        for name,workspace in homes.items():
            assert restored(name,workspace);wayland('close',name)
        dispatch('workspace','1')
        print('Minimized groups keep original workspace IDs; app-icon focus restores only its app: passed',flush=True)

        wayland('add', 'Activate'); wait(lambda: any(c['title'] == 'Activate' for c in clients()))
        ws = client('Activate')['workspace']['id']
        wayland('min', 'Activate'); wait(lambda: status()['active'] == 1)
        dispatch('focuswindow', 'address:'+client('Activate')['address'])
        wait(lambda: status()['active'] == 0)
        assert restored('Activate', ws)
        wayland('close', 'Activate')
        print('External window activation restores the original workspace: passed', flush=True)

        x11 = begin_app('xcb'); x11('add', 'X11'); wait(lambda: any(c['title'] == 'X11' for c in clients()))
        assert client('X11')['xwayland']
        ws = client('X11')['workspace']['id']; x11('min', 'X11'); wait(lambda: status()['active'] == 1)
        click_or_scroll(status()['windows'][0]); wait(lambda: status()['active'] == 0)
        assert restored('X11', ws); x11('close', 'X11')
        print('XWayland minimize and restore: passed', flush=True)

        count = int(output['height'] / output['scale'] / (DEFAULTS['size']+12)) + 3
        for i in range(count):
            name = f'Window {i}'; wayland('add', name); wait(lambda: any(c['title'] == name for c in clients()))
            time.sleep(.08); wayland('min', name); wait(lambda: status()['active'] == i+1)
        time.sleep(.6); items = status()['windows']; assert not items[0]['visible'] and items[-1]['visible']
        for _ in range(count):
            item = next(w for w in status()['windows'] if w['visible']); click_or_scroll(item, '-1')
        assert status()['windows'][0]['visible']
        run('grim', '-o', output_name, str(root/'column.png'))
        # Changing placement moves existing effects and their input hitboxes.
        for edge in model.EDGES:
            for order in model.ORDERS:
                config.write_text(model.encode(dict(DEFAULTS,edge=edge,order=order)))
                dispatch('xetalminimize:reload');time.sleep(.2)
                state=status();assert (state['edge'],state['order'])==(edge,order)
                boxes=[item['box'] for item in state['windows'] if item['visible']]
                assert len(boxes)>1
                assert (boxes[0][0]<output['width']/output['scale']/2)==(edge=='left')
                assert (boxes[0][1]>boxes[1][1])==(order=='bottom-to-top')
                assert all(b[1]>=0 and b[1]+b[3]<=output['height']/output['scale'] for b in boxes)
        click_or_scroll(next(w for w in status()['windows'] if w['visible']))
        wait(lambda:status()['active']==count-1)
        config.write_text(model.encode(DEFAULTS));dispatch('xetalminimize:reload')
        print('Left/right, upward/downward placement, overflow and moved hitboxes: passed',flush=True)
        dispatch('xetalminimize:restoreall'); assert status()['active'] == 0
        for i in range(count):
            assert not client(f'Window {i}')['hidden']; wayland('close', f'Window {i}')
        print('Single-column overflow and restore-all: passed', flush=True)

        wayland('add', 'Group A'); wait(lambda: any(c['title'] == 'Group A' for c in clients()))
        dispatch('focuswindow', 'address:'+client('Group A')['address']); dispatch('togglegroup')
        wayland('add', 'Group B'); wait(lambda: any(c['title'] == 'Group B' for c in clients()))
        assert len(client('Group B')['grouped']) == 2, clients()
        ws = client('Group B')['workspace']['id']
        wayland('min', 'Group B'); wait(lambda: status()['active'] == 1)
        assert client('Group A')['workspace']['id'] == client('Group B')['workspace']['id'] != ws
        click_or_scroll(status()['windows'][0]); wait(lambda: status()['active'] == 0)
        # Hyprland fades inactive tabs and blocks their input; it does not set
        # the generic "hidden" property for inactive group members.
        assert restored('Group B', ws) and client('Group B')['acceptsInput'] and not client('Group A')['acceptsInput'], clients()
        assert len(client('Group B')['grouped']) == 2
        wayland('close', 'Group A'); wayland('close', 'Group B')
        wait(lambda: not clients())
        print('Grouped windows minimize and return together: passed', flush=True)

        from minimize.dock_checks import check as check_dock
        check_dock(root, env, ctl, dispatch, status, clients, client, wait, wayland, run, spawn,
                   pointer, output, model, config, palette)
        config.write_text(model.encode(DEFAULTS));dispatch('xetalminimize:reload')

        wayland('add', 'Viewer'); wayland('add', 'KVM settings'); wait(lambda: len(clients()) == 2)
        for name in ('Viewer', 'KVM settings'):
            dispatch('setfloating', 'address:'+client(name)['address'])
        time.sleep(.6)
        viewer_normal = client('Viewer')
        dispatch('focuswindow', 'address:'+client('Viewer')['address']); dispatch('fullscreenstate', '1 1')
        wait(lambda: client('Viewer')['fullscreen'] == 1)
        dispatch('focuswindow', 'address:'+client('KVM settings')['address'])
        assert client('KVM settings')['allowedOverFullscreen']
        dispatch('focuswindow', 'address:'+client('Viewer')['address']); dispatch('alterzorder', 'top,active')
        assert not client('KVM settings')['allowedOverFullscreen']
        ws = client('Viewer')['workspace']['id']
        for _ in range(3):
            dispatch('workspace', '2'); dispatch('workspace', str(ws)); time.sleep(.15)
            assert not client('KVM settings')['allowedOverFullscreen']
        dispatch('focuswindow', 'address:'+client('Viewer')['address']); dispatch('alterzorder', 'bottom,active')
        assert client('KVM settings')['allowedOverFullscreen']
        assert json.loads(ctl('-j', 'activewindow'))['title'] == 'KVM settings'
        dispatch('workspace', '2'); dispatch('workspace', str(ws))
        assert client('KVM settings')['allowedOverFullscreen']
        dispatch('focuswindow', 'address:'+client('KVM settings')['address']); dispatch('alterzorder', 'bottom,active')
        assert not client('KVM settings')['allowedOverFullscreen']
        assert json.loads(ctl('-j', 'activewindow'))['title'] == 'Viewer'
        wayland('min', 'Viewer'); wait(lambda: status()['active'] == 1)
        click_or_scroll(status()['windows'][0]); wait(lambda: status()['active'] == 0)
        assert client('Viewer')['fullscreen'] == 1
        dispatch('fullscreenstate', '0 0')
        time.sleep(.6)
        assert client('Viewer')['size'] == viewer_normal['size'], (viewer_normal, client('Viewer'))
        print('Maximized viewer ordering, workspace round-trips, fullscreen restore: passed', flush=True)
        dispatch('fullscreenstate', '2 2')
        wayland('min', 'Viewer'); wait(lambda: status()['active'] == 1)
        dispatch('xetalminimize:restoreall'); assert client('Viewer')['fullscreen'] == 2
        dispatch('focuswindow', 'address:'+client('Viewer')['address']); dispatch('fullscreenstate', '0 0')
        ctl('keyword', 'animations:enabled', 'false')
        wayland('min', 'Viewer'); wait(lambda: status()['active'] == 1)
        click_or_scroll(status()['windows'][0]); wait(lambda: status()['active'] == 0)
        ctl('keyword', 'animations:enabled', 'true')
        print('Fullscreen and reduced-motion recovery: passed', flush=True)

        dispatch('focuswindow', 'address:'+client('KVM settings')['address']); dispatch('pin')
        wayland('min', 'KVM settings'); wait(lambda: status()['active'] == 1)
        assert ctl('plugin', 'unload', str(binary)) == 'ok'
        assert client('KVM settings')['pinned'] and not client('KVM settings')['hidden']
        assert not any(c['workspace']['name'].startswith('special:xetal-minimized-') for c in clients())
        assert compositor.poll() is None
        print('Pinned window and plugin-unload recovery: passed', flush=True)
        print('PASS', flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
        for log in logs: log.close()


if __name__ == '__main__':
    main()
