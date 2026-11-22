#!/usr/bin/env python3
"""Check this visual update, then install its managed files for the next login.

No package installation, service restart, logout or live native-plugin swap.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

REPO=Path(__file__).resolve().parents[1];SOURCE=REPO/'config/hypr'
FILES=['compat/hypr_compat.py','runtime/visual_policy_057.hpp','effects/cube/native/plugin_057.cpp',
       'effects/minimize/native/plugin_057.cpp','effects/minimize/build.py','scripts/session.sh',
       'share-picker/app.py','share-picker/model.py','switcher/previews.py','theme/page.py','theme/runtime.py',
       'theme/window_chrome.py','theme/window_chrome.hpp','theme/wrapping_tabs.py','theme/file_preview.py','theme/presets.py',
       'effects/burn/page.py','theme/backend.py','updates/file_policy.py',
       'waybar/workspaces/button.c','waybar/workspaces/previews.h','waybar/workspaces/build.sh']
FILES += ['visuals/'+p.name for p in sorted((SOURCE/'visuals').glob('*.py'))]
HOTKEY='# @hotkey {"id": "f5cb930e55e24945aa22c417ba502023", "label": "Open Fusion Overview", "category": "Workspaces", "protected": false}\nbind = SUPER, O, exec, python3 ~/.config/hypr/visuals/app.py overview\n'


def retire_overview_binding(text):
    # Remove only the exact shortcut this preview supplied. User bindings stay.
    return text.replace(HOTKEY,''),HOTKEY in text


def atomic(path,data,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,mode);os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true',help='Run isolated checks without installing files.')
    args=parser.parse_args()
    if os.geteuid()==0:raise RuntimeError('Run this from your desktop terminal without sudo.')
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') or not os.environ.get('WAYLAND_DISPLAY'):
        raise RuntimeError('Run this from a terminal in your Hyper Fusion desktop.')
    live=Path.home()/'.config/hypr'
    if not (live/'hyprland.lua').is_file():raise RuntimeError('The Hyprland 0.57 Lua profile is not installed.')
    directory=Path.home()/'.local/state/hyperfusion/visuals'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    directory.mkdir(parents=True,mode=0o700)
    report={'passed':False,'installed':False,'backup':str(directory)};written=[];original={}
    print('Visual update log: '+str(directory/'install.log'),flush=True)
    with (directory/'install.log').open('w',buffering=1) as log:
        def run(command,cwd=REPO,timeout=300):
            result=subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,
                                  env={**os.environ,'QT_QPA_PLATFORM':'offscreen','GSETTINGS_BACKEND':'memory','NO_AT_BRIDGE':'1'})
            if result.returncode:
                log.flush()
                tail=(directory/'install.log').read_text(errors='replace').splitlines()[-24:]
                print('\n'.join(tail),flush=True)
                raise RuntimeError('Check failed: '+str(command)+'. Details: '+str(directory/'install.log'))
        def output(command):
            result=subprocess.run(command,capture_output=True,text=True,timeout=240)
            log.write(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError(result.stderr.strip() or 'Command failed. See install.log.')
            return result.stdout.strip()
        try:
            version=json.loads(output(['/usr/bin/hyprctl','-j','version']))
            if version.get('commit')!='11cbc6c577b84ffb1edf4df3fc5b6128c3ae6947':raise RuntimeError('This preview needs the tested Hyprland 0.57.2 build.')
            print('Checking saved appearance, focus rendering and sharing on a private desktop…',flush=True)
            run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_visuals.py','-q'])
            run([sys.executable,'-m','unittest','-q','test_picker.py'],SOURCE/'share-picker')
            run(['bash',str(SOURCE/'share-picker/build.sh')])
            run([sys.executable,str(REPO/'tests/check-visuals.py'),str(directory/'focus')])
            cube=Path(output([sys.executable,str(SOURCE/'effects/cube/build.py')]))
            minimize=Path(output([sys.executable,str(SOURCE/'effects/minimize/build.py')]))
            buttons=Path(output([sys.executable,str(SOURCE/'effects/window_close/build.py')]))
            print('Checking cube rendering and large-window minimize/restore on private outputs…',flush=True)
            run([sys.executable,str(REPO/'tests/check-cube-render.py'),str(cube),str(directory/'native'),str(buttons),str(minimize)])
            report['validation']=[str(directory/'focus/result.json'),str(directory/'native/result.json')]
            if args.check_only:
                report['passed']=True;print('PASS — isolated checks passed. Nothing was installed.',flush=True);return 0
            changes={name:(SOURCE/name).read_bytes() for name in FILES}
            keys=live/'keybindings.conf'
            before=keys.read_text();after,removed=retire_overview_binding(before)
            if after!=before:changes['keybindings.conf']=after.encode()
            report['preview_overview_shortcut_removed']=removed
            protected={str(p.relative_to(live)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for pattern in ('effects/*/settings.*','theme/state.json','control_center/displays.conf')
                       for p in live.glob(pattern) if p.is_file() and p.suffix in ('.json','.conf')}
            # Native verification uses only generated Lua; it never executes startup actions.
            sys.path.insert(0,str(SOURCE));from compat.hypr_compat import Renderer
            from visuals import model
            preferences,preference_token=model.load(live)
            changes['visuals/settings.json']=(json.dumps(preferences,indent=2)+'\n').encode()
            candidate=directory/'candidate.lua'
            candidate.write_text(Renderer(live,visual_settings=preferences).render())
            run(['Hyprland','--verify-config','--config',str(candidate)])
            for name,data in changes.items():
                path=live/name
                if name=='visuals/settings.json' and model.load(live)[1]!=preference_token:raise RuntimeError('Appearance was edited during preparation. Please retry.')
                if path.is_symlink() or not path.parent.resolve().is_relative_to(live.resolve()):raise RuntimeError('Unsupported symlink: '+str(path))
                if path.exists():
                    original[name]=(path.read_bytes(),path.stat().st_mode&0o777)
                    atomic(directory/'files'/name,*original[name])
                else:original[name]=None
            report['files']={name:{'existed':value is not None,'mode':value[1] if value else 0o644} for name,value in original.items()}
            # Publish dependencies before the reader/session entry that imports them.
            ordered=sorted(changes,key=lambda name:name in ('compat/hypr_compat.py','theme/page.py','scripts/session.sh','keybindings.conf'))
            for name in ordered:
                path=live/name;expected=original[name]
                if (path.read_bytes() if path.exists() else None)!=(expected[0] if expected else None):raise RuntimeError('A file changed during preparation: '+name)
                atomic(path,changes[name],expected[1] if expected else 0o644);written.append(name)
            # Each native build uses a unique pathname, so mapped plugins remain intact.
            for effect,binary in (('cube',cube),('minimize',minimize),('window_close',buttons)):
                destination=live/'effects'/effect/'.build'/binary.parent.name/binary.name
                atomic(destination,binary.read_bytes(),0o755)
                output([sys.executable,str(live/'effects'/effect/'build.py')])
            run(['bash',str(live/'waybar/workspaces/build.sh')])
            run(['bash',str(live/'share-picker/build.sh')])
            for name,digest in protected.items():
                if hashlib.sha256((live/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('A saved preference changed during installation: '+name)
            report.update(passed=True,installed=True,preferences_preserved=True)
            print('PASS — window appearance installed with a backup; your current focus, effect and display preferences are preserved.',flush=True)
            print('Log out and back into Hyper Fusion once. Then open Fusion Settings → Theme → Window effects → Window appearance.',flush=True)
            return 0
        except BaseException:
            report['error']=traceback.format_exc();log.write(report['error'])
            for name in reversed(written):
                try:
                    if original[name] is None:(live/name).unlink(missing_ok=True)
                    else:atomic(live/name,*original[name])
                except OSError as error:log.write('Restore '+name+': '+str(error)+'\n')
            if written:
                print('Stopped. Managed source changes were restored; details are in install.log.',flush=True)
            else:
                print('Stopped before installation. Your installed desktop was not changed; details are in install.log.',flush=True)
            return 1
        finally:
            atomic(directory/'result.json',(json.dumps(report,indent=2)+'\n').encode())
            print('Report: '+str(directory/'result.json'),flush=True)


if __name__=='__main__':raise SystemExit(main())
