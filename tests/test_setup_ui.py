"""Run explicitly under Xvfb: GTK navigation and failure/retry, with no installs."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0,str(REPO/'installer'))
    import wizard
    output=Path('/tmp/xetal-setup-preview');output.mkdir(exist_ok=True)
    with patch.object(wizard.runtime_install.policy,'installed',return_value={'version':'0.57.0','commit':'a'*40}):
        app=wizard.Wizard()
    g=app.g;g.lib.gtk_button_clicked.argtypes=[C.c_void_p]
    g.lib.gtk_widget_get_allocated_width.argtypes=[C.c_void_p];g.lib.gtk_widget_get_allocated_width.restype=C.c_int
    g.lib.gtk_widget_get_allocated_height.argtypes=[C.c_void_p];g.lib.gtk_widget_get_allocated_height.restype=C.c_int
    phase=0;attempts=0;failures=[];started=time.monotonic()
    def fake_worker():
        nonlocal attempts
        attempts+=1
        app.events.put(('line','Building Control Panel with 32 parallel jobs.'))
        if attempts==1:
            while not app.cancel_file.exists() and time.monotonic()-started<20:time.sleep(.01)
            app.events.put(('line','Setup cancelled after completing the current step.'))
        app.events.put(('done',1 if attempts==1 else 0))
    app.worker=fake_worker
    def capture(name):
        window=subprocess.check_output(['xdotool','search','--onlyvisible','--name','Hyper Fusion / Setup'],text=True).splitlines()[0]
        subprocess.run(['import','-window',window,str(output/(name+'.png'))],check=True,timeout=5)
        assert g.lib.gtk_widget_get_allocated_width(app.window)<=1100
        assert g.lib.gtk_widget_get_allocated_height(app.window)<=760
    def tick(_):
        nonlocal phase
        try:
            assert time.monotonic()-started<25,'Setup UI test timed out'
            if phase==0:
                assert app.index==0;capture('welcome');app.advance()
            elif phase==1:
                assert app.index==1;g.toggle_button_set_active(app.startup,0);capture('setup');app.advance()
            elif phase==2:
                assert app.index==2;capture('review');app.previous()
                assert not g.toggle_button_get_active(app.startup);app.advance();app.advance()
            elif phase==3:
                assert app.busy;capture('progress');app.close()
                assert app.cancel_file.exists()
            elif phase==4:
                if app.busy:return 1
                assert not app.success;capture('cancelled');app.advance()
            elif phase==5:
                if app.busy:return 1
                assert app.success and app.index==4;capture('complete');app.close();return 0
            phase+=1
        except Exception as error:
            failures.append(str(error));g.main_quit();return 0
        return 1
    callback=C.CFUNCTYPE(C.c_int,C.c_void_p)(tick);g.callbacks.append(callback);g.glib.g_timeout_add(450,callback,None)
    try:g.main()
    finally:app.temporary.cleanup()
    if failures:raise AssertionError('; '.join(failures))
    print('Setup UI: welcome, downgrade review, navigation, progress, cancellation, retry and finish passed.')


if __name__=='__main__':main()
