#!/usr/bin/env python3
"""Real Brave client requests on private Wayland/X11 test windows.

Usage: check-browser-minimize.py PLUGIN DIRECTORY
Runs only a disposable nested compositor and fresh browser profiles. Never
controls the user's browser, installs modules or changes desktop preferences.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import traceback

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'config/hypr'),str(REPO/'config/hypr/compat'),str(REPO/'tests/minimize')]
from effects.minimize import model
import hypr_compat
from cdp import Browser


def main():
    binary=Path(sys.argv[1]).resolve(strict=True)
    root=Path(sys.argv[2]).resolve();root.mkdir(parents=True,exist_ok=False)
    home=root/'home';home.mkdir()
    runtime=Path(tempfile.mkdtemp(prefix='bm-',dir='/tmp'));(root/'run').symlink_to(runtime,target_is_directory=True)
    config=home/'.config/hypr/effects/minimize/settings.conf';config.parent.mkdir(parents=True)
    config.write_text(model.encode(dict(model.DEFAULTS,auto_hide=False)))
    (root/'hyprland.conf').write_text('''monitor = ,1600x900@60,auto,1
monitor = WAYLAND-1,800x450@60,1600x900,1
monitor = BROWSER,1600x900@60,0x0,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
misc:disable_hyprland_guiutils_check = true
misc:focus_on_activate = true
animations:enabled = false
debug:disable_logs = false
debug:enable_stdout_logs = true
''')
    lua=root/'hyprland.lua';lua.write_text(hypr_compat.Renderer(root).render())
    env={k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_INSTANCE','XETAL_'))}
    parent=Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute():parent=Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env.update(HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),
               XDG_STATE_HOME=str(home/'.local/state'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=str(parent),
               AQ_BACKENDS='wayland',HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',
               GSETTINGS_BACKEND='memory',QT_QPA_PLATFORMTHEME='',XETAL_MINIMIZE_CONFIG=str(config))
    env.pop('DBUS_SESSION_BUS_ADDRESS',None);env.pop('DISPLAY',None)
    children=[];logs=[];report={'passed':False,'plugin':str(binary),
        'plugin_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'checks':[]}
    def spawn(args,label,**kwargs):
        stream=(root/(label+'.log')).open('w');logs.append(stream)
        child=subprocess.Popen(args,stdout=stream,stderr=stream,**kwargs);children.append(child);return child
    def run(*args):
        result=subprocess.run(args,env=env,text=True,capture_output=True,timeout=20)
        if result.returncode:raise RuntimeError(str(args)+': '+result.stdout+result.stderr)
        return result.stdout.strip()
    def ctl(*args):return run('/usr/bin/hyprctl',*args)
    def dispatch(name,args=''):
        result=ctl('dispatch',hypr_compat.dispatcher(name,args))
        if result!='ok':raise RuntimeError(result)
    def clients():return json.loads(ctl('-j','clients'))
    def status():return json.loads(ctl('xetal-minimize'))
    def configured(platform):
        if platform!='wayland':return True
        # Mapping alone does not mean Chromium has consumed the latest state.
        # Wait for its acknowledgment before issuing another state request.
        lines=(root/'wayland.log').read_text(errors='replace')
        configs=re.findall(r'xdg_surface#(\d+)\.configure\((\d+)\)',lines)
        if not configs:return False
        surface=configs[0][0]
        serial=next(serial for candidate,serial in reversed(configs) if candidate==surface)
        return f'xdg_surface#{surface}.ack_configure({serial})' in lines
    def wait(predicate,seconds=15,required=True):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            result=predicate()
            if result:return result
            if children and children[0].poll() is not None:raise RuntimeError('Test compositor exited')
            time.sleep(.05)
        if required:raise RuntimeError('Timed out waiting for browser test state')
        return False
    def check(name,okay,detail=None):
        report['checks'].append(dict(name=name,passed=bool(okay),detail=detail))
        print(('PASS ' if okay else 'FAIL ')+name,flush=True)
    def restore(window):
        dispatch('xetalminimize:restoreall')
        wait(lambda:status()['active']==0)
        dispatch('focuswindow','address:'+window['address'])
    try:
        comp=spawn(['/usr/bin/Hyprland','-c',str(lua)],'compositor',env=env,start_new_session=True)
        endpoint=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None))
        env['HYPRLAND_INSTANCE_SIGNATURE']=endpoint.parent.name
        env['WAYLAND_DISPLAY']=str(wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None)))
        ctl('output','create','headless','BROWSER');dispatch('focusmonitor','BROWSER')
        display_file=root/'xdisplay'
        dispatch('exec','sh -c '+shlex.quote('printf "%s" "$DISPLAY" > '+shlex.quote(str(display_file))))
        wait(lambda:display_file.exists() and display_file.read_text())
        env['DISPLAY']=display_file.read_text()
        loaded=False
        for platform in ('wayland','x11'):
            dispatch('focusmonitor','BROWSER')
            profile=root/('brave-'+platform);profile.mkdir()
            child_env=dict(env,WAYLAND_DEBUG='1' if platform=='wayland' else '0')
            browser=spawn(['/usr/bin/brave','--user-data-dir='+str(profile),'--ozone-platform='+platform,
                '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--no-first-run',
                '--no-default-browser-check','--disable-background-networking','--disable-sync',
                '--disable-component-update','--disable-default-apps','--password-store=basic',
                '--window-size=1000,700','about:blank'],platform,env=child_env,start_new_session=True)
            port=wait(lambda:(profile/'DevToolsActivePort').read_text().splitlines() if (profile/'DevToolsActivePort').exists() else None,30)
            debugger=Browser('ws://127.0.0.1:'+port[0]+port[1])
            window=wait(lambda:next((w for w in clients() if 'brave' in w['class'].lower()),None),30)
            report[platform+'_client']=window
            if not loaded:
                assert ctl('plugin','load',str(binary))=='ok';loaded=True
            target=next(t for t in debugger.call('Target.getTargets')['targetInfos'] if t['type']=='page')
            window_id=debugger.call('Browser.getWindowForTarget',targetId=target['targetId'])['windowId']
            wait(lambda:configured(platform) and debugger.call('Browser.getWindowBounds',windowId=window_id)['bounds']['windowState']=='normal')
            # Client state requests also carry maximize/restore. Ensure the
            # minimize subscription leaves these core transitions intact.
            for cycle in range(2):
                for state,expected in (('maximized',1),('normal',0)):
                    debugger.call('Browser.setWindowBounds',windowId=window_id,bounds={'windowState':state})
                    matching=wait(lambda:configured(platform)
                        and debugger.call('Browser.getWindowBounds',windowId=window_id)['bounds']['windowState']==state
                        and next((w for w in clients() if w['address']==window['address']
                        and w['fullscreen']==expected and w['fullscreenClient']==expected),None),seconds=3,required=False)
                    check(platform+' Brave '+state+' '+str(cycle+1),matching,matching or clients())
            for cycle in range(2):
                debugger.call('Browser.setWindowBounds',windowId=window_id,bounds={'windowState':'normal'})
                dispatch('setfloating','address:'+window['address'])
                dispatch('resizewindowpixel','exact 1000 700,address:'+window['address'])
                dispatch('movewindowpixel','exact 200 80,address:'+window['address'])
                time.sleep(.4)
                debugger.call('Browser.setWindowBounds',windowId=window_id,bounds={'windowState':'minimized'})
                okay=wait(lambda:status()['active']==1,seconds=3,required=False)
                snapshot=status();check(platform+' Brave native minimize '+str(cycle+1),okay,snapshot)
                run('grim','-o','BROWSER',str(root/(platform+'-minimize-'+str(cycle)+'.png')))
                restore(window)
                restored=next((w for w in clients() if w['address']==window['address']),None)
                check(platform+' Brave restore '+str(cycle+1),restored and restored['mapped'] and not restored['workspace']['name'].startswith('special:'),restored)
            # New windows must be observed too, without reloading the plugin.
            new_target=debugger.call('Target.createTarget',url='about:blank',newWindow=True)['targetId']
            new_id=debugger.call('Browser.getWindowForTarget',targetId=new_target)['windowId']
            new_window=wait(lambda:next((w for w in clients() if 'brave' in w['class'].lower() and w['address']!=window['address']),None))
            time.sleep(.4)
            debugger.call('Browser.setWindowBounds',windowId=new_id,bounds={'windowState':'minimized'})
            check(platform+' newly opened Brave minimize',wait(lambda:status()['active']==1,seconds=3,required=False),status())
            assert ctl('plugin','unload',str(binary))=='ok';loaded=False
            check(platform+' unload restores all browser windows',all(not w['workspace']['name'].startswith('special:') for w in clients()))
            debugger.call('Browser.close');debugger.close();browser.wait(timeout=15)
            wait(lambda:not any('brave' in w['class'].lower() for w in clients()))
        report['passed']=all(c['passed'] for c in report['checks'])
    except BaseException:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        for stream in logs:stream.close()
        (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(('PASS' if report['passed'] else 'FAILED')+' — '+str(root/'result.json'),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
