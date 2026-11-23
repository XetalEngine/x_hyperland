"""Persistent power preferences and a session-scoped, inhibitor-aware idle manager."""
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import psutil
from .common import ROOT, STATE, read, write, run, monitors

FILE = STATE/'power.json'
DEFAULTS = dict(version=1, enabled=False, ac_lock=0, ac_screen=0, ac_sleep=0,
                battery_lock=5, battery_screen=10, battery_sleep=20,
                lid_ac='system', lid_battery='system', lid_docked='system',
                critical_action='notify', critical_percent=5)
ACTIONS = ('system', 'nothing', 'lock', 'suspend', 'hibernate')


def normalize(value):
    result = dict(DEFAULTS)
    if not isinstance(value, dict): raise ValueError('Invalid power settings.')
    result.update({k:v for k,v in value.items() if k in result})
    if type(result['enabled']) is not bool: raise ValueError('Invalid power switch.')
    for source in ('ac', 'battery'):
        for action in ('lock', 'screen', 'sleep'):
            key = source+'_'+action
            if type(result[key]) is not int or not 0 <= result[key] <= 240: raise ValueError('Choose 0–240 minutes.')
        lock, screen, sleep = (result[source+'_'+s] for s in ('lock','screen','sleep'))
        if lock and screen and lock > screen: raise ValueError('Lock the session before turning off the screen.')
        if sleep and any(v > sleep for v in (lock,screen)): raise ValueError('Suspend must follow locking and screen-off.')
    for key in ('lid_ac','lid_battery','lid_docked'):
        if result[key] not in ACTIONS: raise ValueError('Invalid lid action.')
    if result['critical_action'] not in ('notify','suspend','hibernate'): raise ValueError('Invalid battery action.')
    if type(result['critical_percent']) is not int or not 2 <= result['critical_percent'] <= 20: raise ValueError('Choose a battery threshold from 2–20%.')
    return result


def load(): return normalize(read(FILE,DEFAULTS))


def save(value):
    value = normalize(value)
    if value['enabled'] and not shutil.which('hypridle'): raise RuntimeError('Install the idle service first.')
    write(FILE,value)
    env=dict(os.environ,PYTHONPATH=str(ROOT))
    with (STATE/'power-session.log').open('a') as log:
        subprocess.Popen([sys.executable,'-m','desktop_services.power'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    return 'Power preferences saved. They will be restored every login.'


def hardware_status():
    return json.loads(run([sys.executable,str(ROOT/'control_panel/system_tweaks.py'),'status']))


def apply_hardware(kind,value,revision,restore=False):
    if kind not in ('cpu_governor','cpu_energy','cpu_boost','battery_limit'):raise ValueError('Unknown power setting.')
    result = json.loads(run([sys.executable,str(ROOT/'control_panel/system_tweaks.py'),'restore' if restore else 'apply',kind,str(value),revision],timeout=300,stdin=subprocess.DEVNULL))
    if result.get('error'):raise RuntimeError(result['error'])
    return result.get('message','Saved.')


def idle_config(value,on_battery):
    source='battery' if on_battery else 'ac'
    lock=shlex.join(['hyprlock','--config',str(ROOT/'hyprlock.conf')])
    # Inhibit sleep until Wayland reports the session locked. Ordinary idle
    # listeners retain D-Bus, systemd and Wayland inhibitor support.
    lines=['general {',f'    lock_cmd = pidof hyprlock || {lock}',
           '    before_sleep_cmd = loginctl lock-session','    after_sleep_cmd = hyprctl dispatch dpms on','    inhibit_sleep = 3','}']
    commands={'lock':('loginctl lock-session',''), 'screen':('hyprctl dispatch dpms off','hyprctl dispatch dpms on'), 'sleep':('systemctl suspend','')}
    for key,(command,resume) in commands.items():
        minutes=value[source+'_'+key]
        if not minutes:continue
        lines += ['listener {',f'    timeout = {minutes*60}',f'    on-timeout = {command}']
        if resume:lines += [f'    on-resume = {resume}']
        lines += ['}']
    return '\n'.join(lines)+'\n'


def lid_state():
    # ACPI is available on laptops even when there is no UPower daemon.
    states=[p.read_text().strip().split()[-1] for p in Path('/proc/acpi/button/lid').glob('*/state')]
    if states:return any(s=='closed' for s in states)
    try:
        from gi.repository import Gio,GLib
        bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
        def prop(name):return bus.call_sync('org.freedesktop.UPower','/org/freedesktop/UPower','org.freedesktop.DBus.Properties','Get',GLib.Variant('(ss)',('org.freedesktop.UPower',name)),GLib.VariantType.new('(v)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
        return bool(prop('LidIsClosed')) if prop('LidIsPresent') else None
    except Exception:return None


def inhibit_lid():
    from gi.repository import Gio,GLib
    bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
    value, fds=bus.call_with_unix_fd_list_sync('org.freedesktop.login1','/org/freedesktop/login1',
        'org.freedesktop.login1.Manager','Inhibit',GLib.Variant('(ssss)',('handle-lid-switch','Hyper Fusion','Apply your saved lid preference','block')),
        GLib.VariantType.new('(h)'),Gio.DBusCallFlags.NONE,5000,None,None)
    return fds.get(value.unpack()[0])


def perform(action):
    if action=='lock':run(['loginctl','lock-session'])
    elif action in ('suspend','hibernate'):
        run(['loginctl','lock-session'])
        run(['systemctl',action],timeout=60)


def session():
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')
    if not signature:return
    with (STATE/'power-session.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        socket=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/os.environ.get('WAYLAND_DISPLAY','wayland-1')
        instance=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'hypr'/signature/'.socket.sock'
        idle=None; last=None; lid_fd=None; previous_lid=lid_state(); battery_warned=False; stop=False
        def halt(*_):
            nonlocal stop
            stop=True
        signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
        try:
            while not stop and socket.exists() and instance.exists():
                try:
                    value=load(); battery=psutil.sensors_battery(); on_battery=bool(battery and not battery.power_plugged)
                    configuration=idle_config(value,on_battery) if value['enabled'] else ''
                    if configuration!=last or (idle and idle.poll() is not None):
                        if idle:
                            idle.terminate();idle.wait(timeout=5);idle=None
                        if configuration:
                            config=STATE/'power-idle.conf';write(config,configuration)
                            idle=subprocess.Popen(['hypridle','-c',str(config)],stdin=subprocess.DEVNULL)
                        last=configuration
                    action=value['lid_battery' if on_battery else 'lid_ac'] if value['enabled'] else 'system'
                    if action!='system':
                        connected=monitors()
                        if any(not m['name'].startswith(('eDP','LVDS','DSI')) for m in connected):action=value['lid_docked']
                    if action!='system' and lid_fd is None:lid_fd=inhibit_lid()
                    if action=='system' and lid_fd is not None:os.close(lid_fd);lid_fd=None
                    closed=lid_state()
                    if lid_fd is not None and closed and previous_lid is False:perform(action)
                    previous_lid=closed
                    if value['enabled'] and on_battery and battery.percent<=value['critical_percent']:
                        if not battery_warned:
                            battery_warned=True
                            try:run(['notify-send','Battery is low',f'{battery.percent:g}% remaining. Connect your charger.'])
                            except Exception:pass
                            perform(value['critical_action'])
                    else:battery_warned=False
                except Exception as error:print(str(error),flush=True)
                time.sleep(3)
        finally:
            if idle and idle.poll() is None:idle.terminate()
            if lid_fd is not None:os.close(lid_fd)


if __name__=='__main__':session()
