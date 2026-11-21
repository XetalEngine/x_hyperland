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
import sys

import arch_runtime as arch
import arch_recovery as recovery
import dependencies
import recovery_choice
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


class MissingRecoveryPackages(RuntimeError):
    def __init__(self, packages):
        self.packages = recovery_choice.validate(packages)
        super().__init__('Rollback packages could not be downloaded: '+
                         ', '.join(p['name']+' '+p['version'] for p in packages))


def save_previous(backup, before, expected, waived=()):
    directory = backup/'previous'
    directory.mkdir(mode=0o700)
    # Each Setup retry has a new recovery record. Reuse completed downloads
    # from earlier attempts, but verify every copied archive again below.
    caches = sorted((path for path in backup.parent.glob('*/previous')
                     if path != directory and path.is_dir() and not path.is_symlink()
                     and not path.parent.is_symlink()), reverse=True)
    result, missing, waived_missing = {}, [], []
    accepted = {p['name']:p['version'] for p in waived}
    for name, version in before.items():
        if version == expected.get(name):
            continue
        if accepted.get(name) == version:
            waived_missing.append(dict(name=name, version=version,
                                       error='Recovery download waived by your explicit choice.'))
            continue
        try:
            package = runtime.previous_package(directory, name, recovery_caches=caches)
        except runtime.RecoveryDownloadError as error:
            missing.append(dict(name=name, version=version, error=str(error)))
            print('Recovery download unavailable: '+name+' '+version, flush=True)
            continue
        if package is None:
            raise RuntimeError('Installed runtime changed during recovery preparation: '+name)
        verify(package, name+' '+version)
        result[name] = {'file':package.name, 'sha256':arch.digest(package),
                        'signature_sha256':arch.digest(Path(str(package)+'.sig'))}
    if missing:
        # Report every unavailable download together. Signature, identity and
        # local storage failures are deliberately not eligible for this choice.
        raise MissingRecoveryPackages([*waived_missing, *missing])
    return result


def inventory(database=None):
    args = ['/usr/bin/pacman']
    if database is not None:
        args += ['--dbpath', database]
    result = run([*args, '-Q'], capture_output=True, text=True)
    return dict(line.split() for line in result.stdout.splitlines() if line.strip())


def recovery_configuration(text):
    """Recovery uses only the saved archives, never newer repository packages."""
    sections = list(re.finditer(r'^\[([^\]\n]+)\]\s*$', text, re.M))
    if not sections or sections[0][1] != 'options':
        raise RuntimeError('Unexpected package recovery configuration.')
    end = sections[1].start() if len(sections) > 1 else len(text)
    return text[:end]


