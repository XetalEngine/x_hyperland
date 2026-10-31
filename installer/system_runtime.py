#!/usr/bin/env python3
"""Narrow privileged operation: verified Hyprland package and its pacman hold."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile

import runtime_install as runtime


def config_with_hold(text, include=str(runtime.PIN)):
    directive = 'Include = '+include
    lines = [line for line in text.splitlines(keepends=True) if line.strip() != directive]
    for index, line in enumerate(lines):
        if line.strip() == '[options]':
            lines.insert(index+1, directive+'\n')
            return ''.join(lines)
    raise RuntimeError('pacman.conf has no [options] section; no settings changed.')


def atomic(path, data, mode=0o644):
    if path.is_symlink(): raise RuntimeError('Refusing a symbolic link for '+str(path))
    fd, name = tempfile.mkstemp(prefix='.xetal-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, mode); os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def restore(backup, conf=Path('/etc/pacman.conf'), pin=runtime.PIN,
            state=Path('/var/lib/xetal-hyprland/runtime'), _locked=False):
    backup = backup.resolve()
    if backup.parent != state.resolve() or backup.is_symlink(): raise RuntimeError('Invalid compositor recovery record.')
    if not _locked:
        with (state/'setup.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return restore(backup, conf, pin, state, _locked=True)
    if conf.is_symlink() or pin.is_symlink(): raise RuntimeError('Package configuration must use regular files.')
    record = json.loads((backup/'record.json').read_text())
    current = subprocess.run(['/usr/bin/pacman','-Q','hyprland'],capture_output=True,text=True).stdout.strip()
    expected = 'hyprland '+record['required']['arch_package']
    if current not in (record['previous'], expected):
        raise RuntimeError('The compositor was changed by another operation; recovery will not overwrite it.')
    if current == expected and record['previous'] and record['previous'] != current:
        package = backup/'previous.pkg.tar.zst'
        if hashlib.sha256(package.read_bytes()).hexdigest() != record['previous_sha256']:
            raise RuntimeError('The compositor recovery package changed.')
        subprocess.run(['/usr/bin/pacman-key','--verify',str(package)+'.sig',str(package)],check=True)
        subprocess.run(['/usr/bin/pacman','-U','--noconfirm','--needed',str(package)],check=True)
    # Preserve later unrelated edits in pacman.conf; remove only our added include.
    original = (backup/'pacman.conf').read_bytes()
    expected_conf = config_with_hold(original.decode(),str(pin)).encode()
    if conf.read_bytes() == expected_conf: atomic(conf, original, stat.S_IMODE(conf.stat().st_mode))
    elif ('Include = '+str(pin)) not in original.decode():
        lines = conf.read_text().splitlines(keepends=True)
        atomic(conf, ''.join(line for line in lines if line.strip() != 'Include = '+str(pin)).encode(), stat.S_IMODE(conf.stat().st_mode))
    if record['had_pin']: atomic(pin, (backup/'xetal-hyprland.conf').read_bytes())
    else: pin.unlink(missing_ok=True)
    print('Previous compositor and package hold restored.', flush=True)


def install(package=None, previous_package=None, conf=Path('/etc/pacman.conf'), pin=runtime.PIN,
            state=Path('/var/lib/xetal-hyprland/runtime')):
    target = runtime.policy.manifest()
    if conf.is_symlink() or pin.is_symlink(): raise RuntimeError('Package configuration must use regular files.')
    before = conf.read_bytes(); original_pin = pin.read_bytes() if pin.exists() else None
    changed = config_with_hold(before.decode(), str(pin)).encode()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state/'setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = state/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        backup.mkdir(mode=0o700)
        (backup/'pacman.conf').write_bytes(before)
        if original_pin is not None: (backup/'xetal-hyprland.conf').write_bytes(original_pin)
        previous = subprocess.run(['/usr/bin/pacman', '-Q', 'hyprland'], capture_output=True, text=True).stdout.strip()
        record = {'previous': previous, 'required': target, 'had_pin': original_pin is not None}
        if package and previous:
            if not previous_package: raise RuntimeError('The previous compositor package is required for recovery.')
            saved = backup/'previous.pkg.tar.zst'
            shutil.copyfile(previous_package, saved); shutil.copyfile(Path(str(previous_package)+'.sig'), Path(str(saved)+'.sig'))
            subprocess.run(['/usr/bin/pacman-key','--verify',str(saved)+'.sig',str(saved)],check=True)
            info = subprocess.run(['/usr/bin/pacman','-Qp',str(saved)],capture_output=True,text=True,check=True).stdout.strip()
            if info != previous: raise RuntimeError('The recovery package does not match the installed compositor.')
            record['previous_sha256'] = hashlib.sha256(saved.read_bytes()).hexdigest()
        (backup/'record.json').write_text(json.dumps(record, indent=2)+'\n')
        if package: print('XETAL_RUNTIME_TRANSACTION '+str(backup), flush=True)
        try:
            if package:
                # Copy into a root-owned directory before verification and installation.
                # No mutable user pathname is handed to pacman after its checksum check.
                with tempfile.TemporaryDirectory(prefix='packages-', dir=backup) as temp:
                    verified = Path(temp)/runtime.policy.filename(target)
                    for suffix, key in [('', 'package_sha256'), ('.sig', 'signature_sha256')]:
                        destination = Path(str(verified)+suffix)
                        shutil.copyfile(Path(str(package)+suffix), destination)
                        if hashlib.sha256(destination.read_bytes()).hexdigest() != target[key]:
                            raise RuntimeError('Compositor package verification failed: '+destination.name)
                    subprocess.run(['/usr/bin/pacman-key', '--verify', str(verified)+'.sig', str(verified)], check=True)
                    # Retain dependency and conflict checks; never force incompatible libraries.
                    subprocess.run(['/usr/bin/pacman', '-U', '--noconfirm', '--needed', str(verified)], check=True)
            runtime.policy.require()
            if conf.read_bytes() != before:
                raise RuntimeError('pacman.conf changed during package setup. The later edits were kept; run Setup again.')
            atomic(pin, runtime.pin_text(target).encode())
            atomic(conf, changed, stat.S_IMODE(conf.stat().st_mode))
            subprocess.run(['/usr/bin/pacman-conf', '--config', str(conf), 'IgnorePkg'], check=True)
        except BaseException:
            restore(backup, conf, pin, state, _locked=True)
            raise
        print('Hyprland '+target['hyprland']+' is installed and held. Package configuration backup: '+str(backup), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--package', type=Path)
    parser.add_argument('--previous', type=Path); parser.add_argument('--restore', type=Path); args = parser.parse_args()
    if os.geteuid() != 0: parser.error('This operation requires administrator authentication through Setup.')
    def interrupted(*_): raise KeyboardInterrupt('Compositor setup interrupted.')
    signal.signal(signal.SIGTERM, interrupted)
    if args.restore: restore(args.restore)
    else: install(args.package, args.previous)
