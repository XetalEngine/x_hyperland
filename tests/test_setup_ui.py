"""Run under Xvfb: real GTK choices and worker routing, with all installs faked."""
import argparse
import ctypes as C
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=('fresh','fresh-no-startup','keep','defaults'),default='fresh')
    mode=parser.parse_args().mode
    update=mode in ('keep','defaults');selected=mode in ('fresh','keep')
    sys.path.insert(0,str(REPO/'installer'))
    import wizard
    output=Path('/tmp/xetal-setup-preview');output.mkdir(exist_ok=True)
    with patch.object(wizard.runtime_install.policy,'installed',return_value={'version':'0.57.0','commit':'a'*40}):
        app=wizard.Wizard(update=update)
    app.log_path=Path(app.temporary.name)/'setup.log'
    g=app.g;g.lib.gtk_button_clicked.argtypes=[C.c_void_p]
    g.lib.gtk_widget_get_sensitive.argtypes=[C.c_void_p];g.lib.gtk_widget_get_sensitive.restype=C.c_int
    g.lib.gtk_label_get_text.argtypes=[C.c_void_p];g.lib.gtk_label_get_text.restype=C.c_char_p
    g.lib.gtk_widget_get_allocated_width.argtypes=[C.c_void_p];g.lib.gtk_widget_get_allocated_width.restype=C.c_int
    g.lib.gtk_widget_get_allocated_height.argtypes=[C.c_void_p];g.lib.gtk_widget_get_allocated_height.restype=C.c_int
    phase=0;commands=[];failures=[];started=time.monotonic()
    class FakeProcess:
        def __init__(self,args,**kwargs):
            commands.append(args);self.attempt=len(commands)
            assert Path(args[1]).name==('update.py' if mode=='keep' else 'install.py'),args
            assert ('--no-startup' in args)==(mode=='fresh-no-startup'),args
            assert kwargs['env']['XETAL_SETUP_GUI']=='1'
            assert kwargs['start_new_session']
            if mode=='keep':
                assert all(flag in args for flag in ('--manual','--runtime','--activate')),args
            else:assert '--yes' in args,args
            self.stdout=self.output()
        def output(self):
            yield 'Building Control Panel with 32 parallel jobs.\n'
            if self.attempt==1:
                while not app.cancel_file.exists() and time.monotonic()-started<20:time.sleep(.01)
                yield 'Setup cancelled after completing the current step.\n'
        def wait(self):return 1 if self.attempt==1 else 0
    def capture(name):
        window=subprocess.check_output(['xdotool','search','--onlyvisible','--name','Hyper Fusion / Setup'],text=True).splitlines()[0]
        subprocess.run(['import','-window',window,str(output/(mode+'-'+name+'.png'))],check=True,timeout=5)
        assert g.lib.gtk_widget_get_allocated_width(app.window)<=1100
        assert g.lib.gtk_widget_get_allocated_height(app.window)<=760
    def tick(_):
        nonlocal phase
        try:
            assert time.monotonic()-started<25,'Setup UI test timed out'
            if phase==0:
                assert app.index==0;capture('welcome');app.advance()
            elif phase==1:
                assert app.index==1 and g.lib.gtk_widget_get_sensitive(app.startup)
                assert g.toggle_button_get_active(app.startup)
                g.lib.gtk_button_clicked(app.startup)
                assert not g.toggle_button_get_active(app.startup)
                if selected:g.lib.gtk_button_clicked(app.startup)
            elif phase==2:
                capture('setup');app.advance()
            elif phase==3:
                assert app.index==2
                expected={'keep':'Keep existing desktop and startup preferences',
                          'defaults':'Use current desktop and startup defaults',
                          'fresh':'Startup dashboard: on','fresh-no-startup':'Startup dashboard: off'}[mode]
                assert expected in g.lib.gtk_label_get_text(app.review).decode()
                capture('review');app.previous()
                assert bool(g.toggle_button_get_active(app.startup))==selected
                app.advance();app.advance()
            elif phase==4:
                assert app.busy;capture('progress');app.close()
                assert app.cancel_file.exists()
            elif phase==5:
                if app.busy:return 1
                assert not app.success;capture('cancelled');app.advance()
            elif phase==6:
                if app.busy:return 1
                assert app.success and app.index==4;capture('complete');app.close();return 0
            phase+=1
        except Exception as error:
            failures.append(str(error));g.main_quit();return 0
        return 1
    callback=C.CFUNCTYPE(C.c_int,C.c_void_p)(tick);g.callbacks.append(callback);g.glib.g_timeout_add(450,callback,None)
    try:
        with patch.object(wizard,'subprocess',SimpleNamespace(Popen=FakeProcess,PIPE=subprocess.PIPE,STDOUT=subprocess.STDOUT)):
            g.main()
    finally:app.temporary.cleanup()
    if failures:raise AssertionError('; '.join(failures))
    assert len(commands)==2 and commands[0]==commands[1],commands
    print('Setup UI ('+mode+'): editable choice, review, worker command, cancellation, retry and finish passed.')


if __name__=='__main__':main()
