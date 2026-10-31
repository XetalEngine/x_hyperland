"""Download the tested Arch compositor and request normal administrator auth."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'config/hypr/runtime'))
import runtime_policy as policy

PIN = Path('/etc/pacman.d/xetal-hyprland.conf')
TRANSACTION = None


def administrator():
    if not shutil.which('sudo'):
        raise RuntimeError('Setup needs sudo for system packages. Install sudo and run Setup as your desktop user.')
    if os.environ.get('XETAL_SETUP_GUI') == '1':
        os.environ['SUDO_ASKPASS'] = str(ROOT/'installer/askpass.py')
        return ['sudo', '-A']
    return ['sudo']


def pinned(target=None):
    target = target or policy.manifest()
    try:
        if PIN.read_text() != pin_text(target): return False
        result = subprocess.run(['pacman-conf','IgnorePkg'], capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and 'hyprland' in result.stdout.split()
    except (OSError, subprocess.SubprocessError):
        return False


def pin_text(target):
    return '# Managed by Xetal Setup: Hyprland '+target['hyprland']+'\nIgnorePkg = hyprland\n'


def download(target, cache):
    cache.mkdir(parents=True, exist_ok=True)
    for suffix, key in [('', 'package_sha256'), ('.sig', 'signature_sha256')]:
        destination = cache/(policy.filename(target)+suffix)
        if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == target[key]:
            continue
        local = Path('/var/cache/pacman/pkg')/destination.name
        temporary = destination.with_suffix(destination.suffix+'.part')
        try:
            if local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest() == target[key]:
                shutil.copyfile(local, temporary)
            else:
                print('Downloading '+destination.name, flush=True)
                with urlopen(policy.package_url(target)+suffix, timeout=90) as source, temporary.open('wb') as output:
                    while chunk := source.read(1024*1024): output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != target[key]:
                raise RuntimeError('Downloaded compositor checksum does not match: '+destination.name)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return cache/policy.filename(target)


def previous_package(cache):
    """Keep a signed recovery package before replacing an existing compositor."""
    result = subprocess.run(['pacman', '-Q', 'hyprland'], capture_output=True, text=True)
    if result.returncode: return None
    name, version = result.stdout.split()
    import re
    if name != 'hyprland' or not re.fullmatch(r'[0-9][A-Za-z0-9.+_-]*', version):
        raise RuntimeError('Cannot identify the installed compositor package for recovery.')
    filename = 'hyprland-'+version+'-x86_64.pkg.tar.zst'
    for suffix in ('', '.sig'):
        output = cache/(filename+suffix)
        local = Path('/var/cache/pacman/pkg')/output.name
        if local.is_file(): shutil.copyfile(local, output)
        elif not output.exists():
            print('Saving the previous compositor for recovery: '+output.name, flush=True)
            temporary = output.with_suffix(output.suffix+'.part')
            try:
                with urlopen('https://archive.archlinux.org/packages/h/hyprland/'+output.name, timeout=90) as src, temporary.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.replace(temporary, output)
            finally: temporary.unlink(missing_ok=True)
    return cache/filename


def complete():
    global TRANSACTION
    TRANSACTION = None


def rollback():
    global TRANSACTION
    if not TRANSACTION: return
    print('Restoring the previous compositor because desktop setup did not finish.', flush=True)
    subprocess.run([*administrator(), '/usr/bin/python3', str(ROOT/'installer/system_runtime.py'),
                    '--restore', str(TRANSACTION)], check=True)
    TRANSACTION = None


def ensure(yes=False):
    global TRANSACTION
    import dependencies
    target = policy.manifest()
    message = policy.problem()
    if not message and (dependencies.distro() != 'arch' or pinned(target)):
        return False
    if dependencies.distro() != 'arch' or platform.machine() != target['architecture']:
        raise RuntimeError('Automatic compositor setup supports Arch-based x86-64 systems. '+
                           (message or 'Install and hold the matching compositor with your distribution package manager.'))
    print('Required desktop compositor: Hyprland '+target['hyprland']+'; '+
          ('install/downgrade and hold this version.' if message else 'hold the installed version.'), flush=True)
    if not yes and input('Apply this compositor version and package hold? [y/N] ').strip().lower() not in ('y','yes'):
        raise RuntimeError('Compositor setup cancelled.')
    cache = Path.home()/'.cache/xetal-hyprland/runtime'/target['arch_package']
    package = download(target, cache) if message else None
    args = [*administrator(), '/usr/bin/python3', str(ROOT/'installer/system_runtime.py')]
    if package:
        previous = previous_package(cache)
        args += ['--package', str(package)]
        if previous: args += ['--previous', str(previous)]
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
        try:
            for line in process.stdout:
                if line.startswith('XETAL_RUNTIME_TRANSACTION '):
                    TRANSACTION = Path(line.strip().split(' ',1)[1])
                else: print(line, end='', flush=True)
            code = process.wait()
        except KeyboardInterrupt:
            # The privileged helper restores its transaction on interruption.
            # Wait for that recovery before the caller attempts another action.
            process.wait()
            raise
    if code: raise RuntimeError('Compositor package setup failed. See the package details above.')
    if package and not TRANSACTION: raise RuntimeError('Compositor setup did not return a recovery record.')
    policy.require()
    if not pinned(target): raise RuntimeError('The compositor hold was not installed.')
    return bool(message)
