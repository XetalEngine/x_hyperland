#!/usr/bin/env python3
"""Drive real thumbnail drags on a private Xvfb display, never the user's desktop.

Requires Xvfb, libX11, libXtst and PyQt6. Evidence goes into a new /tmp directory.
Checks native drag routing, highlighted targets, persistent moves and Escape.
"""
import argparse
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import traceback

REPO = Path(__file__).resolve().parents[1]


def child(root, presets=False):
    from unittest.mock import patch
    sys.path[:0] = [str(REPO/'config/hypr'),str(REPO/'config/hypr/theme'),str(REPO/'config/hypr/control_center')]
    from PyQt6.QtCore import QPoint, QTimer
    from PyQt6.QtGui import QColor, QImage, QPixmap, QShortcut
    from PyQt6.QtWidgets import QApplication, QComboBox
    from wallpaper import library
    from wallpaper.browser import Browser, STYLE
    import runtime

    x11 = ctypes.CDLL(ctypes.util.find_library('X11')); xtst = ctypes.CDLL(ctypes.util.find_library('Xtst'))
    pointer = ctypes.c_void_p
    x11.XOpenDisplay.argtypes=[ctypes.c_char_p]; x11.XOpenDisplay.restype=pointer
    x11.XFlush.argtypes=[pointer]; x11.XCloseDisplay.argtypes=[pointer]
    x11.XKeysymToKeycode.argtypes=[pointer,ctypes.c_ulong]; x11.XKeysymToKeycode.restype=ctypes.c_uint
    xtst.XTestFakeMotionEvent.argtypes=[pointer,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
    xtst.XTestFakeButtonEvent.argtypes=[pointer,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
    xtst.XTestFakeKeyEvent.argtypes=[pointer,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
    display = x11.XOpenDisplay(os.environ['DISPLAY'].encode()); assert display
    def motion(point): xtst.XTestFakeMotionEvent(display,0,point.x(),point.y(),0); x11.XFlush(display)
    def button(down): xtst.XTestFakeButtonEvent(display,1,int(down),0); x11.XFlush(display)
    def escape():
        code=x11.XKeysymToKeycode(display,0xff1b)
        xtst.XTestFakeKeyEvent(display,code,1,0); xtst.XTestFakeKeyEvent(display,code,0,0); x11.XFlush(display)

    app=QApplication([]); app.setQuitOnLastWindowClosed(False); runtime.install(app,STYLE)
    pictures=[]; image=QImage(160,90,QImage.Format.Format_RGB32); image.fill(QColor('#268bc0'))
    for i in range(3):
        path=root/f'picture-{i}.png'; image.save(str(path)); pictures.append(library.Picture(str(path),'Test'))
    if presets:
        import gallery_state as library
        from gallery import DesignPage, ThemeThumbnail
        from unittest.mock import Mock
        pictures=[ThemeThumbnail(name,runtime.DESIGNS[name]) for name in ('raw','modern','integra')]
    results=[]; errors=[]
    def later(delay,callback):
        def guarded():
            try: callback()
            except BaseException:
                errors.append(traceback.format_exc()); app.quit()
        QTimer.singleShot(delay,guarded)
    state_patch=(patch.object(runtime,'STATE',root/'theme.json') if presets else patch.object(library,'PREFERENCES',root/'browser.json'))
    with state_patch,patch.object(Browser,'scan'):
        before=library.read(); options=library.add_hidden_tab(before,'Favorites')
        destination=options['active_hidden_tab']; options['active_hidden_tab']='hidden'; options['hidden']=[pictures[0].path]
        library.save(options,before)
        if presets:
            owner=Mock(); owner.design=QComboBox(); owner.mode=QComboBox()
            owner.design.addItem('BMW','hp4'); owner.mode.addItem('Dark','dark')
            w=DesignPage(owner); w.refresh(); w.hidden_dock.reduced_motion=True
            # Fusion Settings owns an Escape shortcut; native drags must consume
            # it before the settings window closes.
            shortcut=QShortcut('Escape',w); shortcut.activated.connect(w.close)
        else:
            w=Browser(preview=True,style='overlay'); w.reduced_motion=True; w.carousel.reduced_motion=True
            for picture in pictures:
                w.thumbnails.cache[picture.path]=QPixmap.fromImage(image); w.hidden_dock.thumbnails.cache[picture.path]=QPixmap.fromImage(image)
            w.scanned(w.cancel_scan,(pictures,[],''))
        w.resize(1200,800); w.move(0,0); w.show(); w.activateWindow()
        dock=w.hidden_dock; bar=dock.tabbar
        def source(path): return dock.mapToGlobal(dock.location(path).center().toPoint())
        def target(index): return bar.mapToGlobal(bar.tabRect(index).center())
        def highlight(index):
            assert bar.drop_index==index,(bar.drop_index,dock.drag_path,dock.drop_hint)
            assert dock.drop_hint.startswith('Release to move')
            w.grab().save(str(root/'highlight.png')); results.append('native drag highlights destination')
        def moved():
            assert w.options['active_hidden_tab']==destination,w.options
            assert library.hidden_tab(w.options,destination)['paths']==[pictures[0].path]
            assert not library.hidden_tab(w.options,'hidden')['paths']
            assert w.options['hidden']==[pictures[0].path]
            assert library.read()==w.options
            results.append('drop moves and persists the thumbnail without unhiding it')
            if presets: w.hide_preset(pictures[1].path)
            else: w.hide_picture(pictures[1])
            snapshot=library.read()
            later(100,lambda:motion(source(pictures[1].path)))
            later(220,lambda:button(True))
            later(360,lambda:motion(source(pictures[1].path)-QPoint(0,20)))
            later(520,lambda:motion(target(0)))
            later(720,lambda:highlight(0))
            later(850,escape); later(970,lambda:button(False))
            def cancelled():
                assert w.isVisible(); assert not dock.drag_path; assert bar.drop_index==-1
                assert library.read()==snapshot; assert w.options==snapshot
                if presets: owner.select_preset.assert_not_called()
                results.append('Escape cancels the drag and keeps the browser and all tab contents')
                app.quit()
            later(1200,cancelled)
        later(350,lambda:motion(source(pictures[0].path)))
        later(500,lambda:button(True))
        later(650,lambda:motion(source(pictures[0].path)-QPoint(0,20)))
        later(850,lambda:motion(target(1)))
        later(1150,lambda:highlight(1)); later(1300,lambda:button(False)); later(1600,moved)
        later(10000,lambda:(_ for _ in ()).throw(TimeoutError('Native drag test timed out')))
        app.exec(); w.hide()
        if not presets: w.shutdown()
        w.deleteLater(); app.processEvents(); x11.XCloseDisplay(display)
    if errors: raise AssertionError('\n'.join(errors))
    (root/'report.json').write_text(json.dumps(results,indent=2)+'\n')
    for result in results: print('PASS:',result)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('directory',type=Path); parser.add_argument('--child',action='store_true'); parser.add_argument('--presets',action='store_true')
    args=parser.parse_args(); root=args.directory.resolve()
    assert root.is_relative_to('/tmp') and root!=Path('/tmp')
    if args.child: child(root,args.presets); return
    root.mkdir(parents=True,exist_ok=False)
    read,write=os.pipe(); server=None
    try:
        with (root/'xvfb.log').open('w') as log:
            server=subprocess.Popen(['Xvfb','-displayfd',str(write),'-screen','0','1280x900x24','-nolisten','tcp','-noreset'],pass_fds=(write,),stdout=log,stderr=log)
            os.close(write); write=None
            assert select.select([read],[],[],5)[0],'Xvfb did not start'
            number=os.read(read,64).decode().strip(); assert number.isdigit(),number
            env={k:v for k,v in os.environ.items() if not k.startswith(('HYPRLAND_','WAYLAND_','XETAL_'))}
            env.update(DISPLAY=':'+number,QT_QPA_PLATFORM='xcb',HOME=str(root/'home'))
            env.pop('DBUS_SESSION_BUS_ADDRESS',None)
            subprocess.run([sys.executable,__file__,str(root),'--child']+(['--presets'] if args.presets else []),env=env,check=True,timeout=20)
    finally:
        os.close(read)
        if write is not None: os.close(write)
        if server:
            server.terminate()
            try: server.wait(timeout=3)
            except subprocess.TimeoutExpired: server.kill(); server.wait()
    print('Evidence:',root)


if __name__=='__main__': main()
