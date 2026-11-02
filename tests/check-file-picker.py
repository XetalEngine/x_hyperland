#!/usr/bin/env python3
"""Exercise portal/Qt pickers and general size memory in a private compositor.

Usage: python3 tests/check-file-picker.py NEW_OUTPUT_DIRECTORY FILES_BUILD
No test input reaches the parent session; XWayland is disabled in the fixture.
"""
import json
import shutil
import http.server
import threading
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]


def main():
    root = Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=False)
    build = Path(sys.argv[2]).resolve()
    plugin = subprocess.check_output([sys.executable,str(REPO/'config/hypr/runtime/window_memory/build.py')],text=True).strip()
    for name, xml in [('pointer',REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
                      ('keyboard',REPO/'tests/native/virtual-keyboard-unstable-v1.xml')]:
        for mode,suffix in [('client-header','h'),('private-code','c')]:
            subprocess.run(['wayland-scanner',mode,str(xml),str(root/f'virtual-{name}.{suffix}')],check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True))
    subprocess.run(['cc','-I'+str(root),str(REPO/'tests/native/gesture-input.c'),str(root/'virtual-pointer.c'),
                    str(root/'virtual-keyboard.c'),'-o',str(root/'input'),*flags],check=True)
    runtime = Path(tempfile.mkdtemp(prefix='ft-'))
    home = root/'home';home.mkdir()
    profile = home/'.config/hypr'
    for part in ('theme', 'cursors', 'file_manager', 'desktop/data/xdg-desktop-portal', 'desktop/data/dbus-1'):
        shutil.copytree(REPO/'config/hypr'/part, profile/part, ignore=shutil.ignore_patterns('.build', '__pycache__', 'state', 'qt-settings'))
    (profile/'runtime').mkdir()
    shutil.copyfile(REPO/'config/hypr/runtime/command_paths.py', profile/'runtime/command_paths.py')
    (profile/'file_manager/.build').mkdir()
    shutil.copy2(build/'xetal-files', profile/'file_manager/.build/xetal-files')
    shutil.copyfile(profile/'desktop/data/xdg-desktop-portal/hyprland-portals.conf',
                    profile/'desktop/data/xdg-desktop-portal/portals/hyprland-portals.conf')
    shutil.copyfile('/usr/share/xdg-desktop-portal/portals/gtk.portal',
                    profile/'desktop/data/xdg-desktop-portal/portals/gtk.portal')
    (profile/'assets').mkdir()
    shutil.copyfile(REPO/'config/hypr/assets/fonts.conf', profile/'assets/fonts.conf')
    for path in (profile/'desktop/data/dbus-1').rglob('*.service'):
        path.write_text(path.read_text().replace('@HYPR@', str(profile)).replace('@HOME@', str(home)))
    parent = os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'): parent = str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=parent,
               XDG_CONFIG_HOME=str(home/'.config'), XDG_DATA_HOME=str(home/'.local/share'),
               XDG_CACHE_HOME=str(home/'.cache'), XDG_STATE_HOME=str(home/'.local/state'),
               AQ_BACKENDS='wayland', HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1',
               QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='', QT_PLUGIN_PATH='',
               QT_WAYLAND_DISABLE_WINDOWDECORATION='1', GSETTINGS_BACKEND='memory',
               XCURSOR_THEME='Adwaita', XCURSOR_SIZE='24',
               XETAL_FILES_ROOT=str(profile), XDG_CURRENT_DESKTOP='Hyprland', GTK_USE_PORTAL='1',
               XDG_DATA_DIRS=str(profile/'desktop/data')+':/usr/share',
               XDG_DESKTOP_PORTAL_DIR=str(profile/'desktop/data/xdg-desktop-portal/portals'))
    for key in ('HYPRLAND_INSTANCE_SIGNATURE','DISPLAY','DBUS_SESSION_BUS_ADDRESS'): env.pop(key,None)
    children=[];logs=[];input_process=None;results=[]
    def spawn(args,**kwargs):
        log=(root/f'process-{len(children)}.log').open('w');logs.append(log)
        process=subprocess.Popen(args,env=env,stdout=log,stderr=log,**kwargs);children.append(process);return process
    def ctl(*args):
        return subprocess.check_output(['hyprctl',*args],env=env,text=True,stderr=subprocess.STDOUT,timeout=10).strip()
    def dispatch(*args): assert ctl('dispatch',*args)=='ok',args
    def wait(predicate,label):
        for _ in range(100):
            if predicate(): return
            time.sleep(.05)
        (root/'failure-clients.json').write_text(ctl('-j','clients'))
        (root/'failure-monitors.json').write_text(ctl('-j','monitors'))
        raise AssertionError('Timed out: '+label)
    def client(): return next((c for c in json.loads(ctl('-j','clients')) if c['title']=='Text drag fixture'),None)
    def cursor(): return json.loads(ctl('xetal-cursor'))
    conf=root/'hyprland.conf'
    conf.write_text(f'''monitor=,1100x700@60,auto,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
animations:enabled=false
xwayland:enabled=false
bindm=SUPER,mouse:272,movewindow
bindn=,mouse:272,event,xetal-floating-drag-press
bindinr=,mouse:272,event,xetal-floating-drag-release
windowrule=match:tag ^xetal-title-drag$,no_anim on
plugin={plugin}
windowrule=match:class ^xetal-file-picker.*$,float on,center on
''')
    compositor=spawn(['Hyprland','--config',str(conf)],start_new_session=True)
    try:
        instance=None
        for _ in range(100):
            assert compositor.poll() is None,'Nested compositor exited'
            try: instances=json.loads(ctl('-j','instances'))
            except json.JSONDecodeError: instances=[]
            instance=next((i for i in instances if i['pid']==compositor.pid),None)
            if instance: break
            time.sleep(.1)
        assert instance
        env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket'])
        assert not ctl('configerrors'),ctl('configerrors')
        log=(root/'dbus.log').open('w');logs.append(log)
        bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],env=env,stdout=subprocess.PIPE,stderr=log,text=True)
        children.append(bus);env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
        assert env['DBUS_SESSION_BUS_ADDRESS'].startswith('unix:')
        monitor=json.loads(ctl('-j','monitors'))[0]
        input_process=subprocess.Popen([str(root/'input'),str(round(monitor['width']/monitor['scale'])),str(round(monitor['height']/monitor['scale']))],
                                       env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def gesture(command,delay=.1):
            input_process.stdin.write(command+'\n');input_process.stdin.flush()
            assert input_process.stdout.readline().strip()=='ok';time.sleep(delay)
        def key(code): gesture(f'key {code} 1', .02); gesture(f'key {code} 0')
        def clients(): return json.loads(ctl('-j', 'clients'))
        def find(app): return next((c for c in clients() if c['class'].startswith(app)), None)
        def record(name, **details):
            results.append(dict(check=name, **details))
            (root/'results.json').write_text(json.dumps(results, indent=2)+'\n')
        memory = spawn([sys.executable, str(REPO/'config/hypr/runtime/window_memory/service.py'), '--state', str(root/'windows.json')])
        fixture = root/'window.py'
        fixture.write_text('''from PyQt6.QtWidgets import QApplication,QWidget
import sys
app=QApplication([]);app.setDesktopFileName(sys.argv[1])
window=QWidget();window.setWindowTitle('Memory fixture');window.resize(600,400);window.show()
app.exec()
''')
        time.sleep(.6)
        regular = spawn([sys.executable, str(fixture), 'memory-fixture'])
        wait(lambda: find('memory-fixture'), 'ordinary window')
        time.sleep(.7)
        window = find('memory-fixture'); address = window['address']
        dispatch('setfloating', 'address:'+address)
        dispatch('resizewindowpixel', 'exact 700 480,address:'+address)
        time.sleep(1)
        record('initial resized window', client=find('memory-fixture'))
        dispatch('closewindow', 'address:'+address)
        regular.wait(timeout=5)
        time.sleep(.4)
        regular = spawn([sys.executable, str(fixture), 'memory-fixture'])
        wait(lambda: find('memory-fixture') and find('memory-fixture')['floating'] and find('memory-fixture')['size']==[700,480], 'restored floating size')
        record('floating reopen', size=find('memory-fixture')['size'])
        address = find('memory-fixture')['address']
        assert ctl('xetal-window-state', address, '1', '1') == 'ok'
        time.sleep(1)
        dispatch('closewindow', 'address:'+address); regular.wait(timeout=5); time.sleep(.4)
        regular = spawn([sys.executable, str(fixture), 'memory-fixture'])
        wait(lambda: find('memory-fixture') and find('memory-fixture')['fullscreen']==1, 'maximized restoration')
        record('maximized reopen', fullscreen=find('memory-fixture')['fullscreen'])
        address = find('memory-fixture')['address']
        assert ctl('xetal-window-state', address, '0', '0') == 'ok'
        wait(lambda: find('memory-fixture')['size']==[700,480], 'normal size after unmaximize')
        dispatch('settiled','address:'+address);time.sleep(1)
        dispatch('closewindow', 'address:'+address);regular.wait(timeout=5);time.sleep(.4)
        regular=spawn([sys.executable,str(fixture),'memory-fixture'])
        wait(lambda:find('memory-fixture') and not find('memory-fixture')['floating'] and not find('memory-fixture')['fullscreen'], 'tiled restoration')
        time.sleep(1)
        assert not find('memory-fixture')['floating'] and not find('memory-fixture')['fullscreen']
        record('tiled reopen',size=find('memory-fixture')['size'])
        dispatch('closewindow','address:'+find('memory-fixture')['address']);regular.wait(timeout=5)
        assert memory.poll() is None, 'Memory service stopped'
        # Let D-Bus activate the backend from the profile's service definition.
        client_script = root/'request.py'
        client_script.write_text('''import json,sys
from pathlib import Path
from gi.repository import Gio,GLib
root=Path(sys.argv[1]);mode=sys.argv[2];name=sys.argv[3]
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);loop=GLib.MainLoop()
def response(_bus,_sender,_path,_interface,_signal,parameters):
    (root/(name+'.json')).write_text(json.dumps(parameters.unpack()));loop.quit()
bus.signal_subscribe(None,'org.freedesktop.portal.Request','Response',None,None,Gio.DBusSignalFlags.NONE,response)
options={'handle_token':GLib.Variant('s','test_'+name),'current_folder':GLib.Variant('ay',bytes(str(root/'files'),'utf8')+b'\\0'),
         'current_name':GLib.Variant('s','sample'), 'filters':GLib.Variant('a(sa(us))',[('Text files',[(0,'*.txt')])])}
handle=bus.call_sync('org.freedesktop.portal.Desktop','/org/freedesktop/portal/desktop','org.freedesktop.portal.FileChooser',mode,
                    GLib.Variant('(ssa{sv})',('', 'Fusion picker test', options)),GLib.VariantType.new('(o)'),Gio.DBusCallFlags.NONE,15000,None).unpack()[0]
(root/(name+'.handle')).write_text(handle)
GLib.timeout_add_seconds(25,lambda:(loop.quit(),False)[1]);loop.run()
''')
        (root/'files').mkdir();(root/'files/existing.txt').write_text('Test file; stays local.\n')
        time.sleep(1)
        caller = spawn([sys.executable,str(client_script),str(root),'SaveFile','save'])
        wait(lambda: find('xetal-file-picker'), 'portal Fusion picker')
        picker = find('xetal-file-picker'); assert picker['floating']
        address = picker['address'];dispatch('resizewindowpixel','exact 980 620,address:'+address)
        time.sleep(1)
        subprocess.run(['grim',str(root/'picker.png')],env=env,check=True)
        dispatch('focuswindow', 'address:'+address);key(28)
        wait(lambda:(root/'save.json').exists(),'portal save response')
        response=json.loads((root/'save.json').read_text());assert response[0]==0,response
        assert response[1]['uris']==[(root/'files/sample.txt').as_uri()],response
        record('portal save and extension', response=response)
        caller.wait(timeout=5);time.sleep(.4)
        caller=spawn([sys.executable,str(client_script),str(root),'SaveFile','reopen'])
        wait(lambda:find('xetal-file-picker') and find('xetal-file-picker')['size']==[980,620], 'picker restored size')
        record('picker size and floating mode', size=find('xetal-file-picker')['size'],floating=find('xetal-file-picker')['floating'])
        dispatch('focuswindow','address:'+find('xetal-file-picker')['address']);key(1)
        wait(lambda:(root/'reopen.json').exists(),'cancel response')
        assert json.loads((root/'reopen.json').read_text())[0]==1
        record('portal cancel')
        caller.wait(timeout=5);time.sleep(.3)
        caller=spawn([sys.executable,str(client_script),str(root),'OpenFile','abandon'])
        wait(lambda:find('xetal-file-picker'),'requester lifetime picker')
        caller.terminate();caller.wait(timeout=5)
        wait(lambda:not find('xetal-file-picker'),'request cancellation on application exit')
        record('caller exit closes only its picker')
        # The profile-local native Qt integration also works without a portal
        # restart, including applications using synchronous QFileDialog APIs.
        qt_fixture=root/'qt-picker.py'
        qt_fixture.write_text('''from PyQt6.QtWidgets import QApplication,QFileDialog
from pathlib import Path
import sys,json
app=QApplication([]);app.setApplicationName('Qt picker fixture')
value=QFileDialog.getOpenFileName(None,'Open in Qt',str(Path(sys.argv[1])/'files/existing.txt'),'Text files (*.txt)')
(Path(sys.argv[1])/'qt-result.json').write_text(json.dumps(value))
''')
        qt_env=dict(env,QT_QPA_PLATFORMTHEME='xetal',QT_PLUGIN_PATH=str(profile/'theme/qt6'),XETAL_THEME_CONFIG=str(profile/'theme/state.json'))
        qt_log=(root/'qt.log').open('w');logs.append(qt_log)
        qt=subprocess.Popen([sys.executable,str(qt_fixture),str(root)],env=qt_env,stdout=qt_log,stderr=qt_log);children.append(qt)
        wait(lambda:find('xetal-file-picker'), 'Qt Fusion picker')
        dispatch('focuswindow','address:'+find('xetal-file-picker')['address']);key(28)
        wait(lambda:(root/'qt-result.json').exists(),'Qt selected result')
        assert json.loads((root/'qt-result.json').read_text())[0]==str(root/'files/existing.txt')
        record('native Qt open')
        qt.wait(timeout=5)
        received=[]
        class Page(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                data=b'''<title>Fusion portal upload check</title><input id="pick" type="file" autofocus><script>
                pick.onchange=async()=>{let f=pick.files[0];await fetch('/result',{method:'POST',body:JSON.stringify({name:f.name,text:await f.text()})});};
                pick.focus();fetch('/ready',{method:'POST',body:'{}'});</script>'''
                self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(data)
            def do_POST(self):
                value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append((self.path,value));self.send_response(200);self.end_headers()
            def log_message(self,*_): pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Page)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        browser=shutil.which('google-chrome-stable') or shutil.which('chromium')
        assert browser,'Chrome/Chromium required for the real portal test'
        chrome=spawn([browser,'--user-data-dir='+str(root/'chrome'),'--ozone-platform=wayland',
                      '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-gpu',
                      '--password-store=basic','--use-mock-keychain',
                      f'http://127.0.0.1:{server.server_port}/'])
        wait(lambda:any(path=='/ready' for path,_ in received),'Chrome local fixture')
        wait(lambda:any('Fusion portal upload check' in c['title'] for c in clients()),'Chrome mapped page')
        browser_window=next(c for c in clients() if 'Fusion portal upload check' in c['title'])
        dispatch('focuswindow','address:'+browser_window['address']);key(28)
        wait(lambda:find('xetal-file-picker'),'Chrome Fusion picker')
        assert find('xetal-file-picker')['floating']
        dispatch('focuswindow','address:'+find('xetal-file-picker')['address'])
        clipboard=spawn(['wl-copy','--foreground','--type','text/plain'],stdin=subprocess.PIPE)
        clipboard.stdin.write(str(root/'files/existing.txt').encode());clipboard.stdin.close();time.sleep(.2)
        gesture('key 56 1');key(49);gesture('key 56 0') # Alt+N: file name.
        gesture('key 29 1');key(30);key(47);gesture('key 29 0');key(28)
        wait(lambda:any(path=='/result' for path,_ in received),'Chrome upload result')
        result=next(value for path,value in received if path=='/result')
        assert result==dict(name='existing.txt',text='Test file; stays local.\n'),result
        record('Chrome file input uses Fusion picker',result=result)
        server.shutdown();server.server_close()
        print(json.dumps(results,indent=2),flush=True)
    finally:
        if input_process:
            try:input_process.communicate('quit\n',timeout=2)
            except (BrokenPipeError,subprocess.TimeoutExpired):input_process.kill();input_process.wait()
        for process in reversed(children):
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        # Only descendants carrying this unique disposable runtime may remain.
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():continue
            try:
                if ('XDG_RUNTIME_DIR='+str(runtime)).encode() in (entry/'environ').read_bytes().split(b'\0'):
                    os.kill(int(entry.name),signal.SIGTERM)
            except (OSError,ProcessLookupError):pass
        for log in logs:log.close()


if __name__=='__main__':main()
