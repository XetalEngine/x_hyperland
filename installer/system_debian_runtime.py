#!/usr/bin/env python3
"""Debian transaction: native packages, dependency resolution and exact recovery."""
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

import debian_runtime as debian
import dependencies
import runtime_install as runtime
from system_runtime import atomic

STATE = Path('/var/lib/xetal-hyprland/debian-runtime')


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, env=debian.ENV, **kwargs)


def identity(path):
    result = run(['/usr/bin/dpkg-deb', '-f', path, 'Package', 'Version', 'Architecture'],
                 capture_output=True, text=True)
    values = dict(line.split(': ', 1) for line in result.stdout.splitlines())
    return values['Package'], values['Version'], values['Architecture']


def versions():
    result = run(['/usr/bin/dpkg-query', '-W', '-f=${Package}:${Architecture} ${Version} ${db:Status-Status}\n'],
                 capture_output=True, text=True)
    return {f[0]: f[1] for line in result.stdout.splitlines()
            if len(f := line.split()) == 3 and f[2] in
            ('installed', 'unpacked', 'half-configured', 'half-installed', 'triggers-awaited', 'triggers-pending')}


def auto_packages():
    return set(run(['/usr/bin/apt-mark', 'showauto'], capture_output=True, text=True).stdout.split())


def mark_auto(keys):
    if keys:
        run(['/usr/bin/apt-mark', 'auto', *sorted(key.replace(':all', '') for key in keys)], capture_output=True, text=True)


def qualified(plan, before, paths):
    local = {name: arch for name, _, arch in map(identity, paths)}
    unknown = [name+'='+version for name, version in plan.items()
               if ':' not in name and name not in local and not any(key.split(':')[0] == name for key in before)]
    available = {}
    if unknown:
        info = run(['/usr/bin/apt-cache', 'show', *unknown], capture_output=True, text=True).stdout
        for paragraph in info.split('\n\n'):
            fields = dict(line.split(': ', 1) for line in paragraph.splitlines() if ': ' in line and not line.startswith(' '))
            if {'Package', 'Version', 'Architecture'} <= fields.keys():
                available.setdefault((fields['Package'], fields['Version']), set()).add(fields['Architecture'])
    result = {}
    for name, version in plan.items():
        if ':' not in name:
            existing = [key for key in before if key.split(':')[0] == name]
            if len(existing) > 1:
                raise RuntimeError('Ambiguous multiarch package in APT plan: '+name)
            if name in local:
                arch = local[name]
            elif existing:
                arch = existing[0].split(':')[1]
            else:
                architectures = available.get((name, version), set())
                if len(architectures) != 1:
                    raise RuntimeError('Could not identify the architecture of '+name)
                arch = architectures.pop()
            name += ':'+arch
        result[name] = version
    return result


