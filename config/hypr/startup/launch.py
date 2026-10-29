#!/usr/bin/env python3
"""Staggered, idempotent startup on one dedicated Hyprland special workspace."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import time
import login_settings

ROOT = Path(__file__).resolve().parent
WORKSPACE = 'special:xetal-startup'


def wait_for_login(runtime, delay):
    """Wait without surviving a compositor exit, even if stale sockets remain."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.connect(str(runtime / '.socket2.sock'))
        deadline = time.monotonic() + delay
        while (remaining := deadline - time.monotonic()) > 0:
            stream.settimeout(remaining)
            try:
                if not stream.recv(65536):
                    return False
            except socket.timeout:
                break
    return True


def ctl(*args, json_output=False):
    command=['hyprctl']+(['-j'] if json_output else [])+list(args)
    result=subprocess.run(command,capture_output=True,text=True,timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout) if json_output else result.stdout.strip()


def command_for(mode, target):
    if mode == 'projects':
        return ['env', 'QT_QPA_PLATFORM=wayland', 'python3', str(ROOT/'projects.py')]
    command=['kitty','--config',str(ROOT/'kitty.conf'),'--class','xetal-startup-'+mode,
             '--title','Xetal / '+mode.title(),'python3',str(ROOT/'scene.py'),mode]
    if target['width']/target['scale']<2200:
        command[3:3]=['-o','font_size=10.5']
    return command


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--toggle',action='store_true')
    parser.add_argument('--login',action='store_true',help='Wait five seconds before the login animation')
    args=parser.parse_args()
    if args.login and not login_settings.enabled():
        return
    sig=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')
    if not sig:
        return
    runtime=Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/sig
    if args.login and not wait_for_login(runtime, 5.0):
        return
    if args.login and not login_settings.enabled():
        return
    with (runtime/'xetal-startup.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        monitors=ctl('monitors',json_output=True)
        visible=next((m for m in monitors if m.get('specialWorkspace',{}).get('name')==WORKSPACE),None)
        if visible and args.toggle:
            ctl('dispatch','focusmonitor',visible['name'])
            ctl('dispatch','togglespecialworkspace','xetal-startup')
            return
        target=(monitors[min(1,len(monitors)-1)] if args.login else next((m for m in monitors if m.get('focused')),monitors[0]))
        clients=ctl('clients',json_output=True)
        modes=['info','matrix','clock','projects']
        existing={c['class']:c for c in clients if c.get('mapped') and c['class'].startswith('xetal-startup-')}
        ctl('dispatch','focusmonitor',target['name'])
        # Existing consoles are reused; closed ones are recreated in sequence.
        if not visible and existing:
            ctl('dispatch','togglespecialworkspace','xetal-startup')
            visible=True
        with (runtime/'startup-scene.log').open('a') as log:
            for mode in modes:
                cls='xetal-startup-'+mode
                if cls in existing:
                    continue
                command=command_for(mode,target)
                # Spawn via compositor to inherit its actual Wayland session environment.
                ctl('dispatch','exec',shlex.join(command)+' >> '+shlex.quote(str(runtime/f'startup-{mode}.log'))+' 2>&1')
                found=False
                for _ in range(50):
                    time.sleep(.08)
                    if any(c['class']==cls and c.get('mapped') for c in ctl('clients',json_output=True)):
                        found=True;break
                if not found:
                    log.write(f'{time.time():.3f} failed to map {cls}\n');log.flush()
                    raise RuntimeError('A startup console did not open; see '+str(runtime/f'startup-{mode}.log'))
                log.write(f'{time.time():.3f} mapped {cls}\n');log.flush()
                if not visible:
                    ctl('dispatch','togglespecialworkspace','xetal-startup')
                    visible=True
                time.sleep(.5)
            # Upgrade an already-open dashboard only after its replacement maps.
            # These are our generated mascot consoles, not user terminal shells.
            for client in clients:
                if client.get('class')=='xetal-startup-hero' and client.get('mapped'):
                    ctl('dispatch','closewindow','address:'+client['address'])


if __name__=='__main__':main()
