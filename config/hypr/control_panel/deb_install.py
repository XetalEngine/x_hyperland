#!/usr/bin/env python3
"""Prepare debtap completely, then convert and install one .deb in a terminal."""
import argparse
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tempfile

TOOLS = {'pactree':'pacman-contrib', 'pkgfile':'pkgfile', 'ar':'binutils',
         'readelf':'binutils', 'fakeroot':'fakeroot', 'curl':'curl', 'gzip':'gzip',
         'gawk':'gawk', 'tar':'tar', 'bsdtar':'libarchive', 'file':'file',
         'which':'which', 'namcap':'namcap', 'xz':'xz', 'zstd':'zstd'}
# Debtap can exit zero after failed commands. Check the outputs it actually
# consumes, including the base list that becomes just a newline without pactree.
DATABASES = ('debian-main-packages-files', 'debian-non-free-packages-files',
             'debian-contrib-packages-files', 'ubuntu-packages-files',
             'aur-packages', 'virtual-packages', 'extended-base-packages-list')
# Debtap 3.6.3 requires a numbered pkgfile cache suffix, rejecting the current
# repo.files layout. Replace only that known probe in a disposable copy; query
# pkgfile itself so a missing/corrupt database still fails the original guard.
LEGACY_CACHE_PROBE = b"ls /var/cache/pkgfile | grep -E '*.files?(.[[:digit:]]{3})'"


def run(args, *, cwd=None, capture=False, stdin=None):
    if not capture:print('\n== '+shlex.join(map(str,args)),flush=True)
    result=subprocess.run(list(map(str,args)),cwd=cwd,text=True,stdin=stdin,
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


def converter(work):
    executable=shutil.which('debtap')
    if not executable:raise RuntimeError('The debtap command is no longer available.')
    source=Path(executable).read_bytes()
    if LEGACY_CACHE_PROBE not in source:return ['debtap']
    adapted=work/'debtap-compat'
    adapted.write_bytes(source.replace(LEGACY_CACHE_PROBE,b'pkgfile -l pacman',1))
    print('== Using debtap compatibility for current and older pkgfile databases.',flush=True)
    return ['bash',str(adapted)]


def payload_paths(listing):
    """Read archive names without extracting or executing package contents."""
    paths=set()
    for name in listing.splitlines():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:
            raise RuntimeError('The package contains an unsafe file path: '+name)
        if not path.parts or name.endswith('/') or str(path) in ('.PKGINFO','.BUILDINFO','.MTREE','.INSTALL'):
            continue
        paths.add(str(path))
    return paths


def application_files(paths):
    # Match debtap's Arch filesystem moves for executable directories. /opt
    # and application-menu entries must survive conversion at their own paths.
    required=set()
    for name in paths:
        for prefix in ('bin/','sbin/','usr/sbin/','usr/games/','usr/local/bin/','usr/local/sbin/','usr/local/games/'):
            if name.startswith(prefix):
                name='usr/bin/'+name[len(prefix):]
                break
        if name.startswith(('opt/','usr/bin/','usr/share/applications/','usr/local/share/applications/')):
            required.add(name)
    return required


def source_payload(deb):
    members=run(['ar','t',deb],capture=True).stdout.splitlines()
    data=[name for name in members if re.fullmatch(r'data\.tar(?:\.(?:gz|xz|bz2|lzma|zst))?',name)]
    if len(data)!=1:
        raise RuntimeError('The .deb must contain exactly one supported data archive.')
    # Stream compressed contents to libarchive. Neither Debian maintainer
    # scripts nor application files run during these checks.
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(['ar','p',str(deb),data[0]],stdout=subprocess.PIPE,stderr=errors) as reader:
            try:
                listing=run(['bsdtar','-tf','-'],stdin=reader.stdout,capture=True).stdout
            finally:
                reader.stdout.close()
            if reader.wait():
                errors.seek(0)
                raise RuntimeError('Could not read the .deb payload: '+errors.read().decode(errors='replace'))
    return payload_paths(listing)


def converted_package(package, original):
    identity=run(['pacman','-Qp','--',package],capture=True).stdout.split()
    if len(identity)!=2 or not re.fullmatch(r'[A-Za-z0-9@_+][A-Za-z0-9@._+\-]*',identity[0]):
        raise RuntimeError('The converted package has no valid package name/version.')
    paths=payload_paths(run(['bsdtar','-tf',package],capture=True).stdout)
    missing=application_files(original)-paths
    if original and not paths:
        raise RuntimeError('Conversion produced an empty package. Nothing was installed.')
    if missing:
        raise RuntimeError('Conversion lost application files. Nothing was installed:\n  '+
                           '\n  '.join(sorted(missing)[:12]))
    print('== Converted package: '+' '.join(identity)+f' ({len(paths)} payload files)',flush=True)
    return identity,application_files(paths)


def verify_installation(identity, required, root=Path('/')):
    name,version=identity
    print('== Verifying installed package and files: '+name,flush=True)
    try:
        installed=run(['pacman','-Q','--',name],capture=True).stdout.split()
    except RuntimeError as error:
        raise RuntimeError('Installation was not verified: '+name+' is not registered with pacman. '+str(error)) from error
    if installed!=identity:
        raise RuntimeError('Installation was not completed: expected '+name+' '+version+
                           ', found '+(' '.join(installed) or 'no installed version')+'.')
    run(['pacman','-Qk','--',name],capture=True)
    missing=[path for path in sorted(required) if not (root/path).exists()]
    if missing:
        raise RuntimeError('The package is registered, but application files are missing or broken:\n  '+
                           '\n  '.join('/'+path for path in missing[:12]))
    launchers=sorted(path for path in required if path.endswith('.desktop') and '/applications/' in path)
    for path in launchers:print('== Verified Apps launcher: /'+path,flush=True)


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
        print('== Checking application files in '+str(deb),flush=True)
        original=source_payload(work/'source.deb')
        print('== Converting '+str(deb),flush=True)
        run([*converter(work),'-q','source.deb'],cwd=work)
        packages=[p for p in work.iterdir() if p.is_file() and re.fullmatch(
            r'.+\.pkg\.tar(?:\.(?:zst|xz|gz|bz2|lz4|lrz|lzo|lz|Z))?',p.name)]
        if len(packages)!=1:
            raise RuntimeError(f'Conversion produced {len(packages)} installable packages; expected one. Nothing was installed.')
        identity,required=converted_package(packages[0],original)
        print('== Installing converted package: '+' '.join(identity)+
              '. Review and confirm the pacman transaction below.',flush=True)
        run(['sudo','pacman','-U',packages[0]],cwd=work)
        verify_installation(identity,required)
    print('\n== Installed successfully: '+' '.join(identity)+'. Package registration and files verified.',flush=True)


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
