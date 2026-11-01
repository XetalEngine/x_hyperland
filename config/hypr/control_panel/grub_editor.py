#!/usr/bin/env python3
"""Drive discovery and transactional, additive GRUB menu editing.

The GUI owns the authenticated helper through its stdin pipe. Foreign disks are
only read; this never installs a bootloader, changes a partition or writes EFI
variables. Only our grub.d generator, its generated block and private journal
are written. All disk selections are re-discovered before saving.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
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
import struct
import subprocess
import sys
import tempfile
import uuid

GENERATOR = '/etc/grub.d/42_hyper_fusion'
BEGIN = '### BEGIN ' + GENERATOR + ' ###'
END = '### END ' + GENERATOR + ' ###'
SIGNATURE = '# Hyper Fusion GRUB Boot Editor v1'
READY_FS = {'vfat': 'fat', 'fat': 'fat', 'ext2': 'ext2', 'ext3': 'ext2',
            'ext4': 'ext2', 'btrfs': 'btrfs', 'xfs': 'xfs', 'ntfs': 'ntfs', 'ntfs3': 'ntfs'}
VENDORS = {'ubuntu': 'Ubuntu', 'debian': 'Debian', 'fedora': 'Fedora',
           'arch': 'Arch Linux', 'archlinux': 'Arch Linux', 'cachyos': 'CachyOS',
           'opensuse': 'openSUSE', 'manjaro': 'Manjaro', 'linuxmint': 'Linux Mint',
           'endeavouros': 'EndeavourOS', 'systemd': 'Linux Boot Manager'}
DEVICE_COLUMNS = 'NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,FSTYPE,UUID,PARTUUID,PTTYPE,PARTTYPE,MOUNTPOINTS,MAJ:MIN,RO,RM'


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2)+'\n').encode()


def command(args, timeout=25):
    result = subprocess.run(list(map(str, args)), capture_output=True, timeout=timeout,
                            env={**os.environ, 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    if result.returncode:
        message = result.stderr.decode(errors='replace').strip() or result.stdout.decode(errors='replace').strip()
        raise RuntimeError(message[-1600:] or f'{Path(args[0]).name} failed.')
    return result.stdout


def executable(*names):
    for name in names:
        found = shutil.which(name, path='/usr/sbin:/usr/bin:/sbin:/bin')
        if found:
            return found
    raise RuntimeError('GRUB tools are unavailable. Install GRUB before using this editor.')


def descendants(node):
    yield node
    for child in node.get('children', []):
        yield from descendants(child)


def inventory():
    data = json.loads(command(['lsblk', '--json', '--bytes', '--paths', '--output', DEVICE_COLUMNS]))
    return [item for item in data['blockdevices'] if item.get('type') == 'disk' and item.get('size', 0) > 0]


def drive_token(drive):
    return digest(encoded({key: drive.get(key) for key in ('path', 'maj:min', 'size', 'serial', 'wwn')}))


def drive_summary(drive):
    return {'path': drive['path'], 'token': drive_token(drive), 'size': drive['size'],
            'model': (drive.get('model') or Path(drive['path']).name).strip(),
            'connection': drive.get('tran') or '', 'serial': drive.get('serial') or '',
            'partitions': sum(1 for p in descendants(drive) if p.get('type') == 'part')}


def selected_drive(drives, path, token):
    matches = [drive for drive in drives if drive['path'] == path and drive_token(drive) == token]
    if len(matches) != 1:
        raise RuntimeError('The selected drive changed or was disconnected. Refresh drives and select it again.')
    info = os.stat(path)
    if not stat.S_ISBLK(info.st_mode) or f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' != matches[0]['maj:min']:
        raise RuntimeError('The drive identity changed. Refresh drives before continuing.')
    return matches[0]


def firmware(root=Path('/')):
    return 'uefi' if (root/'sys/firmware/efi').exists() else 'bios'


def secure_boot():
    try:
        files = list(Path('/sys/firmware/efi/efivars').glob('SecureBoot-*'))
        return bool(files and files[0].read_bytes()[4] == 1)
    except (OSError, IndexError):
        return False


def current_efi():
    try:
        output = command(['efibootmgr', '-v'], timeout=8).decode(errors='replace')
        current = re.search(r'^BootCurrent: ([0-9A-Fa-f]{4})$', output, re.M)
        if not current:
            return None
        line = next(line for line in output.splitlines() if line.startswith('Boot'+current[1]))
        match = re.search(r'HD\(\d+,GPT,([0-9a-fA-F-]+),[^)]*\)/(?:File\(([^)]+)\)|([\\/][^\t\r\n]+))', line, re.I)
        return (match[1].lower(), (match[2] or match[3]).strip().replace('\\', '/').lower()) if match else None
    except (OSError, RuntimeError, StopIteration, subprocess.TimeoutExpired):
        return None


def current_config(path):
    """Identify the live BIOS menu by filesystem, including Btrfs subvolumes."""
    fs_uuid = command([executable('grub-probe', 'grub2-probe'), '--target=fs_uuid', path]).decode().strip()
    relative = command([executable('grub-mkrelpath', 'grub2-mkrelpath'), path]).decode().strip()
    if not fs_uuid or not relative.startswith('/'):
        raise RuntimeError('Could not identify the current GRUB menu. No boot entries were changed.')
    return fs_uuid.lower(), relative


def private_mounts():
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.unshare(0x00020000) != 0:  # CLONE_NEWNS
        raise OSError(ctypes.get_errno(), 'Could not isolate drive inspection')
    command(['mount', '--make-rprivate', '/'])


def mounted_root(partition):
    """Reuse a mounted filesystem through a private, read-only bind mount."""
    if not any(partition.get('mountpoints') or []): return None
    try:
        mounts = json.loads(command(['findmnt', '--json', '--source', partition['path'],
                                    '--output', 'TARGET,FSROOT,MAJ:MIN']))['filesystems']
        for mount in mounts:
            if mount.get('fsroot') == '/' and mount.get('maj:min') == partition.get('maj:min'):
                return mount['target']
    except (OSError, ValueError, KeyError, RuntimeError): pass
    return None


@contextmanager
def inspect_partition(partition):
    """Use a private read-only mount, suppressing journal replay as well."""
    fs = partition.get('fstype')
    if fs not in READY_FS:
        raise ValueError('This filesystem cannot be inspected automatically.')
    options = ['ro', 'nosuid', 'nodev', 'noexec']
    if fs in ('ext3', 'ext4'): options += ['noload']
    if fs == 'btrfs': options += ['nologreplay', 'subvolid=5']
    if fs == 'xfs': options += ['norecovery', 'nouuid']
    existing = mounted_root(partition)
    if fs in ('ntfs', 'ntfs3') and not existing:
        if not shutil.which('ntfs-3g', path='/usr/sbin:/usr/bin:/sbin:/bin'):
            raise RuntimeError('Legacy Windows inspection needs the ntfs-3g package. UEFI Windows is detected from its EFI boot partition.')
        options += ['norecover']
    with tempfile.TemporaryDirectory(prefix='hyper-fusion-grub-', dir='/run') as directory:
        mounted = False
        try:
            # mount(8) is told the filesystem type explicitly; no guessing or
            # fallback that might replay a journal or clear Windows hibernation.
            if existing:
                command(['mount', '--bind', '--', existing, directory], timeout=20)
                mounted = True
                command(['mount', '-o', 'remount,bind,ro,nosuid,nodev,noexec', '--', directory], timeout=20)
            else:
                command(['mount', '-t', 'ntfs-3g' if fs in ('ntfs', 'ntfs3') else fs, '-o', ','.join(options),
                         '--', partition['path'], directory], timeout=20)
                mounted = True
            yield Path(directory)
        finally:
            if mounted:
                command(['umount', '--', directory], timeout=15)


def within(root, relative):
    path = (root/relative.lstrip('/')).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('A boot file points outside the selected filesystem.')
    return path


def small_file(root, relative, maximum=4*1024*1024):
    path = within(root, relative)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise ValueError('The boot file is not a supported regular file.')
    with path.open('rb') as stream:
        data = stream.read(maximum+1)
    if len(data) > maximum: raise ValueError('The boot file is too large.')
    return data


def efi_image(data, machine=None):
    machine = machine or platform.machine().lower()
    architectures = {'x86_64': 0x8664, 'amd64': 0x8664, 'aarch64': 0xaa64, 'i386': 0x14c, 'i686': 0x14c}
    try:
        offset = struct.unpack_from('<I', data, 60)[0]
        return (data[:2] == b'MZ' and data[offset:offset+4] == b'PE\0\0'
                and struct.unpack_from('<H', data, offset+4)[0] == architectures.get(machine)
                and struct.unpack_from('<H', data, offset+24+68)[0] == 10)
    except (struct.error, IndexError):
        return False


def entry_id(entry):
    return 'fusion-'+digest(encoded({key: entry.get(key) for key in ('kind', 'uuid', 'partuuid', 'loader')}))[:24]


def candidate(partition, kind, loader, title, data):
    result = {'kind': kind, 'loader': loader, 'title': title, 'uuid': partition['uuid'],
              'partuuid': partition.get('partuuid') or '', 'partition': partition['path'],
              'filesystem': partition['fstype'], 'loader_hash': digest(data), 'available': True}
    result['id'] = entry_id(result)
    return result


def detect(root, partition, mode, machine=None):
    """Pure filesystem inspection; fixtures exercise the same discovery path."""
    result = []
    efi = next((p for p in root.iterdir() if p.name.casefold() == 'efi' and p.is_dir()), None)
    if efi and efi.resolve().is_relative_to(root.resolve()):
        suffix = {'aarch64': 'aa64', 'i386': 'ia32', 'i686': 'ia32'}.get(machine or platform.machine().lower(), 'x64')
        for vendor in sorted(efi.iterdir())[:128]:
            if not vendor.is_dir() or not vendor.resolve().is_relative_to(root.resolve()): continue
            key = vendor.name.casefold()
            options = ([vendor/'Boot'/'bootmgfw.efi'] if key == 'microsoft' else
                       [vendor/f'shim{suffix}.efi', vendor/f'grub{suffix}.efi', vendor/f'systemd-boot{suffix}.efi'])
            # FAT is case insensitive on disk, but image fixtures need to be too.
            if key == 'microsoft':
                boot = next((p for p in vendor.iterdir() if p.name.casefold() == 'boot' and p.is_dir()), None)
                options = [p for p in boot.iterdir() if p.name.casefold() == 'bootmgfw.efi'] if boot else []
            elif key == 'linux':
                options = sorted(vendor.glob('*.efi'))[:32]
            else:
                files = {p.name.casefold(): p for p in vendor.iterdir()}
                options = [files[p.name.casefold()] for p in options if p.name.casefold() in files]
                if key == 'boot': options = [files[f'boot{suffix}.efi']] if f'boot{suffix}.efi' in files else []
            for path in options:
                relative = '/'+path.relative_to(root).as_posix()
                try: data = small_file(root, relative, 128*1024*1024)
                except (OSError, ValueError): continue
                if not efi_image(data, machine): continue
                title = ('Windows Boot Manager' if key == 'microsoft' else
                         'Linux · '+path.stem if key == 'linux' else
                         'UEFI bootloader' if key == 'boot' else VENDORS.get(key, vendor.name+' Linux'))
                item = candidate(partition, 'efi', relative, title, data)
                if mode != 'uefi': item.update(available=False, reason='This system needs UEFI; this computer is currently booted in BIOS mode.')
                result.append(item)
                if key != 'linux': break  # Prefer shim to GRUB, one entry per installation.
        if any('/efi/boot/' not in c['loader'].lower() for c in result):
            result = [c for c in result if '/efi/boot/' not in c['loader'].lower()]
    if mode == 'bios':
        # Delegate Linux kernel selection, root flags and encryption to its own
        # maintained GRUB menu, including separate /boot and Btrfs @ layouts.
        prefixes = ('', '@/', '@rootfs/', 'root/') if partition['fstype'] == 'btrfs' else ('',)
        for prefix in prefixes:
            for name in ('boot/grub/grub.cfg', 'grub/grub.cfg', 'boot/grub2/grub.cfg', 'grub2/grub.cfg'):
                relative = '/'+prefix+name
                try: data = small_file(root, relative)
                except (OSError, ValueError): continue
                if b'menuentry ' not in data and b'blscfg' not in data: continue
                title = 'Linux'
                try:
                    release = small_file(root, prefix+'etc/os-release', 65536).decode(errors='replace')
                    match = re.search(r'^PRETTY_NAME=["\']?([^\n"\']+)', release, re.M)
                    if match: title = match[1]
                except (OSError, ValueError): pass
                item = candidate(partition, 'config', relative, title, data)
                if re.search(rb'^\s*blscfg\b', data, re.M) and not any(
                        (Path(p)/'i386-pc/blscfg.mod').is_file() for p in ('/usr/lib/grub', '/usr/lib/grub2')):
                    item.update(available=False, reason='This Linux menu needs a GRUB boot module that is not installed on this computer.')
                result.append(item)
        if partition['fstype'] in ('ntfs', 'ntfs3') and partition.get('pttype') == 'dos':
            files = {p.name.casefold(): p for p in root.iterdir()}
            try:
                boot = files['boot']; manager = small_file(root, files['bootmgr'].name, 16*1024*1024)
                bcd = next(p for p in boot.iterdir() if p.name.casefold() == 'bcd')
                small_file(root, str(bcd.relative_to(root)), 16*1024*1024)
                result.append(candidate(partition, 'legacy-windows', '+1', 'Windows', manager))
            except (OSError, ValueError, KeyError, StopIteration): pass
    return result


def shared_reference(root, entry, partitions):
    """Associate a shared ESP only with a UUID/GPT reference to this drive."""
    if '/microsoft/' in entry['loader'].lower():
        parent = PurePosixPath(entry['loader']).parent
        try:
            directory = within(root, str(parent))
            path = next(p for p in directory.iterdir() if p.name.casefold() == 'bcd')
            data = small_file(root, str(path.relative_to(root)), 16*1024*1024)
            if data[:4] != b'regf': return False
            # BCD device records carry a GPT partition GUID in Windows GUID byte
            # order. Ignore recovery/MSR partitions; this selects the shared boot
            # manager, preserving its existing Windows OS choices and BitLocker.
            return any(uuid.UUID(p['partuuid']).bytes_le in data for p in partitions
                       if p.get('partuuid') and (p.get('parttype') or '').lower() == 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7')
        except (OSError, ValueError, StopIteration): return False
    try:
        data = small_file(root, str(PurePosixPath(entry['loader']).parent/'grub.cfg'), 65536).decode().lower()
        return any(re.search(r'(?<![a-z0-9-])'+re.escape(p['uuid'].lower())+r'(?![a-z0-9-])', data)
                   for p in partitions if p.get('uuid'))
    except (OSError, ValueError, UnicodeError): return False


def scan_drive(drive, drives, mode, *, inspector=inspect_partition, current=None, live_config=None, alive=lambda: None):
    candidates, notes = [], []
    counts = {}
    for disk in drives:
        for part in descendants(disk):
            if part.get('uuid'):
                counts.setdefault(part['uuid'].lower(), set()).add(part['path'])
    partitions = list(descendants(drive))
    probes = [(part, False) for part in partitions]
    if mode == 'uefi':
        # EFI boot files can live on a different disk than Windows/Linux itself.
        # Only a matching boot configuration reference makes that association.
        probes += [(p, True) for d in drives if d['path'] != drive['path'] for p in descendants(d)
                   if p.get('fstype') in ('fat', 'vfat')]
    for partition, shared in probes:
        alive()
        if partition.get('fstype') not in READY_FS or not partition.get('uuid'): continue
        if mode == 'uefi' and partition['fstype'] not in ('fat', 'vfat'): continue
        try:
            with inspector(partition) as root:
                found = detect(root, partition, mode)
                if shared:
                    found = [item for item in found if shared_reference(root, item, partitions)]
                    for item in found:
                        item['detail'] = 'Uses a boot manager shared with another drive. Its existing operating-system choices are kept.'
                        item['source_drive'] = next(d['path'] for d in drives if any(p['path'] == partition['path'] for p in descendants(d)))
            for item in found:
                if len(counts.get(item['uuid'].lower(), ())) > 1:
                    item.update(available=False, reason='Another connected filesystem has the same UUID. This cloned drive cannot be selected reliably by GRUB.')
                if current and (item['partuuid'].lower(), item['loader'].lower()) == current:
                    item.update(available=False, reason='This bootloader already starts this computer.')
                if live_config and item['kind'] == 'config' and (item['uuid'].lower(), item['loader']) == live_config:
                    item.update(available=False, reason='This is the GRUB menu already used by this computer.')
                item['drive'] = drive['path']; item['drive_token'] = drive_token(drive)
                candidates.append(item)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            if not shared: notes.append(f"{Path(partition['path']).name}: {error}")
    if not candidates:
        notes.insert(0, 'No compatible Windows or Linux bootloader was found on this drive. Locked volumes, missing boot files and unsupported filesystems cannot be added automatically.')
    return {'candidates': candidates, 'notes': notes}


def title_text(value):
    if not isinstance(value, str): raise ValueError('Enter a name for the boot menu.')
    value = value.strip()
    if not value or len(value) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Use a boot-menu name between 1 and 100 characters on one line.')
    return value


def quote(value):
    return "'" + value.replace("'", "'\\''") + "'"


def render_entry(entry):
    name = title_text(entry['name'])
    if not re.fullmatch(r'[A-Za-z0-9-]{4,128}', entry['uuid']): raise ValueError('Unsupported filesystem UUID.')
    if entry['id'] != entry_id(entry): raise ValueError('The saved boot entry has an invalid identity.')
    kind = entry['kind']; loader = entry['loader']; fs = READY_FS.get(entry['filesystem'])
    if not fs: raise ValueError('Unsupported GRUB filesystem.')
    if kind not in ('efi', 'config', 'legacy-windows'): raise ValueError('Unsupported boot method.')
    if kind != 'legacy-windows':
        path = PurePosixPath(loader)
        if not path.is_absolute() or '..' in path.parts or str(path) != loader or any(ord(c) < 32 for c in loader):
            raise ValueError('Invalid bootloader path.')
    os_class = 'windows' if kind == 'legacy-windows' or '/microsoft/' in loader.lower() else 'gnu-linux'
    lines = [f'menuentry {quote(name)} --class {os_class} --id {quote(entry["id"])} {{',
             '    insmod part_gpt', '    insmod part_msdos', f'    insmod {fs}',
             f'    if search --no-floppy --fs-uuid --set=root {quote(entry["uuid"])}; then']
    if kind == 'config': lines += ['        configfile '+quote(loader)]
    else:
        lines += ['        insmod chain']
        if kind == 'legacy-windows': lines += ['        insmod drivemap', '        drivemap -s (hd0) ${root}']
        lines += ['        chainloader '+('+1' if kind == 'legacy-windows' else quote(loader))]
    lines += ['    else', "        echo 'The selected drive is not connected.'", '        sleep --interruptible 5', '    fi']
    return '\n'.join(lines+['}', ''])


def render(entries):
    text = SIGNATURE+'\n'
    if entries:
        text += 'set timeout_style=menu\nif [ "${timeout}" = 0 ]; then\n    set timeout=5\nfi\n\n'
    return text + '\n'.join(render_entry(entry) for entry in entries)


def replace_block(config, body):
    lines = config.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip('\r\n') == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.rstrip('\r\n') == END]
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
            raise RuntimeError('The existing Fusion boot-menu block is damaged. No files were changed.')
        if SIGNATURE not in ''.join(lines[starts[0]:ends[0]]):
            raise RuntimeError('Another tool owns the requested GRUB section.')
        lines[starts[0]:ends[0]+1] = [BEGIN+'\n'+body+END+'\n']
        return ''.join(lines)
    return config + ('' if config.endswith('\n') else '\n') + '\n'+BEGIN+'\n'+body+END+'\n'


def read_optional(path):
    try: return path.read_bytes()
    except FileNotFoundError: return None


def atomic(path, data, mode=0o600):
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, mode); os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally: Path(temporary).unlink(missing_ok=True)


class Store:
    def __init__(self, root=Path('/'), checker=None):
        self.root = root
        self.state = root/'var/lib/hyper-fusion/grub-editor'
        self.generator = root/GENERATOR.lstrip('/')
        choices = [root/name for name in ('boot/grub/grub.cfg', 'boot/grub2/grub.cfg') if (root/name).is_file()]
        if len(choices) != 1:
            raise RuntimeError('A single active GRUB configuration could not be identified. This editor needs an existing GRUB installation.')
        self.config = choices[0]
        if self.config.is_symlink() or not self.config.resolve().is_relative_to((root/'boot').resolve()):
            raise RuntimeError('The GRUB configuration location is not supported.')
        self.checker = checker or executable('grub-script-check', 'grub2-script-check')

    def safe_paths(self):
        for path in (self.config, self.generator, self.state):
            for parent in (path, *path.parents):
                if parent == self.root: break
                if parent.is_symlink(): raise RuntimeError('A GRUB editor path is a symbolic link. Nothing was changed.')
                if parent.exists():
                    info = parent.stat()
                    if self.root == Path('/') and (info.st_uid != 0 or info.st_mode & 0o022):
                        raise RuntimeError('GRUB configuration paths must be owned and writable only by root.')

    def files(self):
        return {'config': self.config, 'generator': self.generator, 'entries': self.state/'entries.json'}

    @contextmanager
    def locked(self):
        self.safe_paths()
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.state/'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise RuntimeError('Another GRUB change is in progress. Try again when it finishes.') from None
            self.recover()
            yield

    def revision(self):
        return digest(encoded({key: digest(read_optional(path)) for key, path in self.files().items()}))

    def entries(self):
        data = read_optional(self.state/'entries.json')
        if data is None: return []
        value = json.loads(data)
        if value.get('version') != 1 or not isinstance(value.get('entries'), list):
            raise RuntimeError('The saved GRUB entries need recovery.')
        for entry in value['entries']: render_entry(entry)
        return value['entries']

    def status(self):
        return {'config': str(self.config), 'entries': self.entries(), 'revision': self.revision(),
                'can_undo': (self.state/'last.json').is_file()}

    def check(self, text):
        with tempfile.NamedTemporaryFile(prefix='fusion-grub-check-', suffix='.cfg') as stream:
            stream.write(text.encode()); stream.flush()
            command([self.checker, stream.name])

    def snapshot(self, targets):
        backup = self.state/'backups'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
        backup.mkdir(parents=True, mode=0o700)
        record = {'version': 1, 'config': str(self.config), 'before': {}, 'after': {}, 'backup': str(backup)}
        for key, path in self.files().items():
            old = read_optional(path)
            record['before'][key] = None if old is None else {'sha': digest(old), 'mode': stat.S_IMODE(path.stat().st_mode)}
            if old is not None: atomic(backup/key, old)
            data, mode = targets[key]
            record['after'][key] = None if data is None else {'sha': digest(data), 'mode': mode}
        atomic(backup/'record.json', encoded(record))
        return record

    def restore(self, record):
        backup = Path(record['backup'])
        if record['config'] != str(self.config) or not backup.resolve().is_relative_to((self.state/'backups').resolve()):
            raise RuntimeError('The GRUB recovery record belongs to another installation.')
        for key, path in self.files().items():
            before, after = record['before'][key], record['after'][key]
            if digest(read_optional(path)) not in (before['sha'] if before else None, after['sha'] if after else None):
                raise RuntimeError('GRUB files changed outside this editor. Automatic rollback was stopped to preserve those changes.')
            if before and digest((backup/key).read_bytes()) != before['sha']:
                raise RuntimeError('The GRUB backup did not pass its integrity check.')
        for key, path in self.files().items():
            before = record['before'][key]
            if before: atomic(path, (backup/key).read_bytes(), before['mode'])
            else: path.unlink(missing_ok=True)

    def recover(self):
        data = read_optional(self.state/'pending.json')
        if data is None: return
        record = json.loads(data)
        self.restore(record)
        (self.state/'pending.json').unlink()

    def commit(self, entries, expected, alive=lambda: None):
        if expected != self.revision():
            raise RuntimeError('GRUB changed since you opened this page. Refresh before saving.')
        old_script = read_optional(self.generator)
        if old_script is not None and SIGNATURE.encode() not in old_script:
            raise RuntimeError('Another tool owns the Fusion generator filename. Nothing was changed.')
        config = self.config.read_text()
        self.check(config)
        if not re.search(r'\b(menuentry|blscfg)\b', config):
            raise RuntimeError('The current GRUB menu has no existing boot entries. Nothing was changed.')
        body = render(entries)
        revised = replace_block(config, body)
        self.check(revised)
        targets = {'generator': (('#!/bin/sh\nexec tail -n +3 "$0"\n'+body).encode(), 0o755),
                   'config': (revised.encode(), stat.S_IMODE(self.config.stat().st_mode)),
                   'entries': (encoded({'version': 1, 'entries': entries}), 0o600)}
        alive()
        record = self.snapshot(targets)
        if expected != self.revision():
            raise RuntimeError('Another program changed GRUB while the menu was being checked. Refresh before saving.')
        atomic(self.state/'pending.json', encoded(record))
        try:
            # Publish the complete validated configuration last. No source disk
            # writes, grub-install, firmware edits or third-party scripts run.
            for key in ('generator', 'entries', 'config'):
                data, mode = targets[key]; atomic(self.files()[key], data, mode)
            atomic(self.state/'last.json', encoded(record))
            (self.state/'pending.json').unlink()
        except BaseException:
            self.restore(record)
            (self.state/'pending.json').unlink(missing_ok=True)
            raise
        return str(Path(record['backup']))

    def undo(self, expected, alive=lambda: None):
        if expected != self.revision(): raise RuntimeError('GRUB changed. Refresh before undoing.')
        record = json.loads((self.state/'last.json').read_text())
        for key, path in self.files().items():
            after = record['after'][key]
            if digest(read_optional(path)) != (after['sha'] if after else None):
                raise RuntimeError('Another tool updated GRUB after this change. Remove the entry instead to keep those updates.')
        alive(); atomic(self.state/'pending.json', encoded(record))
        self.restore(record)
        (self.state/'pending.json').unlink()
        (self.state/'last.json').unlink()


def client_alive():
    poll = select.poll(); poll.register(0, select.POLLHUP | select.POLLERR)
    if poll.poll(0): raise RuntimeError('Control Panel closed before the change was saved.')


def status_payload():
    payload = {'mode': firmware(), 'secure_boot': secure_boot(), 'drives': [drive_summary(d) for d in inventory()]}
    try:
        store = Store()
        payload.update(store.status(), supported=True)
    except PermissionError:
        payload.update(supported=True, entries=[], revision='', can_undo=False,
                       message='Select a drive to inspect it with administrator authentication.')
    except (OSError, ValueError, RuntimeError) as error:
        payload.update(supported=False, message=str(error), entries=[], revision='', can_undo=False)
    return payload


class Session:
    def __init__(self):
        self.store = Store()
        private_mounts()

    def handle(self, request):
        action = request.get('action')
        with self.store.locked():
            if action == 'refresh': return status_payload()
            if action in ('scan', 'add'):
                drives = inventory()
                drive = selected_drive(drives, request.get('drive'), request.get('drive_token'))
                emit({'progress': 'Detecting bootloaders on '+drive_summary(drive)['model']+'…'})
                mode = firmware()
                scanned = scan_drive(drive, drives, mode, current=current_efi(),
                                     live_config=current_config(self.store.config) if mode == 'bios' else None,
                                     alive=client_alive)
                if action == 'scan': return {**scanned, **self.store.status()}
                matches = [c for c in scanned['candidates'] if c['id'] == request.get('candidate') and c['available']]
                if len(matches) != 1: raise RuntimeError('That bootloader is no longer available. Select the drive again to rescan.')
                item = matches[0]
                if item['loader_hash'] != request.get('loader_hash'):
                    raise RuntimeError('The boot files changed after detection. Select the drive again before adding it.')
                if item['kind'] == 'legacy-windows':
                    with open(item['partition'], 'rb') as stream: sector = stream.read(512)
                    if len(sector) != 512 or sector[-2:] != b'\x55\xaa' or not any(sector[:440]):
                        raise RuntimeError('The Windows partition has no usable legacy boot sector.')
                entries = [entry for entry in self.store.entries() if entry['id'] != item['id']]
                item['name'] = title_text(request.get('name')); entries.append(item)
            elif action in ('rename', 'remove'):
                entries = self.store.entries()
                matches = [entry for entry in entries if entry['id'] == request.get('id')]
                if len(matches) != 1: raise RuntimeError('That entry no longer exists. Refresh the boot menu.')
                if action == 'rename': matches[0]['name'] = title_text(request.get('name'))
                else: entries.remove(matches[0])
            elif action == 'undo':
                self.store.undo(request.get('revision'), client_alive)
                return {**self.store.status(), 'message': 'The last GRUB change was undone.'}
            else: raise ValueError('Unknown GRUB editor action.')
            emit({'progress': 'Checking the complete GRUB menu and saving a backup…'})
            backup = self.store.commit(entries, request.get('revision'), client_alive)
            return {**self.store.status(), 'backup': backup,
                    'message': 'Saved. Your boot menu is ready for the next restart.'}


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    args = sys.argv[1:]
    try:
        if args == ['status']:
            emit(status_payload()); return 0
        if args == ['connect']:
            os.execv('/usr/bin/pkexec', ['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/python3', '-I',
                                       str(Path(__file__).resolve()), '--serve'])
        if args != ['--serve'] or os.geteuid() != 0:
            raise PermissionError('Open GRUB Boot Editor from Control Panel to authenticate.')
        client_alive()
        session = Session()
        while select.select([sys.stdin], [], [], 300)[0]:
            line = sys.stdin.readline(65537)
            if not line: break
            if len(line) > 65536: raise ValueError('The request is too large.')
            try:
                request = json.loads(line)
                if not isinstance(request, dict): raise ValueError('Invalid request.')
                client_alive()
                result = session.handle(request)
                emit({'result': result})
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                emit({'error': str(error)})
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        emit({'error': str(error)}); return 1


if __name__ == '__main__':
    raise SystemExit(main())
