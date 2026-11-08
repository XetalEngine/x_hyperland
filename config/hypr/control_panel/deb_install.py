#!/usr/bin/env python3
"""Prepare debtap completely, then convert and install one .deb in a terminal."""
import argparse
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from deb_dependencies import AurRepository, MissingRepositoryIndexes, read_control, resolve
from deb_recipes import CHROME, VSCODE, dependency_fields, omitted_application_files

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


def run(args, *, cwd=None, capture=False, stdin=None, package_build=False):
    if not capture:print('\n== '+shlex.join(map(str,args)),flush=True)
    environment=dict(os.environ,LC_ALL='C')
    if package_build:
        # Keep the temporary parent private, but package-created directories
        # need ordinary system permissions. GNU tar must also retain explicit
        # archive modes (private files, group access and setuid sandbox helpers).
        # Scope both settings to this child; never change the desktop's umask.
        environment['TAR_OPTIONS']='--same-permissions'
    result=subprocess.run(list(map(str,args)),cwd=cwd,text=True,stdin=stdin,
                          capture_output=capture,env=environment,
                          umask=0o022 if package_build else -1)
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
            raise RuntimeError('Debtap is not installed. Install Yay or Paru from the Install .deb page, then retry.')
        # AUR builds must run as the desktop user; the helper handles package authentication.
        run([helper,'-S','--needed','debtap'])
        if not shutil.which('debtap'):raise RuntimeError('Debtap installation finished without providing the debtap command.')


def prepare_inspection(check_only=False):
    if not shutil.which('pacman'):
        raise RuntimeError('This .deb converter requires an Arch-based system with pacman.')
    packages=[package for command,package in (('ar','binutils'),('bsdtar','libarchive'))
              if not shutil.which(command)]
    if packages:
        if check_only:
            raise RuntimeError('Dependency inspection needs these tools installed first: '+', '.join(packages)+'.')
        run(['sudo','pacman','-S','--needed',*packages])
        if any(not shutil.which(command) for command in ('ar','bsdtar')):
            raise RuntimeError('Archive inspection tools are still missing.')


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


def converter(work, dependencies=None, package_name=''):
    executable=shutil.which('debtap')
    if not executable:raise RuntimeError('The debtap command is no longer available.')
    source=Path(executable).read_bytes()
    original=source
    if LEGACY_CACHE_PROBE in source:
        source=source.replace(LEGACY_CACHE_PROBE,b'pkgfile -l pacman',1)
        print('== Using debtap compatibility for current and older pkgfile databases.',flush=True)
    if dependencies is not None:
        # Insert BEFORE mtree generation so its metadata hashes describe the
        # actual dependency file. Do not rewrite compressed archives afterwards.
        marker=b'# Generating .MTREE file\n'
        audit_marker=b'rm -rf test.pkg.tar\n'
        if source.count(marker)!=1 or source.count(audit_marker)!=1:
            raise RuntimeError('This debtap version has an unsupported packaging layout; conversion was not started.')
        # Preserve namcap's additional native-library requirements. The first
        # command in its pipeline must succeed; grep legitimately returns 1
        # when there are no findings, so blanket `set -e` is not appropriate.
        native=work/'fusion-native-checks'
        audit=("if [[ ${PIPESTATUS[0]} != 0 ]]; then echo 'Native library inspection failed.' >&2; exit 1; fi\n"
               f"cp namcap-checks {shlex.quote(str(native))} || exit 1\n").encode()
        source=source.replace(audit_marker,audit+audit_marker,1)
        metadata=work/'fusion-dependencies'
        metadata.write_text(''.join('depend = '+dependency+'\n' for dependency in dependencies))
        insertion=("# Use requirements resolved from the original Debian control file.\n"
                   "awk '$1 != \"depend\" {print}' .PKGINFO > .PKGINFO.fusion || exit 1\n"
                   f"cat {shlex.quote(str(metadata))} >> .PKGINFO.fusion || exit 1\n"
                   "awk '$1 == \"dependency-detected-not-included\" {print \"depend = \" $2}' "
                   f"{shlex.quote(str(native))} >> .PKGINFO.fusion || exit 1\n"
                   "awk '$1 != \"depend\" || !seen[$3]++' .PKGINFO.fusion > .PKGINFO || exit 1\n"
                   "rm .PKGINFO.fusion || exit 1\n"
                   + shlex.join([sys.executable,str(Path(__file__).with_name('deb_recipes.py')),
                                 '--package',package_name,'--root','.']) + ' || exit 1\n\n').encode()
        source=source.replace(marker,insertion+marker,1)
    if source==original:return ['debtap']
    adapted=work/'debtap-compat'
    adapted.write_bytes(source)
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


