"""Prepare verified compositor packages and request normal administrator auth."""
import base64
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'config/hypr/runtime'))
import runtime_policy as policy

PIN = Path('/etc/pacman.d/xetal-hyprland.conf')
BUNDLED = ROOT/'installer/packages'
TRANSACTION = None
TRANSACTION_BACKEND = 'arch'


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


def pacman_config(*args):
    result = subprocess.run(['pacman-conf', *args], capture_output=True, text=True, timeout=10)
    return result.stdout.splitlines() if result.returncode == 0 else []


def package_caches():
    return [Path(p) for p in pacman_config('CacheDir')] or [Path('/var/cache/pacman/pkg')]


def download(target, cache):
    cache.mkdir(parents=True, exist_ok=True)
    sources = [BUNDLED, *package_caches()]
    for suffix, key in [('', 'package_sha256'), ('.sig', 'signature_sha256')]:
        destination = cache/(policy.filename(target)+suffix)
        if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == target[key]:
            continue
        local = next((directory/destination.name for directory in sources
                      if (directory/destination.name).is_file()
                      and hashlib.sha256((directory/destination.name).read_bytes()).hexdigest() == target[key]), None)
        temporary = destination.with_suffix(destination.suffix+'.part')
        try:
            if local:
                print('Using '+('bundled package: ' if local.parent == BUNDLED else 'cached package: ')+local.name, flush=True)
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


def save_recovery(cache, filename, local_dirs, url=None, signature=b''):
    """Copy/download only; the privileged helper verifies signatures and identity."""
    for suffix in ('', '.sig'):
        output = cache/(filename+suffix)
        if output.is_file(): continue
        local = next((directory/output.name for directory in local_dirs if (directory/output.name).is_file()), None)
        temporary = output.with_suffix(output.suffix+'.part')
        try:
            if local: shutil.copyfile(local, temporary)
            elif suffix and signature: temporary.write_bytes(signature)
            elif url:
                print('Saving the previous compositor for recovery: '+output.name, flush=True)
                with urlopen(url+suffix, timeout=45) as src, temporary.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
            else: raise FileNotFoundError('No cached '+output.name)
            os.replace(temporary, output)
        finally: temporary.unlink(missing_ok=True)
    return cache/filename


def previous_package(cache):
    """Preserve the exact installed package, including CachyOS architecture builds."""
    result = subprocess.run(['pacman', '-Q', 'hyprland'], capture_output=True, text=True, timeout=10)
    if result.returncode: return None
    name, version = result.stdout.split()
    if name != 'hyprland' or not re.fullmatch(r'[0-9][A-Za-z0-9.+_:-]*', version):
        raise RuntimeError('Cannot identify the installed compositor package for recovery.')
    details = subprocess.run(['pacman', '-Qi', 'hyprland'], capture_output=True, text=True,
                             env={**os.environ, 'LC_ALL':'C'}, timeout=10)
    arch = re.search(r'^Architecture\s*:\s*([A-Za-z0-9_]+)\s*$', details.stdout, re.M)
    if details.returncode or not arch:
        raise RuntimeError('Cannot identify the installed compositor architecture for recovery.')
    architecture = arch[1]
    # Epochs belong in the package version, not its archive filename.
    filename = 'hyprland-'+version.split(':')[-1]+'-'+architecture+'.pkg.tar.zst'
    cache.mkdir(parents=True, exist_ok=True)
    local_dirs = package_caches()
    try:
        return save_recovery(cache, filename, local_dirs)
    except FileNotFoundError:
        pass
    # --print only queries pacman's configured repositories. It never changes
    # packages or refreshes databases. %g also covers caches without a .sig file.
    result = subprocess.run(['pacman', '-Spdd', '--noconfirm', '--print-format',
                             '%n|%v|%a|%f|%l|%g', 'hyprland='+version],
                            capture_output=True, text=True, timeout=15)
    sources = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            fields = line.split('|')
            if len(fields) != 6: continue
            pkg, candidate_version, candidate_arch, file, url, encoded = fields
            if (pkg, candidate_version, candidate_arch, file) != ('hyprland', version, architecture, filename):
                continue
            if urlparse(url).scheme not in ('https', 'http', 'file'): continue
            try: signature = base64.b64decode(encoded, validate=True)
            except ValueError: signature = b''
            sources.append((url, signature))
    # Try other configured mirrors when the preferred mirror lacks the file.
    for repo in pacman_config('--repo-list'):
        for server in pacman_config('--repo', repo, 'Server')[:3]:
            if urlparse(server).scheme in ('https', 'http', 'file'):
                sources.append((server.rstrip('/')+'/'+filename, b''))
    sources.append(('https://archive.archlinux.org/packages/h/hyprland/'+filename, b''))
    errors = []
    for url, signature in dict.fromkeys(sources):
        try: return save_recovery(cache, filename, local_dirs, url, signature)
        except OSError as error:
            errors.append(str(error))
            if isinstance(error, HTTPError): error.close()
    raise RuntimeError('Could not save the installed Hyprland '+version+' ('+architecture+
                       ') for recovery from the package cache or configured repositories. '+
                       'No compositor changes were made. Last download error: '+errors[-1])


def complete():
    global TRANSACTION
    TRANSACTION = None


def check_transaction(package):
    # Pacman's print mode prepares dependency/conflict resolution without taking
    # the package lock or changing installed packages. Keep dependency checks on.
    result = subprocess.run(['pacman', '-Up', '--noconfirm', '--print-format', '%n %v', str(package)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('The required Hyprland package is incompatible with the installed packages or '+
                           'configured repositories. The current compositor has not been changed.\n'+
                           (result.stderr or result.stdout).strip())


def rollback():
    global TRANSACTION
    if not TRANSACTION: return
    print('Restoring the previous compositor because desktop setup did not finish.', flush=True)
    helper = {'fedora':'system_fedora_runtime.py', 'debian':'system_debian_runtime.py', 'arch':'system_runtime.py'}[TRANSACTION_BACKEND]
    subprocess.run([*administrator(), '/usr/bin/python3', str(ROOT/'installer'/helper),
                    '--restore', str(TRANSACTION)], check=True)
    TRANSACTION = None


def ensure(yes=False):
    global TRANSACTION, TRANSACTION_BACKEND
    import dependencies
    if policy.fedora_host(dependencies.distribution()):
        import fedora_runtime
        return fedora_runtime.ensure(yes)
    if policy.debian_host(dependencies.distribution()):
        import debian_runtime
        return debian_runtime.ensure(yes)
    TRANSACTION_BACKEND = 'arch'
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
    if package: check_transaction(package)
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
