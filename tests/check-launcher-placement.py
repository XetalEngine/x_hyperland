#!/usr/bin/env python3
"""Check the first Apps opening on three private outputs of Hyprland 0.57+.

Run from a desktop: python3 tests/check-launcher-placement.py REPORT_DIRECTORY
Uses the real preloaded menu and a compositor-issued login workspace token.
All input, rules and windows belong to a separate nested compositor.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback

SOURCE = Path(__file__).resolve().parents[1]/'config/hypr'


def main():
    report_dir = Path(sys.argv[1]).resolve()
    report_dir.mkdir(parents=True, exist_ok=False)
    # Keep socket paths below the Unix-domain socket length limit.
    runtime = Path(tempfile.mkdtemp(prefix='fl-', dir='/tmp'))
    home = report_dir/'home'
    profile = home/'.config/hypr'
    profile.mkdir(parents=True)
    for name in ('launcher', 'theme', 'compat', 'control_center', 'sounds',
                 'icon_themes', 'window_rules', 'runtime', 'scripts', 'assets',
                 'waybar', 'desktop', 'visuals', 'effects', 'cursors'):
        shutil.copytree(SOURCE/name, profile/name,
                        ignore=shutil.ignore_patterns('.build', '__pycache__', 'third_party'))
    parent = Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute():
        parent = Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env = {k: v for k, v in os.environ.items() if k not in (
        'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'HYPRLAND_INSTANCE_SIGNATURE',
        'HL_INITIAL_WORKSPACE_TOKEN', 'HL_EXEC_RULE_TOKEN', 'XDG_ACTIVATION_TOKEN',
        'DESKTOP_STARTUP_ID') and not k.startswith('XETAL_')}
    env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
               XDG_CONFIG_HOME=str(home/'.config'), XDG_CACHE_HOME=str(home/'.cache'),
               XDG_STATE_HOME=str(home/'.local/state'), AQ_BACKENDS='wayland',
               WAYLAND_DISPLAY=str(parent), HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1',
               QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='', QT_STYLE_OVERRIDE='Fusion',
               GSETTINGS_BACKEND='memory', PATH=str(profile/'compat/bin')+':/usr/bin:/bin')
    config = report_dir/'hyprland.lua'
    config.write_text('''hl.monitor({output="",mode="1280x900@60",position="auto",scale=1})
hl.monitor({output="WAYLAND-1",mode="640x400@60",position="3840x0",scale=1})
hl.monitor({output="LEFT",mode="1280x900@60",position="0x0",scale=1})
hl.monitor({output="CENTER",mode="1280x900@60",position="1280x0",scale=1})
hl.monitor({output="RIGHT",mode="1280x900@60",position="2560x0",scale=1})
hl.config({animations={enabled=false},xwayland={enabled=false},misc={
    disable_hyprland_logo=true,disable_splash_rendering=true,
    disable_hyprland_guiutils_check=true,initial_workspace_token_timeout=60}})
hl.window_rule({name="xetal-launcher",match={class="^(xetal-launcher)$"},
    tag="+fusion-placement-owned",float=true,decorate=false,border_size=0})
''')
    children = []
    report = {'passed': False, 'openings': []}

    def ctl(*args):
        return subprocess.check_output([str(profile/'compat/bin/hyprctl'), *args],
                                       env=env, text=True, timeout=5).strip()

    def wait(predicate, seconds=20, process=None):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            if children[0].poll() is not None:
                raise RuntimeError('Private compositor exited; see compositor.log')
            if process is not None and process.poll() is not None:
                raise RuntimeError('Apps exited; see the apps.log for this case')
            time.sleep(.05)
        raise RuntimeError('Timed out waiting for private Apps test state')

    def menu_client(pid):
        return next((c for c in json.loads(ctl('-j', 'clients'))
                     if c['pid'] == pid and c.get('mapped')), None)

    def toggle():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(2)
            peer.connect(str(endpoint))
            peer.sendall(b'toggle-bar\n')

    try:
        with (report_dir/'compositor.log').open('w') as log:
            children.append(subprocess.Popen(['/usr/bin/Hyprland', '-c', str(config)],
                                             env=env, stdout=log, stderr=log, start_new_session=True))
        ipc = wait(lambda: next(iter(runtime.glob('hypr/*/.socket.sock')), None))
        env['HYPRLAND_INSTANCE_SIGNATURE'] = ipc.parent.name
        env['WAYLAND_DISPLAY'] = str(wait(lambda: next(
            (p for p in runtime.glob('wayland-*') if p.is_socket()), None)))
        endpoint = ipc.parent/'xetal-launcher.sock'
        for name in ('LEFT', 'CENTER', 'RIGHT'):
            ctl('output', 'create', 'headless', name)
        monitors = {m['name']: m for m in json.loads(ctl('-j', 'monitors'))}
        for first in ('CENTER', 'RIGHT', 'LEFT'):
            ctl('reload')
            origin = 'RIGHT' if first == 'LEFT' else 'LEFT'
            ctl('dispatch', 'focusmonitor', origin)
            token_path = report_dir/(first+'-startup-token')
            # Ask this compositor to issue a real token for the preload workspace.
            command = shlex.join(['/bin/sh', '-c',
                'printf %s "$HL_INITIAL_WORKSPACE_TOKEN" > '+shlex.quote(str(token_path))])
            ctl('dispatch', 'hl.dsp.exec_cmd('+json.dumps(command)+')')
            wait(lambda: token_path.exists() and token_path.stat().st_size)
            child_env = dict(env, HL_INITIAL_WORKSPACE_TOKEN=token_path.read_text())
            with (report_dir/(first+'-apps.log')).open('w') as log:
                menu = subprocess.Popen([sys.executable, str(profile/'launcher/placement.py'), '--preload'],
                                        env=child_env, stdout=log, stderr=log)
            children.append(menu)
            wait(lambda: endpoint.is_socket(), process=menu)
            for index, name in enumerate((first, 'LEFT', 'CENTER', 'RIGHT')):
                monitor = monitors[name]
                ctl('dispatch', f'hl.dsp.cursor.move({{x={monitor["x"]+10},y=10}})')
                toggle()
                client = wait(lambda: menu_client(menu.pid))
                passed = client['monitor'] == monitor['id'] and client['at'] == [monitor['x']+24, 14]
                report['openings'].append(dict(first=index == 0, origin=origin, expected=name,
                                                monitor=client['monitor'], position=client['at'], passed=passed))
                print(('PASS' if passed else 'FAIL')+f' {name}: '+('first opening' if index == 0 else 'reopen'), flush=True)
                if not passed:
                    raise AssertionError(f'Apps opened on the wrong output: {report["openings"][-1]}')
                toggle()
                wait(lambda: not menu_client(menu.pid))
            menu.terminate()
            menu.wait(timeout=4)
            endpoint.unlink(missing_ok=True)
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        print(report['error'], flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        (report_dir/'result.json').write_text(json.dumps(report, indent=2)+'\n')
        shutil.rmtree(runtime)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
