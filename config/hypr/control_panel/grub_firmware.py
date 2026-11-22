#!/usr/bin/env python3
"""Reviewed UEFI registration of this installation, never grub-install.

A dedicated standalone EFI image finds this GRUB menu by filesystem UUID.
No existing vendor loader, fallback loader, partition or boot sector is replaced.
All reads are repeated at confirmation. The review includes a missing EFI module
directory, when needed. Existing bootloaders and firmware entries are preserved.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
import grub_editor as grub

ESP_TYPE = 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b'


def parse_firmware(text):
    order = re.search(r'^BootOrder:\s*([0-9a-fA-F,]*)\s*$', text, re.M)
    entries = []
    for m in re.finditer(r'^Boot([0-9a-fA-F]{4})(\*?)\s+([^\n]*)$', text, re.M):
        body = m[3]
        hd = re.search(r'HD\(\d+,GPT,([0-9a-fA-F-]+),', body, re.I)
        device = grub.efi_device_path(body)
        label = re.split(r'\s+(?:HD|PciRoot|VenHw|BBS|FvFile)\(', body, maxsplit=1)[0].strip()
        entries.append({'number': m[1].upper(), 'active': bool(m[2]), 'label': label,
                        'partuuid': hd[1].lower() if hd else '',
                        'loader': device[1].replace('/', '\\') if device else ''})
    return {'order': [v.upper() for v in order[1].split(',') if v] if order else [], 'entries': entries}


def loader_config(filesystem_uuid, config_path):
    if not re.fullmatch(r'[A-Za-z0-9-]{4,128}', filesystem_uuid): raise ValueError('Unsupported boot filesystem UUID.')
    path = Path(config_path)
    if not path.is_absolute() or '..' in path.parts or any(ord(c) < 32 for c in config_path):
        raise ValueError('Unsupported GRUB configuration path.')
    return '''# Hyper Fusion: this installation's menu, located by filesystem UUID.
insmod part_gpt
insmod part_msdos
insmod search_fs_uuid
if search --no-floppy --fs-uuid --set=root '''+grub.quote(filesystem_uuid)+'''; then
  set prefix=($root)'''+grub.quote(str(path.parent))+'''
  configfile ($root)'''+grub.quote(config_path)+'''
else
  echo 'The Hyper Fusion boot filesystem was not found.'
  sleep --interruptible 10
fi
'''


class Firmware:
    def __init__(self, store):
        self.store = store; self.root = store.root
        self.state = store.state/'firmware'

    def nvram(self):
        raw = grub.command([grub.executable('efibootmgr'), '--verbose']).decode(errors='replace')
        return {**parse_firmware(raw), 'raw': raw}

    def platform_check(self):
        if grub.firmware(self.root) != 'uefi': raise RuntimeError('Boot this system in UEFI mode to register it in firmware.')
        if platform.machine().lower() not in ('x86_64', 'amd64'):
            raise RuntimeError('Creating a Hyper Fusion EFI loader currently requires x86-64 UEFI.')
        variables = self.root/'sys/firmware/efi/efivars'
        if not variables.is_dir() or os.statvfs(variables).f_flag & os.ST_RDONLY:
            raise RuntimeError('UEFI variables are unavailable or read-only. Boot Linux directly in UEFI mode.')
        for path in variables.glob('SecureBoot-*'):
            value = path.read_bytes()
            if len(value) != 5 or value[4] not in (0, 1): raise RuntimeError('The Secure Boot state could not be verified.')
            if value[4]: raise RuntimeError('Secure Boot is enabled. This action creates an unsigned GRUB loader; use your distribution’s signed bootloader setup instead.')
        grub.executable('efibootmgr'); grub.executable('grub-mkstandalone', 'grub2-mkstandalone')

    def partitions(self):
        result = []
        for disk in grub.inventory():
            for part in grub.descendants(disk):
                if (part.get('parttype') or '').lower() != ESP_TYPE or part.get('fstype') not in ('fat', 'vfat') or part.get('ro'):
                    continue
                mounts = [m for m in part.get('mountpoints') or [] if m and m != '/']
                if not mounts or not part.get('partuuid'): continue
                for mount in mounts:
                    target = Path(mount)
                    if not target.is_absolute() or target.resolve() != target: continue
                    mounted = json.loads(grub.command(['findmnt', '--json', '--mountpoint', mount,
                                                       '--output', 'TARGET,MAJ:MIN,FSROOT,FSTYPE,OPTIONS']))['filesystems']
                    if len(mounted) != 1 or mounted[0].get('maj:min') != part.get('maj:min') or mounted[0].get('fsroot') != '/': continue
                    if 'ro' in mounted[0].get('options', '').split(','): continue
                    number = (self.root/'sys/class/block'/Path(part['path']).name/'partition').read_text().strip()
                    if not number.isdigit() or int(number) < 1: continue
                    result.append({'partition': part['path'], 'disk': disk['path'], 'number': int(number),
                                   'partuuid': part['partuuid'].lower(), 'mount': mount, 'device': part['maj:min'],
                                   'token': grub.digest(grub.encoded([grub.drive_token(disk), part['partuuid'], part['maj:min'], mount]))})
                    break
        return result

    def status(self):
        try:
            virtual = subprocess.run(['systemd-detect-virt', '--vm'], capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError): virtual = False
        scope = ('This is a virtual machine. Registration changes the VM firmware only. Run Linux on the physical machine to add it to that motherboard’s boot menu.'
                 if virtual else 'Registration adds this Linux installation to this computer’s UEFI boot menu.')
        try:
            self.platform_check()
            partitions = self.partitions(); nvram = self.nvram()
            return {'available': bool(partitions), 'reason': '' if partitions else 'Mount this installation’s EFI System Partition first (usually /boot, /efi or /boot/efi).',
                    'partitions': partitions, 'entries': nvram['entries'], 'order': nvram['order'], 'scope': scope}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            return {'available': False, 'reason': str(error), 'partitions': [], 'entries': [], 'scope': scope}

    def destination(self, partition, relative):
        mount = Path(partition['mount']); target = mount/relative
        if not target.is_relative_to(mount) or '..' in target.parts: raise ValueError('Invalid EFI loader location.')
        for path in (target, *target.parents):
            if path == mount.parent: break
            if path.is_symlink(): raise RuntimeError('The EFI loader path contains a symbolic link.')
            if path.exists() and self.root == Path('/') and path.stat().st_uid != 0:
                raise RuntimeError('The EFI partition must be mounted with root ownership.')
        if target.exists() and not target.is_file(): raise RuntimeError('The EFI loader destination is not a regular file.')
        return target

    def matching(self, nvram, part, loader):
        return [e for e in nvram['entries'] if e['partuuid'] == part['partuuid'] and e['loader'] == loader.lower()]

    def unique_reference(self, reference, part):
        devices = [p for d in grub.inventory() for p in grub.descendants(d)]
        roots = {p['path'] for p in devices if str(p.get('uuid', '')).lower() == reference[0].lower()}
        esps = {p['path'] for p in devices if str(p.get('partuuid', '')).lower() == part['partuuid'].lower()}
        if len(roots) != 1:
            raise RuntimeError('The GRUB filesystem must have a unique UUID. Check for a connected clone of this installation.')
        if len(esps) != 1:
            raise RuntimeError('The EFI partition must have a unique partition UUID. Disconnect cloned EFI partitions before registration.')

    def module_files(self, directory):
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError('GRUB EFI support files are missing or linked. Install the distribution’s GRUB EFI tools first.')
        files = {}
        for path in directory.iterdir():
            if path.suffix not in ('.mod', '.lst'): continue
            if path.is_symlink() or not path.is_file(): raise RuntimeError('An EFI support file is not a regular file.')
            if self.root == Path('/') and (path.stat().st_uid != 0 or path.stat().st_mode & 0o022):
                raise RuntimeError('GRUB EFI support files must be writable only by root.')
            files[path.name] = grub.digest(path.read_bytes())
        if not {'normal.mod', 'configfile.mod', 'linux.mod', 'echo.mod', 'halt.mod'} <= files.keys():
            raise RuntimeError('The installed GRUB EFI support files are incomplete.')
        return files

    def prepare_modules(self, backup):
        source = self.root/'usr/lib/grub/x86_64-efi'
        target = self.store.config.parent/'x86_64-efi'
        hashes = self.module_files(source)
        install = not target.exists()
        installed_hashes = {} if install else self.module_files(target)
        # grub-install copies .mod files and a fixed list of runtime indexes
        # (util/grub-install-common.c). Arch also packages an empty fdt.lst for
        # x86_64-efi, which grub-install does not copy. Its absence is normal,
        # not an ABI mismatch. Keep every real module/index comparison and the
        # full source/target snapshots used to detect changes after review.
        mismatched = [name for name, sha in hashes.items()
                      if installed_hashes.get(name) != sha
                      and not (name == 'fdt.lst' and sha == grub.digest(b'') and name not in installed_hashes)]
        if not install and mismatched:
            raise RuntimeError('Existing GRUB EFI support files differ from the installed GRUB tools ('+
                               ', '.join(sorted(mismatched)[:5])+'). Update them with your distribution’s bootloader installer first; they were not overwritten.')
        if target.is_symlink(): raise RuntimeError('The GRUB EFI support directory is a symbolic link.')
        if install:
            staged = backup/'modules'; staged.mkdir(mode=0o700)
            for name, sha in hashes.items():
                content = (source/name).read_bytes()
                if grub.digest(content) != sha: raise RuntimeError('GRUB was updated while preparing its EFI support files. Review again.')
                grub.atomic(staged/name, content, 0o644)
        return {'target': str(target), 'source': str(source), 'install': install, 'hashes': hashes,
                'installed_hashes': installed_hashes}

    def check_modules(self, plan):
        modules = plan['modules']; target = Path(modules['target'])
        if self.module_files(Path(modules['source'])) != modules['hashes']:
            raise RuntimeError('Installed GRUB tools changed after review. Review again.')
        if modules['install']:
            if target.exists() or target.is_symlink(): raise RuntimeError('The EFI support directory changed after review.')
            if self.module_files(Path(plan['backup'])/'modules') != modules['hashes']:
                raise RuntimeError('The prepared EFI support files failed verification.')
        elif self.module_files(target) != modules['installed_hashes']:
            raise RuntimeError('GRUB EFI support files changed after review.')

    def prepare(self, request, alive=lambda: None):
        self.platform_check(); alive()
        if request.get('revision') != self.store.revision(): raise RuntimeError('GRUB changed. Reload the current menu first.')
        self.store.check(self.store.config.read_text())
        parts = [p for p in self.partitions() if p['token'] == request.get('partition_token')]
        if len(parts) != 1: raise RuntimeError('The EFI partition changed or was unmounted. Reload firmware details.')
        part = parts[0]; label = grub.title_text(request.get('label'))
        if len(label.encode('utf-16-le')) > 160: raise ValueError('Use a shorter firmware boot label (at most 80 characters).')
        first = request.get('first', False)
        if type(first) is not bool: raise ValueError('Invalid boot-priority selection.')
        reference = grub.current_config(self.store.config)
        if not reference: raise RuntimeError('The current GRUB filesystem UUID and path could not be identified.')
        fs_uuid, config_path = reference
        self.unique_reference(reference, part)
        probe = grub.executable('grub-probe', 'grub2-probe')
        if grub.command([probe, '--target=abstraction', self.store.config]).strip():
            raise RuntimeError('This boot filesystem needs additional encrypted, RAID or LVM setup. Use the distribution bootloader installer for it.')
        fs = grub.command([probe, '--target=fs', self.store.config]).decode().strip()
        if fs not in ('ext2', 'btrfs', 'fat', 'xfs'): raise RuntimeError('This boot filesystem is not supported for standalone registration.')
        identity = grub.digest(grub.encoded(reference))[:16]
        relative = 'EFI/HyperFusion-'+identity+'/grubx64.efi'
        loader = '\\'+relative.replace('/', '\\'); target = self.destination(part, relative)
        owner = self.state/(identity+'.json')
        previous = grub.read_optional(target)
        if previous is not None:
            metadata = json.loads(owner.read_text()) if owner.exists() else {}
            if metadata.get('target') != str(target) or metadata.get('sha') != grub.digest(previous):
                raise RuntimeError('An existing EFI loader at this location is not owned by this editor. It was left unchanged.')
        nvram = self.nvram(); matches = self.matching(nvram, part, loader)
        if len(matches) > 1: raise RuntimeError('Duplicate firmware entries already point to this loader. Resolve them in firmware settings first.')
        if matches and not matches[0]['active']: raise RuntimeError('The existing firmware entry for this loader is disabled. Enable it in firmware settings first.')
        if matches and matches[0]['label'] != label:
            raise RuntimeError('This loader is already registered as “'+matches[0]['label']+'”. Use that label to refresh it without creating a duplicate.')
        token = uuid.uuid4().hex
        backup = self.state/'backups'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+token[:8])
        backup.mkdir(parents=True, mode=0o700); os.chmod(self.state, 0o700)
        modules = self.prepare_modules(backup)
        script = loader_config(fs_uuid, config_path)
        self.store.check(script)
        grub.atomic(backup/'embedded.cfg', script.encode())
        image = backup/'grubx64.efi'
        grub.command([grub.executable('grub-mkstandalone', 'grub2-mkstandalone'), '--format=x86_64-efi',
                      '--modules=part_gpt part_msdos search search_fs_uuid configfile normal loadenv linux chain',
                      '--locales=', '--fonts=', '--output='+str(image),
                      'boot/grub/grub.cfg='+str(backup/'embedded.cfg')], timeout=120)
        content = image.read_bytes()
        if not grub.efi_image(content, 'x86_64'): raise RuntimeError('The generated EFI loader did not pass validation.')
        if previous is not None: grub.atomic(backup/'previous.efi', previous)
        old_owner = grub.read_optional(owner)
        if old_owner is not None: grub.atomic(backup/'previous-owner.json', old_owner)
        grub.atomic(backup/'firmware-before.txt', nvram['raw'].encode())
        plan = dict(token=token, created=time.monotonic(), revision=request['revision'], partition=part,
                    target=str(target), relative=relative, reference=reference, label=label, first=first,
                    loader=loader, owner=str(owner), previous_sha=grub.digest(previous), image_sha=grub.digest(content),
                    owner_sha=grub.digest(old_owner), backup=str(backup), nvram=nvram,
                    existing=matches[0]['number'] if matches else '', modules=modules)
        plan['review'] = dict(token=token, label=label, partition=part['partition'], target=str(target),
                              config=str(self.store.config), filesystem_uuid=fs_uuid, backup=str(backup),
                              priority='Make this the first firmware boot choice.' if first else 'Keep the current boot priority; add this entry at the end if needed.',
                              scope=self.status()['scope'], existing=bool(matches),
                              support_files=('Install missing EFI support files: ' if modules['install'] else 'Reuse verified EFI support files: ')+modules['target'])
        recovery = f'UEFI registration backup\nEFI loader: {target}\nGRUB filesystem UUID: {fs_uuid}\nGRUB menu: {config_path}\n'
        recovery += 'The firmware state before registration is in firmware-before.txt; plan.json records the reviewed target.\n'
        recovery += plan['review']['support_files']+'\n'
        recovery += ('The old loader is previous.efi; restore it to the EFI loader path shown above if needed.\n' if previous is not None else
                     'No loader existed at that exact path before registration. Other EFI loaders were not changed.\n')
        grub.atomic(backup/'RECOVERY.txt', recovery.encode())
        grub.atomic(backup/'plan.json', grub.encoded(plan)); alive()
        if self.store.revision() != plan['revision']:
            raise RuntimeError('GRUB changed while preparing the loader. Reload and review again.')
        return plan

    def install(self, plan, token, alive=lambda: None):
        if not plan or plan['token'] != token or time.monotonic()-plan['created'] > 300:
            raise RuntimeError('This firmware review expired. Review again before registering.')
        self.platform_check(); alive()
        if self.store.revision() != plan['revision'] or grub.current_config(self.store.config) != plan['reference']:
            raise RuntimeError('The boot menu changed after review. Review again before registering.')
        self.check_modules(plan)
        matches = [p for p in self.partitions() if p == plan['partition']]
        if len(matches) != 1: raise RuntimeError('The EFI partition changed after review. Nothing was installed.')
        self.unique_reference(plan['reference'], matches[0])
        target = self.destination(matches[0], plan['relative']); backup = Path(plan['backup']); owner = Path(plan['owner'])
        if grub.digest(grub.read_optional(target)) != plan['previous_sha'] or grub.digest(grub.read_optional(owner)) != plan['owner_sha']:
            raise RuntimeError('The EFI loader changed after review. Nothing was installed.')
        nvram = self.nvram()
        if nvram != plan['nvram']: raise RuntimeError('Firmware boot entries changed after review. Reload and review again.')
        content = (backup/'grubx64.efi').read_bytes()
        if grub.digest(content) != plan['image_sha']: raise RuntimeError('The reviewed EFI image changed. Review again.')
        if plan['previous_sha'] and grub.digest((backup/'previous.efi').read_bytes()) != plan['previous_sha']:
            raise RuntimeError('The EFI backup failed its integrity check.')
        if plan['owner_sha'] and grub.digest((backup/'previous-owner.json').read_bytes()) != plan['owner_sha']:
            raise RuntimeError('The EFI ownership backup failed its integrity check.')
        tool = grub.executable('efibootmgr'); created = ''; number = plan['existing']; order = None
        installed_modules = False; modules_target = Path(plan['modules']['target'])
        if not number:
            used = {int(e['number'], 16) for e in nvram['entries']}
            number = next((f'{n:04X}' for n in range(65536) if n not in used), '')
            if not number: raise RuntimeError('No unused firmware boot entry number is available.')
            created = number
        grub.atomic(backup/'result.json', grub.encoded({'status': 'installing', 'target': str(target), 'entry': number, 'created': bool(created)}))
        if created:
            recovery = (backup/'RECOVERY.txt').read_text()+f'The new entry is Boot{number}. To remove only this registration if it exists: sudo efibootmgr --bootnum {number} --delete-bootnum\n'
            grub.atomic(backup/'RECOVERY.txt', recovery.encode())
        try:
            if plan['modules']['install']:
                # Publish the complete support directory at once. Never merge
                # over another bootloader installation's existing modules.
                temporary = Path(tempfile.mkdtemp(prefix='.fusion-efi-', dir=modules_target.parent))
                try:
                    for name in plan['modules']['hashes']:
                        grub.atomic(temporary/name, (backup/'modules'/name).read_bytes(), 0o644)
                    os.chmod(temporary, 0o755)
                    alive(); temporary.rename(modules_target); installed_modules = True
                    fd = os.open(modules_target.parent, os.O_DIRECTORY | os.O_RDONLY)
                    try: os.fsync(fd)
                    finally: os.close(fd)
                finally:
                    if temporary.exists(): shutil.rmtree(temporary)
            alive(); target.parent.mkdir(parents=True, exist_ok=True)
            grub.atomic(target, content, 0o644)
            if created:
                # Reserve an explicit unused slot, then append to BootOrder.
                # --create-only avoids replacing the user's first boot choice.
                grub.command([tool, '--create-only', '--bootnum', number, '--disk', matches[0]['disk'],
                              '--part', str(matches[0]['number']), '--label', plan['label'], '--loader', plan['loader']])
            current = self.nvram()
            if not any(e['number'] == number for e in self.matching(current, matches[0], plan['loader'])):
                raise RuntimeError('Firmware did not retain the requested boot entry.')
            if current['order'] != nvram['order']:
                raise RuntimeError('Another program changed boot priority during registration.')
            order = list(nvram['order'])
            if plan['first']: order = [number]+[n for n in order if n != number]
            elif number not in order: order.append(number)
            if order != current['order']: grub.command([tool, '--bootorder', ','.join(order)])
            verified = self.nvram()
            if verified['order'] != order: raise RuntimeError('Firmware did not retain the requested boot order.')
            if grub.digest(target.read_bytes()) != plan['image_sha']: raise RuntimeError('The installed EFI loader failed verification.')
            grub.atomic(owner, grub.encoded({'target': str(target), 'sha': plan['image_sha'], 'entry': number, 'backup': str(backup)}))
            grub.atomic(backup/'result.json', grub.encoded({'status': 'registered', 'entry': number, 'created': bool(created), 'order': order}))
            instructions = f'EFI loader: {target}\nFirmware entry: Boot{number}\nPrevious firmware entries: firmware-before.txt\n'+plan['review']['support_files']+'\n'
            if created: instructions += f'To remove only this new firmware entry: sudo efibootmgr --bootnum {number} --delete-bootnum\n'
            if nvram['order']: instructions += 'Previous boot order (review against current entries before restoring): sudo efibootmgr --bootorder '+','.join(nvram['order'])+'\n'
            if plan['previous_sha']: instructions += f'The previous EFI loader is saved at {backup}/previous.efi\n'
            grub.atomic(backup/'RECOVERY.txt', instructions.encode())
            return f'Registered {plan["label"]} as Boot{number}. Select it in this machine’s UEFI boot menu. Backup and recovery details: {backup}'
        except BaseException as error:
            recovery = []
            try:
                current = self.nvram()
                if order is not None and current['order'] == order:
                    grub.command([tool, '--bootorder', ','.join(nvram['order'])] if nvram['order'] else [tool, '--delete-bootorder'])
                if created and any(e['number'] == created for e in self.matching(self.nvram(), matches[0], plan['loader'])):
                    grub.command([tool, '--bootnum', created, '--delete-bootnum'])
            except (OSError, RuntimeError, subprocess.SubprocessError) as failure: recovery.append(str(failure))
            try:
                # If firmware cleanup failed, retain the working candidate and
                # support files instead of leaving an active entry dangling.
                if not recovery and grub.digest(grub.read_optional(target)) == plan['image_sha']:
                    if plan['previous_sha']: grub.atomic(target, (backup/'previous.efi').read_bytes(), 0o644)
                    else: target.unlink()
                if not recovery:
                    if plan['owner_sha']: grub.atomic(owner, (backup/'previous-owner.json').read_bytes())
                    else: owner.unlink(missing_ok=True)
                    if installed_modules:
                        if self.module_files(modules_target) != plan['modules']['hashes'] or set(p.name for p in modules_target.iterdir()) != set(plan['modules']['hashes']):
                            raise RuntimeError('New EFI support files changed; they were kept for manual recovery.')
                        shutil.rmtree(modules_target)
            except (OSError, RuntimeError) as failure: recovery.append(str(failure))
            grub.atomic(backup/'result.json', grub.encoded({'status': 'failed', 'error': str(error), 'recovery_errors': recovery}))
            raise RuntimeError(str(error)+' Registration failed. '+('Recovery needs attention. ' if recovery else 'The registration changes were rolled back. ')+
                               'Details: '+str(backup)) from error
