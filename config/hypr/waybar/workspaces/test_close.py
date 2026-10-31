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
            runtime=root/'runtime';state=runtime/'hypr/test/xetal-cube-faces';state.parent.mkdir(parents=True)
            proc=subprocess.Popen([str(binary),temp],stdout=log,stderr=log,
                                  env={**os.environ,'NO_AT_BRIDGE':'1','XDG_RUNTIME_DIR':str(runtime),'HYPRLAND_INSTANCE_SIGNATURE':'test'})
            def xdo(*args):
                return subprocess.check_output(['xdotool',*map(str,args)],text=True).strip()
            def geometry():
                try:return list(map(int,(root/'geometry').read_text().split()))
                except (FileNotFoundError,ValueError):return []
            def actions():return (root/'actions').read_text().splitlines() if (root/'actions').exists() else []
            def add_state():
                lines=(root/'add-state').read_text().splitlines()
                return list(map(int,lines[0].split())),lines[1]
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
                state.write_text('enabled\n2 1\n5 2\n')
                def cube_state():
                    try:return (root/'cube-state').read_text()
                    except OSError:return ''
                wait_for(lambda:cube_state()=='1 |2 |1|0', 'Cube labels or guarded add/remove controls are wrong')
                xdo('key','u')
                labels=[line for line in actions() if line.startswith('labels ')]
                assert labels==['labels 1 |2 ']*25, 'Internal workspace numbers escaped before refresh: '+repr(labels)
                _,_,_,bx,by=geometry();click(bx,by);assert actions()[-1]=='activate 5',actions()
                original,tip=add_state();assert tip=='Not available with 3D Cube on',tip
                before=actions();click(*original[:2])
                wait_for(lambda:add_state()[0][3], 'Blocked click did not show feedback')
                xdo('key','p')
                wait_for(lambda:(root/'feedback.png').is_file(), 'Feedback screenshot was not saved')
                from PIL import Image
                with Image.open(root/'feedback.png').convert('RGB') as image:
                    red=sum(r>g*1.4 and r>b*1.25 and r>100 for r,g,b in image.getdata())
                assert red>30, 'Blocked workspace button did not render red'
                positions=set();deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    sample,_=add_state();positions.add(sample[2])
                    assert sample[4:]==original[4:], 'Feedback moved the bar or its neighbouring controls'
                    if not sample[3]:break
                    time.sleep(.02)
                else:raise AssertionError('Blocked feedback did not return to normal')
                assert len(positions)>1, 'Blocked button did not shake'
                assert actions()==before, 'Blocked click tried to create a workspace'
                # Repeated clicks and module reload must not leave a frame callback alive.
                click(*add_state()[0][:2]);click(*add_state()[0][:2])
                xdo('key','b');time.sleep(.3)
                assert cube_state()=='1 |2 |1|0',cube_state()
                assert not add_state()[0][3],add_state()
                assert actions()==before,actions()
                click(*add_state()[0][:2])
                state.write_text('disabled\n')
                wait_for(lambda:cube_state()=='2 |5 |1|1','Global workspace labels were not restored')
                assert not add_state()[0][3],add_state()
                assert add_state()[1]=='New empty workspace on this display'
                click(*add_state()[0][:2]);assert actions()[-1].startswith('new-workspace.py '),actions()
                xdo('key','u')
                assert actions()[-25:]==['labels 2 |5 ']*25,actions()[-25:]
                xdo('key','l');wait_for(lambda:geometry()[0]==0,'Last workspace must keep its number without a close button')
                assert proc.poll() is None
                print('PASS: close/add click routing; cube labels stay local; blocked tooltip, red pixels and shake; stable neighbouring controls; feedback resets on timeout, Cube off and module reload.')
            finally:
                proc.terminate();proc.wait(timeout=4);log.seek(0);errors=log.read()
                assert not any(word in errors for word in ['CRITICAL','WARNING','ERROR']),errors


if __name__=='__main__':run()
