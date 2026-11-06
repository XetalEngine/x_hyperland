#!/usr/bin/env python3
"""Real Firefox child-surface pixels and input in an isolated compositor.

Usage: dbus-run-session -- python3 tests/check-firefox-geometry.py MEMORY_SO MINIMIZE_SO OUTPUT_DIR
Requires Firefox, a parent Wayland session, grim, Pillow and the Wayland C tools.
Uses only a fresh browser profile and a local test page. Never loads plugins or
sends pointer input into the parent session.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from effects.minimize import model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('memory', type=Path)
    parser.add_argument('minimize', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    binaries = [args.memory.resolve(strict=True), args.minimize.resolve(strict=True)]
    root = args.output.resolve();root.mkdir(parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix='fg-'))  # Unix socket path length.
    (root/'runtime-path').write_text(str(runtime))
    (root/'minimize.conf').write_text(model.encode(model.DEFAULTS))
    profile = root/'profile';profile.mkdir()
    (profile/'user.js').write_text('''user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.newtabpage.enabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("browser.tabs.inTitlebar", 1);
user_pref("layout.css.devPixelsPerPx", "-1.0");
''')
    page = root/'geometry.html'
    page.write_text('''<!doctype html><meta charset="utf-8"><title>Geometry ready</title>
<style>html,body {margin:0;height:100%;background:rgb(24,76,104);overflow:hidden}
#patch {position:fixed;left:2px;bottom:140px;width:8px;height:8px;background:rgb(24,76,104)}
</style><div id="patch"></div><script>
let points=[];
function point(e) { return [Math.round(e.clientX),Math.round(innerHeight-e.clientY),e.buttons]; }
addEventListener('pointerdown',e=>{points=[point(e)];});
addEventListener('pointermove',e=>{if(e.buttons) points.push(point(e));});
addEventListener('pointerup',e=>{
 points.push(point(e));
 document.getElementById('patch').style.background='rgb(239,89,37)';
 document.title='Geometry '+JSON.stringify(points);
});
</script>''')
    conf = root/'hyprland.conf'
    conf.write_text('''monitor = ,1280x800@60,auto,1
misc {
 disable_hyprland_logo = true
 disable_splash_rendering = true
 background_color = rgb(111111)
}
general {
 gaps_in = 8
 gaps_out = 30
 border_size = 2
 col.active_border = rgb(00ffff)
}
decoration {
 rounding = 8
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
}
''')
    protocol = REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'
    subprocess.run(['wayland-scanner','client-header',str(protocol),str(root/'virtual-pointer.h')],check=True)
    subprocess.run(['wayland-scanner','private-code',str(protocol),str(root/'virtual-pointer.c')],check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True))
    pointer = root/'pointer'
    subprocess.run(['cc','-I'+str(root),str(REPO/'tests/minimize/pointer.c'),str(root/'virtual-pointer.c'),'-o',str(pointer),*flags],check=True)
    parent = os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'):parent = str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=parent,
               GSETTINGS_BACKEND='memory', XETAL_MINIMIZE_CONFIG=str(root/'minimize.conf'),
               XETAL_WORKSPACE_RULES=str(root/'workspace-rules.json'))
    env.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
    children = [];logs = []

    def spawn(command, name, **kwargs):
        stream = (root/name).open('w');logs.append(stream)
        process = subprocess.Popen(command,stdout=stream,stderr=stream,start_new_session=True,**kwargs)
        children.append(process);return process

    def run(*command):
        result = subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
        if result.returncode:raise RuntimeError(str(command)+result.stdout+result.stderr)
        return result.stdout.strip()

    def ctl(*command):return run('hyprctl',*command)

    def wait(predicate, seconds=20):
        deadline = time.monotonic()+seconds
        while time.monotonic()<deadline:
            value = predicate()
            if value:return value
            time.sleep(.04)
        raise AssertionError('Timed out waiting for Firefox geometry/input')

    def clients():return json.loads(ctl('-j','clients'))
    def client():return next(c for c in clients() if c['class'].lower()=='firefox')

    def check(name):
        time.sleep(.8)
        window = client();monitor = json.loads(ctl('-j','monitors'))[0]
        x,y = window['at'];width,height = window['size'];scale = monitor['scale']
        logical_width = round(monitor['width']/scale);logical_height = round(monitor['height']/scale)
        screenshot = root/(name+'.png');run('grim',str(screenshot))
        pixels = Image.open(screenshot).convert('RGB')
        # The page must reach both inner edges of the frame, without a shadow
        # gap on the left or content clipped at the right/bottom.
        for px,py in ((x+4,y+height-40),(x+width-5,y+height-40),(x+width/2,y+height-4)):
            actual = pixels.getpixel((round(px*scale),round(py*scale)))
            assert max(abs(a-b) for a,b in zip(actual,(24,76,104)))<=2,(name,(px,py),actual)
        for kind,dx,dy in (('click',0,0),('drag',12,8)):
            previous = client()['title']
            run(str(pointer),str(x+60),str(y+height-80),str(logical_width),str(logical_height),kind)
            title = wait(lambda:client()['title'] if client()['title']!=previous else None)
            match = re.search(r'Geometry (\[.*\])',title);assert match,(name,title)
            points = json.loads(match[1])
            expected = [(60,80,1),(60+dx,80-dy,0)]
            for actual,wanted in zip((points[0],points[-1]),expected):
                assert all(abs(a-b)<=1 for a,b in zip(actual,wanted)),(name,kind,points)
            if kind=='drag':
                assert any(p[2]==1 and abs(p[0]-72)<=1 and abs(p[1]-72)<=1 for p in points[1:]),(name,points)
        # Updating a small patch at the left edge must damage its corrected
        # position, too; a full repaint alone would hide this class of bug.
        run('grim',str(root/(name+'-damage.png')))
        pixels = Image.open(root/(name+'-damage.png')).convert('RGB')
        color = pixels.getpixel((round((x+6)*scale),round((y+height-144)*scale)))
        assert max(abs(a-b) for a,b in zip(color,(239,89,37)))<=2,(name,'damage',color)
        print(name+': frame edges, click, held drag and redraw passed',flush=True)

    try:
        compositor = spawn(['Hyprland','-c',str(conf)],'compositor.log',env=env)
        def connected():
            assert compositor.poll() is None,'Nested compositor exited'
            try:instances = json.loads(run('hyprctl','-j','instances'))
            except json.JSONDecodeError:return None
            return next((i for i in instances if i['pid']==compositor.pid and (runtime/'hypr'/i['instance']/'.socket.sock').exists()),None)
        instance = wait(connected)
        env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket'])
        time.sleep(1)
        # Parent mouse movement must not interfere with held-pointer checks.
        for group in ('mice','keyboards'):
            for device in json.loads(ctl('-j','devices'))[group]:
                assert ctl('keyword',f'device[{device["name"]}]:enabled','false')=='ok'
        for binary in binaries:
            answer = ctl('plugin','load',str(binary));assert answer=='ok',(binary,answer)
        firefox_env = dict(env,MOZ_ENABLE_WAYLAND='1',GDK_BACKEND='wayland',WAYLAND_DEBUG='1')
        spawn(['firefox','--no-remote','--profile',str(profile),'--new-window',page.as_uri()],'firefox.log',env=firefox_env)
        wait(lambda:any('Geometry ready' in c['title'] for c in clients()),40)
        address = client()['address']
        output = json.loads(ctl('-j','monitors'))[0]['name']
        for scale in (1,1.25):
            assert ctl('keyword','monitor',f'{output},1280x800@60,auto,{scale}')=='ok'
            for mode in ('tiled','floating','maximized','restored'):
                if mode=='tiled':ctl('dispatch','settiled','address:'+address)
                elif mode=='floating':
                    ctl('dispatch','setfloating','address:'+address)
                    ctl('dispatch','resizewindowpixel','exact 700 460,address:'+address)
                    ctl('dispatch','movewindowpixel','exact 70 80,address:'+address)
                else:
                    # Use Firefox's own maximize/restore button: this exercises
                    # xdg requests and the client's changing shadow padding.
                    window = client();monitor = json.loads(ctl('-j','monitors'))[0]
                    x,y = window['at'];width,height = window['size']
                    run(str(pointer),str(x+width-60),str(y+18),
                        str(round(monitor['width']/scale)),str(round(monitor['height']/scale)),'click')
                    wait(lambda:client()['fullscreen']==(1 if mode=='maximized' else 0))
                check(f'{scale}-{mode}')
            assert ctl('dispatch','xetalminimize:minimize','address:'+address)=='ok'
            wait(lambda:json.loads(ctl('xetal-minimize'))['active']==1)
            assert ctl('dispatch','focuswindow','address:'+address)=='ok'
            wait(lambda:json.loads(ctl('xetal-minimize'))['active']==0)
            check(f'{scale}-dock-restored')
        print('PASS',flush=True)
    finally:
        for process in reversed(children):
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        for stream in logs:stream.close()


if __name__=='__main__':main()
