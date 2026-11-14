#!/usr/bin/env python3
"""Build, validate and atomically install the Xetal Hyprland profile."""
from __future__ import annotations
import argparse
import ast
from collections import deque
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

import dependencies
import runtime_install
import login_setup
import commands

REPO=Path(__file__).resolve().parents[1]
PAYLOAD=REPO/'config/hypr'
sys.path.insert(0, str(PAYLOAD/'compat'))
import hypr_compat
sys.path.insert(0, str(PAYLOAD))
from dolphin import profile as dolphin_profile

DOLPHIN_DEFAULTS = {'dolphin/config/dolphinrc', 'dolphin/config/kdeglobals',
                    'dolphin/config/kservicemenurc',
                    'dolphin/data/kio/servicemenus/hyprland-wallpaper.desktop'}

# A source checkout may also have been used as a desktop. Seed portable
# launcher settings explicitly instead of copying its owner's saved pins.
LAUNCHER_DEFAULTS = {
    'favorites.json': {'add': ['xetal-files-computer.desktop', 'kitty.desktop', 'xetal-calculator.desktop'], 'hide': []},
    'shortcuts.json': {'version': 1, 'overrides': {'xetal-calculator.desktop': {'floating': True}}, 'copies': {}},
    'bar-pins.json': {'version': 1, 'pins': []},
    'window.json': {'width': 980, 'height': 720},
}


def payload_ignored(directory, names):
    ignored = set(shutil.ignore_patterns('__pycache__','*.pyc','*.so','*.o','*.lock','build','.build',
                 'cache','state','font-cache','qt-settings','window-preview','version.txt')(directory, names))
    relative = Path(directory).relative_to(PAYLOAD).as_posix()
    if relative == 'grub':
        # Ship appearance assets for Control Panel, never the old one-machine
        # installer. Copying the profile does not apply a boot theme.
        ignored.add('apply-this-machine.py')
    if relative == 'launcher':
        ignored.update((*LAUNCHER_DEFAULTS, 'favorite-layout.json', 'floating-sizes.json', 'icons'))
    if relative == 'workspaces':
        ignored.add('rules.json')
    if relative == 'icon_themes':
        ignored.update(('custom','imported','backups'))
    if relative.startswith('wallpaper/'):
        # Artwork creation notes remain in the repository, not in recipients'
        # desktop profiles (they can refer to the artist's local source files).
        ignored.add('prompts.json')
    if relative in ('dolphin/config', 'dolphin/data') or relative.startswith(('dolphin/config/', 'dolphin/data/')):
        ignored.update(name for name in names if not any(
            path == relative+'/'+name or path.startswith(relative+'/'+name+'/') for path in DOLPHIN_DEFAULTS))
    return ignored


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
    binary_suffixes={'.xz','.gz','.zip','.tar','.bin','.fd','.rom','.aml','.ko','.so','.a','.o','.iso','.img','.efi','.xvm'}
    for path in (root/'kvm').rglob('*'):
        if not path.is_file():continue
        with path.open('rb') as stream:magic=stream.read(4)
        if path.suffix.lower() in binary_suffixes or magic==b'\x7fELF':
            raise RuntimeError('KVM binaries must be downloaded in KVM Settings: '+str(path.relative_to(root)))


