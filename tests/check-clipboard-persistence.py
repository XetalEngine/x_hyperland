#!/usr/bin/python3
"""Copy/close/paste on a disposable compositor; never reads the real clipboard.

Usage: check-clipboard-persistence.py OUTPUT_DIRECTORY
Requires a graphical terminal for a private nested Wayland compositor.
"""
from nested_session import nested_environment, assert_seat_isolated
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import traceback

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'config/hypr'), str(REPO/'config/hypr/compat')]
from clipboard.build import build
import hypr_compat


def main():
    root = Path(sys.argv[1]).resolve(); root.mkdir(parents=True, exist_ok=False)
    home = root/'home'; home.mkdir()
    runtime = Path(tempfile.mkdtemp(prefix='clip-', dir='/tmp'))
    (root/'run').symlink_to(runtime, target_is_directory=True)
    report = {'passed':False, 'checks':[], 'runtime':str(runtime)}
    (root/'hyprland.conf').write_text('''monitor = ,1000x700@60,auto,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
misc:disable_hyprland_guiutils_check = true
animations:enabled = false
debug:disable_logs = false
debug:enable_stdout_logs = true
''')
    lua = root/'hyprland.lua'; lua.write_text(hypr_compat.Renderer(root).render())
    parent = Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute(): parent = Path(os.environ['XDG_RUNTIME_DIR'])/parent
    env = nested_environment({k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_INSTANCE', 'XETAL_'))})
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home/'.config'), XDG_CACHE_HOME=str(home/'.cache'),
        XDG_STATE_HOME=str(home/'.local/state'), XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=str(parent),
        AQ_BACKENDS='wayland', HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1',
        QT_QPA_PLATFORMTHEME='', QT_QPA_PLATFORM='wayland', PATH='/usr/bin:/bin')
    env.pop('DBUS_SESSION_BUS_ADDRESS',None); env.pop('DISPLAY',None)
    children=[]; logs=[]; comp=None; sequence=0

    def spawn(args, label, child_env=None):
        log=(root/(label+'.log')).open('w'); logs.append(log)
        child=subprocess.Popen(args, env=child_env or env, stdout=log, stderr=log, start_new_session=True)
        children.append(child); return child
    def wait(predicate, seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if comp is not None and comp.poll() is not None: raise RuntimeError('Test compositor exited; see compositor.log')
            result=predicate()
            if result:return result
            time.sleep(.05)
        raise RuntimeError('Timed out waiting for the isolated clipboard test')
    def run(*args):
        result=subprocess.run(args,env=env,capture_output=True,timeout=5)
        if result.returncode:raise RuntimeError(str(args)+': '+result.stderr.decode(errors='replace'))
        return result.stdout
    def ctl(*args):return run('/usr/bin/hyprctl',*args).decode().strip()
    def types():
        result=subprocess.run(['wl-paste','--list-types'],env=env,capture_output=True,text=True,timeout=2)
        return result.stdout.splitlines() if result.returncode==0 else []
    def owned():return any(m.startswith('application/x-fusion-clipboard-') for m in types())
    def get(mime):return run('wl-paste','--no-newline','--type',mime)
    def stop(child):
        if child.poll() is None:child.terminate();child.wait(timeout=5)
    def check(name, okay):
        report['checks'].append({'name':name,'passed':bool(okay)})
        print(('PASS ' if okay else 'FAIL ')+name,flush=True)
        if not okay:raise RuntimeError(name)
    def source(data, platform='wayland'):
        nonlocal sequence
        sequence+=1; path=root/f'copy-{sequence}.json'
        data={**data,'application/x-fusion-test-sequence':str(sequence).encode()}
        path.write_text(json.dumps({mime:base64.b64encode(value).decode() for mime,value in data.items()}))
        child=spawn([sys.executable,str(REPO/'tests/clipboard/source.py'),str(path)],f'source-{sequence}',dict(env,QT_QPA_PLATFORM=platform))
        wait(lambda:path.with_suffix('.ready').exists())
        wait(lambda:set(data)<=set(types()))
        wait(lambda:get('application/x-fusion-test-sequence')==str(sequence).encode())
        return child

    try:
        keeper=build().with_name('fusion-clipboard-keeper')
        comp=spawn(['/usr/bin/Hyprland','-c',str(lua)],'compositor')
        endpoint=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None),20)
        env['HYPRLAND_INSTANCE_SIGNATURE']=endpoint.parent.name
        env['WAYLAND_DISPLAY']=str(wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None)))
        assert_seat_isolated(comp.pid,root/'compositor.log')
        check('compositor has no physical login seat or input devices',True)
        xdisplay=root/'xdisplay'
        ctl('dispatch',hypr_compat.dispatcher('exec','sh -c '+shlex.quote('printf "%s" "$DISPLAY" > '+shlex.quote(str(xdisplay)))))
        wait(lambda:xdisplay.exists() and xdisplay.read_text());env['DISPLAY']=xdisplay.read_text()
        text='https://example.org/café?one=1&two=2'.encode()
        original=source({'text/plain':text})
        check('baseline copy is available',get('text/plain')==text)
        stop(original);wait(lambda:not types())
        check('baseline source exit loses clipboard',not types())
        process=spawn([str(keeper)],'keeper');time.sleep(.2)
        check('keeper starts',process.poll() is None)
        for platform in ('wayland','xcb'):
            data={'text/plain':text,'text/html':b'<b>preserved formatting</b>'}
            original=source(data,platform);wait(owned)
            # XWayland maps legacy STRING to text/plain (Latin-1). Prefer its
            # separately advertised UTF-8 format and preserve both byte streams.
            preferred='text/plain;charset=utf-8' if 'text/plain;charset=utf-8' in types() else 'text/plain'
            before=get(preferred);plain_before=get('text/plain');html_before=get('text/html')
            check(platform+' Unicode source text is intact',before==text)
            stop(original)
            check(platform+' URL survives closing source',get(preferred)==text)
            check(platform+' legacy text bytes are preserved',get('text/plain')==plain_before)
            check(platform+' rich text survives closing source',get('text/html')==html_before==data['text/html'])
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jJ0sAAAAASUVORK5CYII=')
        original=source({'image/png':image});wait(owned);stop(original)
        check('image bytes survive closing source',get('image/png')==image)
        original=source({'text/plain':b'A'*200000});wait(owned)
        stop(original);check('large paste completes without truncation',get('text/plain')==b'A'*200000)
        old=source({'text/plain':b'older'});wait(owned)
        newer=source({'text/plain':b'newer'});wait(lambda:owned() and get('text/plain')==b'newer')
        stop(old);check('closing old source cannot replace newer copy',get('text/plain')==b'newer')
        duplicate=spawn([str(keeper)],'duplicate');duplicate.wait(timeout=3)
        check('duplicate keeper leaves the active clipboard alone',duplicate.returncode==0 and get('text/plain')==b'newer')
        run('wl-copy','--clear');time.sleep(.3)
        check('explicit clear stays empty',not types())
        stop(newer)
        for hint in ('x-kde-passwordManagerHint','application/x-keepassxc','text/uri-list','application/x-kde-cutselection'):
            original=source({'text/plain':b'synthetic excluded data',hint:b'1'})
            time.sleep(.35);check(hint+' is not retained',not owned())
            stop(original);wait(lambda:not types())
        original=source({'text/plain':b'x'*(1024*1024+1)})
        time.sleep(.4);check('oversized copy keeps its original owner',not owned())
        stop(original);wait(lambda:not types())
        check('keeper remains responsive',process.poll() is None)
        report['passed']=True
    except BaseException:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        for child in reversed(children):
            if child is comp:continue
            try:stop(child)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        if comp is not None and comp.poll() is None:
            try:ctl('dispatch',hypr_compat.dispatcher('exit'));comp.wait(timeout=5)
            except Exception:comp.kill();comp.wait()
        for log in logs:log.close()
        (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(('PASS' if report['passed'] else 'FAILED')+' — '+str(root/'result.json'),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