def arch_path(name):
    for prefix in ('bin','sbin','usr/sbin','usr/games','usr/local/bin','usr/local/sbin','usr/local/games'):
        if name==prefix or name.startswith(prefix+'/'):
            return 'usr/bin'+name[len(prefix):]
    return name


def application_files(paths):
    # Match debtap's Arch filesystem moves for executable directories. /opt
    # and application-menu entries must survive conversion at their own paths.
    # VS Code stores its executable and runtime under /usr/share/code.
    required=set()
    for name in paths:
        name=arch_path(name)
        if name.startswith(('opt/','usr/bin/','usr/share/applications/','usr/local/share/applications/',
                            'usr/share/code/')):
            required.add(name)
    return required


class Payload(set):
    """Payload filenames plus archived permissions, without extracting files."""
    def __init__(self, entries):
        self.entries=entries
        super().__init__(name for name,(kind,mode) in entries.items() if kind!='dir')


def payload_manifest(archive, *, stdin=None):
    # libarchive reads all supported Debian/Arch compression formats. Mtree
    # escapes whitespace/backslashes in names and includes directory modes;
    # a plain filename listing misses an inaccessible /opt/vendor parent.
    listing=run(['bsdtar','-cf','-','--format=mtree','--options=!all,type,mode',
                 '@'+str(archive)],stdin=stdin,capture=True).stdout
    entries={}
    for line in listing.splitlines():
        if not line or line.startswith('#'):continue
        tokens=line.split()
        name=re.sub(r'\\([0-7]{3})',lambda match:chr(int(match[1],8)),tokens[0])
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:
            raise RuntimeError('The package contains an unsafe file path: '+name)
        if not path.parts or str(path) in ('.PKGINFO','.BUILDINFO','.MTREE','.INSTALL'):continue
        attrs=dict(token.split('=',1) for token in tokens[1:] if '=' in token)
        if not attrs.get('type') or not re.fullmatch(r'[0-7]{1,4}',attrs.get('mode','')):
            raise RuntimeError('Could not inspect archived permissions for '+name)
        entries[str(path)]=(attrs['type'],int(attrs['mode'],8))
    return Payload(entries)


def verify_permissions(original, converted):
    changed=[]
    for name,(kind,mode) in getattr(original,'entries',{}).items():
        target=arch_path(name)
        actual=converted.entries.get(target)
        if actual and kind in ('file','dir') and actual[0]==kind and actual[1]!=mode:
            changed.append(f'/{target}: expected {mode:04o}, got {actual[1]:04o}')
    if changed:
        raise RuntimeError('Conversion changed package file permissions. Nothing was installed:\n  '+
                           '\n  '.join(changed[:12]))


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
                payload=payload_manifest('-',stdin=reader.stdout)
            finally:
                reader.stdout.close()
            if reader.wait():
                errors.seek(0)
                raise RuntimeError('Could not read the .deb payload: '+errors.read().decode(errors='replace'))
    return payload


def converted_package(package, original, *, omitted=()):
    identity=run(['pacman','-Qp','--',package],capture=True).stdout.split()
    if len(identity)!=2 or not re.fullmatch(r'[A-Za-z0-9@_+][A-Za-z0-9@._+\-]*',identity[0]):
        raise RuntimeError('The converted package has no valid package name/version.')
    paths=payload_manifest(package)
    missing=application_files(original)-set(omitted)-paths
    if original and not paths:
        raise RuntimeError('Conversion produced an empty package. Nothing was installed.')
    if missing:
        raise RuntimeError('Conversion lost application files. Nothing was installed:\n  '+
                           '\n  '.join(sorted(missing)[:12]))
    verify_permissions(original,paths)
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


