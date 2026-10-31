#!/usr/bin/env python3
"""Privileged Fedora RPM transaction with exact-package recovery and DNF locks."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

import fedora_runtime as fedora
import runtime_install as runtime
from system_runtime import atomic

STATE = Path('/var/lib/xetal-hyprland/fedora-runtime')
DNF = ['/usr/bin/dnf', '-y', '--setopt=install_weak_deps=False', '--setopt=localpkg_gpgcheck=True']
ENV = {**os.environ, 'LC_ALL':'C'}


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, env=ENV, **kwargs)


def signature(path, database=None):
    args = ['/usr/bin/rpmkeys', *(['--dbpath', str(database)] if database else []), '--checksig', str(path)]
    result = run(args, capture_output=True, text=True)
    if 'digests signatures OK' not in result.stdout:
        raise RuntimeError('A trusted RPM signature is required: '+str(path))


def identity(path):
    result = run(['/usr/bin/rpm', '-qp', '--qf', '%{NAME} %{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}', path],
                 capture_output=True, text=True)
    return result.stdout.strip()


def stage_bundle(backup, required):
    directory = backup/'packages'; directory.mkdir(mode=0o700)
    for item in [dict(file=required['key_file'], sha256=required['key_sha256']), *required['packages']]:
        saved = directory/item['file']
        shutil.copyfile(fedora.BUNDLE/item['file'], saved)
        if hashlib.sha256(saved.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('Fedora bundle checksum failed: '+saved.name)
    # Verify against only the pinned publisher key, before adding that key to
    # RPM's trust database. Never pass a mutable user-owned file to DNF.
    database = backup/'keyring'; database.mkdir(mode=0o700)
    key = directory/required['key_file']
    run(['/usr/bin/rpmkeys', '--dbpath', database, '--import', key])
    for item in required['packages']:
        path = directory/item['file']; signature(path, database)
        if identity(path) != item['name']+' '+item['evr']+'.'+item['architecture']:
            raise RuntimeError('Unexpected RPM identity: '+path.name)
    return directory


def save_previous(backup, before, expected):
    directory = backup/'previous'; directory.mkdir(mode=0o700)
    result = {}
    for name, version in before.items():
        if version == expected[name]: continue
        filename = name+'-'+version.split(':', 1)[1]+'.rpm'
        destination = directory/filename
        # A previous release bundled by an earlier Setup also remains available
        # in its root-owned transaction record, even after repository rotation.
        caches = [Path('/var/cache/libdnf5'), Path('/var/cache/dnf'), STATE]
        cached = next((p for base in caches for p in base.rglob(filename)
                       if p.is_file() and p != destination and identity(p) == name+' '+version), None)
        if cached:
            shutil.copyfile(cached, destination)
        else:
            print('Saving the previous Fedora package for recovery: '+name+' '+version, flush=True)
            run(['/usr/bin/dnf', 'download', '--destdir='+str(directory), name+'-'+version])
        if not destination.is_file() or identity(destination) != name+' '+version:
            raise RuntimeError('The exact previous Fedora package is unavailable: '+name+' '+version+'. No compositor packages were changed.')
        signature(destination)
        result[name] = {'file':filename, 'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
    return result


def plan_packages(directory):
    file = directory/'transaction.json'
    if not file.exists(): return []  # DNF reports a no-op without a plan.
    plan = json.loads(file.read_text())
    if plan.get('version') != '1.0' or set(plan) - {'version', 'rpms'}:
        raise RuntimeError('Unsupported DNF transaction format; no package transaction was applied.')
    return plan.get('rpms', [])


def package_name(nevra):
    return nevra.rsplit('-', 2)[0]


def check_plan(directory, names, recovery=False):
    packages = plan_packages(directory)
    for item in packages:
        if item['action'] not in ('Install', 'Upgrade', 'Downgrade', 'Reinstall', 'Replaced', 'Remove', 'Reason Change'):
            raise RuntimeError('Unsupported DNF action: '+item['action'])
        if package_name(item['nevra']) not in names and (recovery or item['action'] == 'Remove'):
            raise RuntimeError('The package transaction would change an unrelated package: '+item['nevra'])
    return bool(packages)


def complete_plan(directory, local_packages):
    # DNF 5 stores command-line RPM references but may leave their files outside
    # the saved transaction. Make the root-owned plan self-contained for replay.
    local = {p.name:p for p in map(Path, local_packages)}
    for item in plan_packages(directory):
        relative = item.get('package_path')
        if not relative: continue
        destination = (directory/relative).resolve()
        if not destination.is_relative_to(directory.resolve()):
            raise RuntimeError('DNF produced a package path outside its saved transaction.')
        if destination.is_file(): continue
        source = local.get(destination.name)
        if source is None: raise RuntimeError('DNF did not save a required package: '+destination.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def restore_hold(record, pin=fedora.PIN):
    current = pin.read_text() if pin.exists() else ''
    base, block = fedora.split_hold(current)
    if fedora.same_hold(block, record['old_hold']): return
    if not fedora.same_hold(block, record['new_hold']):
        raise RuntimeError('The runtime version locks were edited externally; recovery will not overwrite them.')
    # Keep unrelated locks added since Setup began.
    restored = base.rstrip()+'\n\n'+record['old_hold'] if record['old_hold'] else base
    if not record['had_pin'] and restored.strip() == 'version = "1.0"': pin.unlink()
    else: atomic(pin, restored.encode())


def restore(backup, state=STATE, _locked=False):
    if backup.is_symlink() or backup.resolve().parent != state.resolve():
        raise RuntimeError('Invalid Fedora recovery record.')
    if not _locked:
        with (state/'setup.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return restore(backup, state, True)
    record_path = backup/'record.json'; record = json.loads(record_path.read_text())
    if record.get('restored'): return
    expected, before = record['expected'], record['before']
    current = runtime.policy.rpm_versions(expected)
    for name in expected:
        if current.get(name) not in (before.get(name), expected[name]):
            raise RuntimeError('Fedora runtime package changed externally: '+name+'. Recovery will not overwrite it.')
    restore_hold(record)
    packages, remove = [], []
    for name in expected:
        if current.get(name) == before.get(name): continue
        if name not in before:
            remove.append(name)
        else:
            saved = record['previous'][name]; package = backup/'previous'/saved['file']
            if hashlib.sha256(package.read_bytes()).hexdigest() != saved['sha256']:
                raise RuntimeError('The Fedora recovery package changed: '+name)
            signature(package); packages.append(str(package))
    if packages or remove:
        plan = backup/('restore-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
        args = [*DNF, '--setopt=clean_requirements_on_remove=False', 'do', '--store='+str(plan)]
        if packages: args += ['--action=install', *packages]
        if remove: args += ['--action=remove', *remove]
        run(args)
        if check_plan(plan, expected, recovery=True):
            complete_plan(plan, packages)
            run([*DNF, 'replay', plan])
    if runtime.policy.rpm_versions(expected) != before:
        raise RuntimeError('Fedora runtime recovery did not restore the recorded package versions.')
    record['restored'] = True; atomic(record_path, (json.dumps(record, indent=2)+'\n').encode(), 0o600)
    print('Previous Fedora runtime and version locks restored. Desktop dependencies remain installed.', flush=True)


def install(state=STATE):
    if not runtime.policy.fedora_host() or os.uname().machine != 'x86_64' or Path('/run/ostree-booted').exists():
        raise RuntimeError('This runtime bundle requires mutable Fedora 44 x86-64.')
    required = fedora.target(); pin = fedora.PIN
    if pin.is_symlink() or state.is_symlink(): raise RuntimeError('Package state must use regular files and directories.')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state/'setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = pin.read_text() if pin.exists() else ''
        new = fedora.with_hold(original, required)
        backup = state/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'); backup.mkdir(mode=0o700)
        directory = stage_bundle(backup, required)
        expected = {p['name']:p['evr']+'.'+p['architecture'] for p in required['packages']}
        before = runtime.policy.rpm_versions(expected)
        previous = save_previous(backup, before, expected)
        record = dict(before=before, expected=expected, previous=previous, had_pin=pin.exists(),
                      old_hold=fedora.split_hold(original)[1], new_hold=fedora.hold_block(required))
        atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
        print('XETAL_RUNTIME_TRANSACTION '+str(backup), flush=True)
        try:
            if (pin.read_text() if pin.exists() else '') != original:
                raise RuntimeError('DNF version locks changed while Setup was preparing packages.')
            pin.parent.mkdir(parents=True, exist_ok=True); atomic(pin, new.encode())
            run(['/usr/bin/rpmkeys', '--import', directory/required['key_file']])
            plan = backup/'install'
            run([*DNF, 'install', '--store='+str(plan), *[directory/p['file'] for p in required['packages']]])
            if check_plan(plan, expected):
                complete_plan(plan, [directory/p['file'] for p in required['packages']])
                run([*DNF, 'replay', plan])
            runtime.policy.require()
            if not fedora.pinned(required): raise RuntimeError('Fedora version locks changed during package setup.')
        except BaseException:
            restore(backup, state, True)
            raise
        print('Fedora compositor, matching libraries and headers installed and held. Recovery: '+str(backup), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--restore', type=Path); args = parser.parse_args()
    if os.geteuid() != 0: parser.error('Run this helper through Setup administrator authentication.')
    def interrupted(*_): raise KeyboardInterrupt('Fedora runtime setup interrupted.')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.restore: restore(args.restore)
        else: install()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        parser.exit(1, 'Fedora runtime setup: '+str(error)+'\n')