def prepare_recovery(backup, prefix, targets, database, base, waived=(), rollback=True):
    """Prove forward/rollback dependency resolution in a disposable database.

    --dbonly updates this copy, with an empty filesystem root and no scriptlets.
    When rollback is enabled, every replaced package gets a signed archive and
    the complete reverse transaction is checked too. The forward dependency
    check remains mandatory when rollback downloads are disabled.
    """
    before = inventory(database)
    (backup/'install-reasons.json').write_text(json.dumps(recovery.reasons(database))+'\n')
    projection = backup/'projection'
    db = projection/'db'
    root = projection/'root'
    root.mkdir(parents=True)
    shutil.copytree(database/'local', db/'local')
    shutil.copytree(database/'sync', db/'sync')
    isolated = ['--root', root, '--dbpath', db, '--logfile', projection/'pacman.log']
    print('Checking the full upgrade'+(' and its recovery' if rollback else '')+
          ' in a disposable package database…', flush=True)
    run([*prefix, *isolated, '-Su', '--noconfirm', '--needed', '--dbonly', '--noscriptlet', *targets])
    expected = inventory(db)
    if waived:
        recovery_choice.validate(waived)
    previous = {}
    if rollback:
        previous = save_previous(backup, before, expected, waived=waived) if waived else save_previous(backup, before, expected)
    else:
        print('Package rollback is off. Historical package downloads are skipped.', flush=True)
    missing = [p for p in waived if before.get(p['name']) == p['version']
               and before[p['name']] != expected.get(p['name'])]
    recovery_config = backup/'recovery.conf'
    recovery_config.write_text(recovery_configuration(base))
    additions=[dict(path=str(backup/'previous'/saved['file']),name=name,version=before[name])
               for name,saved in previous.items()]
    removals=[dict(name=name,version=expected[name]) for name in sorted(set(expected)-set(before))]
    # Upgrading OpenSSL can introduce openssl-3. The old package owns the same
    # files, so restoration and removal must be a single checked transaction.
    # A database-only pacman -U by itself misses this file ownership collision.
    if rollback and not missing:
        recovery.replay(backup,base,additions,removals,expected,database=db,root=root,database_only=True)
        restored = inventory(db)
        if restored != before:
            raise RuntimeError('The previous package set could not be restored in the recovery check. '
                               'The live system has not been upgraded.')
    if inventory(database) != before:
        raise RuntimeError('Packages changed while preparing recovery. Retry Setup.')
    recovery_status = {'available':bool(rollback and not missing), 'enabled':rollback, 'missing':missing}
    if missing:
        recovery_status.update(choice=recovery_choice.CONTINUE,
                               acknowledged_at=datetime.now(timezone.utc).isoformat())
    elif not rollback:
        recovery_status['choice'] = 'disabled'
    atomic(backup/'package-recovery.json', (json.dumps(recovery_status, indent=2)+'\n').encode(), 0o600)
    return before, expected, previous


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
    upgraded = backup/'pacman.conf.after-system-upgrade'
    baseline = upgraded.read_bytes() if upgraded.exists() else original
    if conf.read_bytes() in (config_with_hold(original.decode(), str(pin)).encode(),
                            config_with_hold(baseline.decode(), str(pin)).encode(), baseline):
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
    if record.get('rollback_available') is False:
        raise RuntimeError('Automatic package rollback was disabled for this transaction. '
                           'A partial downgrade would be unsafe. Manual repair may be needed; '
                           'transaction details: '+str(backup))
    original_pin = (backup/'hold.conf').read_bytes() if record['had_pin'] else None
    if pin.is_symlink() or conf.is_symlink() or (pin.read_bytes() if pin.exists() else None) not in (
            original_pin, record['new_hold'].encode()):
        raise RuntimeError('Package configuration was edited externally; recovery will not overwrite it.')
    before, expected = record['before'], record['expected']
    current = runtime.policy.arch_versions(set(before) | set(expected))
    for name in set(before) | set(expected):
        if current.get(name) not in (before.get(name), expected.get(name)):
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
    if record.get('schema',1)>=3:
        additions=[dict(path=str(backup/'previous'/saved['file']),name=name,version=before[name])
                   for name,saved in record['previous'].items() if current.get(name)!=before[name]]
        removals=[dict(name=name,version=current[name]) for name in sorted(set(expected)-set(before)) if name in current]
        if additions or removals:
            recovery.replay(backup,(backup/'recovery.conf').read_text(),additions,removals,current)
    elif paths:
        # Restore ALL upgraded packages together; libjxl/OpenSSL/etc. are part
        # of the same dependency graph as the compositor's own libraries.
        config = ['--config', backup/'recovery.conf'] if record.get('schema', 1) >= 2 else []
        run(['/usr/bin/pacman', *config, '-Up', '--noconfirm', *paths])
        run(['/usr/bin/pacman', *config, '-U', '--noconfirm', '--needed', *paths])
    if record.get('schema',1)<3 and 'hyprland' not in before and 'hyprland' in current:
        run(['/usr/bin/pacman', '-R', '--noconfirm', 'hyprland'])
    restored = runtime.policy.arch_versions(before) if before else {}
    if restored != before:
        raise RuntimeError('Previous runtime package versions could not be verified after recovery.')
    if record.get('schema',1)>=3 and inventory()!=before:
        raise RuntimeError('The full previous package inventory could not be verified after recovery.')
    restore_configuration(backup, record, conf, pin)
    record['restored'] = True
    atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
    print('Previous package versions and compositor holds restored.'+
          (' Newly introduced packages were removed.' if record.get('schema',1)>=3 else ' Compatible new dependencies may remain.'), flush=True)