def check_dependencies(deb, fields=None, aur=None):
    fields=fields or read_control(deb)
    print('== Checking '+fields['package']+' '+fields['version']+' ('+fields['architecture']+')',flush=True)
    if fields['package']==CHROME:
        print('== Chrome Arch recipe: package-owned icons and native hooks; Debian updater scripts and dpkg prerequisite are replaced.',flush=True)
    elif fields['package']==VSCODE:
        print('== VS Code Arch recipe: package-owned code launcher and native desktop, icon and MIME hooks replace Debian setup scripts.',flush=True)
    dependencies,rows=resolve(dependency_fields(fields), aur=aur)
    print('== Debian requirements → Arch packages:\n  '+('\n  '.join(rows) or 'No declared dependencies.'),flush=True)
    print('== Version checks use upstream minimums; Debian packaging revisions are not Arch revisions.',flush=True)
    return dependencies


def verify_dependencies(package, dependencies, *, plan=True):
    metadata=run(['bsdtar','-xOf',package,'.PKGINFO'],capture=True).stdout
    actual=[line.partition(' = ')[2] for line in metadata.splitlines() if line.startswith('depend = ')]
    if sorted(actual)!=sorted(dependencies):
        raise RuntimeError('The converted package does not contain the reviewed dependency list. Nothing was installed.')
    # Resolve the COMPLETE native transaction, including dependencies of the
    # dependencies. This does not install/download packages or disable checks.
    if plan:
        run(['pacman','-Up','--print-format','%n %v','--',package],capture=True)


def install_aur_dependencies(dependencies):
    if not dependencies:
        return
    helper=shutil.which('yay') or shutil.which('paru')
    if not helper:
        raise RuntimeError('This application needs AUR dependencies. Yay and Paru are not installed. '
                           'Use Install Yay or Install Paru on the Install .deb page, then retry.')
    names=list(dict.fromkeys(re.split(r'[<>=]',dependency,maxsplit=1)[0] for dependency in dependencies))
    print('== AUR dependencies: '+', '.join(dependencies)+'. Review the helper’s build files and transaction below.',flush=True)
    run([helper,'-S','--needed','--asdeps','--',*names])
    # A helper can finish without installing a declined build. Ask pacman to
    # confirm that the actual installed versions satisfy every requirement.
    run(['pacman','-T','--',*dependencies],capture=True)


def native_dependencies(work):
    path=work/'fusion-native-checks'
    if not path.exists():
        raise RuntimeError('Conversion did not produce the native-library inspection result.')
    dependencies=[]
    for line in path.read_text().splitlines():
        if line.startswith('dependency-detected-not-included '):
            name=line.split(' ',1)[1].strip()
            if not re.fullmatch(r'[A-Za-z0-9@_+][A-Za-z0-9@._+\-]*',name):
                raise RuntimeError('Unexpected native-library dependency: '+name)
            if name not in dependencies:dependencies.append(name)
    return dependencies


