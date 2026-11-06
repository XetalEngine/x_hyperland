#!/usr/bin/env python3
"""Prepare debtap completely, then convert and install one .deb in a terminal."""
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

TOOLS = {'pactree':'pacman-contrib', 'pkgfile':'pkgfile', 'ar':'binutils',
         'readelf':'binutils', 'fakeroot':'fakeroot', 'curl':'curl', 'gzip':'gzip',
         'gawk':'gawk', 'tar':'tar', 'xz':'xz', 'zstd':'zstd'}
# Debtap can exit zero after failed commands. Check the outputs it actually
# consumes, including the base list that becomes just a newline without pactree.
DATABASES = ('debian-main-packages-files', 'debian-non-free-packages-files',
             'debian-contrib-packages-files', 'ubuntu-packages-files',
             'aur-packages', 'virtual-packages', 'extended-base-packages-list')


def run(args, *, cwd=None, capture=False):
    if not capture:print('\n== '+shlex.join(map(str,args)),flush=True)
    result=subprocess.run(list(map(str,args)),cwd=cwd,text=True,
                          capture_output=capture,env=dict(os.environ,LC_ALL='C'))
    if result.returncode:
        detail=(result.stderr or result.stdout or '').strip() if capture else 'See the command output above.'
        raise RuntimeError(f'{shlex.join(map(str,args))} failed (exit {result.returncode}). {detail}')
    return result


def prepare_tools():
    if not shutil.which('pacman'):
        raise RuntimeError('This .deb converter requires an Arch-based system with pacman.')
    if not shutil.which('sudo'):
        raise RuntimeError('Administrator authentication requires sudo in this terminal.')
    packages=list(dict.fromkeys(package for command,package in TOOLS.items() if not shutil.which(command)))
    if packages:run(['sudo','pacman','-S','--needed',*packages])
    missing=[command for command in TOOLS if not shutil.which(command)]
    if missing:raise RuntimeError('Conversion tools are still missing: '+', '.join(missing))
    if not shutil.which('debtap'):
        helper=shutil.which('yay') or shutil.which('paru')
        if not helper:
            raise RuntimeError('Debtap is not installed. Install Yay or Paru from its Control Panel page, then retry.')
        # AUR builds must run as the desktop user; the helper handles package authentication.
        run([helper,'-S','--needed','debtap'])
        if not shutil.which('debtap'):raise RuntimeError('Debtap installation finished without providing the debtap command.')


def has_data(path):
    try:
        with path.open('rb') as stream:return bool(stream.read(4096).strip())
    except OSError:return False


def database_problems(cache=Path('/var/cache/debtap'), pkgcache=Path('/var/cache/pkgfile')):
    problems=['missing or empty '+str(cache/name) for name in DATABASES if not has_data(cache/name)]
    indexes=[p for p in pkgcache.glob('*') if re.fullmatch(r'.+\.files(?:\.(?:gz|xz|zst|bz2|[0-9]{3}))?',p.name)]
    if not any(has_data(p) for p in indexes):problems.append('pkgfile repository indexes are missing or empty')
    return problems


def prepare_database(cache=Path('/var/cache/debtap'), pkgcache=Path('/var/cache/pkgfile')):
    problems=database_problems(cache,pkgcache)
    if not problems:
        try:
            if not run(['pkgfile','-l','pacman'],capture=True).stdout.strip():
                problems.append('pkgfile cannot read the pacman file list')
        except RuntimeError as error:problems.append(str(error))
    if problems:
        print('== Preparing debtap and pkgfile databases:\n  '+'\n  '.join(problems),flush=True)
        run(['sudo','debtap','-u'])
        problems=database_problems(cache,pkgcache)
        if problems:
            raise RuntimeError('Debtap database update is incomplete; conversion was not started:\n  '+'\n  '.join(problems))
        if not run(['pkgfile','-l','pacman'],capture=True).stdout.strip():
            raise RuntimeError('Debtap update finished, but pkgfile still cannot read the pacman file list.')


def install(deb):
    if os.geteuid()==0:raise RuntimeError('Open the .deb installer as your desktop user, without sudo.')
    deb=Path(deb).expanduser().resolve(strict=True)
    if not deb.is_file() or deb.suffix.lower()!='.deb':raise ValueError('Choose an existing .deb package.')
    prepare_tools()
    prepare_database()
    with tempfile.TemporaryDirectory(prefix='fusion-debtap-') as directory:
        work=Path(directory)
        # Debtap itself uses shell word splitting on arguments. A neutral local
        # filename also supports downloads with spaces, quotes or shell symbols.
        shutil.copyfile(deb,work/'source.deb')
        print('== Converting '+str(deb),flush=True)
        run(['debtap','-q','source.deb'],cwd=work)
        packages=[p for p in work.iterdir() if p.is_file() and re.fullmatch(
            r'.+\.pkg\.tar(?:\.(?:zst|xz|gz|bz2|lz4|lrz|lzo|lz|Z))?',p.name)]
        if len(packages)!=1:
            raise RuntimeError(f'Conversion produced {len(packages)} installable packages; expected one. Nothing was installed.')
        run(['sudo','pacman','-U',packages[0]],cwd=work)
    print('\n== Installed successfully. The package is now managed by pacman (PKG Uninstall).',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait',action='store_true',help='Keep the terminal open after completion or failure.')
    parser.add_argument('deb',type=Path)
    args=parser.parse_args(argv)
    code=0
    try:install(args.deb)
    except KeyboardInterrupt:
        print('\n== Installation cancelled.',flush=True);code=130
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print('\n== Installation stopped: '+str(error),flush=True);code=1
    if args.wait:
        try:input('\nPress Enter to close…')
        except (EOFError,KeyboardInterrupt):pass
    return code


if __name__=='__main__':raise SystemExit(main())
