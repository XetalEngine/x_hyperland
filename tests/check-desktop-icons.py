#!/usr/bin/env python3
"""Real desktop-layer input in a disposable Hyprland, private HOME and bus.

Usage: python3 tests/check-desktop-icons.py NEW_OUTPUT_DIRECTORY FILES_BUILD [--menus-only | --drag-actions-only | --drag-refresh-only]
Only virtual input in the nested compositor is used; no personal files change.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO/'config/hypr'


def main():
    root = Path(sys.argv[1]).resolve(); root.mkdir(parents=True, exist_ok=False)
    build = Path(sys.argv[2]).resolve()
    home = root/'home'; desktop = home/'Desktop'; desktop.mkdir(parents=True)
    (desktop/'A folder').mkdir()
    for index in range(7): (desktop/f'{index+1} notes # café.txt').write_text(f'fixture {index}\n')
    (desktop/'.hidden').write_text('hidden')
    profile = home/'.config/hypr'; profile.mkdir(parents=True)
    # KIO may activate KDE's first-run helper on its private bus during a
    # transfer. Mark that tour seen only in the fixture so it cannot cover icons.
    if shutil.which('plasma-welcome'):
        version = subprocess.check_output(['plasma-welcome', '--version'], text=True,
            env=dict(os.environ, QT_QPA_PLATFORM='offscreen')).strip().split()[-1]
        (home/'.config/plasma-welcomerc').write_text('[General]\nLastSeenVersion='+version+'\n')
    for name in ('desktop_menu', 'file_manager', 'theme', 'icon_themes'):
        shutil.copytree(SOURCE/name, profile/name, ignore=shutil.ignore_patterns('.build', '__pycache__', 'state', 'automount.json', 'generated', 'backups'))
    (profile/'desktop_menu/icons.json').unlink(missing_ok=True)
    for name in ('control_center', 'control_panel', 'cursors', 'compat', 'runtime', 'desktop', 'assets'):
        (profile/name).symlink_to(SOURCE/name)
    shutil.copy2(SOURCE/'keybindings.conf', profile/'keybindings.conf')
    (profile/'hyprland.conf').write_text('source = '+str(profile/'keybindings.conf')+'\n')
    (profile/'file_manager/.build').mkdir(); shutil.copy2(build/'xetal-files', profile/'file_manager/.build/xetal-files')
    (profile/'scripts').mkdir()
    launcher = profile/'scripts/files.sh'
    launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(profile/'file_manager/.build/xetal-files'))+' "$@"\n')
    launcher.chmod(0o700)
    commands = root/'commands'; commands.mkdir()
    (commands/'lsblk').write_text('#!/bin/sh\nprintf \'{"blockdevices":[]}\\n\'\n')
    (commands/'lsblk').chmod(0o700)
    runtime = Path(tempfile.mkdtemp(prefix='fi-'))
    parent = os.environ['WAYLAND_DISPLAY']
    if not parent.startswith('/'): parent = str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
    env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=parent,
        XDG_CONFIG_HOME=str(home/'.config'), XDG_DATA_HOME=str(home/'.local/share'),
        XDG_CACHE_HOME=str(home/'.cache'), XDG_STATE_HOME=str(home/'.local/state'),
        AQ_BACKENDS='wayland', HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1',
        QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='', QT_PLUGIN_PATH='',
        QT_WAYLAND_DISABLE_WINDOWDECORATION='1', GSETTINGS_BACKEND='memory', NO_AT_BRIDGE='1',
        XETAL_FILES_ROOT=str(profile), XDG_CURRENT_DESKTOP='Hyprland',
        PATH=str(commands)+os.pathsep+os.environ['PATH'], PYTHONWARNINGS='ignore::DeprecationWarning')
    for key in ('HYPRLAND_INSTANCE_SIGNATURE', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'GTK3_MODULES'):
        env.pop(key, None)
    for name, xml in [('pointer', REPO/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),
                      ('keyboard', REPO/'tests/native/virtual-keyboard-unstable-v1.xml')]:
        for mode, suffix in [('client-header', 'h'), ('private-code', 'c')]:
            subprocess.run(['wayland-scanner', mode, str(xml), str(root/f'virtual-{name}.{suffix}')], check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'wayland-client', 'xkbcommon'], text=True))
    subprocess.run(['cc', '-I'+str(root), str(REPO/'tests/native/gesture-input.c'),
        str(root/'virtual-pointer.c'), str(root/'virtual-keyboard.c'), '-o', str(root/'input'), *flags], check=True)
    processes, logs = [], []
    def spawn(args, **options):
        log = (root/f'process-{len(processes)}.log').open('w'); logs.append(log)
        process = subprocess.Popen(args, env=env, stdout=log, stderr=log, **options)
        processes.append(process); return process
    def run(*args):
        return subprocess.check_output(args, env=env, text=True, stderr=subprocess.STDOUT, timeout=10).strip()
    def ctl(*args): return run('hyprctl', *args)
    def wait(predicate, label):
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(.05)
        raise AssertionError('Timed out: '+label)
    report = root/'state.json'
    def state():
        try: return json.loads(report.read_text())
        except (FileNotFoundError, ValueError): return {}
    fixture = root/'desktop.py'
    fixture.write_text('''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import app
from gi.repository import GLib,Gtk,Gdk
from desktop_icons import Canvas,Tile
from desktop_clipboard import Clipboard
report=Path(sys.argv[2])
def trace(kind,**values):
 with report.with_suffix('.input.jsonl').open('a') as stream:stream.write(json.dumps(dict(kind=kind,**values))+'\\n')
motion=Canvas.drag_motion
def drag_motion(self,widget,context,x,y,timestamp):
 result=motion(self,widget,context,x,y,timestamp)
 trace('motion',modifiers=int(Gdk.Keymap.get_for_display(self.get_display()).get_modifier_state()),
       suggested=int(context.get_suggested_action()),selected=int(context.get_selected_action()),
       accepted=int(self.drop_action),actions=int(context.get_actions()))
 return result
Canvas.drag_motion=drag_motion
pressed=Tile.pressed
def tile_pressed(self,widget,event):
 trace('press',name=self.name,modifiers=int(event.state));return pressed(self,widget,event)
Tile.pressed=tile_pressed
tile_motion=Tile.motion
def source_motion(self,widget,event):
 was_dragging=bool(self.canvas.controller.drag)
 result=tile_motion(self,widget,event)
 if not was_dragging and self.canvas.controller.drag:trace('drag-start',name=self.name)
 return result
Tile.motion=source_motion
tile_end=Tile.drag_end
def source_end(self,*args):
 trace('drag-end',name=self.name);return tile_end(self,*args)
Tile.drag_end=source_end
received=Canvas.received
def data_received(self,widget,context,x,y,data,info,timestamp):
 trace('drop',selected=int(context.get_selected_action()),operation=int(self.drop_operation),info=info,
       destination=self.destination(x,y),payload=bytes(data.get_data()).decode('utf-8',errors='replace') if data is not None and data.get_length()>0 else '')
 return received(self,widget,context,x,y,data,info,timestamp)
Canvas.received=data_received
canvas_pressed=Canvas.pressed
def background_pressed(self,widget,event):
 trace('background',x=event.x,y=event.y);return canvas_pressed(self,widget,event)
Canvas.pressed=background_pressed
canvas_key=Canvas.key
def key_pressed(self,widget,event):
 trace('key',key=Gdk.keyval_name(event.keyval),modifiers=int(event.state));return canvas_key(self,widget,event)
Canvas.key=key_pressed
clipboard_read=Clipboard.read
def read_clipboard(self,callback):
 trace('clipboard-request',generation=self.generation,owned=self.owned)
 def received(*values):
  trace('clipboard',values=values);callback(*values)
 return clipboard_read(self,received)
Clipboard.read=read_clipboard
def labels(widget):
 if isinstance(widget,Gtk.Label):return [widget.get_text()]
 if isinstance(widget,Gtk.Container):return [label for child in widget.get_children() for label in labels(child)]
 return []
class Desktop(app.Desktop):
 def __init__(self,display):
  super().__init__(display);self.report_timer=GLib.timeout_add(60,self.report)
 def report(self):
  surfaces=[];menus=[]
  for surface,canvas in self.icons.canvases.items():
   geometry=surface.desktop_monitor.get_geometry()
   surfaces.append(dict(monitor=canvas.monitor,positions=canvas.positions,area=self.icons.areas.get(canvas.monitor),
       allocation=[surface.get_allocated_width(),surface.get_allocated_height()],
       geometry=[geometry.x,geometry.y,geometry.width,geometry.height],scale=surface.get_scale_factor()))
   menu=surface.menu
   while menu and menu.get_visible():
    selected=menu.get_selected_item();menus.append(dict(labels=labels(menu),selected=labels(selected) if selected else [],
        height=menu.get_allocated_height(),popup_height=menu.get_toplevel().get_allocated_height(),
        preferred_height=menu.get_preferred_height()[1]))
    menu=selected.get_submenu() if selected else None
  editors={name:tile.editor.get_text() for canvas in self.icons.canvases.values() for name,tile in canvas.tiles.items() if tile.editor}
  data=dict(settings=self.icons.settings,surfaces=surfaces,menus=menus,selected=list(self.icons.selected),editors=editors,
      flights=sum(len(layer.batches) for layer in self.icons.flights.values()),trash_full=self.icons.trash_full)
  temporary=report.with_suffix('.tmp');temporary.write_text(json.dumps(data));temporary.replace(report)
  return True
 def dispose(self):
  GLib.source_remove(self.report_timer);super().dispose()
app.Desktop=Desktop
raise SystemExit(app.main())
''')
    conf = root/'hyprland.conf'
    conf.write_text('''monitor=,1100x760@60,auto,1
misc:disable_hyprland_logo=true
misc:disable_splash_rendering=true
misc:disable_hyprland_guiutils_check=true
animations:enabled=false
xwayland:enabled=false
general:layout=dwindle
windowrule=match:class ^xetal-files-external$,float on,center on
''')
    compositor = spawn(['Hyprland', '--config', str(conf)], start_new_session=True)
    input_process = None
    try:
        instance = None
        for _ in range(120):
            assert compositor.poll() is None, 'Nested compositor exited'
            try: instances = json.loads(ctl('-j', 'instances'))
            except (ValueError, subprocess.CalledProcessError): instances = []
            instance = next((item for item in instances if item['pid'] == compositor.pid), None)
            if instance: break
            time.sleep(.1)
        assert instance
        # The host tiler can resize its nested compositor window between
        # gestures. Fix only our own host window's size before creating icons.
        if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
            parent_clients=json.loads(subprocess.check_output(['hyprctl','-j','clients'],text=True))
            for owned in parent_clients:
                if owned.get('pid')==compositor.pid:
                    address='address:'+owned['address']
                    subprocess.run(['hyprctl','dispatch','setfloating',address],check=True,stdout=subprocess.DEVNULL)
                    subprocess.run(['hyprctl','dispatch','resizewindowpixel','exact 1280 900,'+address],check=True,stdout=subprocess.DEVNULL)
                    break
        env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'], WAYLAND_DISPLAY=instance['wl_socket'])
        assert not ctl('configerrors')
        if '--menus-only' not in sys.argv[3:]:
            plugin = subprocess.check_output([sys.executable, str(SOURCE/'runtime/cursor_probe/build.py')], text=True).strip()
            assert ctl('plugin', 'load', plugin) == 'ok'
        devices = json.loads(ctl('-j', 'devices'))
        for kind in ('mice', 'keyboards'):
            for device in devices.get(kind, []):
                assert ctl('keyword', 'device['+device['name']+']:enabled', 'false') == 'ok'
        # Keep host pointer motion out of the fixture and finish sizing its
        # output before any layer surface observes the initial geometry.
        monitor = json.loads(ctl('-j', 'monitors'))[0]
        assert ctl('keyword', 'monitor', monitor['name']+',1280x900@60,0x0,1') == 'ok'
        time.sleep(.6)
        bus_log = (root/'bus.log').open('w'); logs.append(bus_log)
        bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'], env=env,
                               stdout=subprocess.PIPE, stderr=bus_log, text=True)
        processes.append(bus); env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
        service = spawn([str(profile/'file_manager/.build/xetal-files'), '--service'])
        helper = spawn([sys.executable, str(fixture), str(profile/'desktop_menu'), str(report)])
        monitor = json.loads(ctl('-j', 'monitors'))[0]
        width, height = round(monitor['width']/monitor['scale']), round(monitor['height']/monitor['scale'])
        input_process = subprocess.Popen([str(root/'input'), str(width), str(height)], env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        def gesture(command, delay=.08):
            if command.startswith('move '):
                outputs=json.loads(ctl('-j','monitors'))
                left=min(m['x'] for m in outputs); top=min(m['y'] for m in outputs)
                right=max(m['x']+round(m['width']/m['scale']) for m in outputs)
                bottom=max(m['y']+round(m['height']/m['scale']) for m in outputs)
                input_process.stdin.write(f"size {right-left} {bottom-top}\n")
                input_process.stdin.flush(); assert input_process.stdout.readline().strip() == 'ok'
                _, x, y=command.split();command=f'move {round(float(x)-left)} {round(float(y)-top)}'
            input_process.stdin.write(command+'\n'); input_process.stdin.flush()
            assert input_process.stdout.readline().strip() == 'ok'; time.sleep(delay)
        def key(code): gesture(f'key {code} 1', .02); gesture(f'key {code} 0')
        def click(x, y, button='button'):
            gesture(f'move {round(x)} {round(y)}'); gesture(button+' 1', .03); gesture(button+' 0')
        def popup():
            current=json.loads(ctl('-j','monitors'))[0]
            gesture(f"move {round(current['width']/current['scale'])-100} {round(current['height']/current['scale'])-100}")
            click(round(current['width']/current['scale'])-320, 90, 'right'); wait(lambda: state().get('menus'), 'desktop context menu')
            key(102)  # Home chooses the first enabled item.
        def select_menu(label):
            for _ in range(15):
                menus = state().get('menus', [])
                if menus and label in menus[-1]['selected']: return
                key(108)
            raise AssertionError('Menu item was not reachable: '+label+' '+str(state().get('menus')))
        def arrange(label):
            popup(); select_menu('Arrange icons'); key(106)
            wait(lambda: len(state().get('menus', [])) == 2, 'arrangement submenu')
            key(102); select_menu(label); key(28)
            wait(lambda: not state().get('menus'), 'submenu dismissed')
        def positions():
            return state().get('surfaces', [{}])[0].get('positions', {})
        def layout_current():
            monitor = json.loads(ctl('-j', 'monitors'))[0]
            area = state().get('surfaces', [{}])[0].get('area', [])
            return area == [16, 16, round(monitor['width']/monitor['scale'])-32,
                           round(monitor['height']/monitor['scale'])-32]
        def drag(name, x, y):
            # The parent can resize its nested compositor window after mapping.
            # Wait for the desktop's output-change update before aiming at icons.
            wait(layout_current, 'desktop layout matches output')
            a, b = positions()[name]
            gesture(f'move {a+40} {b+26}'); gesture('button 1')
            gesture(f'move {a+55} {b+40}'); gesture(f'move {x} {y}', .2); gesture('button 0', .3)
        wait(lambda: state().get('surfaces'), 'transparent desktop surface')
        assert not state()['settings']['enabled']
        layers = json.loads(ctl('-j', 'layers'))
        assert any(layer['namespace'] == 'xetal-desktop-menu' for output in layers.values()
                   for layer in output['levels'].get('1', [])), layers
        popup(); run('grim', str(root/'context-menu.png'))
        select_menu('Show Desktop icons'); key(28)
        wait(lambda: len(positions()) == 8, 'Desktop files displayed')
        wait(layout_current, 'initial output layout')
        if '--drag-actions-only' in sys.argv[3:]:
            from check_drag_actions import check_drag_actions
            check_drag_actions(root, build, desktop, positions, spawn, ctl, run, gesture, wait)
            return
        if '--drag-refresh-only' in sys.argv[3:]:
            from check_drag_refresh import check_drag_refresh
            check_drag_refresh(root, desktop, positions, spawn, ctl, gesture, wait, popup, key, state)
            return
        # File actions arrive over D-Bus after the popup request. Its Wayland
        # window must fit the completed menu, not the one-row loading message.
        file_menus = []
        for name in ('A folder', '1 notes # café.txt'):
            a, b = positions()[name]
            click(a+35, b+30, 'right')
            wait(lambda: any('Customize desktop file menu…' in menu['labels']
                            for menu in state().get('menus', [])), 'file actions received')
            time.sleep(.3)
            menu = state()['menus'][0]
            file_menus.append(dict(name=name, **menu))
            (root/'file-menus.json').write_text(json.dumps(file_menus, indent=2))
            run('grim', str(root/('folder-menu.png' if name == 'A folder' else 'file-menu.png')))
            assert menu['popup_height'] >= min(menu['preferred_height'], height-80), menu
            key(102); select_menu('Copy'); key(28)
            wait(lambda: not state().get('menus'), 'file menu action dismissed')
            copied = run('wl-paste', '--type', 'text/uri-list')
            assert (desktop/name).as_uri() in copied, copied
        key(68)  # F10 requests the same asynchronous menu from the keyboard.
        wait(lambda: any('Customize desktop file menu…' in menu['labels']
                        for menu in state().get('menus', [])), 'keyboard file menu')
        key(102); select_menu('Copy'); key(28)
        wait(lambda: not state().get('menus'), 'keyboard menu action dismissed')
        assert (desktop/'1 notes # café.txt').as_uri() in run('wl-paste', '--type', 'text/uri-list')
        if '--menus-only' in sys.argv[3:]:
            print('PASS: folder/file menus fit their content; pointer and keyboard invocations copy the selected file.')
            return
        (root/'monitors.json').write_text(ctl('-j', 'monitors'))
        (root/'input-size.json').write_text(json.dumps([width,height]))
        assert '.hidden' not in positions()
        points = list(positions().values()); assert points[0][0] == points[1][0]
        run('grim', str(root/'columns.png'))
        original = positions().copy()
        drag('A folder', 640, 470)
        wait(lambda: positions()['A folder'] == [576, 472], 'custom aligned grid cell')
        assert not state()['settings']['auto_arrange']
        assert all(positions()[name] == point for name,point in original.items() if name != 'A folder')
        aligned = positions()['A folder']
        run('grim', str(root/'custom-grid-position.png'))
        assert (desktop/'A folder').is_dir()
        arrange('Auto align')
        wait(lambda: not state()['settings']['auto_align'], 'free placement enabled')
        assert positions()['A folder'] == aligned
        drag('A folder', 655, 340)
        wait(lambda: abs(positions()['A folder'][0]-615) < 8, 'free placement')
        free = positions()['A folder']; run('grim', str(root/'free-placement.png'))
        a, b = free
        click(a+35, b+30); click(a+35, b+30)
        def folder(): return next((c for c in json.loads(ctl('-j', 'clients')) if c['class'] == 'xetal-files-external'), None)
        wait(folder, 'floating Fusion folder window')
        assert folder()['floating'], folder()
        run('grim', str(root/'floating-folder.png'))
        assert ctl('dispatch', 'closewindow', 'address:'+folder()['address']) == 'ok'
        wait(lambda: not folder(), 'folder window closed')
        helper.terminate(); assert helper.wait(timeout=5) == 0
        helper = spawn([sys.executable, str(fixture), str(profile/'desktop_menu'), str(report)])
        wait(lambda: helper.poll() is None and state().get('settings', {}).get('enabled') and len(positions()) == 8, 'desktop restart')
        time.sleep(.4)
        assert positions()['A folder'] == free
        arrange('Rows')
        wait(lambda: state()['settings']['flow'] == 'rows', 'row preference')
        assert positions()['A folder'] == free
        arrange('Auto arrange')
        wait(lambda: len(set(point[1] for point in positions().values())) == 1, 'row arrangement')
        packed = positions().copy()
        arrange('Auto arrange')
        wait(lambda: not state()['settings']['auto_arrange'], 'automatic arrangement disabled')
        assert positions() == packed
        a, b = positions()['A folder']
        drag('1 notes # café.txt', a+40, b+30)
        wait(lambda: (desktop/'A folder/1 notes # café.txt').exists() and len(positions()) == 7,
             'move into a desktop folder')
        assert not (desktop/'1 notes # café.txt').exists()
        a, b = positions()['A folder']
        gesture('key 29 1')  # Ctrl changes a folder drop to Copy.
        drag('2 notes # café.txt', a+40, b+30)
        gesture('key 29 0')
        wait(lambda: (desktop/'A folder/2 notes # café.txt').exists(), 'Ctrl-copy into a desktop folder')
        assert (desktop/'2 notes # café.txt').exists()

        # Native desktop editing: F2 selects the stem, Escape leaves the file,
        # and Enter performs a real KIO rename without moving the icon.
        a,b=positions()['7 notes # café.txt']; click(a+35,b+30); key(60)
        wait(lambda: state().get('editors'), 'inline rename editor')
        run('grim', str(root/'inline-rename.png'))
        key(1); wait(lambda: not state().get('editors'), 'rename cancelled')
        assert (desktop/'7 notes # café.txt').exists()
        key(60); wait(lambda: state().get('editors'), 'rename editor reopened')
        for code in (19,18,49,30,50,18,32): key(code)  # renamed (keep .txt)
        key(28)
        wait(lambda: 'renamed.txt' in positions(), 'native inline rename')
        assert positions()['renamed.txt']==[a,b]

        # Copy from the GTK desktop and paste in the real Qt Files window.
        a,b=positions()['3 notes # café.txt']; click(a+35,b+30)
        gesture('key 29 1'); key(46); gesture('key 29 0')
        a,b=positions()['A folder']; click(a+35,b+30); click(a+35,b+30)
        wait(folder, 'floating folder for clipboard exchange')
        assert ctl('dispatch','focuswindow','address:'+folder()['address'])=='ok'
        gesture('key 29 1'); key(47); gesture('key 29 0')
        wait(lambda: (desktop/'A folder/3 notes # café.txt').exists(), 'desktop-to-Files clipboard copy')
        assert ctl('dispatch','closewindow','address:'+folder()['address'])=='ok'
        wait(lambda:not folder(),'clipboard folder closed')

        # Native Properties must map floating on its very first frame.
        a,b=positions()['renamed.txt']; click(a+35,b+30)
        gesture('key 56 1'); key(28); gesture('key 56 0')
        wait(folder,'desktop Properties window')
        properties=folder(); assert properties['floating'] and properties['pid']==service.pid,properties
        run('grim',str(root/'floating-properties.png'))
        assert ctl('dispatch','closewindow','address:'+properties['address'])=='ok'
        wait(lambda:not folder(),'Properties closed')

        # A real Qt clipboard source supplies KDE's cut marker to GTK. Its
        # window remains alive until the transfer has completed.
        incoming=home/'from Qt.txt'; incoming.write_text('native clipboard fixture')
        probe=root/'clipboard.py'
        probe.write_text('''import sys
from pathlib import Path
from PyQt6.QtCore import QMimeData,QUrl,Qt
from PyQt6.QtWidgets import QApplication,QPushButton
app=QApplication([]);app.setDesktopFileName('fusion-clipboard-fixture')
button=QPushButton('Cut fixture');button.resize(250,80)
def copy():
 data=QMimeData();data.setUrls([QUrl.fromLocalFile(sys.argv[1])]);data.setData('application/x-kde-cutselection',b'1')
 app.clipboard().setMimeData(data)
 Path(sys.argv[1]+'.copied').touch()
button.clicked.connect(copy);button.show();app.exec()
''')
        assert ctl('keyword','windowrule','match:class ^fusion-clipboard-fixture$, float on, size 250 80, move 850 700')=='ok'
        clipboard_source=spawn([sys.executable,str(probe),str(incoming)])
        def probe_window(): return next((c for c in json.loads(ctl('-j','clients')) if c['class']=='fusion-clipboard-fixture'),None)
        wait(probe_window,'Qt clipboard fixture')
        time.sleep(.4)
        # Distribution first-run helpers can activate on the fixture's private
        # D-Bus/HOME. Close only that disposable compositor's Welcome window so
        # a blank-desktop click cannot hit it instead of the layer surface.
        for client in json.loads(ctl('-j','clients')):
            if client['class']=='org.kde.plasma-welcome':
                assert ctl('dispatch','closewindow','address:'+client['address'])=='ok'
        wait(lambda:not any(c['class']=='org.kde.plasma-welcome' for c in json.loads(ctl('-j','clients'))), 'fixture Welcome closed')
        (root/'clipboard-source-clients.json').write_text(ctl('-j','clients'))
        run('grim',str(root/'clipboard-source.png'))
        c=probe_window();assert ctl('dispatch','focuswindow','address:'+c['address'])=='ok'
        key(57)
        wait(lambda: Path(str(incoming)+'.copied').exists(),'Qt clipboard source clicked')
        click(550,650)
        run('grim',str(root/'clipboard-paste.png'))
        (root/'clipboard-clients.json').write_text(ctl('-j','clients'))
        gesture('key 29 1');key(47);gesture('key 29 0')
        wait(lambda: (desktop/incoming.name).exists() and not incoming.exists(),'Qt-to-desktop cut paste')
        assert (desktop/incoming.name).read_text()=='native clipboard fixture'
        clipboard_source.terminate();clipboard_source.wait(timeout=5)

        popup();select_menu('Show Trash');key(28)
        wait(lambda:'trash:/' in positions(),'Trash icon shown')
        a,b=positions()['trash:/'];click(a+35,b+30);click(a+35,b+30)
        wait(folder,'floating Trash folder');assert folder()['floating']
        assert ctl('dispatch','closewindow','address:'+folder()['address'])=='ok'
        wait(lambda:not folder(),'Trash folder closed')
        a,b=positions()['renamed.txt'];click(a+35,b+30);key(111)
        wait(lambda:state().get('flights',0)>0,'successful Trash flight')
        run('grim',str(root/'trash-animation.png'))
        wait(lambda:not state().get('flights') and 'renamed.txt' not in positions(),'Trash animation settled')
        assert (home/'.local/share/Trash/files/renamed.txt').read_text()=='fixture 6\n'
        wait(lambda:state().get('trash_full'),'full Trash icon')
        a,b=positions()['trash:/'];drag('6 notes # café.txt',a+35,b+30)
        wait(lambda:'6 notes # café.txt' not in positions(),'drop onto Trash')
        assert (home/'.local/share/Trash/files/6 notes # café.txt').exists()
        run('grim',str(root/'trash-full.png'))

        # Create and paste on a second monitor. The destination survives the
        # menu moving, a floating name dialog, and asynchronous clipboard I/O.
        primary=json.loads(ctl('-j','monitors'))[0]['name']
        assert ctl('output','create','wayland')=='ok'
        wait(lambda:len(json.loads(ctl('-j','monitors')))==2,'second desktop output')
        second=next(m['name'] for m in json.loads(ctl('-j','monitors')) if m['name']!=primary)
        time.sleep(.8)
        assert ctl('keyword','monitor',primary+',1280x900@60,0x0,1')=='ok'
        assert ctl('keyword','monitor',second+',1280x900@60,1280x0,1')=='ok'
        wait(lambda:len(state().get('surfaces',[]))==2,'second desktop layer')
        def second_positions():
            return next((s['positions'] for s in state().get('surfaces',[]) if s['monitor']==second),{})
        time.sleep(.6)
        secondary=next(m for m in json.loads(ctl('-j','monitors')) if m['name']==second)
        sx,sy=secondary['x'],secondary['y']
        click(sx+260,sy+240,'right');wait(lambda:state().get('menus'),'second-monitor menu')
        key(102);select_menu('New folder…');key(28)
        wait(folder,'native New folder dialog')
        time.sleep(.3)
        assert ctl('dispatch','focuswindow','address:'+folder()['address'])=='ok'
        time.sleep(.2)
        key(28)  # Keep the suggested "New folder" name.
        wait(lambda:'New folder' in second_positions(),'new folder on clicked monitor')
        a,b=second_positions()['New folder'];assert abs(a-260)<8 and abs(b-240)<8,(a,b)
        assert 'New folder' not in positions()
        run('grim',str(root/'second-monitor-new-folder.png'))

        incoming=home/'second monitor.txt';incoming.write_text('second monitor clipboard fixture')
        clipboard_source=spawn([sys.executable,str(probe),str(incoming)])
        wait(probe_window,'second clipboard fixture');time.sleep(.4)
        assert ctl('dispatch','focuswindow','address:'+probe_window()['address'])=='ok'
        key(57);wait(lambda:Path(str(incoming)+'.copied').exists(),'second clipboard ready')
        click(sx+520,sy+490)
        gesture('key 29 1');key(47);gesture('key 29 0')
        wait(lambda:incoming.name in second_positions(),'paste on pointer monitor')
        a,b=second_positions()[incoming.name];assert abs(a-520)<8 and abs(b-490)<8,(a,b)
        assert incoming.name not in positions() and not incoming.exists()
        clipboard_source.terminate();clipboard_source.wait(timeout=5)
        run('grim',str(root/'second-monitor-paste.png'))

        count=len(list(desktop.iterdir()))
        popup(); select_menu('Show Desktop icons'); key(28)
        wait(lambda: not positions() and not state()['settings']['enabled'], 'desktop icons hidden')
        assert len(list(desktop.iterdir())) == count
        assert service.poll() is None, 'Files service exited before logout'
        compositor.terminate(); compositor.wait(timeout=10)
        # GDK may observe the closed Wayland connection before Hyprland's IPC
        # hangup handler; it exits with 1 and this diagnostic in that case.
        helper_status = helper.wait(timeout=5)
        assert helper_status == 0 or (helper_status == 1 and
            'Error reading events from display: Broken pipe' in (root/'process-4.log').read_text())
        # Qt's checkWaylandError calls _exit(-1) when the compositor closes,
        # which is status 255 if it wins the race with the IPC shutdown event.
        service_status = service.wait(timeout=5)
        assert service_status in (0, 255), service_status
        print('PASS: bottom layer, layouts, native drag, persistence, floating folders/Properties, clipboard exchange, inline rename, Trash open/drop/animation, second-monitor creation/paste, hide and logout.')
    finally:
        if input_process:
            if input_process.poll() is None: input_process.terminate()
            input_process.wait(timeout=5)
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        for log in logs: log.close()
        shutil.rmtree(runtime, ignore_errors=True)


if __name__ == '__main__': main()