def install(deb, *, check_only=False, convert_only=None):
    if os.geteuid()==0:raise RuntimeError('Open the .deb installer as your desktop user, without sudo.')
    deb=Path(deb).expanduser().resolve(strict=True)
    if not deb.is_file() or deb.suffix.lower()!='.deb':raise ValueError('Choose an existing .deb package.')
    prepare_inspection(check_only)
    with tempfile.TemporaryDirectory(prefix='fusion-debtap-') as directory:
        work=Path(directory)
        # Debtap itself uses shell word splitting on arguments. A neutral local
        # filename also supports downloads with spaces, quotes or shell symbols.
        shutil.copyfile(deb,work/'source.deb')
        fields=read_control(work/'source.deb')
        aur=AurRepository()
        helper=shutil.which('yay') or shutil.which('paru')
        print('== AUR helper: '+(Path(helper).name if helper else
              'Yay and Paru are not installed. Install either from the Install .deb page for AUR packages.'),flush=True)
        try:
            dependencies=check_dependencies(work/'source.deb',fields,aur=aur)
        except MissingRepositoryIndexes:
            if check_only or convert_only is not None:
                raise
            print('== Arch package indexes have not been initialized. Connect to the internet.\n'
                  '== Pacman will refresh them and offer a full system update. Review its package list and confirmation below.\n'
                  '== The .deb dependency check will run again after the update.',flush=True)
            # Never initialize a live system with -Sy followed by individual
            # packages: that can create an unsupported partial Arch upgrade.
            run(['sudo','pacman','-Syu'])
            dependencies=check_dependencies(work/'source.deb',fields,aur=aur)
        if check_only:
            print('== Dependency mapping check passed. No packages were installed or converted.',flush=True)
            return
        if aur.selected and not helper and convert_only is None:
            raise RuntimeError('AUR dependencies were found, but Yay and Paru are not installed. '
                               'Install either helper from the Install .deb page, then retry.')
        prepare_tools()
        prepare_database()
        print('== Checking application files in '+str(deb),flush=True)
        original=source_payload(work/'source.deb')
        print('== Converting '+str(deb),flush=True)
        run([*converter(work,dependencies,fields['package']),'-Q','source.deb'],cwd=work,package_build=True)
        packages=[p for p in work.iterdir() if p.is_file() and re.fullmatch(
            r'.+\.pkg\.tar(?:\.(?:zst|xz|gz|bz2|lz4|lrz|lzo|lz|Z))?',p.name)]
        if len(packages)!=1:
            raise RuntimeError(f'Conversion produced {len(packages)} installable packages; expected one. Nothing was installed.')
        identity,required=converted_package(packages[0],original,
                                           omitted=omitted_application_files(fields['package']))
        native=native_dependencies(work)
        if native:print('== Native library requirements: '+', '.join(native),flush=True)
        dependencies=list(dict.fromkeys([*dependencies,*native]))
        # Validate the archive before building any additional AUR dependencies.
        verify_dependencies(packages[0],dependencies,plan=not aur.selected)
        if convert_only is not None:
            destination=Path(convert_only).expanduser().resolve()
            destination.mkdir(parents=True,exist_ok=True)
            target=destination/packages[0].name
            # Do not overwrite a previous result, especially an original .deb.
            with target.open('xb') as output,packages[0].open('rb') as source:
                shutil.copyfileobj(source,output)
            if aur.selected:
                print('== Required AUR packages were not installed: '+', '.join(aur.selected),flush=True)
            print('== Converted package saved: '+str(target)+'. The application was not installed.',flush=True)
            return
        if aur.selected:
            install_aur_dependencies(aur.selected)
            verify_dependencies(packages[0],dependencies)
        print('== Installing converted package: '+' '.join(identity)+
              '. Review and confirm the pacman transaction below.',flush=True)
        run(['sudo','pacman','-U',packages[0]],cwd=work)
        verify_installation(identity,required)
    print('\n== Installed successfully: '+' '.join(identity)+'. Package registration and files verified.',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait',action='store_true',help='Keep the terminal open after completion or failure.')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--check',action='store_true',help='Only check dependency mappings; do not install tools or packages.')
    mode.add_argument('--convert-only',type=Path,metavar='DIRECTORY',
                      help='Prepare conversion tools and save a checked native package without installing the application.')
    parser.add_argument('deb',type=Path)
    args=parser.parse_args(argv)
    code=0
    try:install(args.deb,check_only=args.check,convert_only=args.convert_only)
    except KeyboardInterrupt:
        print('\n== Installation cancelled.',flush=True);code=130
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print('\n== Installation stopped: '+str(error),flush=True);code=1
    if args.wait:
        try:input('\nPress Enter to close…')
        except (EOFError,KeyboardInterrupt):pass
    return code


if __name__=='__main__':raise SystemExit(main())
