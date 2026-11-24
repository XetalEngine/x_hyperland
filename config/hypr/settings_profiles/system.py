"""Authenticated system-settings worker. Never accepts arbitrary target roots."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from settings_profiles import archive, catalog, packages

STATE = Path('/var/lib/hyperfusion/settings-profiles')


def machine(root=Path('/')):
    identity = (root/'etc/machine-id').read_bytes().strip()
    if not identity or identity == b'uninitialized':
        raise ValueError('The installed system has no permanent machine identity yet.')
    return archive.digest(identity)


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=120,
                            env={**os.environ, 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    if result.returncode: raise RuntimeError((result.stderr or result.stdout).strip()[-3000:] or 'System operation failed.')
    return result.stdout


def runtime_values(root=Path('/')):
    sys.path.insert(0, str(ROOT/'control_panel'))
    import tweaks_runtime as runtime
    found = {}
    # Read exact per-policy/device values, including choices set outside Fusion.
    for kind in runtime.RUNTIME_IDS:
        for value in runtime.available(kind, root):
            try:
                for path in runtime.targets(kind, value, root):
                    found[path.relative_to(root).as_posix()] = runtime.selected(runtime.read(path))
            except ValueError: continue
    return found


def restore_runtime(values, root=Path('/')):
    sys.path.insert(0, str(ROOT/'control_panel'))
    import tweaks_runtime as runtime
    if not isinstance(values, dict) or len(values) > 10000: raise ValueError('Invalid saved hardware policy.')
    # CPU governor first: energy preference availability depends on it.
    for name in sorted(values, key=lambda n: (not n.endswith('scaling_governor'), n)):
        allowed = {}
        for kind in runtime.RUNTIME_IDS:
            for choice in runtime.available(kind, root):
                try:
                    for path, value in runtime.targets(kind, choice, root).items():
                        allowed.setdefault(path.relative_to(root).as_posix(), set()).add(value)
                except ValueError: continue
        if name not in allowed or values[name] not in allowed[name]:
            raise ValueError('Saved hardware policy is not supported: ' + name)
        runtime.write_verified(root/name, values[name])


def capture(groups, roots=None, package_reader=packages.snapshot):
    roots = roots or catalog.roots(); groups = sorted(set(groups) & catalog.SYSTEM_IDS)
    records, blobs = archive.collect(roots, groups, ('system',))
    extra = {'machine': machine(roots['system']), 'architecture': platform.machine()}
    if 'packages' in groups: extra['packages'] = package_reader()
    if 'system' in groups: extra['hardware'] = runtime_values(roots['system'])
    return archive.manifest(groups, records, **extra), blobs


def payload(document, blobs):
    return archive.encode({'manifest': document, 'objects': {k:base64.b64encode(v).decode('ascii') for k,v in blobs.items()}})


def unpack(data):
    if len(data) > archive.MAX_TOTAL * 2: raise ValueError('Settings input too large.')
    value = json.loads(data)
    blobs = {k:base64.b64decode(v, validate=True) for k,v in value['objects'].items()}
    archive.validate(value['manifest'], blobs)
    return value['manifest'], blobs


def restore(document, blobs, groups, roots=None, state=None, command=run):
    roots = roots or catalog.roots(); state = Path(state or STATE)
    groups = sorted(set(groups) & catalog.SYSTEM_IDS)
    if document.get('machine') != machine(roots['system']):
        raise ValueError('System settings belong to another machine. Load desktop categories on this computer instead.')
    if document.get('architecture') != platform.machine(): raise ValueError('System architecture does not match this backup.')
    archive.validate(document, blobs)
    transaction = state/'transactions'/uuid.uuid4().hex
    old_runtime = runtime_values(roots['system']) if 'system' in groups else {}
    with archive.locked(state):
        for pending in (state/'transactions').glob('*/journal.json'):
            archive.recover_transaction(pending.parent, roots)
        # Mount declarations are settings too, but validate them against this
        # computer before replacing anything. Never fabricate disk identities.
        for entry in document['files']:
            if entry['category'] not in groups or entry['scope'] != 'system' or entry['kind'] != 'file': continue
            if entry['path'] == 'etc/fstab':
                transaction.mkdir(parents=True, exist_ok=True, mode=0o700)
                candidate = transaction/'fstab-check'
                archive.atomic(candidate, blobs[entry['sha256']])
                command(['findmnt', '--verify', '--tab-file', str(candidate)])
        count = archive.restore_files(document, blobs, roots, groups, transaction, ('system',))
        try:
            if 'system' in groups:
                if (roots['system']/'etc/sudoers').is_file(): command(['visudo', '-c'])
                restore_runtime(document.get('hardware', {}), roots)
                command(['systemctl', 'daemon-reload'])
            if 'boot' in groups:
                # Generate from the restored preferences and this computer's
                # actual disks. Never import another installation's grub.cfg.
                target = roots['system']/'boot/grub/grub.cfg'
                if not target.parent.is_dir(): raise RuntimeError('This installation does not use GRUB.')
                temp = target.with_name('.fusion-settings-grub-' + uuid.uuid4().hex)
                try:
                    command(['grub-mkconfig', '-o', str(temp)])
                    command(['grub-script-check', str(temp)])
                    os.replace(temp, target)
                finally: temp.unlink(missing_ok=True)
        except BaseException:
            before, previous = archive.read(transaction/'before.hfsettings')
            archive.restore_files(before, previous, roots, groups, transaction/'rollback', ('system',))
            if old_runtime: restore_runtime(old_runtime, roots)
            command(['systemctl', 'daemon-reload'])
            raise
    return {'files': count, 'recovery': str(transaction/'before.hfsettings'), 'restart_required': True}


def factory():
    """Installer-only: call after first installation, before personal changes."""
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with archive.locked(STATE):
        target = STATE/'factory.hfsettings'
        if target.exists(): return
        # This command is run by Setup against the new installed profile. The
        # final keyboard/display choices are now known (including ISO choices).
        if ROOT.name != 'hypr' or ROOT.parent.name != '.config':
            raise ValueError('Factory capture must use a freshly installed desktop profile.')
        from settings_profiles.factory import build
        user_defaults = ROOT/'settings_profiles/factory.hfsettings'
        build(ROOT, user_defaults, ROOT.parent.parent, rendered=True)
        owner = ROOT.stat()
        os.chown(user_defaults, owner.st_uid, owner.st_gid)
        document, blobs = capture(catalog.SYSTEM_IDS)
        document['factory'] = True
        archive.write(target, document, blobs)
        # A nonsecret availability marker lets Settings explain legacy installs
        # without prompting for a password just to open the page.
        marker = Path('/usr/local/share/hyperfusion/settings-factory.json')
        marker.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        archive.atomic(marker, archive.encode({'version': 1, 'created': document['created'], 'machine': document['machine']}), 0o644)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('capture', 'restore', 'factory', 'read-factory'))
    parser.add_argument('--categories', default=','.join(sorted(catalog.SYSTEM_IDS)))
    args = parser.parse_args()
    if os.geteuid() != 0: raise PermissionError('Administrator authentication is required.')
    groups = catalog.selected(args.categories.split(','))
    if set(groups) - catalog.SYSTEM_IDS: raise ValueError('The administrator helper only handles system categories.')
    os.umask(0o077)
    if args.operation == 'capture': sys.stdout.buffer.write(payload(*capture(groups)))
    elif args.operation == 'factory': factory()
    elif args.operation == 'read-factory': sys.stdout.buffer.write(payload(*archive.read(STATE/'factory.hfsettings')))
    else:
        document, blobs = unpack(sys.stdin.buffer.read(archive.MAX_TOTAL * 2 + 1))
        print(json.dumps(restore(document, blobs, groups)))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Settings operation failed: ' + str(error), file=sys.stderr); sys.exit(1)
