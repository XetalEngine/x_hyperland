#!/usr/bin/env python3
"""Exercise native default/pinned routing in a private PipeWire session.

No hardware monitors are loaded. Silence goes to two disposable null outputs;
the desktop's server, default devices, volume and saved routes are untouched.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def wait_for(fn,timeout=6):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            result=fn()
            if result:return result
        except (RuntimeError,subprocess.SubprocessError,OSError,ValueError):pass
        time.sleep(.08)
    raise AssertionError('Audio condition did not settle: '+str(fn))


def exercise(folder):
    sys.path.insert(0,str(ROOT/'config/hypr/control_center'))
    import audio_backend as audio
    import audio_routing as routing
    children=[];logs=[];checks=[]
    def start(name,*args):
        log=(folder/(name+'.log')).open('a');logs.append(log)
        process=subprocess.Popen(args,stdout=log,stderr=log);children.append(process);return process
    def stream(name):
        return start(name,'pacat','--playback','--raw','--rate=48000','--channels=2','--format=s16le',
            '--client-name='+name,'--property=application.id=org.hyperfusion.test.'+name,
            '--property=application.name='+name,'/dev/zero')
    def group(name):
        return next((g for g in audio.groups(audio.listing('sink-input'),'playback') if g['name']==name),None)
    def device(name):return next(d for d in audio.listing('sink') if d['name']==name)
    def main(name):audio.apply_device('sink',device(name),'default',None)
    def route(name,output):audio.apply_app(group(name),'device',output)
    def expect(label,locations,selections):
        def ready():
            data=audio.snapshot(playback_only=True)
            by_name={g['name']:g for g in data['apps']['playback']}
            sink_names={d['index']:d['name'] for d in data['devices']['sink']}
            for name,output in locations.items():
                if name not in by_name:return False
                for s in by_name[name]['streams']:
                    if sink_names.get(s['sink'])!=output:return False
                    actual=routing.selection(s,'sink',data['devices']['sink'],data['defaults']['sink'],data['routes'])
                    if actual!=selections[name]:return False
                    if s.get('mute') or audio.level([s])!=100:raise AssertionError('Routing changed volume or mute')
            return True
        wait_for(ready);checks.append(label);print('PASS '+label,flush=True)
    try:
        start('pipewire','pipewire');wait_for(lambda:(folder/'run/pipewire-0').exists())
        start('wireplumber','wireplumber','--profile','policy')
        start('pulse','pipewire-pulse');wait_for(lambda:audio.pactl('info'))
        wait_for(lambda:routing.targets() is not None)
        for name in ('hf_test_a','hf_test_b'):
            audio.pactl('load-module','module-null-sink','sink_name='+name,'sink_properties=device.description='+name)
        wait_for(lambda:len(audio.listing('sink'))>=2)
        main('hf_test_a');wait_for(lambda:json.loads(audio.pactl('-f','json','info'))['default_sink_name']=='hf_test_a')
        streams={name:stream(name) for name in ('Follow','Override','Pinned')}
        default=routing.SYSTEM_DEFAULT
        expect('new apps use System Default',dict.fromkeys(streams,'hf_test_a'),dict.fromkeys(streams,default))
        route('Override','hf_test_b');route('Pinned','hf_test_a')
        expect('individual choices include pinning the current default',
               {'Follow':'hf_test_a','Override':'hf_test_b','Pinned':'hf_test_a'},
               {'Follow':default,'Override':'hf_test_b','Pinned':'hf_test_a'})
        main('hf_test_b')
        expect('main output moves followers and preserves both overrides',
               {'Follow':'hf_test_b','Override':'hf_test_b','Pinned':'hf_test_a'},
               {'Follow':default,'Override':'hf_test_b','Pinned':'hf_test_a'})
        main('hf_test_a');route('Override',default)
        expect('System Default clears an individual override',dict.fromkeys(streams,'hf_test_a'),
               {'Follow':default,'Override':default,'Pinned':'hf_test_a'})
        main('hf_test_b')
        expect('returned app follows subsequent main changes with no mixer running',
               {'Follow':'hf_test_b','Override':'hf_test_b','Pinned':'hf_test_a'},
               {'Follow':default,'Override':default,'Pinned':'hf_test_a'})
        for name in ('Override','Pinned'):
            streams[name].terminate();streams[name].wait(timeout=2)
            wait_for(lambda name=name:group(name) is None)
            streams[name]=stream(name)
        expect('restarted apps restore explicit choices and default followers',
               {'Follow':'hf_test_b','Override':'hf_test_b','Pinned':'hf_test_a'},
               {'Follow':default,'Override':default,'Pinned':'hf_test_a'})
        (folder/'result.json').write_text(json.dumps({'passed':checks},indent=2)+'\n')
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait()
        for log in logs:log.close()


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--inside':exercise(Path(sys.argv[2]));return 0
    for name in ('pipewire','pipewire-pulse','wireplumber','pactl','pw-dump','pw-metadata','pacat','dbus-run-session'):
        if not shutil.which(name):raise RuntimeError('Missing test dependency: '+name)
    folder=Path(tempfile.mkdtemp(prefix='hyperfusion-audio-routing-'))
    for name in ('run','config','state','cache'):(folder/name).mkdir(mode=0o700)
    env=dict(os.environ,XDG_RUNTIME_DIR=str(folder/'run'),PIPEWIRE_RUNTIME_DIR=str(folder/'run'),
             XDG_CONFIG_HOME=str(folder/'config'),XDG_STATE_HOME=str(folder/'state'),XDG_CACHE_HOME=str(folder/'cache'),
             PIPEWIRE_REMOTE='pipewire-0',PULSE_RUNTIME_PATH=str(folder/'run/pulse'),PULSE_SERVER='unix:'+str(folder/'run/pulse/native'))
    env.pop('WIREPLUMBER_CONFIG_DIR',None);env.pop('PIPEWIRE_CONFIG_DIR',None)
    print('Private audio test: '+str(folder),flush=True)
    return subprocess.call(['dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--inside',str(folder)],env=env)


if __name__=='__main__':raise SystemExit(main())
