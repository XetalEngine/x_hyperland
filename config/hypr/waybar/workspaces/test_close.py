"""Native GTK pointer regression: xvfb-run -a env GDK_BACKEND=x11 python test_close.py."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parent


def wait_for(predicate, message):
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(.05)
    raise AssertionError(message)


def run():
    with tempfile.TemporaryDirectory(prefix='workspace-close-test-') as temp:
        root=Path(temp);binary=root/'widget'
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gtk+-3.0','gtk-layer-shell-0'],text=True))
        subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(ROOT/'test-close.c'),'-o',str(binary),*flags],check=True)
        with (root/'log').open('w+') as log:
            proc=subprocess.Popen([str(binary),temp],stdout=log,stderr=log,
                                  env={**os.environ,'NO_AT_BRIDGE':'1'})
            def xdo(*args):
                return subprocess.check_output(['xdotool',*map(str,args)],text=True).strip()
            def geometry():
                try:return list(map(int,(root/'geometry').read_text().split()))
                except (FileNotFoundError,ValueError):return []
            def actions():return (root/'actions').read_text().splitlines() if (root/'actions').exists() else []
            try:
                wait_for(lambda:geometry() and geometry()[0], 'Close control not visible')
                window=xdo('search','--name','^Workspace close test$')
                xdo('windowfocus',window)
                def click(x,y):xdo('mousemove','--window',window,x,y);xdo('click',1);time.sleep(.15)
                _,x,y,bx,by=geometry();click(x,y)
                assert actions()==['remove-workspace.py 5'],actions()
                click(bx,by);assert actions()[-1]=='activate 5',actions()
                xdo('key','o');wait_for(lambda:geometry()[0]==0,'Occupied workspace still has a close button')
                xdo('key','e');wait_for(lambda:geometry()[0]==1,'Newly empty workspace did not regain close button')
                # Repeated native taskbar button destruction/recreation must remain safe.
                xdo('key','r');time.sleep(.3);xdo('key','n')
                wait_for(lambda:geometry()[0]==1,'Recreated workspace lost close button')
                _,x,y,*_=geometry();click(x,y)
                assert actions()[-1]=='remove-workspace.py 5',actions()
                xdo('key','b');wait_for(lambda:geometry()[0]==1,'Module teardown/reload failed')
                xdo('key','l');wait_for(lambda:geometry()[0]==0,'Last workspace must keep its number without a close button')
                assert proc.poll() is None
                print('PASS: real close click never activates workspace; number click works; occupied/last protection; live empty updates; destroy/recreate; module reload.')
            finally:
                proc.terminate();proc.wait(timeout=4);log.seek(0);errors=log.read()
                assert not any(word in errors for word in ['CRITICAL','WARNING','ERROR']),errors


if __name__=='__main__':run()
