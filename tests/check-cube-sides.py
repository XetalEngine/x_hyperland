#!/usr/bin/env python3
"""Exercise real 4–10 side add/remove transactions in a disposable compositor.

Usage: check-cube-sides.py new-plugin.so new-test-directory [previous-plugin.so]
Never changes the working compositor, workspace files, or application windows.
Set FUSION_CUBE_CHECK_FRAMES=0 only when the nested driver cannot capture outputs;
workspace/scene checks still run and pixel verification is reported as skipped.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO/'config/hypr'
sys.path[:0] = [str(PROFILE), str(PROFILE/'scripts')]
from effects.cube import model
from compat import hypr_compat


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, PROFILE/'scripts'/file)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def main():
    frames = os.environ.get('FUSION_CUBE_CHECK_FRAMES','1') != '0'
    binary = Path(sys.argv[1]).resolve(strict=True)
    root = Path(sys.argv[2]).resolve(); root.mkdir(parents=True, exist_ok=False)
    profile = root/'profile'; (profile/'control_center').mkdir(parents=True)
    (profile/'compat').symlink_to(PROFILE/'compat', target_is_directory=True)
    config = profile/'effects/cube/settings.json'; config.parent.mkdir(parents=True)
    values = dict(model.DEFAULTS, duration=150, workspace_animation='cube',
                  top_image='', bottom_image='', sky_image='', sky_mode='gradient')
    config.write_text(model.encode(values))
    (profile/'hyprland.conf').write_text('''monitor = ,preferred,auto,1
source = ~/.config/hypr/control_center/workspaces.conf
misc {
 disable_hyprland_logo = true
 disable_splash_rendering = true
}
xwayland {
 enabled = false
}
''')
    rules = profile/'control_center/workspaces.conf'; rules.write_text('# Workspace test\n')
    modern = hypr_compat.uses_lua()
    if modern:
        shutil.copyfile(PROFILE/'compat/entry.lua', profile/'hyprland.lua')
    entry = profile/('hyprland.lua' if modern else 'hyprland.conf')
    add = module('add_sides', 'new-workspace.py'); remove = module('remove_sides', 'remove-workspace.py')
    original_store = add.settings.Store
    def store(name): return original_store(name, root=profile, state=root/'state')
    env = dict(os.environ); env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
    env.update(AQ_BACKENDS=os.environ.get('XETAL_TEST_BACKEND','wayland'), XETAL_CUBE_CONFIG=str(config), GSETTINGS_BACKEND='memory')
    children = []
    with (root/'compositor.log').open('w') as log:
        comp = subprocess.Popen(['Hyprland', '--config', str(entry)], env=env,
                                stdout=log, stderr=log, start_new_session=True)
        children.append(comp)
        try:
            for _ in range(120):
                if comp.poll() is not None: raise RuntimeError('Nested compositor exited; see '+str(root/'compositor.log'))
                instances = json.loads(subprocess.check_output(['/usr/bin/hyprctl', '-j', 'instances'], text=True))
                instance = next((i for i in instances if i['pid']==comp.pid), None)
                if instance:
                    env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'], WAYLAND_DISPLAY=instance['wl_socket']); break
                time.sleep(.1)
            else: raise RuntimeError('No test compositor socket')
            if modern: env['PATH'] = str(PROFILE/'compat/bin')+':'+env['PATH']
            def run(*args):
                result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)
                if result.returncode: raise RuntimeError(str(args)+'\n'+result.stdout+result.stderr)
                return result.stdout.strip()
            def ctl(*args): return run('hyprctl', *args)
            def dispatch(*args):
                result = ctl('dispatch', *args); assert result=='ok', (args,result)
            def monitors(): return json.loads(ctl('-j','monitors'))
            def workspaces(): return json.loads(ctl('-j','workspaces'))
            def clients(): return json.loads(ctl('-j','clients'))
            def status(): return json.loads(ctl('xetal-cube'))
            def wait(predicate):
                for _ in range(150):
                    if predicate(): return
                    if comp.poll() is not None: raise RuntimeError('Test compositor crashed')
                    time.sleep(.04)
                raise AssertionError('Timed out waiting for native transition: '+ctl('xetal-cube'))
            time.sleep(.4)
            # Virtual outputs render independently of parent window occlusion.
            # Remove only this disposable compositor's initial Wayland output.
            initial = monitors()
            ctl('output','create','headless','SIDES-A')
            ctl('output','create','headless','SIDES-B')
            wait(lambda:len(monitors())==len(initial)+2)
            for monitor in initial:ctl('output','remove',monitor['name'])
            wait(lambda:len(monitors())==2)
            a,b=monitors()
            ctl('keyword','monitor',f"{a['name']},preferred,0x0,1")
            ctl('keyword','monitor',f"{b['name']},preferred,1280x0,1")
            wait(lambda:all(m['width']>0 for m in monitors()))
            assert ctl('configerrors')=='',ctl('configerrors')
            if len(sys.argv)>3:
                previous=str(Path(sys.argv[3]).resolve(strict=True))
                assert ctl('plugin','load',previous)=='ok'; time.sleep(.3)
                dispatch('xetalcube:preview',a['name']); wait(lambda:status()['draws']>0 if frames else status()['active'])
                assert ctl('plugin','unload',previous)=='ok'
            assert ctl('plugin','load',str(binary))=='ok'
            mapfile=Path(env['XDG_RUNTIME_DIR'])/'hypr'/env['HYPRLAND_INSTANCE_SIGNATURE']/'xetal-cube-faces'
            def ids(monitor):
                if not mapfile.exists():return []
                mapped={int(line.split()[0]) for line in mapfile.read_text().splitlines()[1:]}
                return sorted(w['id'] for w in workspaces() if w['monitor']==monitor['name'] and w.get('id') in mapped)
            wait(lambda:len(ids(a))==4 and len(ids(b))==4)
            # 0.57 omits numeric IDs for named/special workspaces. The real
            # desktop has a Welcome/Stash workspace alongside ordinary sides.
            dispatch('focusmonitor',a['name'])
            dispatch('togglespecialworkspace','cube-side-hidden')
            hidden=subprocess.Popen(['kitty','--config','/dev/null','--class','cube-hidden-test','-e','sleep','120'],env=env,stdout=log,stderr=log)
            children.append(hidden);wait(lambda:any(c['pid']==hidden.pid for c in clients()))
            dispatch('togglespecialworkspace','cube-side-hidden')
            with patch.dict(os.environ,env), patch.object(add.settings,'Store',side_effect=store):
                for count in range(5,11):
                    number,monitor=add.create(400,400)
                    assert monitor==a['name']
                    wait(lambda:len(ids(a))==count)
                    assert number in ids(a) and len(ids(b))==4,(ids(a),ids(b))
                    wait(lambda:not status()['active'])
                    time.sleep(.3)
                    dispatch('xetalcube:preview',a['name'])
                    wait(lambda:status()['active'])
                    if frames:
                        run('grim','-o',a['name'],str(root/f'cube-{count}-initial.png'))
                        wait(lambda:status()['draws']>0)
                    assert len(status()['workspaces'])==count,status()
                    dispatch('xetalcube:turn','40 -10')
                    if frames:run('grim','-o',a['name'],str(root/f'cube-{count}-sides.png'))
                    assert status()['error']=='',status()
                    dispatch('xetalcube:finish','cancel');wait(lambda:not status()['active'])
                saved=rules.read_text()
                try:add.create(400,400)
                except ValueError as error:assert 'up to 10' in str(error)
                else:raise AssertionError('Eleventh side was allowed')
                assert rules.read_text()==saved
                # Numeric shortcuts and wraparound use the actual side count.
                if modern:dispatch(hypr_compat.call('dsp.cursor.move',{'x':400,'y':400}))
                else:dispatch('movecursor','400 400')
                for key in ('10','e+1','e-1','5'):
                    expected=ids(a)[{'10':9,'e+1':0,'e-1':9,'5':4}[key]]
                    dispatch('xetalcube:workspace','switch '+key);wait(lambda:not status()['active'])
                    assert next(m for m in monitors() if m['name']==a['name'])['activeWorkspace']['id']==expected
                occupied=ids(a)[4]
                app=subprocess.Popen(['kitty','--config','/dev/null','--class','cube-sides-test','-e','sleep','120'],env=env,stdout=log,stderr=log)
                children.append(app);wait(lambda:any(c['pid']==app.pid for c in clients()))
                try:remove.remove(occupied,400,400)
                except ValueError as error:assert 'open windows' in str(error)
                else:raise AssertionError('Occupied workspace removed')
                # Remove empty sides, including the active face, down to four.
                while len(ids(a))>4:
                    number=next(n for n in reversed(ids(a)) if n!=occupied)
                    dispatch('workspace',str(number));wait(lambda:not status()['active'])
                    before=len(ids(a));remove.remove(number,400,400)
                    wait(lambda:len(ids(a))==before-1)
                    assert len(ids(b))==4
                    assert next(c for c in clients() if c['pid']==app.pid)['workspace']['id']==occupied
                number=next(n for n in ids(a) if n!=occupied)
                try:remove.remove(number,400,400)
                except ValueError as error:assert 'at least 4' in str(error)
                else:raise AssertionError('Removed the fourth side')
                # Save a fifth side again; Cube off/on, compositor reload and
                # plugin replacement must retain the same configured IDs.
                add.create(400,400);wait(lambda:len(ids(a))==5);expected=ids(a)
                values['enabled']=False;config.write_text(model.encode(values));dispatch('xetalcube:reload')
                assert all(w['ispersistent'] for w in workspaces() if w.get('id') in expected)
                values['enabled']=True;config.write_text(model.encode(values));dispatch('xetalcube:reload')
                ctl('reload');wait(lambda:ids(a)==expected)
                assert ctl('plugin','unload',str(binary))=='ok'
                assert ctl('plugin','load',str(binary))=='ok';wait(lambda:ids(a)==expected)
                ctl('output','remove',b['name']);wait(lambda:len(monitors())==1)
                assert 4<=len(ids(a))<=10
                assert ctl('plugin','unload',str(binary))=='ok'
            print('PASS: 4–10 sides; real add/remove and saved rules; per-monitor isolation; 5–10-sided scenes; 10/5 shortcuts and wraparound; occupied/minimum/maximum guards; reload, toggle, replacement and hot-unplug.',flush=True)
            print('Frames: captured and rendered' if frames else 'Frames: explicitly skipped (FUSION_CUBE_CHECK_FRAMES=0)',flush=True)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':main()
