#!/usr/bin/env python3
"""Observe real Waybar workspace frames on two disposable compositor outputs.

Only private compositor rules are edited. The +/close helper commands are
covered by the GTK pointer suite; this check does not click those launchers.
"""
from nested_session import nested_environment, assert_seat_isolated
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[1]
SOURCE=REPO/'config/hypr'
sys.path.insert(0,str(SOURCE/'compat'))
import hypr_compat


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=False)
    runtime=Path(tempfile.mkdtemp(prefix='wm-'));runtime.chmod(0o700)
    (root/'runtime').symlink_to(runtime)
    parent=json.loads(subprocess.check_output(['hyprctl','-j','instances']))[-1]
    env=nested_environment(dict(os.environ,XDG_RUNTIME_DIR=str(runtime),
        WAYLAND_DISPLAY=str(Path('/run/user')/str(os.getuid())/parent['wl_socket']),
        XDG_CONFIG_HOME=str(root/'config'),XDG_CACHE_HOME=str(root/'cache'),
        XDG_STATE_HOME=str(root/'state'),GDK_BACKEND='wayland',QT_QPA_PLATFORM='wayland',
        GSETTINGS_BACKEND='memory',NO_AT_BRIDGE='1',FUSION_WORKSPACE_REPORT=str(root/'frames.jsonl')))
    for key in ('DISPLAY','DBUS_SESSION_BUS_ADDRESS','HYPRLAND_INSTANCE_SIGNATURE'):env.pop(key,None)
    ids=[2,7,8,17];other=[31,32,33,34];children=[];logs=[];comp=None;baseline_modes={}
    config=root/'hyprland.conf';lua=root/'hyprland.lua'
    def configure(numbers):
        text='''monitor = ,1000x400@60,auto,1
monitor = LEFT,1000x400@60,0x0,1
monitor = RIGHT,1000x400@60,1000x0,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
animations:enabled = false
debug:disable_logs = false
debug:enable_stdout_logs = true
'''
        for output,values in (('LEFT',numbers),('RIGHT',other)):
            text+=''.join(f'workspace = {n}, monitor:{output}, persistent:true\n' for n in values)
        config.write_text(text);lua.write_text(hypr_compat.Renderer(root).render())
    def spawn(args,name):
        log=(root/(name+'.log')).open('w');logs.append(log)
        child=subprocess.Popen(list(map(str,args)),env=env,stdout=log,stderr=log,start_new_session=True)
        children.append(child);return child
    def run(*args):return subprocess.check_output(args,env=env,text=True,stderr=subprocess.PIPE,timeout=10).strip()
    def ctl(*args):return run('/usr/bin/hyprctl',*args)
    def dispatch(name,arg=''):return ctl('dispatch',hypr_compat.dispatcher(name,arg))
    def wait(predicate):
        end=time.monotonic()+12
        while time.monotonic()<end:
            if comp is not None and comp.poll() is not None:raise RuntimeError('Private compositor exited')
            value=predicate()
            if value:return value
            time.sleep(.03)
        raise AssertionError('Timed out waiting for the private workspace test')
    def mapping(numbers):
        data='enabled\n'+''.join(f'{n} {index}\t{n}\n' for values in (numbers,other) for index,n in enumerate(values,1))
        temporary=face_path.with_suffix('.tmp');temporary.write_text(data);temporary.replace(face_path)
    def frames():
        try:lines=(root/'frames.jsonl').read_text().splitlines()
        except FileNotFoundError:return []
        return [json.loads(line) for line in lines if line.endswith('}')]
    def verify(label,numbers,start):
        time.sleep(.65);samples=frames()[start:]
        expected={n:str(index) for values in (numbers,other) for index,n in enumerate(values,1)}
        for frame in samples:
            if baseline_modes:assert frame['mode']==baseline_modes[frame['monitor_x']],('Mode indicator flickered',label,frame)
            for button in frame['buttons']:
                # A disappearing pill may still be represented by its last
                # frame, but raw internal IDs must never reach a painted label.
                assert button['label'].strip() in {'1','2','3','4','5'},(label,frame)
        for x,values in ((0,numbers),(1000,other)):
            latest=next(frame for frame in reversed(samples) if frame['monitor_x']==x)
            assert [b['id'] for b in latest['buttons']]==values,(label,latest)
            assert [b['label'].strip() for b in latest['buttons']]==[expected[n] for n in values]
        print('PASS',label,len(samples),'painted frames',flush=True)
        return samples
    try:
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gtk+-3.0','gtk-layer-shell-0','json-glib-1.0'],text=True))
        subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-shared','-fPIC',str(REPO/'tests/workspace-observer.c'),'-o',str(root/'observer.so'),*flags],check=True)
        configure(ids);comp=spawn(['/usr/bin/Hyprland','-c',lua],'compositor')
        ipc=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None))
        env['HYPRLAND_INSTANCE_SIGNATURE']=ipc.parent.name
        env['WAYLAND_DISPLAY']=str(wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None)))
        assert_seat_isolated(comp.pid,root/'compositor.log')
        for name in ('LEFT','RIGHT'):ctl('output','create','headless',name)
        for monitor in json.loads(ctl('-j','monitors')):
            if monitor['name'] not in ('LEFT','RIGHT'):ctl('output','remove',monitor['name'])
        ctl('reload');dispatch('focusmonitor','LEFT');dispatch('workspace','2')
        dispatch('focusmonitor','RIGHT');dispatch('workspace','31')
        face_path=ipc.parent/'xetal-cube-faces';mapping(ids)
        dispatch('focusmonitor','LEFT');dispatch('workspace','2')
        app=spawn(['kitty','--config','/dev/null','--class','fusion-workspace-motion-test','-e','sleep','90'],'app')
        wait(lambda:any(client['pid']==app.pid for client in json.loads(ctl('-j','clients'))))
        bar_config={'output':['LEFT','RIGHT'],'height':36,'modules-left':['hyprland/workspaces','cffi/new-workspace','cffi/workspace-mode','cffi/observer'],
            'hyprland/workspaces':{'format':'{icon} {windows}','all-outputs':False,'sort-by':'number','workspace-taskbar':{'enable':True,'format':'{icon}','icon-size':21}},
            'cffi/new-workspace':{'module_path':str(SOURCE/'waybar/workspaces/controls.so')},
            'cffi/workspace-mode':{'module_path':str(SOURCE/'waybar/workspaces/mode.so')},
            'cffi/observer':{'module_path':str(root/'observer.so')}}
        (root/'waybar.json').write_text(json.dumps(bar_config))
        style=Path.home()/'.config/hypr/waybar/style.css'
        if not style.exists():style=SOURCE/'waybar/style.css'
        bar=spawn(['waybar','-c',root/'waybar.json','-s',style],'waybar')
        wait(lambda:len(frames())>=2);verify('initial local labels on both outputs',ids,0)
        baseline_modes.update({x:next(f['mode'] for f in reversed(frames()) if f['monitor_x']==x) for x in (0,1000)})
        start=len(frames());expanded=ids+[24];mapping(expanded);configure(expanded);ctl('reload')
        samples=verify('add a fifth workspace through config reload',expanded,start)
        widths={f['add_x'] for f in samples if f['monitor_x']==0}
        assert len(widths)>=5,('No smooth native entrance',widths)
        run('grim','-o','LEFT',str(root/'five-workspaces.png'))
        start=len(frames());ctl('reload');verify('repeated rebuild keeps labels stable',expanded,start)
        start=len(frames());mapping(ids);configure(ids);ctl('keyword','workspace','24, persistent:false');ctl('reload')
        samples=verify('remove fifth workspace through config reload',ids,start)
        widths={f['add_x'] for f in samples if f['monitor_x']==0}
        assert len(widths)>=5,('No smooth native removal',widths)
        run('grim','-o','LEFT',str(root/'four-workspaces.png'))
        assert bar.poll() is None
        start=len(frames());baseline_modes.clear();bar.send_signal(signal.SIGUSR2)
        wait(lambda:len(frames())>start+3)
        verify('Waybar module reload and animation cleanup',ids,start)
        assert bar.poll() is None
        assert 'CRITICAL' not in (root/'waybar.log').read_text()
        print('PASS real Waybar remained responsive; report',root,flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        for log in logs:log.close()
    current=json.loads(subprocess.check_output(['hyprctl','-j','instances']))
    assert any(item['pid']==parent['pid'] for item in current),'Parent desktop changed'
    print('PASS parent desktop unchanged',flush=True)


if __name__=='__main__':main()
