#!/usr/bin/env python3
"""Real fullscreen/restore requests in a private three-output compositor.

Usage: check-fullscreen-monitors.py MEMORY_PLUGIN OUTPUT_DIR
       --minimize-plugin PATH --controls-plugin PATH [--allow-output] [--game-owned]
The default exercises the shipped current-display rule. --allow-output omits
that rule to test workspace policy when a client explicitly changes displays.
Only the disposable compositor loads plugins or receives test commands.
"""
import argparse
import json
import os
from pathlib import Path
import re
import select
import shlex
import subprocess
import tempfile
import time

from nested_session import nested_environment, assert_seat_isolated
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from compat import hypr_compat
from effects.window_close import model as controls
from effects.minimize import model as minimize
from workspaces import model as workspaces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('memory_plugin', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--minimize-plugin', type=Path, required=True)
    parser.add_argument('--controls-plugin', type=Path, required=True)
    parser.add_argument('--allow-output', action='store_true')
    parser.add_argument('--game-owned', action='store_true', help='Run the GLFW client with a native Steam game identity.')
    args = parser.parse_args()
    plugins = [p.resolve(strict=True) for p in (args.memory_plugin, args.minimize_plugin, args.controls_plugin)]
    root = args.directory.resolve()
    assert root.is_relative_to('/tmp') and root != Path('/tmp')
    root.mkdir(parents=True, exist_ok=False)
    home = root/'home'; profile = home/'.config/hypr'
    runtime = Path(tempfile.mkdtemp(prefix='fs-', dir='/tmp'))
    (root/'run').symlink_to(runtime, target_is_directory=True)
    for name, content in (
        ('effects/window_close/settings.conf', controls.encode(controls.DEFAULTS)),
        ('effects/minimize/settings.conf', minimize.encode(minimize.DEFAULTS)),
        ('workspaces/rules.json', workspaces.encode({'version': 1, 'default_layout': 'kde',
            'workspaces': {'2': dict(workspaces.DEFAULT, layout='tile')}})),
    ):
        path = profile/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
    conf = root/'hyprland.conf'
    # Leave room for the parent to resize its nested surface without overlapping
    # the two virtual outputs used for pointer focus tests.
    conf.write_text('''monitor = ,800x600@60,auto,1
monitor = WAYLAND-1,800x600@60,0x0,1
monitor = FS2,800x600@60,4096x0,1
monitor = FS3,800x600@60,4896x0,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
misc:disable_hyprland_guiutils_check = true
debug:disable_logs = false
input:follow_mouse = 1
animations:enabled = false
''')
    if not args.allow_output:
        source = (REPO/'config/hypr/hyprland.conf').read_text()
        rule = re.search(r'windowrule\s*\{\s*name\s*=\s*fusion-fullscreen-current-display\b[^}]*}', source)
        assert rule, 'The delivered fullscreen placement rule is missing'
        conf.write_text(conf.read_text()+'\n'+rule.group()+'\n')
    lua = conf.with_suffix('.lua'); lua.write_text(hypr_compat.Renderer(profile).render(conf))
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','glfw3','gl'], text=True))
    binary = root/'client'
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(REPO/'tests/window-buttons/fullscreen_client.c'),
                    '-o', str(binary), *flags], check=True)
    sources = []
    for name, protocol in (
        ('virtual-pointer', REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
        ('virtual-keyboard', REPO/'tests/native/virtual-keyboard-unstable-v1.xml'),
        ('system-bell', Path('/usr/share/wayland-protocols/staging/xdg-system-bell/xdg-system-bell-v1.xml')),
    ):
        subprocess.run(['wayland-scanner','client-header',str(protocol),str(root/(name+'.h'))],check=True)
        source = root/(name+'.c'); sources.append(str(source))
        subprocess.run(['wayland-scanner','private-code',str(protocol),str(source)],check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True))
    pointer_binary = root/'pointer'
    subprocess.run(['cc','-I'+str(root),str(REPO/'tests/wobbly/pointer.c'),*sources,'-o',str(pointer_binary),*flags],check=True)
    parent = Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute(): parent = Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env = nested_environment({k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_INSTANCE','XETAL_'))})
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home/'.config'), XDG_CACHE_HOME=str(home/'.cache'),
               XDG_DATA_HOME=str(home/'.local/share'), XDG_STATE_HOME=str(home/'.local/state'),
               XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=str(parent))
    for key in ('DISPLAY','DBUS_SESSION_BUS_ADDRESS'): env.pop(key, None)
    children, logs, results = [], [], []
    def spawn(argv, label, **options):
        log = (root/(label+'.log')).open('w'); logs.append(log)
        process = subprocess.Popen(argv, env=env, stderr=log, stdout=options.pop('stdout', log), **options)
        children.append(process); return process
    def ctl(*argv):
        result = subprocess.run(['/usr/bin/hyprctl', *argv], env=env, capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, result.stdout+result.stderr
        return result.stdout.strip()
    def dispatch(name, arguments=''):
        assert ctl('dispatch', hypr_compat.dispatcher(name, arguments)) == 'ok'
    def wait(predicate, timeout=8):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            assert children[0].poll() is None, 'Test compositor exited'
            value = predicate()
            if value: return value
            time.sleep(.04)
        state = {key: json.loads(ctl('-j',key)) for key in ('clients','monitors','activewindow','cursorpos')}
        state['follow_mouse'] = ctl('getoption','input:follow_mouse')
        (root/'timeout.json').write_text(json.dumps(state,indent=2)+'\n')
        raise AssertionError('Timed out waiting for test state; see '+str(root/'timeout.json'))
    try:
        compositor = spawn(['/usr/bin/Hyprland','-c',str(lua)], 'compositor', start_new_session=True)
        endpoint = wait(lambda: next(iter(runtime.glob('hypr/*/.socket.sock')), None))
        assert_seat_isolated(compositor.pid, root/'compositor.log')
        env['HYPRLAND_INSTANCE_SIGNATURE'] = endpoint.parent.name
        env['WAYLAND_DISPLAY'] = str(wait(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None)))
        for output in ('FS2','FS3'): ctl('output','create','headless',output)
        dispatch('focusmonitor','FS2'); dispatch('workspace','2')
        dispatch('focusmonitor','FS3'); dispatch('workspace','3')
        for plugin in plugins: assert ctl('plugin','load',str(plugin)) == 'ok'
        # Parent input must not override the private test pointer.
        for group in ('mice','keyboards'):
            for device in json.loads(ctl('-j','devices'))[group]:
                assert ctl('eval',hypr_compat.call('device',{'name':device['name'],'enabled':False})) == 'ok'
        if args.game_owned: env['SteamAppId'] = '480'
        app = spawn([str(binary)], 'client', stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        env.pop('SteamAppId', None)
        def current(): return next((w for w in json.loads(ctl('-j','clients')) if w['pid'] == app.pid), None)
        def command(operation):
            app.stdin.write(operation+'\n'); app.stdin.flush()
            assert select.select([app.stdout],[],[],5)[0], 'Client did not acknowledge command'
            assert app.stdout.readline().strip() == 'ok'
        window = wait(current); address = 'address:'+window['address']
        def normal():
            command('normal')
            wait(lambda: current()['fullscreen'] != 2)
            # GLFW receives the restored maximized state asynchronously. Clear
            # that state only after the fullscreen configure has arrived.
            time.sleep(.2); command('restore')
            wait(lambda: current()['fullscreen'] == 0)
            # The client must consume this configure before another native
            # maximize request; compositor state alone is not its acknowledgment.
            time.sleep(.25)
        def settled(name, mode, workspace=None):
            try:
                wait(lambda: current()['fullscreen'] == mode and current()['fullscreenClient'] == mode)
            except AssertionError:
                raise AssertionError((name, current(), json.loads(ctl('xetal-minimize'))))
            # Catch delayed workspace enforcement, not just the first configure.
            time.sleep(.35); value = current()
            assert value['fullscreen'] == mode and value['fullscreenClient'] == mode, (name, value)
            assert not value['hidden'], (name, value)
            if workspace is not None: assert value['workspace']['name'] == str(workspace), (name, value)
            results.append(dict(check=name, window=value)); print('PASS:', name, flush=True)
        for cycle in range(2):
            normal(); time.sleep(.25)
            dispatch('movetoworkspacesilent','3,'+address)
            dispatch('focuswindow',address); time.sleep(.2)
            command('maximize'); settled('maximize on display 3',1,3)
            command('fullscreen')
            destination = 1 if args.allow_output else 3
            settled('fullscreen output request, cycle '+str(cycle+1),2,destination)
            normal()
        command('fullscreen'); settled('enter fullscreen before move',2,1 if args.allow_output else 3)
        dispatch('movetoworkspace','2,'+address)
        settled('fullscreen survives forced tiling on display 2',2,2)
        assert not current()['floating']
        dispatch('movetoworkspace','3,'+address)
        settled('fullscreen survives KDE layout on display 3',2,3)
        assert current()['floating']
        dispatch('xetalminimize:minimize')
        wait(lambda: json.loads(ctl('xetal-minimize'))['active'] == 1)
        time.sleep(.35)
        minimized = json.loads(ctl('xetal-minimize'))['windows'][0]
        dispatch('xetalminimize:restore',str(minimized['id']))
        wait(lambda: json.loads(ctl('xetal-minimize'))['active'] == 0)
        settled('fullscreen survives minimize and restore',2,3)

        # GLFW's default AUTO_ICONIFY sends a native minimize request when a
        # fullscreen window loses activation (as Echo does on native Wayland).
        # Exercise actual pointer focus changes, including an empty display:
        # the monitor can change before the core clears its focused window.
        monitors = json.loads(ctl('-j','monitors'))
        width = max(m['x']+m['width']/m['scale'] for m in monitors)
        height = max(m['y']+m['height']/m['scale'] for m in monitors)
        pointer = spawn([str(pointer_binary),str(round(width)),str(round(height))],'pointer',
                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
        def focused_pid(): return json.loads(ctl('-j','activewindow')).get('pid')
        def point(output):
            monitor = next(m for m in monitors if m['name'] == output)
            x,y = round(monitor['x']+monitor['width']/monitor['scale']/2),round(monitor['y']+monitor['height']/monitor['scale']/2)
            # Crossing an output and moving within it are separate input frames
            # during normal mouse motion; do not simulate a single cursor warp.
            for position in (x-8,x):
                pointer.stdin.write(f'move {position} {y}\n'); pointer.stdin.flush()
                assert select.select([pointer.stdout],[],[],5)[0], 'Pointer did not acknowledge motion'
                assert pointer.stdout.readline().strip() == 'ok'
                time.sleep(.04)
        def restore_minimized(label, mode):
            wait(lambda: json.loads(ctl('xetal-minimize'))['active'] == 1)
            time.sleep(.35)
            item = json.loads(ctl('xetal-minimize'))['windows'][0]
            assert current()['workspace']['name'].startswith('special:xetal-minimized-')
            dispatch('xetalminimize:restore',str(item['id']))
            wait(lambda: json.loads(ctl('xetal-minimize'))['active'] == 0)
            settled(label,mode,3)

        point('FS3'); wait(lambda: focused_pid() == app.pid)
        point('FS2')
        wait(lambda: any(m['name'] == 'FS2' and m['focused'] for m in json.loads(ctl('-j','monitors'))))
        settled('fullscreen stays visible after pointer enters an empty display',2,3)
        other = spawn([str(binary)],'other-client',stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
        wait(lambda: focused_pid() == other.pid)
        settled('fullscreen stays visible when another app opens',2,3)
        for cycle in range(2):
            point('FS3'); wait(lambda: focused_pid() == app.pid)
            point('FS2'); wait(lambda: focused_pid() == other.pid)
            settled('fullscreen survives pointer focus loss, cycle '+str(cycle+1),2,3)
            assert not json.loads(ctl('xetal-minimize'))['active']

        # Desktop controls are explicit intent, even while another app has
        # focus. A native minimize from the focused fullscreen app also works.
        dispatch('xetalminimize:minimize',address)
        restore_minimized('explicit background fullscreen minimize and restore',2)
        point('FS3'); wait(lambda: focused_pid() == app.pid)
        command('minimize')
        restore_minimized('native focused fullscreen minimize and restore',2)
        normal()
        for mode in (0,1):
            if mode:
                dispatch('focuswindow',address)
                dispatch('fullscreen','1 1')
            settled('normal or maximized before native minimize',mode,3)
            point('FS2'); wait(lambda: focused_pid() == other.pid)
            command('minimize')
            restore_minimized('native background minimize and restore, mode '+str(mode),mode)
            normal()
        normal(); settled('exit fullscreen',0,3)
        assert not json.loads(ctl('xetal-minimize'))['active']
        (root/'report.json').write_text(json.dumps(results, indent=2)+'\n')
    finally:
        for process in reversed(children):
            if process.poll() is None: process.terminate()
        for process in reversed(children):
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        for stream in logs: stream.close()
        print('Evidence:',root,flush=True)


if __name__ == '__main__': main()