def install(state=STATE, conf=CONF, pin=runtime.PIN, waived=(), rollback=False):
    if waived:
        recovery_choice.validate(waived)
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
        index = arch.repository(backup/'packages', required, verify=True)
        base = run(['/usr/bin/pacman-conf', '--config', conf], capture_output=True, text=True).stdout
        database = Path((runtime.pacman_config('DBPath') or ['/var/lib/pacman'])[0])/'sync'
        preserve = arch.local_packages(database.parent)
        if preserve:
            print('Preserving locally built packages during this desktop upgrade: '+', '.join(sorted(preserve)), flush=True)
        config = backup/'transaction.conf'
        config.write_text(arch.configuration(base, index.parent, preserve))
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
        targets = arch.package_args(dependencies.PACKAGES['arch'], required, preserve)
        # Refresh + coordinated full upgrade, not -Sy followed by a partial
        # library update. Download everything before modifying package files.
        run([*prefix, '-Syu', '--noconfirm', '--needed', '--downloadonly', *targets])
        plan = arch.resolve(config, dependencies.PACKAGES['arch'], required=required, preserve=preserve)
        before, projected, previous = prepare_recovery(backup, prefix, targets, database.parent, base,
                                                       waived=waived, rollback=rollback)
        recovery_status = json.loads((backup/'package-recovery.json').read_text())
        record = {'schema':3, 'before':before, 'expected':projected, 'previous':previous,
                  'had_pin':old_pin is not None, 'new_hold':arch.hold_text(required),
                  'package_plan':plan, 'preserved_local_packages':sorted(preserve),
                  'rollback_available':recovery_status['available'], 'package_recovery':recovery_status}
        atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
        print(('Recovery files: ' if record['rollback_available'] else 'Transaction details (package rollback disabled): ')+str(backup), flush=True)
        print('XETAL_RUNTIME_TRANSACTION '+str(backup), flush=True)
        if not record['rollback_available']:
            print('XETAL_RUNTIME_ROLLBACK_UNAVAILABLE '+str(backup), flush=True)
        try:
            if inventory(database.parent) != before:
                raise RuntimeError('Packages changed during preparation. Retry Setup.')
            if arch.resolve(config, dependencies.PACKAGES['arch'], required=required, preserve=preserve) != plan:
                raise RuntimeError('The package upgrade plan changed during preparation. Retry Setup.')
            run([*prefix, '-Su', '--noconfirm', '--needed', *targets])
            if inventory(database.parent) != projected:
                raise RuntimeError('Installed packages differ from the verified upgrade plan.')
            if runtime.policy.arch_versions(expected) != expected:
                raise RuntimeError('Installed runtime does not match the verified package set.')
            runtime.policy.require()
            if conf.read_bytes() != original and package_managed_config(conf):
                # An unmodified pacman.conf is normally replaced by pacman's
                # own upgrade. Recognize that new default without discarding
                # the old configuration needed by full-package recovery.
                original = conf.read_bytes()
                atomic(backup/'pacman.conf.after-system-upgrade', original, 0o600)
                record['package_config_upgraded'] = True
                atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
            if conf.read_bytes() != original or (pin.read_bytes() if pin.exists() else None) != old_pin:
                raise RuntimeError('Package configuration changed during Setup; the later edits were kept.')
            atomic(pin, record['new_hold'].encode())
            atomic(conf, config_with_hold(original.decode(), str(pin)).encode(), stat.S_IMODE(conf.stat().st_mode))
        except BaseException:
            if record['rollback_available']:
                restore(backup, state, conf, pin, True)
            else:
                print('Package installation stopped. Automatic package rollback was disabled; '
                      'no partial downgrade was attempted. Manual repair may be needed. '
                      'Transaction details: '+str(backup), flush=True)
            raise
        print('Matching Arch runtime and desktop dependencies installed. '+
              ('Recovery: ' if record['rollback_available'] else 'Package rollback disabled. Transaction details: ')+str(backup), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--package-rollback', action='store_true',
                        help='Save and verify historical packages for automatic rollback (off by default).')
    parser.add_argument('--without-package-rollback', type=json.loads,
                        help='Internal: exact missing package identities explicitly accepted in foreground Setup.')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Administrator authentication is required through Setup.')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if args.restore:
        if args.without_package_rollback is not None or args.package_rollback:
            parser.error('A restore cannot waive package recovery.')
        restore(args.restore)
    else:
        try:
            install(rollback=args.package_rollback, waived=recovery_choice.validate(args.without_package_rollback)
                    if args.without_package_rollback is not None else ())
        except MissingRecoveryPackages as error:
            print(str(error), flush=True)
            print(recovery_choice.MARKER+json.dumps(error.packages), flush=True)
            sys.exit(recovery_choice.EXIT_REQUIRED)
