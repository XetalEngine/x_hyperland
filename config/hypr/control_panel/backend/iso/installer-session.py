#!/usr/bin/env python3
"""Start the graphical live-ISO wizard, with an independent restore worker.

Only a failed graphics startup (before the worker exists), or an explicit
console choice on the welcome page, can switch to the console installer.
A graphical crash must never restart or terminate a restore already underway.
"""
import array
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import termios
import time

from installer_protocol import request

ROOT = Path(__file__).resolve().parent
BACKEND = Path('/usr/local/bin/installer.sh')


def platforms(environment, tty, fbdev, drm):
    if environment.get('WAYLAND_DISPLAY'):return [('wayland', {})]
    if environment.get('DISPLAY'):return [('xcb', {})]
    if not tty.startswith('/dev/tty') or not tty[8:].isdigit():return []
    choices=[]
    if drm:choices.append(('linuxfb', {'QT_QPA_FB_DRM':'1'}))
    if fbdev:choices.append(('linuxfb:fb=/dev/fb0', {'QT_QPA_FB_DRM':'0'}))
    return choices


class ConsoleState:
    def __init__(self):
        self.fd=None; self.attrs=None; self.modes=[]
        try:
            tty=os.ttyname(0)
            if not tty.startswith('/dev/tty') or not tty[8:].isdigit():return
            self.fd=os.open(tty,os.O_RDWR|os.O_NOCTTY)
            self.attrs=termios.tcgetattr(self.fd)
            # Linux kd.h: save the graphics/text and keyboard translation mode.
            for get,setter in ((0x4B3B,0x4B3A),(0x4B44,0x4B45)):
                value=array.array('i',[0]); fcntl.ioctl(self.fd,get,value,True)
                self.modes.append((setter,value[0]))
        except (OSError,termios.error):pass

    def restore(self):
        if self.fd is None:return
        for setter,value in self.modes:
            try:fcntl.ioctl(self.fd,setter,value)
            except OSError:pass
        if self.attrs:
            try:termios.tcsetattr(self.fd,termios.TCSANOW,self.attrs)
            except termios.error:pass

    def close(self):
        self.restore()
        if self.fd is not None:os.close(self.fd)


def stop_gui(process):
    if process is None or process.poll() is not None:return
    process.terminate()
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:process.kill(); process.wait()


def tail(path):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0,2); stream.seek(max(0,stream.tell()-18000))
            return stream.read().decode(errors='replace')
    except OSError:return ''


def run(arguments):
    text='--text' in arguments or os.environ.get('XETAL_INSTALLER')=='text'
    arguments=[arg for arg in arguments if arg!='--text']
    try:text=text or 'xetal.text=1' in Path('/proc/cmdline').read_text().split()
    except OSError:pass
    try:tty=os.ttyname(0)
    except OSError:tty=''
    choices=[] if text or '--dry-run' in arguments else platforms(os.environ,tty,Path('/dev/fb0').exists(),bool(list(Path('/dev/dri').glob('card*'))))
    if not choices:return subprocess.call(['bash',str(BACKEND),*arguments])
    saved=ConsoleState(); gui=None; worker=None
    directory='/run' if os.geteuid()==0 else None
    with tempfile.TemporaryDirectory(prefix='xetal-installer-',dir=directory) as tmp:
        private=Path(tmp); endpoint=private/'ui.sock'; ready=private/'ready'
        log_path=Path('/var/log/xetal-installer.log') if os.geteuid()==0 else private/'installer.log'
        graphics_log=Path('/var/log/xetal-installer-graphics.log') if os.geteuid()==0 else private/'graphics.log'
        # The UI process only renders; the shell worker runs independently and
        # keeps its output in a file, so losing the UI cannot break its pipe.
        try:
            with graphics_log.open('a') as diagnostic:
                for platform,extra in choices:
                    ready.unlink(missing_ok=True);endpoint.unlink(missing_ok=True)
                    environment=dict(os.environ,QT_QPA_PLATFORM=platform,QT_QUICK_BACKEND='software',**extra)
                    for name in ('QT_QPA_PLATFORMTHEME','QT_STYLE_OVERRIDE','QT_PLUGIN_PATH','XETAL_INSTALLER_SOCKET'):
                        environment.pop(name,None)
                    gui=subprocess.Popen([sys.executable,str(ROOT/'installer-graphical.py'),'serve',
                        '--socket',str(endpoint),'--ready',str(ready),'--fullscreen'],
                        env=environment,stdout=diagnostic,stderr=diagnostic)
                    deadline=time.monotonic()+8
                    while gui.poll() is None and not ready.exists() and time.monotonic()<deadline:time.sleep(.1)
                    if ready.exists() and gui.poll() is None:break
                    stop_gui(gui);saved.restore()
                else:
                    print('Graphical startup unavailable. Opening the console installer.')
                    return subprocess.call(['bash',str(BACKEND),*arguments])
                with log_path.open('w') as output:
                    worker=subprocess.Popen(['bash',str(BACKEND),*arguments],
                        env=dict(os.environ,XETAL_INSTALLER_SOCKET=str(endpoint)),stdout=output,stderr=output)
                    announced=False
                    while worker.poll() is None:
                        if gui.poll() is not None and not announced:
                            saved.restore();announced=True
                            if gui.returncode!=20:
                                print('The graphical view closed. Waiting for the existing installer to finish; it will not be restarted.')
                                print('Installation log:',log_path)
                        time.sleep(.15)
                code=worker.returncode
                if gui.poll()==20:
                    # The UI only offers this before a target is selected.
                    saved.restore()
                    return subprocess.call(['bash',str(BACKEND),*arguments])
                if code and gui.poll() is None:
                    try:request(endpoint,dict(kind='finish',title='Installation stopped.',text='Review the details below before trying again.',details=tail(log_path)))
                    except (OSError,ValueError,RuntimeError):pass
                if code:print(tail(log_path),file=sys.stderr)
                return code
        finally:
            # Do not terminate the independent worker, even on a graphics error.
            if worker is not None and worker.poll() is None:
                print('Waiting for the active installation to finish…')
                worker.wait()
            stop_gui(gui);saved.close()


if __name__=='__main__':raise SystemExit(run(sys.argv[1:]))
