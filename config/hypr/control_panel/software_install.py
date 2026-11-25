#!/usr/bin/env python3
"""Install verified official applications for the current user."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile

from software_catalog import vendor_release, VENDOR_MANIFESTS
from software_download import download, emit
from software_favorites import pin_desktop

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {
    'echo': ('Echo', 'echo.desktop'),
    'linuxstudio': ('LinuxStudio', 'linux-studio.desktop'),
    'xmusic': ('XMusic', 'xmusic.desktop'),
    'xvideo': ('XVideo', 'xvideo.desktop'),
}


def preferred(release):
    suffix = '.tar.gz' if release['product'] == 'linuxstudio' else '.run'
    return next((a for a in release['choices'] if a['filename'].endswith(suffix)), None)


def verified(path, artifact):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != artifact['size']: return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == artifact['sha256'].lower()


def run_installer(command, progress=emit):
    # Separate process group permits cancellation without leaving the installer
    # writing in the background. Logs do not share our JSON output channel.
    with tempfile.TemporaryFile(mode='w+b') as log:
        process = subprocess.Popen(list(map(str, command)), stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
        try:
            code = process.wait()
        except BaseException:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
            raise
        log.seek(max(0, log.tell()-16000)); output = log.read().decode(errors='replace').strip()
        if code: raise RuntimeError('Installer failed (exit '+str(code)+').\n'+output)
        if output: progress(dict(type='log', message=output))


def desktop_argument(path):
    value = str(path).replace('%', '%%')
    for c in ('\\', '"', '`', '$'): value = value.replace(c, '\\'+c)
    return '"'+value.replace('\\', '\\\\')+'"'


def install_studio(archive, destination):
    if destination.exists() or destination.is_symlink():
        raise RuntimeError('Linux Studio already has an installation folder. Open the installed app or uninstall it before reinstalling.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.linuxstudio-', dir=destination.parent) as temp:
        stage = Path(temp)
        with tarfile.open(archive, 'r:gz') as package:
            members = package.getmembers()
            if len(members) > 150000 or sum(m.size for m in members) > 12*1024**3:
                raise ValueError('The archive exceeds the installation size limit.')
            # The standard data filter rejects traversal, escaping links,
            # devices and unsafe permissions. Internal library symlinks remain.
            package.extractall(stage, filter='data')
        roots = list(stage.iterdir())
        if len(roots) != 1 or not roots[0].is_dir() or not (roots[0]/'run.sh').is_file() or not (roots[0]/'AppRun').is_file():
            raise ValueError('Linux Studio archive does not contain its expected launcher.')
        roots[0].rename(destination)
    (destination/'run.sh').chmod(0o755); (destination/'AppRun').chmod(0o755)
    icon = next((p for p in (destination/'usr/share/icons').rglob('*') if p.is_file() and p.suffix in ('.png', '.svg')), None)
    icon = icon or next(iter(destination.glob('*.png')), None)
    text = ('[Desktop Entry]\nType=Application\nName=Linux Studio\n'
            'Comment=Write, build and debug C++ projects\nExec='+desktop_argument(destination/'run.sh')+' %F\n'
            'Icon='+str(icon or 'applications-development')+'\nTerminal=false\nCategories=Development;IDE;\n')
    launcher = applications()/'linux-studio.desktop'; launcher.parent.mkdir(parents=True, exist_ok=True)
    from default_apps import atomic_write
    atomic_write(launcher, text, 0o644)
    return launcher


def applications():
    return Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'applications'


def set_music_defaults(destination, progress=emit):
    # XMusic maintains the authoritative list of audio formats. This dedicated
    # command registers those MIME types without starting a player window.
    from gi.repository import Gio
    import default_apps
    state = ROOT/'control_panel/state/default-apps'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state/'change.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run_installer([destination/'run.sh', '--associate-all'], progress)
        app = Gio.DesktopAppInfo.new_from_filename(str(applications()/'xmusic.desktop'))
        types = app.get_supported_types() if app else []
        if not types: raise RuntimeError('XMusic did not register its supported audio formats.')
        # Keep Fusion's isolated app environments consistent with the desktop.
        for path, specific in default_apps.association_paths().items():
            before = default_apps.read(path)
            after = default_apps.updated(before, types, 'xmusic.desktop', specific)
            if before != after:
                default_apps.atomic_write(path, after, path.stat().st_mode & 0o777 if path.exists() else 0o600)


def install(product, *, artifact=None, bundled=None, make_default=False, progress=emit):
    if product not in PRODUCTS: raise ValueError('Unknown application.')
    if os.geteuid() == 0: raise ValueError('Install applications as the desktop user, without sudo.')
    folder, desktop = PRODUCTS[product]
    launcher = applications()/desktop
    destination = Path.home()/'.local/opt'/folder
    cache = Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'hyperfusion/software'
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (cache/(product+'.lock')).open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('This app is already being installed. Wait for that installation to finish.')
        if make_default and product == 'xmusic' and launcher.is_file() and (destination/'run.sh').is_file():
            set_music_defaults(destination, progress); pin_desktop(launcher)
            return launcher
        if artifact is None:
            progress(dict(type='status', message='Checking the latest release…'))
            artifact = preferred(vendor_release(product))
        if artifact is None: raise RuntimeError('An installable Linux release is not currently published. Try again later.')
        filename = artifact['filename']
        if Path(filename).name != filename or not filename.endswith('.tar.gz' if product=='linuxstudio' else '.run'):
            raise ValueError('This format is available as a download only.')
        # Work in a private transaction directory. Public Downloads files are
        # never reused as executable installation inputs.
        with tempfile.TemporaryDirectory(prefix=product+'-', dir=cache) as temp:
            path = Path(temp)/filename
            if bundled is not None:
                shutil.copyfile(bundled, path)
                if not verified(path, artifact): raise ValueError('The bundled installer failed its checksum check.')
            else:
                download(artifact, path, progress=lambda current,total: progress(dict(type='progress', current=current, total=total)))
            progress(dict(type='installing', message='Follow Echo Setup to finish installation.' if product=='echo' else 'Installing '+folder+'…'))
            if product == 'linuxstudio': launcher = install_studio(path, destination)
            else:
                path.chmod(0o700)
                run_installer([path], progress)
            if not launcher.is_file():
                raise RuntimeError('Setup closed without installing an application-menu entry. You can retry Install.')
            if make_default and product == 'xmusic': set_music_defaults(destination, progress)
            warning = ''
            try:
                if not pin_desktop(launcher): warning = 'The app installed, but its launcher could not be added to Favorites.'
            except (OSError, ValueError) as error: warning = 'The app installed, but Favorites could not be updated: '+str(error)
            if warning: progress(dict(type='log', message=warning))
            return launcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, choices=tuple(PRODUCTS))
    parser.add_argument('--make-default', action='store_true')
    parser.add_argument('--bundle', type=Path, help='Pinned offline manifest beside its installer.')
    args = parser.parse_args()
    def cancel(*_): raise InterruptedError('Installation cancelled.')
    signal.signal(signal.SIGTERM, cancel)
    try:
        artifact = json.loads(args.bundle.read_text()) if args.bundle else None
        bundled = args.bundle.parent/artifact['filename'] if artifact else None
        result = install(args.vendor, artifact=artifact, bundled=bundled, make_default=args.make_default)
        emit(dict(type='installed', path=str(result))); return 0
    except (OSError, ValueError, RuntimeError, tarfile.TarError, KeyboardInterrupt, subprocess.SubprocessError) as error:
        emit(dict(type='error', message=str(error) or 'Installation cancelled.')); return 1


if __name__ == '__main__': sys.exit(main())
