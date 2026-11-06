#!/usr/bin/env python3
"""Native Arch package transaction: matched runtime, full upgrade and recovery."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
import signal
import stat
import subprocess

import arch_runtime as arch
import dependencies
import runtime_install as runtime
from system_runtime import atomic, config_with_hold

STATE = Path('/var/lib/xetal-hyprland/arch-runtime')
CONF = Path('/etc/pacman.conf')


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, env=arch.ENV, **kwargs)


def verify(package, identity):
    run(['/usr/bin/pacman-key', '--verify', str(package)+'.sig', package])
    if run(['/usr/bin/pacman', '-Qp', package], capture_output=True, text=True).stdout.strip() != identity:
        raise RuntimeError('Recovery package identity differs: '+package.name)


def save_previous(backup, before, expected):
    directory = backup/'previous'
    directory.mkdir(mode=0o700)
    result = {}
    for name, version in before.items():
        if version == expected[name]:
            continue
        package = runtime.previous_package(directory, name)
        if package is None:
            raise RuntimeError('Installed runtime changed during recovery preparation: '+name)
        verify(package, name+' '+version)
        result[name] = {'file':package.name, 'sha256':arch.digest(package),
                        'signature_sha256':arch.digest(Path(str(package)+'.sig'))}
    return result


def refresh_keyrings():
    # A year-old keyring may reject valid new packages before the full upgrade
    # gets a chance to update the keyring itself. Update only installed distro
    # trust-data packages first, still using pacman's normal signature checks.
    known = ('archlinux-keyring', 'manjaro-keyring', 'cachyos-keyring', 'endeavouros-keyring')
    installed = runtime.policy.arch_versions(known)
    names = [name for name in known if name in installed]
    if not names:
        raise RuntimeError('No supported distribution signing keyring is installed.')
    print('Updating distribution signing keys before verifying current packages…', flush=True)
    run(['/usr/bin/pacman', '-Sy', '--noconfirm', '--needed', *names])


def package_managed_config(conf):
    """Recognize pacman's own stock configuration replacement during upgrade."""
    if conf != Path('/etc/pacman.conf'):
        return False
    version = runtime.policy.arch_versions(['pacman']).get('pacman')
    if not version:
        return False
    db = Path((runtime.pacman_config('DBPath') or ['/var/lib/pacman'])[0])
    try:
        files = (db/'local'/('pacman-'+version)/'files').read_text()
    except OSError:
        return False
    section = re.search(r'%BACKUP%\n(.*?)(?:\n\n|\Z)', files, re.S)
    if not section:
        return False
    for line in section[1].splitlines():
        parts = line.split('\t')
        if len(parts) == 2 and parts[0] == 'etc/pacman.conf':
            # This is libalpm's recorded config checksum, not a trust decision
            # about a downloaded package (those use SHA-256 plus signatures).
            return hashlib.md5(conf.read_bytes()).hexdigest() == parts[1]
    return False


def restore_configuration(backup, record, conf, pin):
    original = (backup/'pacman.conf').read_bytes()
    if conf.is_symlink() or pin.is_symlink():
        raise RuntimeError('Package configuration must use regular files.')
    old_pin = (backup/'hold.conf').read_bytes() if record['had_pin'] else None
    current = pin.read_bytes() if pin.exists() else None
    if current not in (old_pin, record['new_hold'].encode()):
        raise RuntimeError('Package holds were edited externally; recovery will not overwrite them.')
    if conf.read_bytes() == config_with_hold(original.decode(), str(pin)).encode():
        atomic(conf, original, stat.S_IMODE(conf.stat().st_mode))
    elif ('Include = '+str(pin)) not in original.decode():
        lines = conf.read_text().splitlines(keepends=True)
        atomic(conf, ''.join(line for line in lines if line.strip() != 'Include = '+str(pin)).encode(),
               stat.S_IMODE(conf.stat().st_mode))
    if old_pin is None:
        pin.unlink(missing_ok=True)
    else:
        atomic(pin, old_pin)


