#!/usr/bin/env python3
"""Build, validate and atomically install the Xetal Hyprland profile."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import dependencies

REPO=Path(__file__).resolve().parents[1]
PAYLOAD=REPO/'config/hypr'


def safe_home(home):
    # Several upstream configuration formats interpret commas/$/# as syntax.
    if not re.fullmatch(r'/[A-Za-z0-9_./+-]+',str(home)):
        raise ValueError('This installer requires a standard home path without spaces, commas, or shell metacharacters.')


def tree_digest(root):
    if root.is_symlink():return 'symlink:'+os.readlink(root)
    if not root.exists():return 'missing'
    digest=hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if any(part in ('cache','state','__pycache__','mozilla','qt-settings') for part in p.relative_to(root).parts) or p.suffix in ('.lock','.pyc'):continue
        relative=str(p.relative_to(root))
        digest.update(relative.encode()+b'\0')
        if p.is_symlink():digest.update(b'link:'+os.readlink(p).encode())
        elif p.is_file():digest.update(p.read_bytes())
    return digest.hexdigest()


def connected_monitors():
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):return []
    try:
        result=subprocess.run(['hyprctl','-j','monitors','all'],capture_output=True,text=True,timeout=5,check=True)
        return json.loads(result.stdout)
    except (OSError,ValueError,subprocess.SubprocessError):return []


def check_kvm_payload(root):
    """Runtime payloads belong on the component server, never in an install."""
    binary_suffixes={'.xz','.gz','.zip','.tar','.bin','.fd','.rom','.aml','.ko','.so','.a','.o','.iso','.img','.efi'}
    for path in (root/'kvm').rglob('*'):
        if not path.is_file():continue
        with path.open('rb') as stream:magic=stream.read(4)
        if path.suffix.lower() in binary_suffixes or magic==b'\x7fELF':
            raise RuntimeError('KVM binaries must be downloaded in KVM Settings: '+str(path.relative_to(root)))


def render(stage, home, monitors, profile='auto', startup=True):
    safe_home(home)
    check_kvm_payload(PAYLOAD)
    target=home/'.config/hypr'
    shutil.copytree(PAYLOAD,stage,dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.so','*.o','*.lock','build','.build',
                        'cache','state','font-cache','qt-settings','window-preview','version.txt'))
    for p in stage.rglob('*'):
        if not p.is_file():continue
        try:text=p.read_text()
        except UnicodeDecodeError:continue
        text=text.replace('@HOME@',str(home)).replace('@HYPR@',str(target))
        p.write_text(text)
    # Preserve current hardware modes, positions and scaling instead of imposing
    # the author's three DP connectors or 120 Hz refresh rates on another PC.
    active=[m for m in monitors if not m.get('disabled') and m.get('mirrorOf','none') in ('none','',None)]
    for m in monitors:
        if not re.fullmatch(r'[A-Za-z0-9_.:-]+',m['name']):raise ValueError('Unsupported display connector name.')
    if profile=='original':
        for name in ('displays.conf','workspaces.conf'):
            (stage/'control_center'/name).write_text((REPO/'profiles/xetal-original'/name).read_text())
    else:
        lines=['# Local display modes captured by x_hyperinstall.sh; edit in Control desk → Displays.']
        for m in monitors:
            name=m['name']
            if m.get('disabled'):lines.append(f'monitor = {name},disable');continue
            line=f'monitor = {name},{m["width"]}x{m["height"]}@{m["refreshRate"]:.3f},{m["x"]}x{m["y"]},{m.get("scale",1)},transform,{m.get("transform",0)}'
            mirror=m.get('mirrorOf','none')
            if mirror not in ('none','',None):line+=',mirror,'+mirror
            lines.append(line)
        (stage/'control_center/displays.conf').write_text('\n'.join(lines)+'\n')
        lines=['# One initial workspace on each connected display; + adds more.']
        lines += [f'workspace = {i}, monitor:{m["name"]}, default:true' for i,m in enumerate(active,1)]
        (stage/'control_center/workspaces.conf').write_text('\n'.join(lines)+'\n')
    choice=json.loads((stage/'wallpaper/default.json').read_text())
    wallpaper=str(target/'wallpaper'/choice['image'])
    design=json.loads((stage/'theme/state.json').read_text()).get('design','modern')
    sets=json.loads((stage/'wallpaper/sets.json').read_text())
    artwork=sets.get(design,[choice['image']])
    if not artwork or not all((stage/'wallpaper'/name).is_file() for name in artwork):
        raise ValueError('The default theme wallpaper set is incomplete.')
    outputs=[m['name'] for m in sorted(active,key=lambda m:(m.get('x',0),m.get('y',0),m['name']))]
    if profile=='original':outputs=list(json.loads((REPO/'profiles/xetal-original/selection.json').read_text()))
    selection={}
    for index,name in enumerate(outputs):
        path=str(target/'wallpaper'/artwork[index%len(artwork)])
        selection[name]={'path':path,'original':path,'fit':choice['fit']}
    (stage/'wallpaper/selection.json').write_text(json.dumps(selection,indent=2)+'\n')
    # The wildcard also covers outputs connected after installation.
    lines=['ipc = true','splash = false','']
    for name in ['',*outputs]:
        path=selection[name]['path'] if name else wallpaper
        lines+=['wallpaper {',f'    monitor = {name}',f'    path = {path}',f'    fit_mode = {choice["fit"]}','}','']
    (stage/'wallpaper/hyprpaper.conf').write_text('\n'.join(lines))
    if not startup:
        p=stage/'hyprland.conf';p.write_text(p.read_text().replace('exec-once = ~/.config/hypr/scripts/startup-scene.sh --login','# Login animation disabled by installer; Super+D remains available.'))
    # Portable Places; never publish the author's private paths or recent files.
    places=ET.Element('xbel',{'version':'1.0'})
    entries=[('Home',home,'user-home')]+[(name,home/name,icon) for name,icon in [
        ('Desktop','user-desktop'),('Documents','folder-documents'),('Downloads','folder-download'),
        ('Music','folder-music'),('Pictures','folder-pictures'),('Videos','folder-videos')]]
    for label,path,icon in entries:
        bookmark=ET.SubElement(places,'bookmark',{'href':path.as_uri()});ET.SubElement(bookmark,'title').text=label
        metadata=ET.SubElement(ET.SubElement(bookmark,'info'),'metadata',{'owner':'http://freedesktop.org'})
        ET.SubElement(metadata,'{http://www.freedesktop.org/standards/desktop-bookmarks}icon',{'name':icon})
    directory=stage/'dolphin/data';directory.mkdir(parents=True,exist_ok=True)
    ET.ElementTree(places).write(directory/'user-places.xbel',encoding='utf-8',xml_declaration=True)
    # Copy the recipient's XDG directory locations, without invoking a shell or
    # creating/changing any of those folders.
    user_dirs=home/'.config/user-dirs.dirs'
    if user_dirs.is_file():shutil.copy2(user_dirs,stage/'dolphin/config/user-dirs.dirs')
    for directory in ('dolphin/cache','dolphin/state','apps','assets/font-cache'):(stage/directory).mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(stage/'theme/update_widget.py')],check=True)
    return target


def build(stage):
    for args in ([sys.executable,str(stage/'cursors/build.py')],
                 [sys.executable,str(stage/'theme/build.py')],
                 [sys.executable,str(stage/'control_panel/build.py')],
                 ['bash',str(stage/'waybar/pins/build.sh')],
                 ['bash',str(stage/'waybar/workspaces/build.sh')],
                 ['bash',str(stage/'waybar/options/build.sh')],
                 ['bash',str(stage/'share-picker/build.sh')]):
        print('Building '+str(Path(args[-1]).relative_to(stage)),flush=True)
        subprocess.run(args,check=True)

    # The optional compositor adapter has a deliberately narrow ABI boundary.
    # An unsupported Hyprland must not prevent installing the desktop profile.
    for effect,label in [('burn','Burn'),('cube','Desktop Cube & 3D Windows')]:
        result = subprocess.run([sys.executable,str(stage/'effects'/effect/'build.py')],capture_output=True,text=True)
        if result.returncode:
            print('Optional '+label+' effect unavailable: '+result.stderr.strip(),flush=True)
        else:
            print('Built '+label+' for the installed Hyprland.',flush=True)


def register_updates(stage):
    """Record the delivered defaults separately from future personal edits."""
    sys.path.insert(0,str(PAYLOAD/'updates'))
    import update_engine
    commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    update_engine.write_json(stage/update_engine.META,update_engine.metadata(stage,commit))


def validate(stage):
    for p in stage.rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
    for p in stage.rglob('*.json'):json.loads(p.read_text())
    for p in stage.rglob('*.sh'):subprocess.run(['bash','-n',str(p)],check=True)
    # Validate every sourced file from the staged tree. The live config is never
    # borrowed and --verify-config does not run exec/exec-once commands.
    with tempfile.TemporaryDirectory(prefix='.verify-',dir=stage) as temporary:
        candidate=Path(temporary)/'hyprland.conf'
        text=(stage/'hyprland.conf').read_text().replace('~/.config/hypr/',str(stage)+'/')
        candidate.write_text(text)
        result=subprocess.run(['Hyprland','--verify-config','--config',str(candidate)],capture_output=True,text=True)
        if result.returncode or 'config ok' not in result.stdout:
            raise RuntimeError('Full Hyprland validation failed:\n'+result.stdout[-4000:]+result.stderr[-1000:])
    for relative in ('theme/gtk3/libxetal-file-preview.so','theme/qt5/platformthemes/libxetaltheme.so','theme/qt6/platformthemes/libxetaltheme.so',
                     'waybar/pins/pins.so','waybar/workspaces/controls.so','waybar/options/options.so','share-picker/window-preview','control_panel/.build/xetal-control-panel'):
        if not (stage/relative).is_file():raise RuntimeError('Missing built component: '+relative)


def activate(stage,target,state,expected):
    """Replace one profile only; compensate if the final rename fails."""
    if tree_digest(target)!=expected:raise RuntimeError('Your configuration changed during preparation. Run again to include the latest version.')
    backup=state/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup.mkdir(parents=True,mode=0o700)
    existed=target.exists() or target.is_symlink()
    record={'version':1,'target':str(target),'had_previous':existed,'created':datetime.now(timezone.utc).isoformat()}
    (backup/'install.json').write_text(json.dumps(record,indent=2)+'\n')
    (stage/'.xetal-install.json').write_text(json.dumps({'backup':str(backup),'installed':record['created']},indent=2)+'\n')
    if existed:os.replace(target,backup/'hypr')
    try:os.replace(stage,target)
    except BaseException:
        if existed:os.replace(backup/'hypr',target)
        raise
    return backup


def restore(backup,target,state):
    record=json.loads((backup/'install.json').read_text())
    if record.get('version')!=1 or record.get('target')!=str(target):raise RuntimeError('Backup does not belong to this Hyprland profile.')
    previous=backup/'hypr'
    if record['had_previous'] and not (previous.exists() or previous.is_symlink()):raise RuntimeError('The previous profile is missing or already restored.')
    saved=state/'replaced'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    saved.parent.mkdir(parents=True,exist_ok=True)
    current=target.exists() or target.is_symlink()
    if current:os.replace(target,saved)
    try:
        if record['had_previous']:os.replace(previous,target)
    except BaseException:
        if current:os.replace(saved,target)
        raise
    return saved if current else None


def main():
    parser=argparse.ArgumentParser(description='Install the complete Xetal Hyprland desktop, including wallpaper and native modules.')
    parser.add_argument('--yes',action='store_true',help='Accept dependency installation and profile replacement.')
    parser.add_argument('--skip-packages',action='store_true',help='Use existing dependencies; fail if anything is missing.')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--check',action='store_true',help='Read-only dependency/compatibility check.')
    mode.add_argument('--dry-run',action='store_true',help='Read-only installation plan and dependency report.')
    mode.add_argument('--prepare',type=Path,help='Build and validate a review copy here without installing it.')
    parser.add_argument('--profile',choices=['auto','original'],default='auto',help='Adapt to this computer, or use the author\'s three-display layout.')
    parser.add_argument('--no-startup',action='store_true',help='Keep the animated dashboard available with Super+D without opening it at login.')
    mode.add_argument('--restore',type=Path,help='Restore a previous installer backup; retain the replaced profile separately.')
    args=parser.parse_args()
    if os.geteuid()==0:raise RuntimeError('Run as your desktop user, without sudo. The installer asks sudo only for packages.')
    home=Path.home();safe_home(home);target=home/'.config/hypr';state=home/'.local/state/xetal-hyprland'
    print('Xetal / Hyprland desktop\nTarget: '+str(target),flush=True)
    if args.restore:
        if not args.yes and input('Restore this backup and retain the current profile? [y/N] ').strip().lower() not in ('y','yes'):return 0
        state.mkdir(parents=True,exist_ok=True,mode=0o700)
        with (state/'install.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            saved=restore(args.restore.absolute(),target,state)
        print('Restored. Replaced profile retained at '+str(saved)+'. Log out and back in to use it.');return 0
    errors=dependencies.check()
    if args.dry_run or args.check:
        print('Profile: '+args.profile+'; build Qt 5/6 theme plugins, Waybar modules, and screen-share preview helper.')
        print('Include current wallpaper, licensed fonts, all session tools, backup and rollback. Activate at next Hyprland login.')
        for error in errors:print('  '+error)
        if not errors:print('All dependency and version checks passed.')
        family=dependencies.distro()
        if family:print('Package recipe ('+family+'): '+' '.join(dependencies.PACKAGES[family]))
        return 1 if errors and args.check else 0
    if errors:
        if args.skip_packages:raise RuntimeError('\n'.join(errors))
        dependencies.install(args.yes)
        errors=dependencies.check()
        if errors:raise RuntimeError('Dependencies still need attention; profile unchanged:\n'+'\n'.join(errors))
    if args.prepare:
        destination=args.prepare.absolute()
        if destination.exists():raise RuntimeError('--prepare destination must not exist.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        render(destination,home,connected_monitors(),args.profile,not args.no_startup)
        register_updates(destination)
        build(destination);validate(destination)
        print('Built and validated review copy: '+str(destination)+'. Live profile unchanged.');return 0
    target.parent.mkdir(parents=True,exist_ok=True)
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (state/'install.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        expected=tree_digest(target)
        with tempfile.TemporaryDirectory(prefix='.xetal-hypr-',dir=target.parent) as temporary:
            stage=Path(temporary)/'hypr'
            render(stage,home,connected_monitors(),args.profile,not args.no_startup)
            register_updates(stage)
            build(stage);validate(stage)
            print('All components built; full configuration validated. Your existing profile will be backed up.')
            if not args.yes and input('Install this prepared desktop? [y/N] ').strip().lower() not in ('y','yes'):
                print('Cancelled; your current profile is unchanged.');return 0
            backup=activate(stage,target,state,expected)
    print('Installed. Backup: '+str(backup))
    print('Log out and select Hyprland again. This starts the complete desktop and the portal picker together.')
    print('Restore: '+str(REPO/'x_hyperinstall.sh')+' --restore '+str(backup))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (KeyboardInterrupt,EOFError):
        print('\nCancelled. Use --yes for a noninteractive installation.',file=sys.stderr);raise SystemExit(130)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print('Installation stopped: '+str(error),file=sys.stderr);raise SystemExit(1)