def render(stage, home, monitors, profile='auto', *, preserve_theme=False):
    safe_home(home)
    check_kvm_payload(PAYLOAD)
    target=home/'.config/hypr'
    shutil.copytree(PAYLOAD,stage,dirs_exist_ok=True,ignore=payload_ignored)
    # Fresh installs use Papirus-Dark for both system and application icons.
    # Do not copy the author's imports, overrides or generated paths.
    (stage/'theme/icons.json').write_text(json.dumps({'version':1,'system':'other','other':'theme:Papirus-Dark','overrides':{}},indent=2)+'\n')
    for name, defaults in LAUNCHER_DEFAULTS.items():
        (stage/'launcher'/name).write_text(json.dumps(defaults, indent=2)+'\n')
    # Cover every numbered workspace, including later +/Cube/monitor additions,
    # without copying the source checkout's personal per-workspace choices.
    (stage/'workspaces/rules.json').write_text(json.dumps(
        {'version':1, 'default_layout':'kde', 'workspaces':{}}, indent=2)+'\n')
    theme = stage/'theme/state.json'
    theme_defaults = json.loads(theme.read_text())
    theme_defaults.update(design='binaryknife',mode='dark',layout='classic',wallpaper_theme='binaryknife',
                          bar_style='follow',bar_variant='full',launcher_style='follow',
                          launcher_wallpaper=True, launcher_background='')
    # Updates render colors for the recipient's chosen theme, including when
    # it still matches an old release default. Fresh/reset installs use Binary Knife.
    saved_theme=target/'theme/state.json'
    if preserve_theme and saved_theme.is_file():
        saved=json.loads(saved_theme.read_text())
        theme_defaults.update(saved)
        for key in ('layout','wallpaper_theme','bar_style','launcher_style'):
            if key not in saved:theme_defaults.pop(key,None)
    theme.write_text(json.dumps(theme_defaults, indent=2)+'\n')
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
    choice.update(image='binaryknife/workstation-2.png',fit='cover')
    saved_wallpaper=target/'wallpaper/default.json'
    if preserve_theme and saved_wallpaper.is_file():choice.update(json.loads(saved_wallpaper.read_text()))
    (stage/'wallpaper/default.json').write_text(json.dumps(choice,indent=2)+'\n')
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
    # Portable Places; never publish the author's private paths or recent files.
    dolphin_profile.write_changed(stage/'dolphin/data/user-places.xbel', dolphin_profile.default_places(home))
    dolphin_profile.prepare_colors(stage)
    dolphin_profile.prepare_terminal(stage)
    dolphin_profile.prepare_layout(stage)
    # Render the selected fresh-install theme; no live IPC or shared settings.
    subprocess.run([sys.executable,str(stage/'theme/render_defaults.py'),'--asset-root',str(target/'theme')],check=True)
    # Copy the recipient's XDG directory locations, without invoking a shell or
    # creating/changing any of those folders.
    user_dirs=home/'.config/user-dirs.dirs'
    if user_dirs.is_file():shutil.copy2(user_dirs,stage/'dolphin/config/user-dirs.dirs')
    for directory in ('dolphin/cache','dolphin/state','apps','assets/font-cache'):(stage/directory).mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(stage/'theme/update_widget.py')],check=True)
    hypr_compat.install_entry(stage)
    return target


def run_build(args, label):
    """Stream progress and keep useful diagnostics through package recovery."""
    tail = deque(maxlen=60)
    diagnostic = ''
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors='replace', bufsize=1) as process:
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
                tail.append(line.rstrip()[:2000])
                if not diagnostic and any(token in line.lower() for token in
                        ('error:', 'fatal error', 'not found', 'no such file', 'killed signal')):
                    diagnostic = line.strip()[:1000]
            code = process.wait()
        except BaseException:
            process.kill()
            process.wait()
            raise
    if code:
        summary = f'Build failed: {label} (exit {code}).'
        if diagnostic:
            summary += ' ' + diagnostic
        details = '\n'.join(tail).strip()
        raise RuntimeError(summary + ('\nBuild output:\n' + details if details else ''))


