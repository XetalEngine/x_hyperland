#!/usr/bin/env python3
"""Check partial main-surface redraws without screencopy in a nested compositor.

Usage: python3 tests/check-text-damage.py MEMORY_SO MINIMIZE_SO OUTPUT_DIR
Add --expect-bug to verify the old adapter reproduces the padded-surface defect.
All clients, input isolation and plugins belong to the private child session.
"""
import argparse
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from effects.minimize import model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('memory', type=Path)
    parser.add_argument('minimize', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--expect-bug', action='store_true')
    args = parser.parse_args()
    binaries = [args.memory.resolve(strict=True), args.minimize.resolve(strict=True)]
    root = args.output.resolve();root.mkdir(parents=True, exist_ok=False)
    protocol_dir = Path(subprocess.check_output(['pkg-config','--variable=pkgdatadir','wayland-protocols'],text=True).strip())
    protocol = protocol_dir/'stable/xdg-shell/xdg-shell.xml'
    for kind, name in (('client-header','xdg-shell.h'),('private-code','xdg-shell.c')):
        subprocess.run(['wayland-scanner',kind,str(protocol),str(root/name)],check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True))
    client_binary = root/'client'
    subprocess.run(['cc','-Wall','-Wextra','-Wno-unused-parameter','-I'+str(root),
                    str(REPO/'tests/native/text-damage-client.c'),str(root/'xdg-shell.c'),'-o',str(client_binary),*flags],check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','hyprland','libeis-1.0'],text=True))
    probe = root/'probe.so'
    subprocess.run(['g++','-std=c++23','-shared','-fPIC','-O1','-Wall','-Wextra','-Wno-unused-parameter',
                    *flags,str(REPO/'tests/native/text_damage_probe.cpp'),'-o',str(probe)],check=True)
    binaries.append(probe)
    runtime = Path(tempfile.mkdtemp(prefix='td-'))
    (root/'minimize.conf').write_text(model.encode(model.DEFAULTS))
    conf = root/'hyprland.conf'
    conf.write_text('''monitor = ,1280x800@60,auto,1
misc {
 disable_hyprland_logo = true
 disable_splash_rendering = true
 disable_hyprland_guiutils_check = true
 background_color = rgb(111111)
}
general {
 border_size = 0
}
decoration {
 rounding = 0
 blur {
  enabled = false
 }
 shadow {
  enabled = false
 }
}
animations {
 enabled = false
}
xwayland {
 enabled = false
}
debug {
 disable_logs = false
 damage_tracking = 2
}
''')
    parent = os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'):parent = str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    home = root/'home';home.mkdir()
    env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=parent, AQ_BACKENDS='wayland',
               HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1', GSETTINGS_BACKEND='memory',
               XETAL_MINIMIZE_CONFIG=str(root/'minimize.conf'),
               XETAL_WORKSPACE_RULES=str(root/'workspace-rules.json'))
    for key in ('HYPRLAND_INSTANCE_SIGNATURE','DISPLAY','DBUS_SESSION_BUS_ADDRESS',
                'HL_INITIAL_WORKSPACE_TOKEN','XDG_ACTIVATION_TOKEN','DESKTOP_STARTUP_ID'):
        env.pop(key,None)
    # Keep any generated compositor files outside the live profile.
    for key, directory in (('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data'),('XDG_STATE_HOME','state')):
        env[key] = str(root/directory)
    children = [];logs = [];observations = []

    def spawn(command, name, pipe=False):
        stream = (root/name).open('w');logs.append(stream)
        p = subprocess.Popen(command,env=env,stdout=subprocess.PIPE if pipe else stream,
                             stdin=subprocess.PIPE if pipe else subprocess.DEVNULL,
                             stderr=stream,text=True,bufsize=1,start_new_session=True)
        children.append(p);return p

    def ctl(*command):
        result = subprocess.run(['hyprctl',*command],env=env,capture_output=True,text=True,timeout=10)
        if result.returncode:raise RuntimeError(str(command)+result.stdout+result.stderr)
        return result.stdout.strip()

    def wait(predicate, seconds=15):
        until = time.monotonic()+seconds
        while time.monotonic()<until:
            value = predicate()
            if value:return value
            time.sleep(.04)
        raise AssertionError('Timed out waiting for text damage fixture')

    def reply(p, expected):
        assert select.select([p.stdout],[],[],10)[0], 'Fixture stopped responding'
        assert p.stdout.readline().strip()==expected, 'Unexpected fixture response'

    def clients():return json.loads(ctl('-j','clients'))
    def window():return next((c for c in clients() if c['class']=='fusion-text-damage-fixture'),None)

    try:
        compositor = spawn(['Hyprland','-c',str(conf)],'compositor.log')
        def connected():
            assert compositor.poll() is None, 'Nested compositor exited'
            try:instances = json.loads(ctl('-j','instances'))
            except json.JSONDecodeError:return None
            return next((i for i in instances if i['pid']==compositor.pid and
                         (runtime/'hypr'/i['instance']/'.socket.sock').exists()),None)
        instance = wait(connected)
        env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket'])
        time.sleep(1)
        for group in ('mice','keyboards'):
            for device in json.loads(ctl('-j','devices'))[group]:
                assert ctl('keyword',f'device[{device["name"]}]:enabled','false')=='ok'
        for binary in binaries:
            assert ctl('plugin','load',str(binary))=='ok',binary
        (root/'config-errors.txt').write_text(ctl('configerrors'))
        assert not ctl('configerrors'),ctl('configerrors')
        output = json.loads(ctl('-j','monitors'))[0]['name']
        for output_scale in (1,1.25):
            assert ctl('keyword','monitor',f'{output},1280x800@60,auto,{output_scale}')=='ok'
            for padding,buffer_scale in ((0,1),(10,1),(10,2)):
                p = spawn([str(client_binary),str(padding),str(buffer_scale)],f'client-{output_scale}-{padding}-{buffer_scale}.log',pipe=True)
                reply(p,'ready');w = wait(window);address = w['address']
                assert ctl('dispatch','setfloating','address:'+address)=='ok'
                assert ctl('dispatch','resizewindowpixel','exact 400 260,address:'+address)=='ok'
                assert ctl('dispatch','movewindowpixel','exact 50 300,address:'+address)=='ok'
                # Mapping seeds pending full-surface damage in core. Drain it
                # and acknowledge the layout configures before measuring.
                for _ in range(2):
                    p.stdin.write('0 0 400 260 223344 1\n');p.stdin.flush();reply(p,'ok')
                    time.sleep(.15)
                time.sleep(1)
                w = window();assert w['size']==[400,260],w['size']
                (root/f'window-{output_scale}-{padding}-{buffer_scale}.json').write_text(json.dumps(w))
                # Both protocol damage spaces; text-height strips and the edges
                # which would be lost by clipping before removing the padding.
                for buffer_damage in (1,0):
                    color = 'ef5925' if buffer_damage else '38dcb5'
                    for label,rect in (('text',(40,80,120,18)),('bottom',(40,252,120,8)),
                                       ('right',(392,80,8,40)),('corner',(392,252,8,8))):
                        x,y,width,height = rect
                        previous = json.loads(ctl('fusion-text-damage'))['commits']
                        p.stdin.write(f'{x} {y} {width} {height} {color} {buffer_damage}\n');p.stdin.flush();reply(p,'ok')
                        def updated():
                            data = json.loads(ctl('fusion-text-damage'))
                            return data if data['commits']>previous else None
                        data = wait(updated)
                        ok = data['damage']==list(rect)
                        record = dict(output_scale=output_scale,padding=padding,buffer_scale=buffer_scale,
                                      buffer_damage=buffer_damage,case=label,passed=ok,**data)
                        observations.append(record)
                        (root/'results.json').write_text(json.dumps(observations,indent=2)+'\n')
                        expected = not args.expect_bug or padding==0
                        assert ok==expected,record
                p.stdin.close();p.wait(timeout=5);assert p.returncode==0
                wait(lambda:window() is None)
                print(f'output={output_scale} padding={padding} buffer_scale={buffer_scale}: '+
                      ('defect reproduced' if args.expect_bug and padding else 'passed'),flush=True)
        print(f'PASS: {len(observations)} partial updates, no screencopy',flush=True)
    finally:
        for p in reversed(children):
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        for stream in logs:stream.close()
        for log in runtime.glob('hypr/*/hyprland.log'):
            shutil.copy2(log,root/'hyprland.log')
        shutil.rmtree(runtime,ignore_errors=True)


if __name__=='__main__':main()
