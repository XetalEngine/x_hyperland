#!/usr/bin/env python3
"""Click real Waybar tray icons on three private Hyprland outputs.

Uses a private D-Bus session, HOME and compositor; never moves host windows or
the host pointer. Run from a desktop with a destination report directory.
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
import traceback

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO/'config/hypr'


def main():
    report_dir = Path(sys.argv[1]).resolve(); report_dir.mkdir(parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix='ft-', dir='/tmp'))
    home = report_dir/'home'; profile = home/'.config/hypr'; profile.mkdir(parents=True)
    for name in ('launcher', 'compat', 'window_rules', 'scripts', 'waybar'):
        shutil.copytree(SOURCE/name, profile/name,
                        ignore=shutil.ignore_patterns('.build', '__pycache__', 'third_party'))
    shutil.copytree(SOURCE/'effects/window_close', profile/'effects/window_close',
                    ignore=shutil.ignore_patterns('.build', '__pycache__'))
    parent = Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute(): parent = Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env = {k: v for k, v in os.environ.items() if k not in (
        'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'HYPRLAND_INSTANCE_SIGNATURE',
        'HL_INITIAL_WORKSPACE_TOKEN', 'HL_EXEC_RULE_TOKEN', 'XDG_ACTIVATION_TOKEN',
        'DESKTOP_STARTUP_ID') and not k.startswith('XETAL_')}
    env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(home/'.config'),
               XDG_CACHE_HOME=str(home/'.cache'), XDG_STATE_HOME=str(home/'.local/state'),
               AQ_BACKENDS='wayland', WAYLAND_DISPLAY=str(parent), HYPRLAND_NO_SD_VARS='1',
               HYPRLAND_NO_SD_NOTIFY='1', QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='',
               GDK_BACKEND='wayland', QT_STYLE_OVERRIDE='Fusion', GSETTINGS_BACKEND='memory',
               NO_AT_BRIDGE='1', PATH=str(profile/'compat/bin')+':/usr/bin:/bin')
    env['XETAL_HYPRLAND_LUA'] = '1'
    config = report_dir/'hyprland.lua'
    config.write_text('''hl.monitor({output="",mode="900x600@60",position="auto",scale=1})
hl.monitor({output="WAYLAND-1",mode="640x400@60",position="2700x0",scale=1})
hl.monitor({output="LEFT",mode="900x600@60",position="0x0",scale=1})
hl.monitor({output="CENTER",mode="900x600@60",position="900x0",scale=1})
hl.monitor({output="RIGHT",mode="900x600@60",position="1800x0",scale=1})
hl.config({animations={enabled=false},xwayland={enabled=false},input={follow_mouse=0},misc={
    disable_hyprland_logo=true,disable_splash_rendering=true,disable_hyprland_guiutils_check=true}})
''')
    children = []; report = {'passed': False, 'checks': []}

    def spawn(args, name):
        with (report_dir/(name+'.log')).open('w') as log:
            child = subprocess.Popen(list(map(str, args)), env=env, stdout=log, stderr=log)
        children.append(child); return child

    def ctl(*args):
        return subprocess.check_output([str(profile/'compat/bin/hyprctl'), *args],
                                       env=env, text=True, timeout=5).strip()

    def wait(predicate, seconds=15):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value: return value
            time.sleep(.05)
        raise RuntimeError('Timed out waiting for private tray test state')

    def clients(): return json.loads(ctl('-j', 'clients'))
    def window(name='Tray owner'): return next((c for c in clients() if c['title'] == name and c['mapped']), None)
    def state(): return json.loads((report_dir/'app-state.json').read_text())
    def monitors(): return {m['name']: m for m in json.loads(ctl('-j', 'monitors'))}
    def active(): return json.loads(ctl('-j', 'activewindow'))
    def command(action, name):
        identity = time.time_ns()
        temporary = report_dir/'app-command.new'
        temporary.write_text(json.dumps(dict(id=identity, action=action, name=name)))
        temporary.replace(report_dir/'app-command.json')
        wait(lambda: state().get('last_command') == identity)

    def click(monitor, button='click'):
        outputs = monitors(); output = outputs[monitor]
        left = min(m['x'] for m in outputs.values()); top = min(m['y'] for m in outputs.values())
        right = max(m['x']+m['width']/m['scale'] for m in outputs.values())
        bottom = max(m['y']+m['height']/m['scale'] for m in outputs.values())
        subprocess.run([str(pointer), str(output['x']+18-left), str(output['y']+18-top),
                        str(int(right-left)), str(int(bottom-top)), button],
                       env=env, check=True, timeout=5)

    def record(name):
        report['checks'].append(name); print('PASS: '+name, flush=True)

    try:
        bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        children.append(bus); env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
        spawn(['/usr/bin/Hyprland', '-c', config], 'compositor')
        ipc = wait(lambda: next(iter(runtime.glob('hypr/*/.socket.sock')), None))
        env['HYPRLAND_INSTANCE_SIGNATURE'] = ipc.parent.name
        env['WAYLAND_DISPLAY'] = str(wait(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None)))
        for name in ('LEFT', 'CENTER', 'RIGHT'): ctl('output', 'create', 'headless', name)
        widget_test = report_dir/'tray-widget'
        gtk_flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs',
            'gtk+-3.0', 'gtk-layer-shell-0', 'json-glib-1.0'], text=True))
        subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        REPO/'tests/tray-widget.c', '-o', widget_test, *gtk_flags], check=True)
        subprocess.run([widget_test], env={**env, 'G_DEBUG': 'fatal-criticals'}, check=True, timeout=10)
        record('GTK native fallback, duplicate clicks, timeout and bar teardown')
        # One visible and one alternate workspace per output.
        for name, workspace in (('LEFT', 11), ('CENTER', 21), ('RIGHT', 31)):
            ctl('dispatch', 'focusmonitor', name); ctl('dispatch', 'workspace', str(workspace))
        pointer = report_dir/'pointer'
        protocol = REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'
        subprocess.run(['wayland-scanner', 'client-header', protocol, report_dir/'virtual-pointer.h'], check=True)
        subprocess.run(['wayland-scanner', 'private-code', protocol, report_dir/'virtual-pointer.c'], check=True)
        pointer_source = (REPO/'tests/minimize/pointer.c').read_text()
        pointer_source = pointer_source.replace('!strcmp(argv[5],"click") ||', '!strcmp(argv[5],"right") || !strcmp(argv[5],"click") ||')
        pointer_source = pointer_source.replace('272,1', '(!strcmp(argv[5],"right")?273:272),1').replace('272,0', '(!strcmp(argv[5],"right")?273:272),0')
        (report_dir/'pointer.c').write_text(pointer_source)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'wayland-client'], text=True))
        subprocess.run(['cc', '-I'+str(report_dir), report_dir/'pointer.c', report_dir/'virtual-pointer.c', '-o', pointer, *flags], check=True)
        bar_config = report_dir/'waybar.json'
        bar_config.write_text(json.dumps({'output': ['LEFT', 'CENTER', 'RIGHT'], 'height': 36,
            'modules-left': ['tray', 'cffi/bar-options'], 'tray': {'icon-size': 24, 'spacing': 4},
            'cffi/bar-options': {'module_path': str(profile/'waybar/options/options.so')}}))
        css = report_dir/'waybar.css'; css.write_text('window#waybar {background:#17202a;} #tray {padding:6px;}')
        bar = spawn(['waybar', '-c', bar_config, '-s', css], 'waybar')
        wait(lambda: 'Tray' in (report_dir/'waybar.log').read_text() or '.so' in (report_dir/'waybar.log').read_text(), 5)
        ctl('dispatch', 'focusmonitor', 'LEFT'); ctl('dispatch', 'workspace', '11')
        app = spawn([sys.executable, REPO/'tests/tray-fixture.py', report_dir], 'app')
        original = wait(window); wait(lambda: 'Tray::onAdd' in (report_dir/'waybar.log').read_text())
        report['original'] = original; report['monitors'] = monitors()
        time.sleep(.6)
        for name in ('LEFT', 'CENTER', 'RIGHT'):
            ctl('dispatch', 'focusmonitor', 'LEFT'); ctl('dispatch', 'workspace', '12')
            ctl('dispatch', 'focusmonitor', name)
            before = {n: m['activeWorkspace']['id'] for n, m in monitors().items()}
            click(name)
            wait(lambda: active().get('address') == original['address'] and
                 monitors()['LEFT']['activeWorkspace']['id'] == 11)
            after = window()
            assert after['monitor'] == original['monitor'] and after['workspace']['id'] == 11, after
            assert monitors()['LEFT']['activeWorkspace']['id'] == 11
            for n in ('CENTER', 'RIGHT'): assert monitors()[n]['activeWorkspace']['id'] == before[n]
            assert state()['activations'] == 0, 'App toggle was called for an existing window'
            record(name+' tray reveals the existing window on its original monitor/workspace')
        click('RIGHT'); time.sleep(.2); click('RIGHT'); time.sleep(.2)
        assert window() and state()['activations'] == 0
        record('repeated clicks never hide the visible window')
        command('show', 'Tray second'); second = wait(lambda: window('Tray second'))
        ctl('dispatch', 'movetoworkspacesilent', '21,address:'+second['address'])
        ctl('dispatch', 'focuswindow', 'address:'+second['address'])
        ctl('dispatch', 'focusmonitor', 'CENTER'); ctl('dispatch', 'workspace', '22')
        click('LEFT'); wait(lambda: active().get('address') == second['address'])
        assert window('Tray second')['workspace']['id'] == 21
        record('most recently focused window is selected without moving it')
        command('hide', 'Tray second'); command('hide', 'Tray owner'); wait(lambda: not window())
        click('RIGHT'); wait(window)
        assert state()['activations'] == 1
        record('closed window is reopened by exactly one native activation')
        click('RIGHT', 'right'); time.sleep(.4)
        assert window() and state()['activations'] == 1
        # Native GTK menu appears as its own layer/popup without another left activation.
        assert any(c.get('xwayland') is False for c in clients())
        record('right click retains native tray behavior without toggling the app')
        subprocess.run(['grim', '-o', 'RIGHT', str(report_dir/'tray.png')], env=env, check=True, timeout=5)
        assert bar.poll() is None and app.poll() is None
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc(); print(report['error'], flush=True)
        try: report['failure_state'] = {'clients': clients(), 'monitors': monitors(), 'app': state()}
        except Exception: pass
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=4)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
        (report_dir/'result.json').write_text(json.dumps(report, indent=2)+'\n')
        shutil.rmtree(runtime)
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
