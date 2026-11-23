"""Per-display DDC/backlight controls with a separate timed rollback process."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import time
from .common import STATE,read,write,run,monitors

FILE=STATE/'monitor-picture.json'
FEATURES={'brightness':'10','contrast':'12','red':'16','green':'18','blue':'1A'}


def probe(name):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+',name):raise ValueError('Invalid display connector.')
    devices=[]
    try:
        output=run(['ddcutil','detect','--brief'],timeout=30)
        for block in re.split(r'\n(?=Display |Invalid display)',output):
            connector=re.search(r'DRM connector:\s*(card\d+-[^\s]+)',block)
            bus=re.search(r'I2C bus:\s*/dev/i2c-(\d+)',block)
            if connector and bus and re.sub(r'^card\d+-','',connector[1])==name:
                edid=Path('/sys/class/drm')/connector[1]/'edid'
                raw=edid.read_bytes()
                if len(raw)>=128:devices.append(dict(kind='ddc',bus=int(bus[1]),identity=hashlib.sha256(raw).hexdigest(),name=name))
    except (OSError,RuntimeError,subprocess.TimeoutExpired):pass
    if devices:return devices[0]
    backlights=list(Path('/sys/class/backlight').glob('*'))
    internal=[m for m in monitors() if m['name'].startswith(('eDP','LVDS','DSI'))]
    if len(backlights)==1 and len(internal)==1 and internal[0]['name']==name:
        return dict(kind='backlight',device=backlights[0].name,identity='backlight:'+backlights[0].name,name=name)
    raise RuntimeError('No writable brightness interface was found. Enable DDC/CI in the monitor’s own menu for external displays.')


def levels(device):
    if device['kind']=='backlight':
        base=Path('/sys/class/backlight')/device['device'];maximum=int((base/'max_brightness').read_text())
        return {'brightness':dict(value=int((base/'brightness').read_text()),maximum=maximum)}
    process=subprocess.run(['ddcutil','--brief','--bus',str(device['bus']),'getvcp',*FEATURES.values()],timeout=25,capture_output=True,text=True)
    # Unsupported RGB controls must not hide a working brightness control.
    result=process.stdout
    values={}
    for key,code in FEATURES.items():
        match=re.search(r'^VCP '+code+r' C (\d+) (\d+)\s*$',result,re.MULTILINE|re.IGNORECASE)
        if match and int(match[2])>0:values[key]=dict(value=int(match[1]),maximum=int(match[2]))
    if not values:raise RuntimeError('The monitor does not expose usable DDC picture controls.')
    return values


def set_raw(device,key,amount):
    if key not in FEATURES or type(amount) is not int or amount<0:raise ValueError('Invalid picture adjustment.')
    if device['kind']=='backlight':
        if key!='brightness':raise ValueError('Backlights only support brightness.')
        run(['brightnessctl','--device',device['device'],'set',str(amount)])
    else:run(['ddcutil','--bus',str(device['bus']),'setvcp',FEATURES[key],str(amount)],timeout=20)


def apply(device,values):
    before=levels(device);changed=[]
    try:
        for key,percent in values.items():
            if key not in before or type(percent) is not int or not 1<=percent<=100:raise ValueError('Choose a supported adjustment from 1–100%.')
            amount=max(1,round(before[key]['maximum']*percent/100))
            if amount!=before[key]['value']:changed.append(key);set_raw(device,key,amount)
        actual=levels(device)
        if any(abs(actual[k]['value']-max(1,round(before[k]['maximum']*values[k]/100)))>1 for k in changed):raise RuntimeError('The display did not accept the requested picture settings.')
    except Exception as error:
        failures=[]
        for key in reversed(changed):
            try:set_raw(device,key,before[key]['value'])
            except Exception as rollback:failures.append(str(rollback))
        if failures:raise RuntimeError(str(error)+'; restoration errors: '+'; '.join(failures)) from error
        raise
    return before


def restore(device,before):
    errors=[]
    for key,value in before.items():
        try:set_raw(device,key,value['value'])
        except Exception as error:errors.append(str(error))
    if errors:raise RuntimeError('; '.join(errors))


def preview(name,values):
    device=probe(name);STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/('monitor-'+device['identity']+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        before=apply(device,values);kept=False
        try:
            print(json.dumps(dict(ready=True)),flush=True)
            readable,_,_=select.select([sys.stdin],[],[],20)
            if readable and sys.stdin.readline().strip()=='keep':
                state=read(FILE,dict(version=1,displays={}))
                state['displays'][device['identity']]=dict(name=name,values=values)
                write(FILE,state);kept=True
        finally:
            if not kept:restore(device,before)
        print(json.dumps(dict(kept=kept)),flush=True)


def session():
    socket=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/os.environ.get('WAYLAND_DISPLAY','wayland-1')
    instance=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'hypr'/os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')/'.socket.sock'
    seen=set();last=time.monotonic()
    while socket.exists() and instance.exists():
        try:
            now=time.monotonic()
            if now-last>20:seen.clear()
            last=now;current={m['name'] for m in monitors()};seen&=current
            state=read(FILE,dict(displays={}))
            for name in current-seen:
                if not state['displays']:continue
                device=probe(name);saved=state['displays'].get(device['identity'])
                if saved:
                    with (STATE/('monitor-'+device['identity']+'.lock')).open('a') as lock:
                        fcntl.flock(lock,fcntl.LOCK_EX);apply(device,saved['values'])
                seen.add(name)
        except Exception as error:print(str(error),flush=True)
        time.sleep(10)


if __name__=='__main__':
    def interrupted(*_):
        if len(sys.argv)==4 and sys.argv[1]=='--preview':raise InterruptedError('Monitor preview interrupted; restoring previous settings.')
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,interrupted)
    try:
        if len(sys.argv)==4 and sys.argv[1]=='--preview':preview(sys.argv[2],json.loads(sys.argv[3]))
        else:session()
    except Exception as error:
        print(json.dumps(dict(error=str(error))),flush=True);raise SystemExit(1)
