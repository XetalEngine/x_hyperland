#!/usr/bin/python3
"""Administrator-only, reversible installation of the opt-in Fusion greeter.

Never starts/stops a desktop or edits another desktop's session configuration.
The selected desktop itself runs only after greetd's PAM authentication.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

BASE = Path('/var/lib/xetal-fusion-login')
CODE = Path('/usr/local/lib/xetal-fusion-login')
UNIT = 'xetal-fusion-login.service'
STATE = BASE/'installation.json'
SYSTEM_PATHS = [CODE, Path('/etc/xetal-fusion-login'),
                Path('/etc/systemd/system')/UNIT,
                Path('/etc/systemd/system/display-manager.service'),
                Path('/etc/systemd/system/default.target'), Path('/etc/pam.d/greetd'),
                Path('/etc/X11/default-display-manager'),
                Path('/etc/greetd/config.toml'), Path('/run/systemd/system/greetd.service'),
                Path('/etc/systemd/system/getty@tty1.service.d/99-xetal-autologin.conf')]


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.fusion-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream: stream.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class Backup:
    def __init__(self, destination, root=Path('/')):
        self.destination, self.root = destination, root
        self.entries = {}
        self.ownership = {}

    def save(self, path):
        relative = str(path).lstrip('/')
        if relative in self.entries: return
        actual = self.root/relative
        saved = self.destination/'files'/relative
        if actual.is_symlink(): kind = 'link'
        elif actual.is_dir(): kind = 'directory'
        elif actual.is_file(): kind = 'file'
        else: kind = 'missing'
        if kind != 'missing':
            stat = actual.lstat()
            self.ownership[relative] = [stat.st_uid, stat.st_gid]
            saved.parent.mkdir(parents=True, exist_ok=True)
            if kind == 'directory': shutil.copytree(actual, saved, symlinks=True)
            else: shutil.copy2(actual, saved, follow_symlinks=False)
        self.entries[relative] = kind

    def finish(self, metadata):
        write(self.destination/'manifest.json', json.dumps({'files': self.entries, 'ownership': self.ownership,
                                                          **metadata}, indent=2)+'\n', 0o600)

    @staticmethod
    def restore(destination, root=Path('/')):
        manifest = json.loads((destination/'manifest.json').read_text())
        # Trusted administrator-owned manifest, but still reject path traversal.
        for relative, kind in manifest['files'].items():
            if Path(relative).is_absolute() or '..' in Path(relative).parts: raise ValueError('Invalid backup path')
            actual = root/relative
            if actual.is_symlink() or actual.is_file(): actual.unlink()
            elif actual.is_dir(): shutil.rmtree(actual)
            if kind != 'missing':
                saved = destination/'files'/relative
                actual.parent.mkdir(parents=True, exist_ok=True)
                if kind == 'directory': shutil.copytree(saved, actual, symlinks=True)
                else: shutil.copy2(saved, actual, follow_symlinks=False)
                owner = manifest.get('ownership', {}).get(relative)
                if owner is not None: os.chown(actual, *owner, follow_symlinks=False)
        return manifest


def package_command(family):
    recipes = {
        'arch': ['pacman', '-S', '--needed', '--noconfirm', 'greetd', 'gnome-keyring', 'xorg-xinit'],
        'fedora': ['dnf', 'install', '-y', 'greetd', 'gnome-keyring', 'gnome-keyring-pam', 'xorg-x11-xinit'],
        'debian': ['apt-get', 'install', '-y', 'greetd', 'gnome-keyring', 'libpam-gnome-keyring', 'xinit'],
    }
    if family not in recipes: raise RuntimeError('Fusion sign-in supports the installer\'s Arch, Fedora and Debian targets.')
    return recipes[family]


def family():
    data = platform.freedesktop_os_release()
    names = [data.get('ID', ''), *data.get('ID_LIKE', '').split()]
    return next((group for group, values in [('arch', ('arch', 'cachyos', 'manjaro')),
                 ('fedora', ('fedora',)), ('debian', ('debian', 'ubuntu'))] if any(n in values for n in names)), None)


def keyring_pam(content, wallet=None):
    """Keep the distribution stack; add optional hooks, including partially configured cases."""
    for module in ['pam_gnome_keyring.so', *([wallet] if wallet else [])]:
        for kind in ('auth', 'session'):
            pattern = re.compile(r'^([ \t]*-?'+kind+r'[ \t]+[^\n#]*\b'+re.escape(module)+r'\b[^\n#]*)(.*)$', re.MULTILINE)
            match = pattern.search(content)
            if not match:
                content += '\n'+kind+' optional '+module+(' auto_start' if kind == 'session' else '')+'\n'
            elif kind == 'session' and 'auto_start' not in match.group(1).split():
                content = content[:match.start()]+match.group(1).rstrip()+' auto_start '+match.group(2)+content[match.end():]
    return content


def configuration(greetd_binary='/usr/bin/greetd'):
    return {
        Path('/etc/xetal-fusion-login/greetd.toml'): '''[terminal]
vt = 1
switch = true
[general]
source_profile = false
[default_session]
command = "/usr/bin/start-hyprland -- --config /etc/xetal-fusion-login/hyprland.conf"
user = "fusion-greeter"
''',
        Path('/etc/xetal-fusion-login/hyprland.conf'): '''# Dedicated sign-in compositor: no user desktop, plugins, terminals or key bindings.
monitor = , preferred, auto, auto
exec-once = /usr/local/lib/xetal-fusion-login/greeter-session.sh
env = QT_QPA_PLATFORM,wayland
env = XDG_CURRENT_DESKTOP,Hyprland
env = XDG_SESSION_TYPE,wayland
general {
    border_size = 0
    gaps_in = 0
    gaps_out = 0
}
decoration {
    rounding = 0
    shadow {
        enabled = false
    }
}
animations {
    enabled = false
}
misc {
    disable_hyprland_logo = true
    disable_splash_rendering = true
    force_default_wallpaper = 0
    background_color = rgb(101820)
}
input {
    kb_layout = us
}
''',
        Path('/etc/systemd/system')/UNIT: '''[Unit]
Description=Hyper Fusion sign-in
After=systemd-user-sessions.service plymouth-quit-wait.service
Conflicts=getty@tty1.service
After=getty@tty1.service
[Service]
ExecStart=@GREETD@ --config /etc/xetal-fusion-login/greetd.toml
Restart=on-failure
RestartSec=2
IgnoreSIGPIPE=no
SendSIGHUP=yes
KillMode=mixed
TimeoutStopSec=30
[Install]
WantedBy=graphical.target
Alias=display-manager.service
'''.replace('@GREETD@', greetd_binary)}


def install(source, username, skip_packages=False):
    source = source.resolve(strict=True)
    account = pwd.getpwnam(username)
    if account.pw_uid < 1000: raise RuntimeError('Select a regular desktop account.')
    if not (source/'login/app.py').is_file(): raise RuntimeError('Missing Fusion sign-in source files.')
    BASE.mkdir(parents=True, exist_ok=True, mode=0o755)
    backups = BASE/'backups'; backups.mkdir(exist_ok=True, mode=0o700)
    backups.chmod(0o700)
    destination = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-'), dir=backups))
    previous = json.loads(STATE.read_text()) if STATE.is_file() else {}
    backup = Backup(destination)
    paths = [*SYSTEM_PATHS, STATE, Path(account.pw_dir)/'.zprofile']
    manager = Path('/etc/systemd/system/display-manager.service')
    previous_manager = manager.resolve().name if manager.is_symlink() else None
    # Include every enablement link that disabling the old manager may remove.
    for path in Path('/etc/systemd/system').rglob('*'):
        if path.is_symlink() and path.resolve().name in filter(None, (previous_manager, 'greetd.service', UNIT)):
            paths.append(path)
    # The new enablement link must also be recorded when it did not exist.
    paths.append(Path('/etc/systemd/system/graphical.target.wants')/UNIT)
    for path in paths: backup.save(path)
    metadata = {'previous_target': subprocess.check_output(['systemctl', 'get-default'], text=True).strip(),
                'previous_manager': previous_manager}
    backup.finish(metadata)
    print('Fusion sign-in backup: '+str(destination), flush=True)
    try:
        if not skip_packages:
            # Package post-install scripts must not start a second greeter in this session.
            run(['systemctl', 'mask', '--runtime', 'greetd.service'])
            try: run(package_command(family()), env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'})
            finally:
                runtime_mask = Path('/run/systemd/system/greetd.service')
                if runtime_mask.is_symlink(): runtime_mask.unlink()
                saved_mask = destination/'files/run/systemd/system/greetd.service'
                if saved_mask.is_symlink(): shutil.copy2(saved_mask, runtime_mask, follow_symlinks=False)
                run(['systemctl', 'daemon-reload'])
        greetd_binary = shutil.which('greetd')
        if not greetd_binary or not shutil.which('gnome-keyring-daemon'):
            raise RuntimeError('Fusion sign-in needs greetd and GNOME Keyring. Install them and retry.')
        try: greeter = pwd.getpwnam('fusion-greeter')
        except KeyError:
            run(['useradd', '--system', '--create-home', '--home-dir', str(BASE/'greeter'),
                 '--shell', '/bin/sh', 'fusion-greeter'])
            greeter = pwd.getpwnam('fusion-greeter')
        CODE.mkdir(parents=True, exist_ok=True, mode=0o755)
        CODE.chmod(0o755)
        for item in (source/'login').glob('*.py'):
            if item.name.startswith('test_'): continue
            shutil.copy2(item, CODE/item.name); os.chmod(CODE/item.name, 0o644)
        os.chmod(CODE/'launch.py', 0o755)
        shutil.copy2(__file__, CODE/'system_setup.py'); os.chmod(CODE/'system_setup.py', 0o755)
        shutil.copy2(source/'theme/palettes.json', CODE/'palettes.json')
        shutil.copy2(source/'theme/assets/account.gif', CODE/'account.gif')
        (CODE/'palettes.json').chmod(0o644); (CODE/'account.gif').chmod(0o644)
        (CODE/'fonts').mkdir(exist_ok=True)
        (CODE/'fonts').chmod(0o755)
        for item in (source/'assets/fonts').glob('Inter-*'):
            shutil.copy2(item, CODE/'fonts'/item.name)
            (CODE/'fonts'/item.name).chmod(0o644)
        write(CODE/'greeter-session.sh', '''#!/bin/sh
/usr/bin/python3 /usr/local/lib/xetal-fusion-login/app.py
result=$?
# A successful start_session takes effect when this greeter compositor exits.
/usr/bin/hyprctl dispatch exit >/dev/null 2>&1
exit "$result"
''', 0o755)
        for path, text in configuration(greetd_binary).items(): write(path, text)
        # Catch missing Qt modules and unreadable system-owned code before enabling boot changes.
        run(['runuser', '-u', 'fusion-greeter', '--', '/usr/bin/python3', '-c',
             'import sys; sys.path.insert(0, "/usr/local/lib/xetal-fusion-login"); import app'])
        pam = Path('/etc/pam.d/greetd')
        if not pam.is_file(): raise RuntimeError('The greetd package did not supply its PAM configuration.')
        content = pam.read_text()
        wallet = None
        for module in ('pam_kwallet5.so', 'pam_kwallet6.so'):
            if any((Path(folder)/module).is_file() for folder in
                    ('/usr/lib/security', '/usr/lib64/security', '/usr/lib/x86_64-linux-gnu/security')):
                wallet = module
                break
        updated = keyring_pam(content, wallet)
        if updated != content: write(pam, updated)
        profiles = BASE/'profiles'; profiles.mkdir(exist_ok=True, mode=0o755)
        for entry in pwd.getpwall():
            if not 1000 <= entry.pw_uid < 65534 or Path(entry.pw_shell).name in ('false', 'nologin'): continue
            folder = profiles/str(entry.pw_uid)
            folder.mkdir(exist_ok=True, mode=0o755); os.chown(folder, entry.pw_uid, entry.pw_gid)
            # Read/copy each person's artwork with that person's permissions, never root's.
            run(['runuser', '-u', entry.pw_name, '--', '/usr/bin/python3', str(CODE/'profile.py'),
                 '--root', str(Path(entry.pw_dir)/'.config/hypr'), '--destination', str(folder)])
        # Render as the real greeter account: check Qt, fonts, palettes and artwork permissions.
        # This is a non-authenticating offscreen preview; it never opens a login session.
        run(['runuser', '-u', 'fusion-greeter', '--', 'env', 'QT_QPA_PLATFORM=offscreen',
             '/usr/bin/python3', str(CODE/'app.py'), '--preview', '--output',
             str(Path(greeter.pw_dir)/'.cache/fusion-sign-in-preview.png')])
        # Migrate only the exact tty1 autologin files created earlier for this VM.
        old_dropin = Path('/etc/systemd/system/getty@tty1.service.d/99-xetal-autologin.conf')
        old_dropin.unlink(missing_ok=True)
        zprofile = Path(account.pw_dir)/'.zprofile'
        if zprofile.is_file():
            content = zprofile.read_text()
            begin, end = '# BEGIN xetal tty1 Hyprland autostart', '# END xetal tty1 Hyprland autostart'
            if begin in content and end in content:
                before, rest = content.split(begin, 1)
                _, after = rest.split(end, 1)
                write(zprofile, before+after, zprofile.stat().st_mode & 0o777)
                os.chown(zprofile, account.pw_uid, account.pw_gid)
        for unit in dict.fromkeys(filter(None, (previous_manager, 'greetd.service'))):
            if unit != UNIT: run(['systemctl', 'disable', unit])
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', UNIT])
        run(['systemctl', 'set-default', 'graphical.target'])
        write(STATE, json.dumps({'enabled': True, 'original_backup': previous.get('original_backup', str(destination)),
                               'latest_backup': str(destination), 'user': username}, indent=2)+'\n')
        print('Fusion sign-in is ready for the next boot. The current desktop was not restarted.', flush=True)
        print('Recovery: sudo /usr/local/lib/xetal-fusion-login/system_setup.py --restore original', flush=True)
    except BaseException:
        Backup.restore(destination)
        run(['systemctl', 'daemon-reload'])
        print('Fusion sign-in setup failed; original configuration restored.', file=sys.stderr)
        raise


def restore(value):
    if value == 'original':
        value = json.loads(STATE.read_text())['original_backup']
    destination = Path(value).resolve(strict=True)
    if not destination.is_relative_to((BASE/'backups').resolve()): raise RuntimeError('Select a Fusion sign-in backup.')
    Backup.restore(destination)
    run(['systemctl', 'daemon-reload'])
    print('Previous login configuration restored. Reboot when ready. Backups remain at '+str(destination))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--user')
    parser.add_argument('--skip-packages', action='store_true')
    parser.add_argument('--restore')
    args = parser.parse_args()
    if os.geteuid() != 0: raise RuntimeError('Run this system configuration step with sudo.')
    os.umask(0o022)
    if not args.restore and not (args.source and args.user):
        parser.error('--source and --user, or --restore, are required')
    BASE.mkdir(parents=True, exist_ok=True, mode=0o755)
    with (BASE/'setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.restore: restore(args.restore)
        else: install(args.source, args.user, args.skip_packages)


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print('Fusion sign-in: '+str(error), file=sys.stderr)
        raise SystemExit(1)
