#!/usr/bin/env python3
"""Install the exact kernel required by the signed KVM catalogue, on request.

Downloads and AUR builds run as the desktop user. Only package operations and
boot-menu refresh request administrator access. Importing this module is inert.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
ARCHIVE = 'https://archive.archlinux.org/packages'
PACKAGE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9@._+:-]*')


class Cancelled(RuntimeError):
    pass


class PackageTransactionError(RuntimeError):
    """Stop the workflow after a failed system package operation."""


@dataclass(frozen=True)
class Target:
    release: str
    version: str
    package: str = 'linux'
    headers: str = 'linux-headers'

    @classmethod
    def parse(cls, release):
        match = re.fullmatch(r'(\d+\.\d+(?:\.\d+)?)-arch(\d+)-(\d+)', release or '')
        if not match:
            raise RuntimeError('Automatic installation currently supports exact Arch linux kernel builds. '
                               'No verified package mapping is available for '+str(release)+'.')
        return cls(release, f'{match[1]}.arch{match[2]}-{match[3]}')


def required_kernel():
    """Read the newest locally available, signature-verified Enhanced catalogue."""
    import packages
    releases = []
    error = None
    for reader in (lambda:packages.Store(edition='xetallic').cached(),
                   lambda:packages.decode((ROOT/'catalog.json').read_bytes())):
        try:
            release = reader()
            if release and release.get('edition') == 'xetallic':releases.append(release)
        except (OSError, ValueError, RuntimeError) as exc:error = exc
    if not releases:
        raise RuntimeError('The signed KVM catalogue could not be read. '+str(error or 'Check for component updates.'))
    release = max(releases, key=lambda r:packages.version(r['version']))
    return release.get('components', {}).get('kvm-amd', {}).get('kernel', '')


def platform_problem(distribution=None, machine=None):
    if distribution is None:
        distribution = {}
        try:
            for line in Path('/etc/os-release').read_text().splitlines():
                if '=' in line:
                    key, value = line.split('=', 1);distribution[key] = value.strip('"\'')
        except OSError:pass
    ids = {distribution.get('ID', ''), *distribution.get('ID_LIKE', '').split()}
    if not ids.intersection({'arch', 'manjaro', 'cachyos', 'endeavouros'}):
        return 'This published module needs an Arch kernel. Automatic installation is available on Arch-family systems only. Standard KVM remains available.'
    if (machine or platform.machine()) not in ('x86_64', 'AMD64'):
        return 'This published kernel requires an x86-64 machine.'
    return ''


def installed(target, root=Path('/')):
    directory = root/'usr/lib/modules'/target.release
    try:
        with (directory/'vmlinuz').open('rb') as image:return kernel_release(image.read(131072)) == target.release
    except (OSError, ValueError):return False


def kernel_release(image):
    # x86 boot protocol: kernel_version at 0x20e points relative to 0x200.
    # https://docs.kernel.org/arch/x86/boot.html#the-real-mode-kernel-header
    if len(image) < 0x210 or image[0x202:0x206] != b'HdrS':raise ValueError('Invalid x86 kernel boot header.')
    offset = int.from_bytes(image[0x20e:0x210], 'little') + 0x200
    if offset < 0x210 or offset >= len(image):raise ValueError('Kernel release information is missing.')
    text = image[offset:offset+256].split(b'\0', 1)[0].split(b' ', 1)[0]
    try:return text.decode('ascii')
    except UnicodeError:raise ValueError('Invalid embedded kernel release.') from None


def complete(target, root=Path('/')):
    directory = root/'usr/lib/modules'/target.release
    try:
        return installed(target, root) and (directory/'build/include/config/kernel.release').read_text().strip() == target.release
    except OSError:return False


def active(state=None):
    state = state or Path.home()/'.local/state/xetal-kvm/kernel-installs'
    try:
        with (state/'install.lock').open() as lock:
            try:fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:return True
    except OSError:pass
    return False


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream, 'sha256').hexdigest()


def package_metadata(path, run):
    text = run(['bsdtar', '-xOf', str(path), '.PKGINFO'], quiet=True)
    data = {}
    for line in text.splitlines():
        if ' = ' in line:
            key, value = line.split(' = ', 1);data.setdefault(key, []).append(value)
    if any(len(data.get(key, [])) != 1 for key in ('pkgname', 'pkgver', 'arch')):
        raise RuntimeError('Invalid package metadata: '+path.name)
    return data


def validate_pair(paths, target, run, *, official=True):
    """Package versions alone are insufficient: check the full modules release."""
    if len(paths) != 2:raise RuntimeError('Both the kernel and matching headers are required.')
    result = []
    for index, path in enumerate(paths):
        data = package_metadata(path, run)
        name = data['pkgname'][0]
        expected = target.package if index == 0 else target.headers
        if official and (name != expected or data['pkgver'][0] != target.version):
            raise RuntimeError('The downloaded package does not match '+expected+' '+target.version+'.')
        if not PACKAGE.fullmatch(name) or not name.startswith('linux') or data['arch'][0] != 'x86_64':
            raise RuntimeError('Unexpected kernel package identity or architecture: '+path.name)
        files = run(['pacman', '-Qlpq', str(path)], quiet=True).splitlines()
        marker = f'/usr/lib/modules/{target.release}/' + ('vmlinuz' if index == 0 else 'build/include/config/kernel.release')
        if marker not in files:
            raise RuntimeError(path.name+' does not contain the exact '+target.release+' kernel release.')
        if index == 0:
            image = run(['bsdtar', '-xOf', str(path), marker.lstrip('/')], quiet=True, prefix_bytes=131072)
            try:release = kernel_release(image)
            except ValueError as error:raise RuntimeError(str(error)) from None
            if release != target.release:raise RuntimeError('The kernel image contains a different release than its package paths.')
        else:
            release = run(['bsdtar', '-xOf', str(path), marker.lstrip('/')], quiet=True).strip()
            if release != target.release:raise RuntimeError('The headers belong to a different kernel release: '+release)
        result.append(data)
    if result[1]['pkgname'][0] != result[0]['pkgname'][0]+'-headers':
        raise RuntimeError('Kernel and header package names do not form a matching pair.')
    return result


class Installer:
    def __init__(self, target, *, aur=True, log=lambda text:None, phase=lambda text:None, cancel=None, state=None):
        self.target = target;self.aur = aur;self.log = log;self.phase = phase
        self.cancel = cancel or threading.Event()
        self.state = state or Path.home()/'.local/state/xetal-kvm/kernel-installs'
        self.directory = None
        self.changed = False
        self.mutating = False
        self.recovery = {}

    def checkpoint(self):
        if self.cancel.is_set() and not self.mutating:raise Cancelled('Cancelled before the next package operation.')

    def run(self, argv, *, cwd=None, quiet=False, admin=False, timeout=900, check=True, prefix_bytes=0):
        self.checkpoint()
        argv = list(map(str, argv));env = dict(os.environ, LC_ALL='C', GIT_TERMINAL_PROMPT='0')
        package_transaction = admin and Path(argv[0]).name == 'pacman' and any(option in argv for option in ('-U', '-Syu'))
        if admin:
            sys.path.insert(0, str(ROOT/'backend/lib'))
            from uiutil import sudo_command
            argv, extra, available = sudo_command(argv, 'Hyper Fusion: install the compatible KVM kernel')
            if not available:raise RuntimeError('Administrator authentication is unavailable. Install a graphical sudo password helper and retry.')
            env.update(extra);env['LC_ALL'] = 'C'
        if not quiet:self.log('$ '+shlex.join(argv))
        self.mutating = admin
        if admin:self.phase('Installing packages — wait for this operation to finish')
        started = time.monotonic();output = bytearray();hook_error = False;tail = ''
        process = None
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    self.checkpoint()
                    if not admin and time.monotonic()-started > timeout:raise RuntimeError('Command timed out: '+shlex.join(argv))
                    for key, _ in selector.select(0.2):
                        block = os.read(key.fileobj.fileno(), 65536)
                        if not block:selector.unregister(key.fileobj);continue
                        if package_transaction:
                            tail = (tail+block.decode('utf-8', errors='replace'))[-131072:]
                            # Pacman can return zero after a post-transaction
                            # hook failed (for example, generating initramfs).
                            hook_error |= bool(re.search(r'(?im)^\s*(?:error:|==>\s*ERROR:|ERROR:)', tail))
                        if prefix_bytes:output.extend(block[:max(0, prefix_bytes-len(output))])
                        else:
                            output.extend(block)
                            if len(output) > 16*1024*1024:del output[:-8*1024*1024]
                        if not quiet:self.log(block.decode('utf-8', errors='replace').rstrip())
            code = process.wait()
            text = output.decode('utf-8', errors='replace')
            if check and code:
                error = PackageTransactionError if package_transaction else RuntimeError
                raise error('Command failed (exit '+str(code)+'): '+shlex.join(argv)+'\n'+text[-6000:].strip())
            if hook_error:
                raise PackageTransactionError('Packages may have changed, but a package hook reported an error. '
                                              'Do not reboot until the boot files have been repaired.\n'+text[-6000:].strip())
            if admin and code == 0:self.changed = True
            return bytes(output) if prefix_bytes else text if check else (code, text)
        finally:
            if process and process.poll() is None:
                if admin:process.wait()  # Never interrupt a package transaction.
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid, signal.SIGKILL);process.wait()
            if process and process.stdout:process.stdout.close()
            self.mutating = False
            if admin:self.phase('Preparing the next step')

    def download(self, url, destination, *, maximum=1024*1024*1024):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password:
            raise RuntimeError('Kernel packages must be downloaded over HTTPS.')
        self.checkpoint();self.log('Downloading '+destination.name)
        temporary = destination.with_name(destination.name+'.part')
        try:
            request = urllib.request.Request(url, headers={'User-Agent':'HyperFusion-KernelSetup/1'})
            with urllib.request.urlopen(request, timeout=45) as response, temporary.open('wb') as stream:
                if urllib.parse.urlsplit(response.url).scheme != 'https':raise RuntimeError('Insecure package redirect refused.')
                total = 0
                while block := response.read(1024*1024):
                    self.checkpoint();total += len(block)
                    if total > maximum:raise RuntimeError('Package download exceeds its size limit.')
                    stream.write(block)
            if not total:raise RuntimeError('The server returned an empty download.')
            temporary.replace(destination)
        finally:temporary.unlink(missing_ok=True)

    def caches(self):
        code, text = self.run(['pacman-conf', 'CacheDir'], quiet=True, check=False)
        return [Path(p) for p in text.splitlines()] if not code else [Path('/var/cache/pacman/pkg')]

    def official_package(self, name, version, directory):
        """Exact package cache, configured repository, then official archive."""
        if not PACKAGE.fullmatch(name) or not re.fullmatch(r'[A-Za-z0-9_.+:-]+', version):
            raise RuntimeError('Invalid exact package identity.')
        filename = f'{name}-{version}-x86_64.pkg.tar.zst'
        path = directory/filename;errors = []
        urls = [ARCHIVE+'/'+name[0]+'/'+name+'/'+filename]
        code, text = self.run(['pacman', '-Sp', '--print-format', '%n\t%v\t%l', '--', name], quiet=True, check=False)
        if not code:
            for line in text.splitlines():
                fields = line.split('\t')
                if len(fields) == 3 and fields[:2] == [name, version]:urls.insert(0, fields[2])
        for cache in self.caches():
            source = cache/filename
            if source.is_file():
                self.log('Using cached package: '+str(source));shutil.copy2(source, path)
                signature = source.with_name(filename+'.sig')
                if signature.is_file():shutil.copy2(signature, path.with_name(filename+'.sig'))
                break
        for url in dict.fromkeys(urls):
            try:
                if not path.exists():self.download(url, path)
                if not path.with_name(filename+'.sig').exists():
                    self.download(url+'.sig', path.with_name(filename+'.sig'), maximum=64*1024)
                return path
            except Cancelled:raise
            except (OSError, ValueError, RuntimeError) as error:errors.append(str(error))
        raise RuntimeError('Exact signed package unavailable: '+filename+'\n'+'\n'.join(errors))

    def dependencies(self, names):
        if not names:return
        if any(not re.fullmatch(r'[A-Za-z0-9@._+:-]+(?:[<>=]+[A-Za-z0-9@._+:~-]+)?', name) for name in names):
            raise RuntimeError('Invalid dependency metadata.')
        code, text = self.run(['pacman', '-T', '--', *sorted(set(names))], quiet=True, check=False)
        if code not in (0, 127):raise RuntimeError('Could not check installed dependencies:\n'+text)
        missing = [line.strip() for line in text.splitlines() if line.strip() in names]
        if missing:
            self.backup_standard_kernel()
            self.log('Installing missing dependencies with a full system update: '+', '.join(missing))
            self.run(['pacman', '-Syu', '--needed', '--noconfirm', '--', *missing], admin=True, timeout=7200)

    def source_build(self, source, directory):
        """Build as the user; the build cannot install its output automatically."""
        self.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--depth', '1', '--', source, str(directory)], timeout=300)
        info = (directory/'.SRCINFO').read_text()
        dependencies = ['base-devel', 'git']
        for line in info.splitlines():
            match = re.fullmatch(r'\s*(?:depends|makedepends|checkdepends)(?:_x86_64)?\s*=\s*(\S+)\s*', line)
            if match:dependencies.append(match[1])
        self.dependencies(dependencies)
        self.phase('Building community packages as your user')
        self.run(['makepkg', '--noconfirm', '--cleanbuild', '--clean'], cwd=directory, timeout=14400)
        code, output = self.run(['makepkg', '--packagelist'], cwd=directory, quiet=True, check=False)
        if code:raise RuntimeError('Could not identify the built community packages.\n'+output)
        return [Path(line) for line in output.splitlines() if Path(line).is_file()]

    def helpers(self):
        """Both helpers are opt-in, and bootstrapped only for the AUR fallback."""
        available = []
        for name in ('yay', 'paru'):
            self.checkpoint()
            try:
                existing = shutil.which(name)
                if existing and self.run([existing, '--version'], quiet=True, check=False)[0] == 0:
                    available.append(existing);continue
                self.log('Setting up '+name+' for the requested AUR fallback…')
                code, _ = self.run(['pacman', '-Si', '--', name], quiet=True, check=False)
                if code == 0:
                    self.backup_standard_kernel()
                    self.run(['pacman', '-Syu', '--needed', '--noconfirm', '--', name], admin=True, timeout=7200)
                else:
                    self.dependencies(['base-devel', 'git'])
                    paths = self.source_build('https://aur.archlinux.org/'+name+'.git', self.directory/(name+'-build'))
                    paths = [p for p in paths if package_metadata(p, self.run)['pkgname'][0] == name]
                    if len(paths) != 1:raise RuntimeError('The '+name+' build did not produce its expected package.')
                    self.run(['pacman', '-U', '--noconfirm', '--', str(paths[0])], admin=True)
                executable = shutil.which(name)
                if not executable or self.run([executable, '--version'], quiet=True, check=False)[0]:
                    raise RuntimeError(name+' was installed but cannot run.')
                available.append(executable)
            except (Cancelled, PackageTransactionError):raise
            except (OSError, RuntimeError) as error:self.log(name+' setup failed: '+str(error))
        if not available:raise RuntimeError('Neither yay nor paru could be prepared. See the setup errors above.')
        return available

    def aur_pair(self):
        candidates = set()
        for helper in self.helpers():
            code, output = self.run([helper, '-Ss', '--aur', '--color', 'never', '^linux'], check=False, timeout=180)
            if code:self.log(Path(helper).name+' search failed: '+output[-1500:]);continue
            for line in output.splitlines():
                match = re.match(r'^aur/(linux[A-Za-z0-9_.+-]*)\s+(\S+)', line)
                if match and not match[1].endswith(('-headers', '-docs')) and match[2].split(':')[-1] == self.target.version:
                    candidates.add(match[1])
        for name in sorted(candidates)[:10]:
            try:
                paths = self.source_build('https://aur.archlinux.org/'+name+'.git', self.directory/('kernel-'+name))
                by_name = {package_metadata(p, self.run)['pkgname'][0]:p for p in paths}
                if name not in by_name or name+'-headers' not in by_name:continue
                pair = [by_name[name], by_name[name+'-headers']]
                validate_pair(pair, self.target, self.run, official=False)
                return pair
            except (Cancelled, PackageTransactionError):raise
            except (OSError, RuntimeError) as error:self.log(name+' rejected: '+str(error))
        raise RuntimeError('Yay/paru did not produce a kernel and headers with the exact release '+self.target.release+
                           '. They use the same AUR; another kernel with the same upstream version is not interchangeable.')

    def backup_standard_kernel(self):
        # A dependency/helper installation uses a full update and can also
        # replace linux, before the exact-kernel transaction is reached.
        self.backup_previous([dict(pkgname=[name], pkgver=[self.target.version])
                              for name in (self.target.package, self.target.headers)])

    def backup_previous(self, metadata):
        previous = self.directory/'previous';previous.mkdir(exist_ok=True)
        for data in metadata:
            name = data['pkgname'][0]
            if name in self.recovery:continue
            code, text = self.run(['pacman', '-Q', '--', name], quiet=True, check=False)
            if code:
                self.recovery[name] = None;continue
            fields = text.strip().split()
            if len(fields) != 2 or fields[0] != name:raise RuntimeError('Could not identify the installed '+name+' package.')
            # Standard Arch packages can be recovered without creating a new
            # unsigned package from the live system.
            if name not in ('linux', 'linux-headers'):
                raise RuntimeError('An existing community kernel would be replaced. Keep a recovery package and install that build manually.')
            package = self.official_package(name, fields[1], previous)
            self.run(['pacman-key', '--verify', str(package)+'.sig', str(package)], admin=True)
            self.recovery[name] = str(package)
            saved = [path for path in self.recovery.values() if path]
            # Keep recovery instructions even if obtaining the next package fails.
            (self.directory/'restore.txt').write_text('sudo pacman -U -- '+shlex.join(saved)+'\n')
        saved = [path for path in self.recovery.values() if path]
        if saved:
            self.log('Previous kernel packages saved in '+str(previous))

    def install(self):
        problem = platform_problem()
        if problem:raise RuntimeError(problem)
        if os.geteuid() == 0:raise RuntimeError('Open kernel setup as your regular desktop user, without sudo.')
        if complete(self.target):return 'Kernel '+self.target.release+' and matching headers are already installed. Boot that kernel, then reopen KVM Settings.'
        for command in ('pacman', 'pacman-conf', 'bsdtar'):
            if not shutil.which(command):raise RuntimeError('Missing required command: '+command)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state/'install.lock').open('a') as lock:
            try:fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Another compatible-kernel installation is already running.') from None
            self.directory = self.state/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            self.directory.mkdir(mode=0o700)
            official = True
            self.phase('Finding the exact kernel and headers')
            try:
                pair = [self.official_package(name, self.target.version, self.directory)
                        for name in (self.target.package, self.target.headers)]
            except Cancelled:raise
            except (OSError, RuntimeError) as error:
                self.log(str(error))
                if not self.aur:raise
                official = False;pair = self.aur_pair()
            metadata = validate_pair(pair, self.target, self.run, official=official)
            if official:
                for package in pair:self.run(['pacman-key', '--verify', str(package)+'.sig', str(package)], admin=True)
            self.backup_previous(metadata)
            self.dependencies([dep for data in metadata for dep in data.get('depend', [])])
            record = dict(kernel=self.target.release, source='signed Arch packages' if official else 'AUR build',
                          packages=[dict(path=str(p), sha256=digest(p)) for p in pair])
            (self.directory/'install.json').write_text(json.dumps(record, indent=2)+'\n')
            self.checkpoint()
            # Normal pacman signature/dependency checks and install hooks stay
            # enabled. A failed transaction or boot hook is never called success.
            self.run(['pacman', '-U', '--noconfirm', '--', *map(str, pair)], admin=True, timeout=7200)
            if not complete(self.target):
                raise RuntimeError('Package installation finished, but '+self.target.release+' and its matching headers could not be verified. Check the log before rebooting.')
            grub = Path('/boot/grub/grub.cfg')
            if grub.is_file() and shutil.which('grub-mkconfig'):
                self.run(['cp', '--', str(grub), str(self.directory/'grub.cfg.before')], admin=True)
                self.run(['grub-mkconfig', '-o', str(grub)], admin=True)
            elif not any(Path(p).is_dir() for p in ('/boot/loader/entries', '/efi/loader/entries', '/boot/efi/loader/entries',
                                                    '/boot/EFI/Linux', '/efi/EFI/Linux', '/boot/efi/EFI/Linux')):
                return ('Kernel '+self.target.release+' and headers installed. Your bootloader could not be identified; '
                        'add/select this kernel in its boot menu before rebooting. Log and recovery files: '+str(self.directory))
            return ('Kernel '+self.target.release+' and matching headers installed. Reboot and select that kernel, then reopen KVM Settings. '
                    'Log and recovery files: '+str(self.directory))
