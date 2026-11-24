#!/usr/bin/env python3
"""Exercise real snapping in a disposable Hyprland 0.57 session.

Usage: check-snap-layouts.py PLUGIN DIRECTORY [--first top|left|right|palette]
       [--titlebar] [--hotplug] [--capture]

Every invocation starts a fresh compositor and sends input only to its private
socket. No window rules, settings, plugins or input in the working desktop are
changed. Requires Hyprland, kitty, a C compiler and wayland-scanner.
"""
import argparse
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO/'config/hypr'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plugin', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--first', choices=('top', 'left', 'right', 'palette'), default='top')
    parser.add_argument('--titlebar', action='store_true')
    parser.add_argument('--hotplug', action='store_true')
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--wobbly-plugin', type=Path)
    parser.add_argument('--wobbly-first', action='store_true')
    args = parser.parse_args()
    binary = args.plugin.resolve(strict=True)
    root = args.directory.resolve(); root.mkdir(parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix='snap-', dir='/tmp'))
    (root/'run').symlink_to(runtime, target_is_directory=True)
    (root/'compat').symlink_to(PROFILE/'compat', target_is_directory=True)
    shutil.copy2(PROFILE/'compat/entry.lua', root/'hyprland.lua')
    (root/'hyprland.conf').write_text('''monitor = ,1280x900@60,auto,1
monitor = SNAP,1280x900@60,0x0,1
monitor = WAYLAND-1,640x480@60,4096x0,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
xwayland:enabled = false
animations:enabled = false
input:follow_mouse = 1
bindm = SUPER, mouse:272, movewindow
bindm = SUPER, mouse:273, resizewindow
windowrule = match:class ^fusion-snap-test$, float on
''')
    for directory in ('theme', 'effects/window_close', 'workspaces', 'window_rules'):
        (root/directory).mkdir(parents=True, exist_ok=True)
    for name in ('settings.conf', 'kde-rules.json'):
        shutil.copy2(PROFILE/'effects/window_close'/name, root/'effects/window_close'/name)
    if args.wobbly_plugin:
        wobbly = json.loads((PROFILE/'effects/wobbly/settings.json').read_text())
        wobbly.update(focus_effect=0, map_effect=0)
        (root/'wobbly.json').write_text(json.dumps(wobbly))
        # Keep geometry deterministic while allowing Wobbly's actual grab hook.
        config = root/'hyprland.conf'
        config.write_text(config.read_text().replace('animations:enabled = false', 'animations:enabled = true\nanimation = windows,0,1,default\nanimation = fade,0,1,default\nanimation = workspaces,0,1,default'))
    subprocess.run(['/usr/bin/python3', str(PROFILE/'compat/hypr_compat.py'), 'render', str(root)], check=True, capture_output=True)
    (root/'workspaces/rules.json').write_text(json.dumps({'version': 1, 'default_layout': 'kde', 'workspaces': {}}))
    (root/'theme/current.colors').write_text('[Colors:Window]\nBackgroundNormal=14,27,44\nForegroundNormal=239,246,255\nDecorationFocus=32,210,232\n')
    for name, xml in [('pointer', REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
                      ('keyboard', REPO/'tests/native/virtual-keyboard-unstable-v1.xml')]:
        for mode, extension in [('client-header', 'h'), ('private-code', 'c')]:
            subprocess.run(['wayland-scanner', mode, str(xml), str(root/f'virtual-{name}.{extension}')], check=True)
    flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'wayland-client', 'xkbcommon'], text=True).split()
    subprocess.run(['cc', '-I'+str(root), str(REPO/'tests/native/gesture-input.c'),
                    str(root/'virtual-pointer.c'), str(root/'virtual-keyboard.c'), '-o', str(root/'input'), *flags], check=True)
    parent = Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute(): parent = Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env = {k: v for k, v in os.environ.items() if not k.startswith(('HYPRLAND_', 'XETAL_'))}
    env.update(XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(root/'config'), XDG_CACHE_HOME=str(root/'cache'),
               XDG_STATE_HOME=str(root/'state'), WAYLAND_DISPLAY=str(parent), HYPRLAND_NO_SD_VARS='1',
               HYPRLAND_NO_SD_NOTIFY='1', QT_QPA_PLATFORMTHEME='', QT_QPA_PLATFORM='wayland',
               XETAL_WINDOW_CONTROLS_ROOT=str(root), XETAL_WORKSPACE_RULES=str(root/'workspaces/rules.json'))
    if args.wobbly_plugin: env['XETAL_WOBBLY_CONFIG'] = str(root/'wobbly.json')
    env.pop('DISPLAY', None); env.pop('DBUS_SESSION_BUS_ADDRESS', None)
    children = []
    report = dict(passed=False, first=args.first, titlebar=args.titlebar, hotplug=args.hotplug,
                  wobbly=bool(args.wobbly_plugin), wobbly_first=args.wobbly_first, checks=[])
    with (root/'session.log').open('w') as log:
        def spawn(command, **kwargs):
            kwargs.setdefault('stdout', log); kwargs.setdefault('stderr', log)
            child = subprocess.Popen(command, env=env, **kwargs)
            children.append(child); return child

        def wait(predicate, label):
            until = time.monotonic()+6
            while time.monotonic() < until:
                value = predicate()
                if value: return value
                assert compositor.poll() is None, 'Isolated compositor exited'
                time.sleep(.025)
            raise AssertionError('Timed out: '+label)

        def ctl(*command):
            result = subprocess.run([str(PROFILE/'compat/bin/hyprctl'), *command], env=env,
                                    capture_output=True, text=True, timeout=5)
            assert result.returncode == 0, result.stdout+result.stderr
            return result.stdout.strip()

        def dispatch(*command): assert ctl('dispatch', *command) == 'ok'
        def status(): return json.loads(ctl('xetal-windowclose'))
        def check(label, condition, detail):
            report['checks'].append(dict(name=label, passed=bool(condition), detail=detail))
            assert condition, (label, detail)
            print('PASS '+label, flush=True)

        try:
            compositor = spawn(['Hyprland', '--config', str(root/'hyprland.lua')], start_new_session=True)
            socket = wait(lambda: next(iter(runtime.glob('hypr/*/.socket.sock')), None), 'IPC socket')
            display = wait(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None), 'Wayland socket')
            env.update(HYPRLAND_INSTANCE_SIGNATURE=socket.parent.name, WAYLAND_DISPLAY=str(display))
            assert ctl('output', 'create', 'headless', 'SNAP') == 'ok'
            wait(lambda: any(m['name'] == 'SNAP' for m in json.loads(ctl('-j', 'monitors'))), 'test output')
            # Remove the nested surface before loading the plugin. Its parent
            # geometry must not resize the output or send host pointer events.
            for monitor in json.loads(ctl('-j', 'monitors')):
                if monitor['name'] != 'SNAP': assert ctl('output', 'remove', monitor['name']) == 'ok'
            wait(lambda: len(json.loads(ctl('-j', 'monitors'))) == 1, 'only private output')
            dispatch('focusmonitor', 'SNAP')
            assert not ctl('configerrors'), ctl('configerrors')
            plugins = [binary]
            if args.wobbly_plugin:
                plugins.insert(0 if args.wobbly_first else 1, args.wobbly_plugin.resolve(strict=True))
            for plugin in plugins: assert ctl('plugin', 'load', str(plugin)) == 'ok'
            assert status()['snap_layouts_supported']
            app = spawn(['kitty', '--config', '/dev/null', '--class', 'fusion-snap-test', '--title', 'Snap test', '-e', 'sleep', '180'])

            def client(): return next((c for c in json.loads(ctl('-j', 'clients')) if c['pid'] == app.pid), None)
            wait(client, 'fixture window')
            pointer = spawn([str(root/'input'), '1280', '900'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

            def point(command, delay=.012):
                pointer.stdin.write(command+'\n'); pointer.stdin.flush()
                assert select.select([pointer.stdout], [], [], 4)[0], command
                assert pointer.stdout.readline().strip() == 'ok'
                if delay: time.sleep(delay)

            def settle_test_springs():
                if not args.wobbly_plugin: return
                # Headless render callbacks may not run on NVIDIA. Clear the
                # previous spring before an IPC fixture move or next grab;
                # each real grab still uses Wobbly and its placement hook.
                for enabled in (False, True):
                    wobbly['enabled'] = enabled
                    (root/'wobbly.json').write_text(json.dumps(wobbly))
                    dispatch('xetalwobbly:reload')

            sequence = [args.first, 'top', 'left', 'right', 'palette', 'cancel', 'ctrl', 'quick', 'resize']
            for index, choice in enumerate(sequence):
                settle_test_springs()
                address = 'address:'+client()['address']; dispatch('focuswindow', address)
                if client()['fullscreen']: dispatch('fullscreen', '1')
                if not client()['floating']: dispatch('setfloating', address)
                dispatch('resizewindowpixel', 'exact 600 400,'+address)
                dispatch('movewindowpixel', 'exact 330 230,'+address)
                wait(lambda: client()['size'] == [600, 400], 'fixture geometry')
                before = client()
                start = [before['at'][0]+180, before['at'][1]+80]
                use_bar = args.titlebar and choice not in ('ctrl', 'resize')
                if use_bar:
                    ids = json.loads(ctl('xetal-windowbuttons'))['windows']
                    identity = next(i for i in ids if json.loads(ctl('xetal-windowbuttons', i))['address'] == before['address'])
                    def active_bar():
                        value = json.loads(ctl('xetal-windowbuttons', identity))['titlebar']
                        return value if value['enabled'] else None
                    bar = wait(active_bar, 'title bar')
                    check('title bar available', bar['enabled'], bar)
                    start = [round(bar['box'][0]+180), round(bar['box'][1]+bar['box'][3]/2)]
                point(f'move {start[0]} {start[1]}')
                if not use_bar: point('key 125 1')
                button = 'right' if choice == 'resize' else 'button'
                point(button+' 1'); point(f'move {start[0]+24} {start[1]-20}')
                if choice == 'ctrl': point('key 29 1')
                if args.hotplug and index == 0:
                    assert ctl('output', 'create', 'headless', 'SNAP-HOTPLUG') == 'ok'
                    wait(lambda: len(json.loads(ctl('-j', 'monitors'))) == 2, 'hotplug')
                    assert ctl('output', 'remove', 'SNAP-HOTPLUG') == 'ok'
                    wait(lambda: len(json.loads(ctl('-j', 'monitors'))) == 1, 'remove hotplug')
                target = {'left': (1, 450), 'right': (1278, 450), 'top': (640, 1), 'palette': (640, 1)}.get(choice, (1, 450))
                point(f'move {target[0]} {target[1]}', .02 if choice == 'quick' else .23)
                if choice == 'palette': point('move 475 45', .23)  # left half in the chooser
                if choice == 'cancel': point('key 1 1'); point('key 1 0')
                during = status()
                if args.wobbly_plugin:
                    during['wobbly'] = json.loads(ctl('xetal-wobbly'))
                    if index == 0: check('Wobbly received first grab', during['wobbly']['grabs'] > 0, during['wobbly'])
                if args.capture and index == 0:
                    try:
                        capture = subprocess.run(['grim', '-o', 'SNAP', str(root/'preview.png')], env=env, capture_output=True, timeout=3)
                        report['capture'] = 'saved' if capture.returncode == 0 else capture.stderr.decode(errors='replace')
                    except subprocess.TimeoutExpired:
                        report['capture'] = 'Nested output capture timed out; gesture/geometry assertions still run.'
                point(button+' 0', .10)
                if not use_bar: point('key 125 0')
                if choice == 'ctrl': point('key 29 0')
                wait(lambda: not status()['snap_gesture']['active'], 'gesture completion')
                after = client(); detail = dict(before=before, during=during, after=after)
                g = during['snap_gesture']
                if choice in ('top', 'left', 'right', 'palette'):
                    expected = {'top': 10, 'left': 1, 'right': 2, 'palette': 1}[choice]
                    check(f'{index}: {choice} preview', g['active'] and g['threshold'] and g['zone'] == expected and g['preview'][2] > 0, detail)
                    if choice in ('top', 'palette'): check(f'{index}: chooser visible', g['panel'][2] > 0, g)
                    if choice == 'top':
                        check(f'{index}: real maximize', after['fullscreen'] == 1, detail)
                        dispatch('fullscreen', '1')
                        restored = wait(lambda: client() if client()['fullscreen'] == 0 else None, 'restore')
                        check(f'{index}: maximize restore', restored['size'] == before['size'] and restored['at'] == before['at'], restored)
                    else:
                        check(f'{index}: snap geometry', after['fullscreen'] == 0 and abs(after['size'][0]-638) <= 2 and abs(after['at'][0]-(641 if choice == 'right' else 1)) <= 2, detail)
                        if choice == 'left':
                            settle_test_springs()
                            point(f'move {after["at"][0]+180} {after["at"][1]+80}')
                            point('key 125 1'); point('button 1')
                            point('move 800 500', .23); point('button 0', .10); point('key 125 0')
                            wait(lambda: not status()['snap_gesture']['active'], 'drag away')
                            check(f'{index}: drag away restores size', client()['size'] == before['size'], client())
                else:
                    check(f'{index}: {choice} does not snap', after['fullscreen'] == 0 and (choice == 'resize' or after['size'] == before['size']), detail)
            report['passed'] = True
        finally:
            (root/'result.json').write_text(json.dumps(report, indent=2)+'\n')
            for child in reversed(children):
                if child.poll() is None: child.terminate()
            for child in children:
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired: child.kill(); child.wait()


if __name__ == '__main__': main()
