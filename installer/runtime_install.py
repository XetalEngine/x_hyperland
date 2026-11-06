"""Prepare verified compositor packages and request normal administrator auth."""
import base64
import hashlib
import json
import os
from pathlib import Path
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
_handoff = os.environ.pop('XETAL_SETUP_PACKAGE_RECOVERY', '')
if _handoff:
    _record = json.loads(_handoff)
    _roots = {'arch-bundle':'/var/lib/xetal-hyprland/arch-runtime',
              'arch':'/var/lib/xetal-hyprland/runtime',
              'fedora':'/var/lib/xetal-hyprland/fedora-runtime',
              'debian':'/var/lib/xetal-hyprland/debian-runtime'}
    if _record.get('backend') not in _roots or Path(_record['path']).parent != Path(_roots[_record['backend']]):
        raise RuntimeError('Invalid package recovery handoff.')
    TRANSACTION = Path(_record['path'])
    TRANSACTION_BACKEND = _record['backend']
# Reserve these for the Debian authentication wrapper, outside APT's exit codes.
DEBIAN_AUTH_CANCELLED = 200
DEBIAN_AUTH_FAILED = 201
DEBIAN_USE_SU = False


def graphical_administrator(data=None):
    """Debian may use a separate root account instead of a sudo-enabled user."""
    return (os.environ.get('XETAL_SETUP_GUI') == '1' and policy.debian_host(data)
            and bool(shutil.which('pkexec')))


def administrator():
    global DEBIAN_USE_SU
    if os.environ.get('XETAL_SETUP_AUTH_SU') == '1' and shutil.which('su'):
        return ['/usr/bin/python3', str(ROOT/'installer/root_auth.py')]
    if os.environ.get('XETAL_SETUP_AUTH_PKEXEC') == '1' and shutil.which('pkexec'):
        return ['pkexec', '--disable-internal-agent']
    if os.environ.get('XETAL_SETUP_GUI') == '1' and policy.debian_host():
        if not DEBIAN_USE_SU and not shutil.which('pkexec') and shutil.which('su'):
            import debian_administrator
            DEBIAN_USE_SU = not shutil.which('sudo') or not debian_administrator.sudo_session()
        if DEBIAN_USE_SU:
            # Keep this backend for the whole worker, including recovery, even
            # if package installation supplies pkexec midway through Setup.
            return ['/usr/bin/python3', str(ROOT/'installer/debian_su.py')]
    if graphical_administrator():
        # Use the desktop's existing authentication agent. Do not hang waiting
        # for a terminal agent on the wizard's output pipe if none is running.
        return ['pkexec', '--disable-internal-agent']
    if not shutil.which('sudo'):
        if os.environ.get('XETAL_SETUP_GUI') == '1' and shutil.which('pkexec'):
            os.environ['XETAL_SETUP_AUTH_PKEXEC'] = '1'
            return ['pkexec', '--disable-internal-agent']
        if shutil.which('su'):
            # Survive both dependency installation (which supplies sudo) and
            # Python's upgrade/restart without changing authentication backend.
            os.environ['XETAL_SETUP_AUTH_SU'] = '1'
            return ['/usr/bin/python3', str(ROOT/'installer/root_auth.py')]
        raise RuntimeError('Setup needs administrator authentication for system packages. '
                           'Install sudo, su, or a graphical pkexec authentication agent. '
                           'Run Setup as your desktop user.')
    if os.environ.get('XETAL_SETUP_GUI') == '1':
        os.environ['SUDO_ASKPASS'] = str(ROOT/'installer/askpass.py')
        return ['sudo', '-A']
    return ['sudo']


def check_administrator_result(prefix, code, output=''):
    """Recognize authentication failures before reporting a package failure."""
    tool = Path(prefix[0]).name if prefix else ''
    if prefix and str(ROOT/'installer/root_auth.py') in prefix:
        if code == DEBIAN_AUTH_CANCELLED:
            raise RuntimeError('Root authentication was cancelled. Retry Setup when ready.')
        if code == DEBIAN_AUTH_FAILED:
            raise RuntimeError('Root authentication failed. Enter the system root password, not your desktop password.')
    if prefix and str(ROOT/'installer/debian_su.py') in prefix:
        if code == DEBIAN_AUTH_CANCELLED:
            raise RuntimeError('Debian root authentication was cancelled. Retry Setup when ready.')
        if code == DEBIAN_AUTH_FAILED:
            raise RuntimeError('Debian root authentication failed. Enter the root password set during Debian installation. '
                               'Your desktop account password cannot authorize this step yet.')
    if tool == 'pkexec' and code == 126:
        raise RuntimeError('Administrator authentication was cancelled. Retry Setup and authenticate '
                           'using the account shown in the system password dialog.')
    if tool == 'pkexec' and code == 127:
        raise RuntimeError('Administrator access was not granted. Retry from your graphical desktop '
                           'and authenticate with an administrator account or the root password. '
                           'If no password dialog appears, check that the desktop authentication agent is running.')
    if tool == 'sudo' and code and any(message in output.lower() for message in
            ('not in the sudoers', 'not in sudoers', 'not allowed to run sudo', 'not allowed to execute')):
        raise RuntimeError('Your account is not authorized to use sudo. On Debian, use graphical '
                           'Setup with pkexec installed to authenticate as an administrator, '
                           'or ask the system administrator to grant this account sudo access and sign in again. '
                           'Keep running Setup as your desktop user.')
    if tool == 'sudo' and code and any(message in output.lower() for message in
            ('a password is required', 'no password was provided', 'incorrect password',
             'authentication failure', 'unable to read password', 'no askpass program', 'a terminal is required')):
        raise RuntimeError('Administrator authentication failed or was cancelled. Retry Setup and '
                           'authenticate with a sudo-authorized account. See the authentication details above.')


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


