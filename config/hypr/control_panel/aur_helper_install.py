#!/usr/bin/env python3
"""Install an explicitly selected AUR helper with normal terminal authentication."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from deb_install import run, install as install_deb


def install(name, *, reinstall=False):
    if name not in ('yay', 'paru'):
        raise ValueError('Choose Yay or Paru.')
    if os.geteuid() == 0:
        raise RuntimeError('Open this installer as your desktop user, without sudo.')
    if shutil.which(name) and not reinstall:
        print(name.title()+' is already installed.', flush=True)
        return
    helper = shutil.which('paru' if name == 'yay' else 'yay')
    if not helper and reinstall:
        helper = shutil.which(name)
    if helper:
        run([helper, '-S', *([] if reinstall else ['--needed']), '--', name])
    else:
        print('Preparing build tools. Review the pacman update below; sudo asks for your password in this terminal.', flush=True)
        run(['sudo', 'pacman', '-Syu', '--needed', 'base-devel', 'git'])
        with tempfile.TemporaryDirectory(prefix='fusion-aur-helper-') as directory:
            source = Path(directory)/name
            run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--depth', '1', '--',
                 'https://aur.archlinux.org/'+name+'.git', source])
            print('\nBuild files from the Arch User Repository:', flush=True)
            for path in [source/'PKGBUILD', source/'.SRCINFO', *sorted(source.glob('*.install'))]:
                if path.is_file():
                    print('\n--- '+path.name+' ---\n'+path.read_text(), flush=True)
            if input('Build and install '+name.title()+' using these files? [y/N] ').strip().lower() not in ('y', 'yes'):
                raise RuntimeError('Installation cancelled before building.')
            run(['makepkg', '-si'], cwd=source)
    if not shutil.which(name):
        raise RuntimeError(name.title()+' was not installed. Review the terminal output above.')
    print('\n'+name.title()+' is installed.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', action='store_true')
    parser.add_argument('--reinstall', action='store_true', help='Reinstall without removing the existing helper first.')
    parser.add_argument('--deb', type=Path, help='After installing both helpers, continue with this Debian package.')
    parser.add_argument('helper', choices=('yay', 'paru', 'both'))
    args = parser.parse_args(argv)
    if args.deb and (args.helper != 'both' or args.reinstall):
        parser.error('--deb requires both helpers and cannot be used with --reinstall')
    code = 0
    try:
        if args.deb and (not args.deb.is_file() or args.deb.suffix.lower() != '.deb'):
            raise ValueError('The selected Debian package is no longer available.')
        # One terminal, one transaction at a time. A failed/declined bootstrap
        # stops here; it must never start a second helper or the .deb installer.
        for name in (('yay', 'paru') if args.helper == 'both' else (args.helper,)):
            install(name, reinstall=args.reinstall)
        if args.deb:
            if not all(shutil.which(name) for name in ('yay', 'paru')):
                raise RuntimeError('Both helpers must finish installing before continuing.')
            install_deb(args.deb)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, EOFError) as error:
        print('\nInstallation stopped: '+str(error), flush=True); code = 1
    except KeyboardInterrupt:
        print('\nInstallation cancelled.', flush=True); code = 130
    if args.wait:
        try:
            input('\nPress Enter to close…')
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == '__main__':
    raise SystemExit(main())