def build(stage, checkpoint=lambda:None):
    for args in ([sys.executable,str(stage/'runtime/notices/build.py')],
                 [sys.executable,str(stage/'runtime/cursor_probe/build.py')],
                 [sys.executable,str(stage/'runtime/window_memory/build.py')],
                 [sys.executable,str(stage/'cursors/build.py')],
                 [sys.executable,str(stage/'icon_themes/prepare.py')],
                 [sys.executable,str(stage/'theme/build.py')],
                 [sys.executable,str(stage/'wallpaper/build.py')],
                 [sys.executable,str(stage/'control_panel/build.py')],
                 [sys.executable,str(stage/'file_manager/build.py')],
                 ['bash',str(stage/'waybar/pins/build.sh')],
                 ['bash',str(stage/'waybar/workspaces/build.sh')],
                 ['bash',str(stage/'waybar/options/build.sh')],
                 ['bash',str(stage/'share-picker/build.sh')]):
        label = str(Path(args[-1]).relative_to(stage))
        print('Building '+label,flush=True)
        checkpoint()
        run_build(args, label)

    # A complete desktop requires the adapters matched by the runtime manifest.
    for effect,label in [('burn','Burn'),('cube','Desktop Cube & 3D Windows'),('minimize','Fireball Minimize'),('wobbly','Compiz Wobbly Windows'),('window_close','Window controls & forced workspace layout')]:
        result = subprocess.run([sys.executable,str(stage/'effects'/effect/'build.py')],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(label+' could not be built for the required compositor:\n'+result.stderr.strip())
        else:
            print('Built '+label+' for the installed Hyprland.',flush=True)
        checkpoint()


def source_revision(root=None):
    """Identify this checkout or exported archive without guessing a remote head."""
    root = Path(root) if root is not None else REPO
    if (root/'.git').exists():
        # Require this directory's own Git metadata. A ZIP extracted inside an
        # unrelated checkout must never inherit that parent's commit instead.
        try:
            commit = subprocess.check_output(
                ['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD^{commit}'],
                text=True, stderr=subprocess.PIPE, timeout=10).strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError('Could not read this Git checkout. Use a complete clone or a fresh GitHub ZIP download.') from error
    else:
        # .gitattributes export-subst fills this in when GitHub/git archive makes
        # the download. It remains valid offline even when main has moved on.
        try:
            commit = (root/'installer/source-revision.txt').read_text().strip()
        except (FileNotFoundError, UnicodeDecodeError):
            commit = ''
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise RuntimeError('Could not identify this source version. Download a fresh ZIP from GitHub and extract it completely, '
                           'including installer/source-revision.txt, or use a Git clone.')
    return commit


def register_updates(stage, commit=None):
    """Record the delivered defaults separately from future personal edits."""
    sys.path.insert(0,str(PAYLOAD/'updates'))
    import update_engine
    if commit is None:commit=source_revision()
    update_engine.write_json(stage/update_engine.META,update_engine.metadata(stage,commit))


def validate_config(stage):
    # Validate every sourced file from the staged tree. The live config is never
    # borrowed and --verify-config does not run exec/exec-once commands.
    with tempfile.TemporaryDirectory(prefix='.verify-',dir=stage) as temporary:
        candidate=hypr_compat.candidate(stage, temporary)
        print('Checking Hyprland configuration: '+candidate.name,flush=True)
        result=subprocess.run(['Hyprland','--verify-config','--config',str(candidate)],capture_output=True,text=True)
        if result.returncode or 'config ok' not in result.stdout:
            raise RuntimeError('Full Hyprland validation failed:\n'+result.stdout[-4000:]+result.stderr[-1000:])


def validate(stage):
    for p in stage.rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
    for p in stage.rglob('*.json'):json.loads(p.read_text())
    for p in stage.rglob('*.sh'):subprocess.run(['bash','-n',str(p)],check=True)
    validate_config(stage)
    for relative in ('runtime/notices/.build/xetal-startup-notices.so',
                     'theme/gtk3/libxetal-file-preview.so','theme/qt5/platformthemes/libxetaltheme.so','theme/qt6/platformthemes/libxetaltheme.so',
                     'waybar/pins/pins.so','waybar/workspaces/controls.so','waybar/workspaces/mode.so','waybar/options/options.so','share-picker/window-preview','control_panel/.build/xetal-control-panel',
                     'file_manager/.build/xetal-files'):
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


def restore(backup,target,state,runtime_check=True):
    record=json.loads((backup/'install.json').read_text())
    if record.get('version')!=1 or record.get('target')!=str(target):raise RuntimeError('Backup does not belong to this Hyprland profile.')
    previous=backup/'hypr'
    if record['had_previous'] and not (previous.exists() or previous.is_symlink()):raise RuntimeError('The previous profile is missing or already restored.')
    if runtime_check and (previous/'runtime/manifest.json').is_file(): runtime_install.policy.require(previous)
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
    login = parser.add_mutually_exclusive_group()
    login.add_argument('--fusion-login', dest='fusion_login', action='store_true', default=None,
                       help='Opt in to themed Fusion sign-in with an installed-desktop selector; backs up system login settings.')
    login.add_argument('--no-fusion-login', dest='fusion_login', action='store_false',
                       help='Restore the login settings backed up before Fusion sign-in was enabled.')
    parser.add_argument('--cancel-file',type=Path,help=argparse.SUPPRESS)
    mode.add_argument('--restore',type=Path,help='Restore a previous installer backup; retain the replaced profile separately.')
    args=parser.parse_args()
    def checkpoint():
        if args.cancel_file and args.cancel_file.exists():
            raise RuntimeError('Setup cancelled after completing the current step. The desktop profile was not replaced.')
    if os.geteuid()==0:raise RuntimeError('Run as your desktop user, without sudo. Setup requests administrator access for system operations.')
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
        try:print('Installer source: '+source_revision(),flush=True)
        except RuntimeError as error:errors.append(str(error))
        print('Profile: '+args.profile+'; build Qt 5/6 theme plugins, Waybar modules, and screen-share preview helper.')
        print('Include current wallpaper, licensed fonts, all session tools, backup and rollback. Activate at next Hyprland login.')
        if args.fusion_login is not None:
            print('Login: '+('enable Fusion sign-in; system backups in /var/lib/xetal-fusion-login/backups/' if args.fusion_login else 'restore previous login configuration'))
        for error in errors:print('  '+error)
        if not errors:print('All dependency and version checks passed.')
        family=dependencies.distro()
        if family:print('Package recipe ('+family+'): '+' '.join(dependencies.PACKAGES[family]))
        return 1 if errors and args.check else 0
    checkpoint()
    commit=source_revision()
    print('Installer source: '+commit,flush=True)
    if args.skip_packages:
        runtime_install.policy.require()
    else:
        dependencies.prepare_repositories()
        dependencies.preflight()
        runtime_install.ensure(args.yes)
        runtime_install.restart_after_python_upgrade()
        checkpoint()
        errors=dependencies.check()
    if errors:
        if args.skip_packages:raise RuntimeError('\n'.join(errors))
        dependencies.install(args.yes)
        runtime_install.restart_after_python_upgrade()
        dependencies.repair_toolchain(args.yes)
        checkpoint()
        errors=dependencies.check()
        if errors:raise RuntimeError('Dependencies still need attention; profile unchanged:\n'+'\n'.join(errors))
    if args.prepare:
        destination=args.prepare.absolute()
        if destination.exists():raise RuntimeError('--prepare destination must not exist.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        render(destination,home,connected_monitors(),args.profile)
        register_updates(destination,commit)
        validate_config(destination)
        build(destination,checkpoint);validate(destination)
        runtime_install.rollback()
        print('Built and validated review copy: '+str(destination)+'. Live profile unchanged.');return 0
    if not args.skip_packages:
        dependencies.prepare_account()
        checkpoint()
    target.parent.mkdir(parents=True,exist_ok=True)
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (state/'install.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        expected=tree_digest(target)
        with tempfile.TemporaryDirectory(prefix='.xetal-hypr-',dir=target.parent) as temporary:
            stage=Path(temporary)/'hypr'
            render(stage,home,connected_monitors(),args.profile)
            register_updates(stage,commit)
            validate_config(stage)
            build(stage,checkpoint);validate(stage)
            checkpoint()
            print('All components built; full configuration validated. Your existing profile will be backed up.')
            if not args.yes and input('Install this prepared desktop? [y/N] ').strip().lower() not in ('y','yes'):
                runtime_install.rollback()
                print('Cancelled; your current profile is unchanged.');return 0
            backup=activate(stage,target,state,expected)
            try:
                commands.install()
                login_setup.apply(args.fusion_login, target, args.skip_packages)
            except BaseException:
                # Keep the old desktop paired with any compositor recovery.
                # The enclosing error handler also recovers this transaction's runtime.
                restore(backup, target, state, runtime_check=False)
                raise
            runtime_install.complete()
    print('Installed. Backup: '+str(backup))
    print('Reboot to use Fusion sign-in and choose your desktop.' if args.fusion_login else
          'Log out and select Hyprland again. This starts the complete desktop and the portal picker together.')
    print('Restore: '+str(REPO/'x_hyperinstall.sh')+' --restore '+str(backup))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (KeyboardInterrupt,EOFError):
        runtime_install.rollback()
        print('\nCancelled. Use --yes for a noninteractive installation.',file=sys.stderr);raise SystemExit(130)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        runtime_install.rollback()
        print('Installation stopped: '+str(error),file=sys.stderr);raise SystemExit(1)