def previous_package(cache, package_name='hyprland'):
    """Preserve the exact installed package, including CachyOS architecture builds."""
    if not re.fullmatch(r'[a-z][a-z0-9+-]*', package_name):
        raise ValueError('Invalid recovery package name.')
    result = subprocess.run(['pacman', '-Q', package_name], capture_output=True, text=True, timeout=10)
    if result.returncode: return None
    name, version = result.stdout.split()
    if name != package_name or not re.fullmatch(r'[0-9][A-Za-z0-9.+_~:-]*', version):
        raise RuntimeError('Cannot identify the installed compositor package for recovery.')
    details = subprocess.run(['pacman', '-Qi', package_name], capture_output=True, text=True,
                             env={**os.environ, 'LC_ALL':'C'}, timeout=10)
    arch = re.search(r'^Architecture\s*:\s*([A-Za-z0-9_]+)\s*$', details.stdout, re.M)
    if details.returncode or not arch:
        raise RuntimeError('Cannot identify the installed compositor architecture for recovery.')
    architecture = arch[1]
    # Epochs belong in the package version, not its archive filename.
    filename = package_name+'-'+version.split(':')[-1]+'-'+architecture+'.pkg.tar.zst'
    cache.mkdir(parents=True, exist_ok=True)
    local_dirs = package_caches()
    try:
        return save_recovery(cache, filename, local_dirs)
    except FileNotFoundError:
        pass
    # --print only queries pacman's configured repositories. It never changes
    # packages or refreshes databases. %g also covers caches without a .sig file.
    result = subprocess.run(['pacman', '-Spdd', '--noconfirm', '--print-format',
                             '%n|%v|%a|%f|%l|%g', package_name+'='+version],
                            capture_output=True, text=True, timeout=15)
    sources = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            fields = line.split('|')
            if len(fields) != 6: continue
            pkg, candidate_version, candidate_arch, file, url, encoded = fields
            if (pkg, candidate_version, candidate_arch, file) != (package_name, version, architecture, filename):
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
    sources.append(('https://archive.archlinux.org/packages/'+package_name[0]+'/'+package_name+'/'+filename, b''))
    errors = []
    for url, signature in dict.fromkeys(sources):
        try: return save_recovery(cache, filename, local_dirs, url, signature)
        except OSError as error:
            errors.append(str(error))
            if isinstance(error, HTTPError): error.close()
    raise RuntimeError('Could not save the installed '+package_name+' '+version+' ('+architecture+
                       ') for recovery from the package cache or configured repositories. '+
                       'No compositor changes were made. Last download error: '+errors[-1])


def complete():
    global TRANSACTION
    TRANSACTION = None


def restart_after_python_upgrade():
    """An older rolling system may replace Python during the package upgrade."""
    result = subprocess.run(['/usr/bin/python3', '-c', 'import sys;print("%d.%d" % sys.version_info[:2])'],
                            capture_output=True, text=True, check=True, timeout=15)
    if result.stdout.strip() == '%d.%d' % sys.version_info[:2]:
        return
    print('System Python was upgraded. Continuing Setup with the new interpreter and preserved recovery record.', flush=True)
    environment = dict(os.environ)
    if TRANSACTION:
        environment['XETAL_SETUP_PACKAGE_RECOVERY'] = json.dumps({'backend':TRANSACTION_BACKEND, 'path':str(TRANSACTION)})
    os.execve('/usr/bin/python3', ['/usr/bin/python3', *sys.argv], environment)


def package_error_output(result):
    # Pacman can write the dependency names to stdout and only its generic
    # "could not satisfy dependencies" summary to stderr. Keep both streams.
    return '\n'.join(text.strip() for text in (result.stdout, result.stderr)
                     if text and text.strip())


def check_transaction(package):
    # Pacman's print mode prepares dependency/conflict resolution without taking
    # the package lock or changing installed packages. Keep dependency checks on.
    result = subprocess.run(['pacman', '-Up', '--noconfirm', '--print-format', '%n %v', str(package)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('The required Hyprland package is incompatible with the installed packages or '+
                           'configured repositories. The current compositor has not been changed.\n'+
                           package_error_output(result))


def rollback():
    global TRANSACTION
    if not TRANSACTION: return
    print('Restoring the previous compositor because desktop setup did not finish.', flush=True)
    helper = {'fedora':'system_fedora_runtime.py', 'debian':'system_debian_runtime.py',
              'arch':'system_runtime.py', 'arch-bundle':'system_arch_runtime.py'}[TRANSACTION_BACKEND]
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
    if dependencies.distro() == 'arch':
        import arch_runtime
        return arch_runtime.ensure(yes)
    message = policy.problem()
    if not message:
        return False  # A manually supplied native runtime on another distro.
    raise RuntimeError('No matching native compositor bundle is available for this distribution. '+message)