def restore(backup, state=STATE, conf=CONF, pin=runtime.PIN, _locked=False):
    if backup.is_symlink() or backup.resolve().parent != state.resolve():
        raise RuntimeError('Invalid Arch runtime recovery record.')
    if not _locked:
        with (state/'setup.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return restore(backup, state, conf, pin, True)
    record = json.loads((backup/'record.json').read_text())
    if record.get('restored'):
        return
    original_pin = (backup/'hold.conf').read_bytes() if record['had_pin'] else None
    if pin.is_symlink() or conf.is_symlink() or (pin.read_bytes() if pin.exists() else None) not in (
            original_pin, record['new_hold'].encode()):
        raise RuntimeError('Package configuration was edited externally; recovery will not overwrite it.')
    before, expected = record['before'], record['expected']
    current = runtime.policy.arch_versions(expected)
    for name in expected:
        if current.get(name) not in (before.get(name), expected[name]):
            raise RuntimeError('Runtime package changed outside Setup: '+name+'. Recovery will not overwrite it.')
    paths = []
    for name, saved in record['previous'].items():
        if current.get(name) == before[name]:
            continue
        path = backup/'previous'/saved['file']
        if arch.digest(path) != saved['sha256'] or arch.digest(Path(str(path)+'.sig')) != saved['signature_sha256']:
            raise RuntimeError('Runtime recovery package changed: '+name)
        verify(path, name+' '+before[name])
        paths.append(str(path))
    if paths:
        # Restore the previous compositor AND ABI-coupled libraries together.
        run(['/usr/bin/pacman', '-Up', '--noconfirm', *paths])
        run(['/usr/bin/pacman', '-U', '--noconfirm', '--needed', *paths])
    if 'hyprland' not in before and 'hyprland' in current:
        run(['/usr/bin/pacman', '-R', '--noconfirm', 'hyprland'])
    restored = runtime.policy.arch_versions(before) if before else {}
    if restored != before:
        raise RuntimeError('Previous runtime package versions could not be verified after recovery.')
    restore_configuration(backup, record, conf, pin)
    record['restored'] = True
    atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
    print('Previous Arch runtime and package holds restored. Ordinary dependency installs and system updates remain.', flush=True)


def install(state=STATE, conf=CONF, pin=runtime.PIN):
    if conf.is_symlink() or pin.is_symlink():
        raise RuntimeError('Package configuration must use regular files.')
    required, expected = arch.target(), arch.expected()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state/'setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = state/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        backup.mkdir(mode=0o700)
        original = conf.read_bytes()
        (backup/'pacman.conf').write_bytes(original)
        old_pin = pin.read_bytes() if pin.exists() else None
        if old_pin is not None:
            (backup/'hold.conf').write_bytes(old_pin)
        refresh_keyrings()
        before = runtime.policy.arch_versions(expected)
        previous = save_previous(backup, before, expected)
        index = arch.repository(backup/'packages', required, verify=True)
        base = run(['/usr/bin/pacman-conf', '--config', conf], capture_output=True, text=True).stdout
        config = backup/'transaction.conf'
        config.write_text(arch.configuration(base, index.parent))
        database = Path((runtime.pacman_config('DBPath') or ['/var/lib/pacman'])[0])/'sync'
        database.mkdir(parents=True, exist_ok=True)
        # This generated index is local, never fetched by pacman's download
        # user. Usage excludes Sync only for this one temporary repository.
        atomic(database/index.name, index.read_bytes())
        # Packages are copied into root-owned storage and verified first. The
        # private cache also avoids giving the unprivileged downloader access
        # to the recovery directory when fetching file:// runtime packages.
        prefix = ['/usr/bin/pacman', '--config', str(config)]
        for directory in runtime.package_caches():
            prefix += ['--cachedir', str(directory)]
        prefix += ['--cachedir', str(index.parent)]
        targets = arch.package_args(dependencies.PACKAGES['arch'], required)
        # Refresh + coordinated full upgrade, not -Sy followed by a partial
        # library update. Download everything before modifying package files.
        run([*prefix, '-Syu', '--noconfirm', '--needed', '--downloadonly', *targets])
        plan = arch.resolve(config, dependencies.PACKAGES['arch'], required=required)
        record = {'schema':1, 'before':before, 'expected':expected, 'previous':previous,
                  'had_pin':old_pin is not None, 'new_hold':arch.hold_text(required),
                  'package_plan':plan}
        atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
        print('Recovery files: '+str(backup), flush=True)
        print('XETAL_RUNTIME_TRANSACTION '+str(backup), flush=True)
        try:
            if runtime.policy.arch_versions(expected) != before:
                raise RuntimeError('Runtime packages changed during preparation. Retry Setup.')
            run([*prefix, '-Su', '--noconfirm', '--needed', *targets])
            if runtime.policy.arch_versions(expected) != expected:
                raise RuntimeError('Installed runtime does not match the verified package set.')
            runtime.policy.require()
            if conf.read_bytes() != original and package_managed_config(conf):
                # An unmodified pacman.conf is normally replaced by pacman's
                # own upgrade. Keep that new default as our recovery baseline.
                (backup/'pacman.conf.before-system-upgrade').write_bytes(original)
                original = conf.read_bytes()
                atomic(backup/'pacman.conf', original, 0o600)
                record['package_config_upgraded'] = True
                atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
            if conf.read_bytes() != original or (pin.read_bytes() if pin.exists() else None) != old_pin:
                raise RuntimeError('Package configuration changed during Setup; the later edits were kept.')
            atomic(pin, record['new_hold'].encode())
            atomic(conf, config_with_hold(original.decode(), str(pin)).encode(), stat.S_IMODE(conf.stat().st_mode))
        except BaseException:
            restore(backup, state, conf, pin, True)
            raise
        print('Matching Arch runtime and desktop dependencies installed. Recovery: '+str(backup), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Administrator authentication is required through Setup.')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if args.restore:
        restore(args.restore)
    else:
        install()
