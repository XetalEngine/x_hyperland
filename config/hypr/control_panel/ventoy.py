#!/usr/bin/env python3
"""Ventoy's pinned offline engine, behind an independently checked USB boundary.

The ordinary-user scan is advisory. The authenticated worker repeats discovery,
identity, mount, swap and holder checks before it gives Ventoy permission to write.
There is deliberately no force-install, arbitrary command or device override.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import select
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

VERSION = '1.1.18'
SHA256 = 'd86ff9de63d94c8b8f1f6b14d23c55af4b88e8207bf2893890892a6a97b1ad54'
BUNDLE_SIZE = 20320548
BUNDLE = Path(__file__).resolve().parent / 'ventoy/vendor' / f'ventoy-{VERSION}-linux.tar.gz'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C', 'LANG': 'C', 'HOME': '/root'}
DEVICE = re.compile(r'/dev/(?:sd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+)\Z')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
COLUMNS = 'NAME,PATH,TYPE,SIZE,RO,TRAN,MODEL,SERIAL,WWN,MAJ:MIN,FSTYPE,LABEL,UUID,MOUNTPOINTS,LOG-SEC'


def clean(value):
    return ''.join(c for c in ANSI.sub('', str(value or '')) if c >= ' ' or c == '\t').strip()


def emit(value):
    # Finishing a disk write must not depend on the GUI keeping its output open.
    try:
        os.write(1, (json.dumps(value, ensure_ascii=False) + '\n').encode())
    except BrokenPipeError:
        pass


def run(argv, *, timeout=20, cwd=None):
    result = subprocess.run(argv, capture_output=True, text=True, errors='replace',
                            env=ENV, cwd=cwd, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(clean(result.stderr or result.stdout)[-1500:] or f'{argv[0]} failed.')
    return result.stdout


def read_sys(path):
    return Path(path).read_text().strip()


def descendants(node):
    yield node
    for child in node.get('children', []):
        yield from descendants(child)


def mounts(node):
    return [p for p in node.get('mountpoints', []) if p]


def data_mount(path):
    # Never unmount /, /home, /boot, a live ISO, or a custom system mount.
    # Administrators can manually unmount a custom data location before retrying.
    return any(path.startswith(prefix) for prefix in ('/run/media/', '/media/', '/mnt/'))


def protected_devices():
    protected = set()
    for path in ('/', '/boot', '/boot/efi', '/efi', '/home', '/usr', '/var', str(Path(__file__).resolve())):
        try:
            dev = os.stat(path).st_dev
            protected.add(f'{os.major(dev)}:{os.minor(dev)}')
        except FileNotFoundError:
            pass
    # lsblk does not connect a swap FILE or a loop image to its containing disk.
    def backing(path):
        path = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), path)
        # Block devices may be omitted from a sandbox's /dev while sysfs and
        # /proc/swaps still expose them (notably zram). Read their kernel ID.
        if path.startswith('/dev/') and not Path(path).exists():
            protected.add(read_sys(Path('/sys/class/block') / Path(path).name / 'dev'))
            return
        info = os.stat(path)
        dev = info.st_rdev if stat.S_ISBLK(info.st_mode) else info.st_dev
        protected.add(f'{os.major(dev)}:{os.minor(dev)}')
    for line in Path('/proc/swaps').read_text().splitlines()[1:]:
        backing(line.split()[0])
    for path in Path('/sys/class/block').glob('loop*/loop/backing_file'):
        value = path.read_text().strip()
        if value:
            backing('/' + value.lstrip('/'))
    # Include every member of mounted multi-device Btrfs filesystems.
    for path in Path('/sys/fs/btrfs').glob('*/devices/*/dev'):
        protected.add(path.read_text().strip())
    return protected


def identity(node):
    fields = ('path', 'size', 'serial', 'wwn', 'maj:min', 'diskseq', 'sys_path')
    return hashlib.sha256(json.dumps({k: node.get(k) for k in fields},
                                     sort_keys=True).encode()).hexdigest()


def layout_identity(node):
    # Mounting a partition is harmless; replacing its filesystem or partition
    # layout while confirmation/authentication is open invalidates the request.
    fields = ('path', 'size', 'fstype', 'uuid', 'label', 'partn', 'start')
    rows = [{k: child.get(k) for k in fields} for child in descendants(node)]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def blocked_reason(node, protected):
    children = list(descendants(node))
    if node.get('tran') != 'usb' or node.get('type') != 'disk' or not DEVICE.fullmatch(node.get('path', '')):
        return 'Only whole USB disks can be prepared here.'
    if any(child.get('maj:min') in protected for child in children):
        return 'This disk is in use by the running system, swap, or a mounted disk image.'
    if any(child.get('type') not in ('disk', 'part') or child.get('holders') for child in children):
        return 'This disk has active encrypted, RAID, LVM, or other dependent devices.'
    if any(child.get('ro') for child in children):
        return 'This disk is read-only.'
    if int(node.get('size') or 0) < 512 * 1024 * 1024:
        return 'Choose a USB disk with at least 512 MiB of space.'
    if int(node.get('log-sec') or 0) != 512:
        return 'Ventoy requires a disk with 512-byte logical sectors.'
    if not node.get('diskseq') or not node.get('sys_path'):
        return 'The kernel could not confirm this disk’s identity. Reconnect it and refresh.'
    for child in children:
        for path in mounts(child):
            if not data_mount(path):
                return f'Protected or custom mount: {clean(path)}. Unmount data disks manually before retrying.'
    return ''


def ventoy_partitions(node):
    parts = {child.get('partn'): child for child in node.get('children', []) if child.get('type') == 'part'}
    first, efi = parts.get(1), parts.get(2)
    if first and efi and efi.get('label') == 'VTOYEFI' and efi.get('fstype') == 'vfat' and efi.get('size') == 33554432:
        return first, efi
    return None


def disk_inventory():
    data = json.loads(run(['lsblk', '--json', '--bytes', '--paths', '--tree', '--output', COLUMNS]))
    protected = protected_devices()
    result = []
    for node in data['blockdevices']:
        if node.get('type') != 'disk' or node.get('tran') != 'usb':
            continue
        for child in descendants(node):
            name = Path(child['path']).name
            sysdir = Path('/sys/class/block') / name
            child['holders'] = [p.name for p in (sysdir / 'holders').iterdir()]
            child['sys_path'] = str(sysdir.resolve(strict=True))
            if child.get('type') == 'part':
                child['partn'] = int(read_sys(sysdir / 'partition'))
                child['start'] = int(read_sys(sysdir / 'start'))
        node['diskseq'] = read_sys(Path('/sys/class/block') / Path(node['path']).name / 'diskseq')
        node['identity'] = identity(node)
        node['layout'] = layout_identity(node)
        node['blocked'] = blocked_reason(node, protected)
        node['ventoy'] = bool(ventoy_partitions(node))
        node['model'] = clean(node.get('model')) or 'USB disk'
        node['serial'] = clean(node.get('serial'))
        result.append(node)
    return result


def selected_disk(request, disks=None, *, check_layout=True):
    path = request.get('path', '')
    if not isinstance(path, str) or not DEVICE.fullmatch(path):
        raise ValueError('Select a whole USB disk from the list.')
    matches = [node for node in (disk_inventory() if disks is None else disks) if node['path'] == path]
    if len(matches) != 1 or matches[0]['identity'] != request.get('identity'):
        raise RuntimeError('The selected USB disk was disconnected or changed. Refresh and select it again.')
    node = matches[0]
    if node['blocked']:
        raise RuntimeError(node['blocked'])
    if check_layout and node['layout'] != request.get('layout'):
        raise RuntimeError('The USB partition layout changed. Refresh and confirm the disk again.')
    return node


def verify_bundle(path=BUNDLE):
    with bundle_stream(path) as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != SHA256:
            raise RuntimeError('The bundled Ventoy archive failed verification. Repair or update Hyper Fusion before continuing.')


def bundle_stream(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_size != BUNDLE_SIZE:
        os.close(descriptor)
        raise RuntimeError('The bundled Ventoy archive failed verification. Repair or update Hyper Fusion before continuing.')
    return os.fdopen(descriptor, 'rb')


def requirements():
    missing = [name for name in ('bash', 'lsblk', 'parted', 'umount', 'xzcat', 'hexdump', 'udevadm', 'pkexec', 'udisksctl')
               if not shutil.which(name, path=ENV['PATH'])]
    if missing:
        raise RuntimeError('Missing system tools: ' + ', '.join(missing) + '. Run Hyper Fusion Setup to repair dependencies.')
    if platform.machine() not in ('x86_64', 'aarch64', 'i386', 'i686', 'mips64el'):
        raise RuntimeError('The bundled Ventoy engine does not support this CPU architecture.')


def status_payload():
    error = ''
    try:
        verify_bundle()
        requirements()
    except (OSError, RuntimeError) as exc:
        error = ('The offline Ventoy archive is missing. Repair or update Hyper Fusion.'
                 if isinstance(exc, FileNotFoundError) else str(exc))
    return {'ok': True, 'version': VERSION, 'bundle_error': error, 'disks': disk_inventory()}


@contextlib.contextmanager
def engine():
    # Copy and verify the SAME bytes that will be extracted. The user's profile
    # may be updated during authentication; root never runs from a shared cache.
    with tempfile.TemporaryDirectory(prefix='hyperfusion-ventoy-', dir='/tmp') as directory:
        directory = Path(directory)
        archive = directory / 'engine.tar.gz'
        with bundle_stream(BUNDLE) as source, archive.open('xb') as target:
            # Bound the copy even if the user replaces or grows the source.
            target.write(source.read(BUNDLE_SIZE + 1))
        verify_bundle(archive)
        with tarfile.open(archive, 'r:gz') as package:
            members = package.getmembers()
            total = 0
            for member in members:
                name = PurePosixPath(member.name)
                if (name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != f'ventoy-{VERSION}'
                        or not (member.isfile() or member.isdir())):
                    raise RuntimeError('Unexpected member in the Ventoy archive.')
                total += member.size
            if total > 128 * 1024 * 1024:
                raise RuntimeError('Unexpected Ventoy archive size.')
            package.extractall(directory, members=members, filter='data')
        root = directory / f'ventoy-{VERSION}'
        if (root / 'ventoy/version').read_text().strip() != VERSION:
            raise RuntimeError('The bundled Ventoy version is inconsistent.')
        yield root


def probe(root, path):
    output = run(['bash', './Ventoy2Disk.sh', '-l', path], cwd=root, timeout=45)
    version = re.search(r'Ventoy Version in Disk:\s*([0-9]+\.[0-9]+\.[0-9]+)', output)
    if not version:
        return None
    return {'version': version[1], 'secure_boot': bool(re.search(r'Secure Boot Support\s*:\s*YES', output)),
            'style': 'gpt' if re.search(r'Disk Partition Style\s*:\s*GPT', output) else 'mbr'}


def client_alive():
    if select.select([sys.stdin], [], [], 0)[0] and not os.read(sys.stdin.fileno(), 1):
        raise RuntimeError('The Control Panel request was closed before writing started.')


def validate_operation(action, request, node, installed):
    if action not in ('install', 'update'):
        raise ValueError('Unknown Ventoy operation.')
    if action == 'install':
        if request.get('erase_confirmed') != node['path']:
            raise ValueError('Confirm the exact USB disk before creating Ventoy.')
        if installed or node['ventoy']:
            raise RuntimeError('This disk already contains Ventoy. Use Update Ventoy to keep its files.')
        if request.get('style') not in ('mbr', 'gpt') or type(request.get('secure_boot')) is not bool:
            raise ValueError('Choose a partition style and Secure Boot setting.')
        if request['style'] == 'mbr' and node['size'] > 2 * 1024**4:
            raise ValueError('Disks larger than 2 TiB require GPT.')
    elif not installed:
        raise RuntimeError('A valid Ventoy installation was not found. No update was attempted.')
    elif tuple(map(int, installed['version'].split('.'))) > tuple(map(int, VERSION.split('.'))):
        raise RuntimeError(f'This USB has Ventoy {installed["version"]}, newer than the bundled engine. Update Hyper Fusion first.')


def command(action, request, installed):
    # Preserve existing Secure Boot support on updates; partition style is never changed.
    secure = request['secure_boot'] if action == 'install' else installed['secure_boot']
    result = ['bash', './Ventoy2Disk.sh', '-i' if action == 'install' else '-u', '-s' if secure else '-S']
    if action == 'install' and request['style'] == 'gpt':
        result.append('-g')
    return [*result, request['path']]


def unmount_disk(node):
    targets = sorted({p for child in descendants(node) for p in mounts(child)}, key=len, reverse=True)
    for target in targets:
        if not data_mount(target):
            raise RuntimeError('A protected mount appeared. Refresh the USB list.')
        emit({'stage': f'Unmounting {clean(target)}…'})
        run(['umount', '--', target], timeout=30)  # No force, lazy unmount, or swapoff.


def write_engine(root, argv):
    emit({'stage': 'Writing Ventoy… Keep the USB disk connected until completion.'})
    process = subprocess.Popen(argv, cwd=root, env=ENV, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    # The native dialog already confirmed the exact disk. Upstream -i asks twice,
    # -u once. Never send a force-install or non-destructive-install flag.
    try:
        process.stdin.write('y\ny\n')
        process.stdin.close()
    except BrokenPipeError:
        pass  # Read the engine's actual startup error below.
    for line in process.stdout:
        text = clean(line)[:3000]
        if text:
            emit({'log': text})
    code = process.wait()
    if code:
        log = root / 'log.txt'
        if log.exists():
            for line in log.read_text(errors='replace').splitlines()[-40:]:
                emit({'log': clean(line)[:3000]})
        raise RuntimeError(f'Ventoy exited with code {code}. See the operation log for details.')


def apply(action, request):
    if os.geteuid() != 0:
        raise PermissionError('Administrator authentication is required.')
    requirements()
    client_alive()
    node = selected_disk(request)
    lockfd = os.open('/run/hyperfusion-ventoy.lock', os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lockfd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another Ventoy operation is already running.') from exc
        emit({'stage': 'Verifying the bundled Ventoy engine and selected USB disk…'})
        with engine() as root:
            installed = probe(root, node['path'])
            validate_operation(action, request, node, installed)
            node = selected_disk(request)
            client_alive()
            unmount_disk(node)
            # A busy mount, device replacement, or newly active mapper fails closed.
            node = selected_disk(request)
            if any(mounts(child) for child in descendants(node)):
                raise RuntimeError('The USB disk is still mounted. Close files using it and try again.')
            client_alive()
            write_engine(root, command(action, request, installed))
            emit({'stage': 'Checking the installed Ventoy version…'})
            run(['udevadm', 'settle', '--timeout=15'])
            selected_disk(request, check_layout=False)
            final = probe(root, node['path'])
            if not final or final['version'] != VERSION:
                raise RuntimeError('Ventoy finished, but its installed version could not be verified. See the log before using this USB.')
            expected = request if action == 'install' else installed
            if any(final[key] != expected[key] for key in ('style', 'secure_boot')):
                raise RuntimeError('The final partition style or Secure Boot setting did not match the request. Review the log before using this USB.')
            return {'ok': True, 'path': node['path'], **final,
                    'message': ('Ventoy USB is ready. Open it in Fusion Files and copy your ISO files onto it.'
                                if action == 'install' else 'Ventoy updated. Your ISO files and partition style were preserved.')}


def mount_data(request):
    if os.geteuid() == 0:
        raise PermissionError('Open the USB from the normal desktop session.')
    node = selected_disk(request)
    parts = ventoy_partitions(node)
    if not parts:
        raise RuntimeError('The selected disk does not have a Ventoy data partition.')
    part = parts[0]
    if not mounts(part):
        run(['udisksctl', 'mount', '--block-device', part['path']], timeout=90)
    node = selected_disk(request)
    paths = mounts(ventoy_partitions(node)[0])
    if not paths:
        raise RuntimeError('The USB data partition could not be mounted.')
    path = paths[0]
    info = os.stat(path)
    dev = f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'
    if dev != part['maj:min'] or not data_mount(path):
        raise RuntimeError('The USB mount changed. Refresh and try again.')
    return {'ok': True, 'mountpoint': path}


def read_request():
    line = sys.stdin.readline(16385)
    if not line.endswith('\n') or len(line) > 16384:
        raise ValueError('Invalid Ventoy request.')
    request = json.loads(line)
    if not isinstance(request, dict):
        raise ValueError('Invalid Ventoy request.')
    return request


def main():
    args = sys.argv[1:]
    try:
        if args == ['status']:
            emit(status_payload())
        elif args == ['open']:
            emit(mount_data(read_request()))
        elif len(args) == 2 and args[0] == 'apply' and args[1] in ('install', 'update'):
            os.execv('/usr/bin/pkexec', ['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/python3', '-I',
                                       str(Path(__file__).resolve()), '--apply', args[1]])
        elif len(args) == 2 and args[0] == '--apply' and args[1] in ('install', 'update'):
            emit(apply(args[1], read_request()))
        else:
            raise ValueError('Open Ventoy USB from Control Panel.')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as exc:
        emit({'ok': False, 'error': clean(exc) or 'The Ventoy operation failed.'})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