def save_previous(backup, before, expected, state=STATE):
    directory = backup/'previous'; directory.mkdir(mode=0o700)
    saved = {}
    for key, version in before.items():
        if key not in expected or version == expected[key]:
            continue
        name, arch = key.split(':')
        destination = directory/(name+'_'+version.replace(':', '%3a')+'_'+arch+'.deb')
        cached = None
        for base in (Path('/var/cache/apt/archives'), state):
            for path in base.rglob(name+'_*.deb'):
                if path != destination and path.is_file() and identity(path) == (name, version, arch):
                    cached = path
                    break
            if cached:
                break
        if cached:
            shutil.copyfile(cached, destination)
        else:
            print('Saving previous Debian package: '+key+' '+version, flush=True)
            # APT checks authenticated repository hashes; never use --allow-unauthenticated.
            run([*debian.APT, '-o', 'APT::Sandbox::User=root', 'download', name+(':'+arch if arch != 'all' else '')+'='+version], cwd=directory)
            candidates = [p for p in directory.glob(name+'_*.deb') if identity(p) == (name, version, arch)]
            if len(candidates) != 1:
                raise RuntimeError('The exact previous Debian package is unavailable: '+key+' '+version)
            if candidates[0] != destination:
                candidates[0].rename(destination)
        saved[key] = dict(file=destination.name, sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    return saved


def restore_pin(record, pin):
    current = pin.read_text() if pin.exists() else None
    if current == record['old_pin']:
        return
    if pin.is_symlink() or current != record['new_pin']:
        raise RuntimeError('Debian runtime pins changed externally; recovery will not overwrite them.')
    if record['old_pin'] is None:
        pin.unlink(missing_ok=True)
    else:
        atomic(pin, record['old_pin'].encode())


def restore(backup, state=STATE, _locked=False):
    if backup.is_symlink() or backup.resolve().parent != state.resolve():
        raise RuntimeError('Invalid Debian recovery record.')
    if not _locked:
        with (state/'setup.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return restore(backup, state, True)
    record_path = backup/'record.json'; record = json.loads(record_path.read_text())
    if record.get('restored'):
        return
    current = versions(); before, expected = record['before'], record['expected']
    for key, version in expected.items():
        if current.get(key) not in (before.get(key), version):
            raise RuntimeError('Debian package changed externally: '+key+'. Recovery will not overwrite it.')
    pin = debian.PIN
    if (pin.read_text() if pin.exists() else None) not in (record['old_pin'], record['new_pin']):
        raise RuntimeError('Debian runtime pins changed externally; recovery will not overwrite them.')
    bundled = set(record.get('bundled', [p['name']+':'+p['architecture'] for p in debian.target()['packages']]))
    # Ordinary dependencies (including a container's newly installed init
    # system) may remain. Only remove the new runtime and newly installed
    # dependants selected by APT; never remove a pre-existing application.
    remove = {arg for key in expected if key not in before for arg in (key, key.split(':')[0])}
    args, paths = [], []
    for key in expected:
        if current.get(key) == before.get(key):
            continue
        if key not in before:
            if key not in bundled:
                continue
            name, arch = key.split(':')
            arg = name if arch == 'all' else key
            args.append(arg+'-')
        else:
            item = record['previous'][key]; path = backup/'previous'/item['file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError('Debian recovery package changed: '+key)
            name, arch = key.split(':')
            if identity(path) != (name, before[key], arch):
                raise RuntimeError('Unexpected Debian recovery package: '+key)
            paths.append(path); args.append(str(path))
    restore_pin(record, pin)
    if args:
        plan, _ = debian.simulate(args, allow_remove=remove)
        resolved = qualified(plan, current, paths)
        if any(key not in expected or version != before.get(key) for key, version in resolved.items()):
            raise RuntimeError('APT recovery would change an unrelated package; the saved packages remain available.')
        run([*debian.APT, '-y', '--allow-downgrades', 'install', *args])
    restored = versions()
    if (any(restored.get(key) != before[key] for key in before)
            or any(key in restored for key in bundled if key not in before)
            or any(restored.get(key) not in (None, expected[key]) for key in expected if key not in before)):
        raise RuntimeError('Debian recovery did not restore all recorded package versions.')
    mark_auto(record.get('automatic_before', []))
    record['restored'] = True
    atomic(record_path, (json.dumps(record, indent=2)+'\n').encode(), 0o600)
    print('Previous Debian packages and runtime pins restored. Ordinary dependency packages may remain installed.', flush=True)


def install(state=STATE):
    if not runtime.policy.debian_host() or os.uname().machine != 'x86_64':
        raise RuntimeError('This bundle requires Debian 13 x86-64.')
    pin = debian.PIN; required = debian.target()
    if pin.is_symlink() or state.is_symlink():
        raise RuntimeError('Package state must use regular files and directories.')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state/'setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_pin = pin.read_text() if pin.exists() else None
        debian.check_hold(old_pin or '')
        backup = state/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'); backup.mkdir(mode=0o700)
        directory = backup/'packages'; directory.mkdir(mode=0o700)
        paths = debian.extract(directory, required)
        items = {p['file']: p for p in required['packages']}
        for path in paths:
            item = items[path.name]
            if identity(path) != (item['name'], item['version'], item['architecture']):
                raise RuntimeError('Unexpected Debian package identity: '+path.name)
        args = debian.package_args(paths, required, dependencies.PACKAGES['debian'])
        before = versions()
        automatic = auto_packages()
        plan, _ = debian.simulate(args)
        expected = qualified(plan, before, paths)
        expected.update({p['name']+':'+p['architecture']: p['version'] for p in required['packages']})
        previous = save_previous(backup, before, expected, state)
        # Preserve exact selections even if a mirror advances while downloading.
        local = {p['name'] for p in required['packages']}
        exact = [*map(str, paths), *[key.replace(':all', '')+'='+version for key, version in expected.items()
                                    if key.split(':')[0] not in local]]
        run([*debian.APT, '-y', '--no-remove', '--allow-downgrades', '--download-only', 'install', *exact])
        if versions() != before or (pin.read_text() if pin.exists() else None) != old_pin:
            raise RuntimeError('Debian package state changed while preparing Setup. Retry after the other package operation finishes.')
        record = dict(before={k: v for k, v in before.items() if k in expected}, expected=expected,
                      previous=previous, old_pin=old_pin, new_pin=debian.hold_text(required))
        record['bundled'] = [p['name']+':'+p['architecture'] for p in required['packages']]
        record['automatic_before'] = [key for key in expected if key in before and
                                      (key in automatic or key.split(':')[0] in automatic)]
        atomic(backup/'record.json', (json.dumps(record, indent=2)+'\n').encode(), 0o600)
        print('XETAL_RUNTIME_TRANSACTION '+str(backup), flush=True)
        try:
            pin.parent.mkdir(parents=True, exist_ok=True)
            atomic(pin, record['new_pin'].encode())
            run([*debian.APT, '-y', '--no-remove', '--allow-downgrades', 'install', *exact])
            requested = local | set(dependencies.PACKAGES['debian'])
            mark_auto(set(record['automatic_before']) | {key for key in expected if key not in before and key.split(':')[0] not in requested})
            runtime.policy.require()
            if not debian.pinned(required):
                raise RuntimeError('Debian runtime pins changed during Setup.')
        except BaseException:
            restore(backup, state, True)
            raise
        print('Debian runtime installed. Recovery: '+str(backup), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--restore', type=Path); args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run this helper through Setup administrator authentication.')
    def interrupted(*_):
        raise KeyboardInterrupt('Debian runtime setup interrupted.')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.restore:
            restore(args.restore)
        else:
            install()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        parser.exit(1, 'Debian runtime setup: '+str(error)+'\n')
