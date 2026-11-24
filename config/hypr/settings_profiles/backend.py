"""User-side Save / Load / Reset, with next-login desktop activation."""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import copy
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from . import archive, catalog, packages, system, windows

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home()/'.local/state/hyperfusion-settings'
FACTORY = ROOT/'settings_profiles/factory.hfsettings'
SYSTEM_FACTORY = Path('/usr/local/share/hyperfusion/settings-factory.json')


@contextmanager
def update_lock(directory):
    """Share Setup/updater's lock order so an archive cannot straddle releases."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory.parent/'install.lock').open('a') as setup, (directory/'operation.lock').open('a') as update:
        try:
            fcntl.flock(setup, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(update, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Desktop Setup or an update is running. Finish it before saving or loading settings.')
        yield


def administrator(arguments, data=None):
    env = dict(os.environ, SUDO_ASKPASS=str(ROOT/'scripts/sudo-askpass.sh'))
    # -k forces a fresh prompt for this privileged action, even if Control Panel
    # recently authenticated. No retained administrator helper or password.
    prefix = ['sudo', '-k', '-A', '--']
    result = subprocess.run([*prefix, *arguments], input=data, capture_output=True, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace').strip()[-4000:] or 'Administrator authentication was cancelled.')
    return result.stdout


def root_operation(operation, groups, document=None, blobs=None):
    arguments = ['/usr/bin/python3', str(ROOT/'settings_profiles/system.py'), operation,
                 '--categories', ','.join(sorted(set(groups) & catalog.SYSTEM_IDS))]
    data = system.payload(document, blobs) if document is not None else None
    output = administrator(arguments, data)
    return system.unpack(output) if operation in ('capture', 'read-factory') else json.loads(output)


def instance():
    sig = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    run = os.environ.get('XDG_RUNTIME_DIR', '')
    if not run or not sig or '/' in sig: return None
    path = Path(run)/'hypr'/sig
    return path if (path/'.socket.sock').is_socket() else None


def user_snapshot(groups, roots=None, live=True):
    roots = roots or catalog.roots(); user_groups = sorted(set(groups) & catalog.USER_IDS)
    if not user_groups: return [], {}
    records, blobs = archive.collect(roots, user_groups)
    if live and 'windows' in user_groups and instance():
        # Ask the owner to flush its latest sampled rectangles before export.
        request = instance()/'settings-memory-flush'
        archive.atomic(request, b'flush\n')
        deadline = time.monotonic() + 2.5
        while request.exists() and time.monotonic() < deadline: time.sleep(.05)
        if request.exists():
            request.unlink(missing_ok=True)
            # An older already-running helper uses its two-second write timer.
            # Closed windows flush immediately; capture() below additionally
            # records each live window directly, including its current geometry.
        records, blobs = archive.collect(roots, user_groups)
        sys.path.insert(0, str(ROOT/'launcher'))
        from floating import Hypr
        previous = roots['profile']/windows.FILE
        old = windows.validate(json.loads(previous.read_text())) if previous.exists() else {'windows': []}
        data = windows.capture(Hypr(instance()), instance(), old)
        # Preserve previously loaded overrides for applications currently closed.
        if old['windows']:
            matches = [r['match'] for r in data['windows']]
            data['windows'] += [r for r in old['windows'] if r['match'] not in matches]
        content = archive.encode(windows.validate(data)); sha = archive.digest(content); blobs[sha] = content
        records = [r for r in records if not (r['scope'] == 'profile' and r['path'] == windows.FILE)]
        records.append(dict(scope='profile', path=windows.FILE, category='windows', kind='file', mode=0o600,
                            sha256=sha, size=len(content)))
    if live and 'audio' in user_groups and instance():
        from . import audio
        content = archive.encode(audio.capture()); sha = archive.digest(content); blobs[sha] = content
        records = [r for r in records if not (r['scope'] == 'profile' and r['path'] == 'settings_profiles/audio.json')]
        records.append(dict(scope='profile', path='settings_profiles/audio.json', category='audio', kind='file',
                            mode=0o600, sha256=sha, size=len(content)))
    records += archive.referenced_artwork(records, blobs, roots)
    return records, blobs


def snapshot(groups, roots=None, live=True, privileged=root_operation):
    groups = catalog.selected(groups); roots = roots or catalog.roots()
    records, blobs = user_snapshot(groups, roots, live)
    metadata = {'home': str(roots['home']), 'profile': str(roots['profile']), 'architecture': platform.machine()}
    version = roots['profile']/'VERSION'
    if version.is_file(): metadata['desktop_version'] = version.read_text().strip()
    if set(groups) & catalog.SYSTEM_IDS:
        doc, objects = privileged('capture', groups)
        records += doc['files']; blobs.update(objects)
        for key in ('machine', 'packages', 'hardware'):
            if key in doc: metadata[key] = doc[key]
    return archive.manifest(groups, records, **metadata), blobs


def preview(groups, roots=None):
    """No authentication on opening Settings. System inspection is explicit."""
    roots = roots or catalog.roots(); groups = catalog.selected(groups)
    records, blobs = user_snapshot(groups, roots, live=False)
    return archive.manifest(groups, records, home=str(roots['home']), profile=str(roots['profile'])), blobs


def save(path, groups, roots=None, live=True, state=None, privileged=root_operation):
    state = Path(state or STATE); roots = roots or catalog.roots()
    with update_lock(roots['home']/'.local/state/xetal-hyprland/updates'), archive.locked(state):
        document, blobs = snapshot(groups, roots, live, privileged)
        archive.write(path, document, blobs)
    return document, blobs


def factory_status(root=None):
    root = Path(root or ROOT); desktop = (root/'settings_profiles/factory.hfsettings').is_file()
    system_ready = SYSTEM_FACTORY.is_file()
    return {'desktop': desktop, 'system': system_ready,
            'detail': ('Fresh-install desktop and system defaults are available.' if desktop and system_ready else
                       'This installation has no original system/package baseline. A complete factory reset is unavailable; existing settings will not be guessed.' if desktop else
                       'The installer has not supplied desktop factory defaults yet.')}


def factory_snapshot(privileged=root_operation, root=None):
    root = Path(root or ROOT)
    status = factory_status(root)
    if not status['desktop'] or not status['system']: raise RuntimeError(status['detail'])
    document, blobs = archive.read(root/'settings_profiles/factory.hfsettings')
    sysdoc, sysblobs = privileged('read-factory', catalog.SYSTEM_IDS)
    document['categories'] = catalog.selected([*document['categories'], *sysdoc['categories']])
    document['files'] += sysdoc['files']; blobs.update(sysblobs)
    for key in ('machine', 'packages', 'hardware', 'architecture'):
        if key in sysdoc: document[key] = sysdoc[key]
    return document, blobs


def validate_load(document, blobs, groups, roots=None):
    roots = roots or catalog.roots(); archive.validate(document, blobs)
    groups = catalog.selected(groups)
    if set(groups) - set(document['categories']): raise ValueError('A selected category is missing from this archive.')
    if set(groups) & catalog.SYSTEM_IDS:
        if document.get('machine') != system.machine(roots['system']): raise ValueError('System settings are from another computer. Select desktop categories to migrate them.')
        if document.get('architecture') != platform.machine(): raise ValueError('The system architecture differs from this backup.')
    for entry in document['files']:
        if entry['category'] not in groups: continue
        entry = archive.relocated(entry, document, roots)
        path = archive.destination(roots, entry)
        if entry['kind'] == 'link': archive.link_allowed(path, entry['target'], roots, entry['scope'])
        if entry['scope'] == 'profile' and entry['path'] == windows.FILE:
            windows.validate(json.loads(blobs[entry['sha256']]))
        if entry['scope'] == 'profile' and entry['path'] == 'settings_profiles/audio.json':
            from .audio import validate
            validate(json.loads(blobs[entry['sha256']]))
        if entry['scope'] == 'profile' and entry['kind'] == 'file' and entry['path'].endswith('.json'):
            try: json.loads(blobs[entry['sha256']])
            except ValueError as error: raise ValueError('Invalid JSON settings: ' + entry['path']) from error
    verify_desktop(document, blobs, groups, roots)
    if 'packages' in groups:
        if 'packages' not in document: raise ValueError('This archive has no installed application inventory.')
        return packages.plan(document['packages'], packages.snapshot())
    return None


def verify_desktop(document, blobs, groups, roots):
    """Validate proposed compositor settings without executing startup commands."""
    relevant = set(groups) & {'desktop', 'appearance', 'windows', 'launcher'}
    if not relevant or not (roots['profile']/'hyprland.conf').is_file(): return
    from compat import hypr_compat
    overrides = {}
    for row in document['files']:
        if row['scope'] != 'profile' or row['category'] not in groups or row['kind'] != 'file' or not row['path'].endswith('.conf'): continue
        text = blobs[row['sha256']].decode('utf-8')
        text = text.replace(document.get('profile', str(roots['profile'])), str(roots['profile']))
        text = text.replace(document.get('home', str(roots['home'])), str(roots['home']))
        overrides[roots['profile']/row['path']] = text
    if not overrides: return
    with tempfile.TemporaryDirectory(prefix='fusion-settings-check-') as folder:
        candidate = hypr_compat.candidate(roots['profile'], folder, overrides=overrides)
        result = subprocess.run(['Hyprland', '--verify-config', '--config', str(candidate)], capture_output=True, text=True, timeout=45)
        if result.returncode or 'config ok' not in result.stdout:
            raise ValueError('The saved desktop configuration did not pass validation. No settings were changed.\n' + (result.stdout + result.stderr)[-3000:])


def package_terminal(document, state):
    """AUR has its own interactive build/review flow; keep it visible."""
    folder = Path(state)/('packages-' + uuid.uuid4().hex); folder.mkdir(mode=0o700)
    archive.atomic(folder/'wanted.json', archive.encode(document['packages']))
    process = subprocess.run(['kitty', '--class', 'fusion-settings-packages', '--title', 'Restore installed applications',
                              '/usr/bin/python3', str(ROOT/'settings_profiles/cli.py'), 'packages', str(folder)])
    status = folder/'result.json'
    if not status.exists(): raise RuntimeError('Application restore was interrupted. Settings have not been loaded. Recovery package list is in ' + str(state))
    result = json.loads(status.read_text())
    if not result.get('ok'): raise RuntimeError(result.get('error', 'Package restore failed.'))
    return result


def load(document, blobs, groups, *, roots=None, state=None, privileged=root_operation,
         package_runner=package_terminal, live=True):
    roots = roots or catalog.roots(); state = Path(state or STATE); groups = catalog.selected(groups)
    with update_lock(roots['home']/'.local/state/xetal-hyprland/updates'), archive.locked(state):
        validate_load(document, blobs, groups, roots)
        if (state/'pending.json').exists(): raise RuntimeError('A settings change is already waiting for your next sign-in. Cancel it or sign out before loading another.')
        transaction = state/'recovery'/uuid.uuid4().hex; transaction.mkdir(parents=True, mode=0o700)
        old, old_blobs = snapshot(groups, roots, live, privileged)
        archive.write(transaction/'before.hfsettings', old, old_blobs)
        archive.write(transaction/'requested.hfsettings', document, blobs)
        report = {'status': 'starting', 'categories': groups, 'recovery': str(transaction/'before.hfsettings')}
        archive.atomic(transaction/'result.json', archive.encode(report))
        try:
            if 'packages' in groups:
                report['packages'] = package_runner(document, transaction)
                report['status'] = 'packages-complete'; archive.atomic(transaction/'result.json', archive.encode(report))
            if set(groups) & catalog.SYSTEM_IDS:
                report['system'] = privileged('restore', groups, document, blobs)
            if set(groups) & catalog.USER_IDS:
                # The archive is copied into our private state; changing or
                # deleting the original selected file cannot change activation.
                archive.atomic(state/'pending.json', archive.encode({'version': 1, 'transaction': transaction.name,
                    'categories': groups, 'archive_sha256': archive.digest((transaction/'requested.hfsettings').read_bytes())}))
            report['status'] = 'pending-sign-in' if set(groups) & catalog.USER_IDS else 'restart-required'
            archive.atomic(transaction/'result.json', archive.encode(report))
            return report
        except BaseException as error:
            report.update(status='failed', error=str(error), note='Package operations may have completed. The recovery archive records the previous package set and settings.')
            archive.atomic(transaction/'result.json', archive.encode(report))
            raise RuntimeError(str(error) + '\nRecovery: ' + str(transaction/'before.hfsettings')) from error


def cancel_pending(state=None):
    state = Path(state or STATE)
    with archive.locked(state):
        (state/'pending.json').unlink(missing_ok=True)
    return 'Pending desktop changes cancelled. Any completed package/system changes remain; use the recovery archive to restore them.'


def activate(roots=None, state=None, render=True):
    roots = roots or catalog.roots(); state = Path(state or STATE)
    if not (state/'pending.json').exists(): return False
    with update_lock(roots['home']/'.local/state/xetal-hyprland/updates'), archive.locked(state):
        pending = json.loads((state/'pending.json').read_text())
        name = pending.get('transaction', '')
        if not isinstance(name, str) or len(name) != 32 or any(c not in '0123456789abcdef' for c in name): raise ValueError('Invalid pending settings transaction.')
        folder = state/'recovery'/name; source = folder/'requested.hfsettings'
        if archive.digest(archive.read_stable(source)) != pending.get('archive_sha256'): raise ValueError('Pending settings archive changed; activation stopped.')
        document, blobs = archive.read(source); groups = sorted(set(pending['categories']) & catalog.USER_IDS)
        try:
            validate_load(document, blobs, groups, roots)
            archive.restore_files(document, blobs, roots, groups, folder/'desktop')
            if document.get('factory') and document.get('render_theme') and render:
                subprocess.run(['/usr/bin/python3', str(roots['profile']/'theme/render_defaults.py'),
                                '--asset-root', str(roots['profile']/'theme')], check=True, timeout=120)
            archive.atomic(state/'last-result.json', archive.encode({'status': 'complete', 'recovery': str(folder/'before.hfsettings')}))
            (state/'pending.json').unlink()
        except BaseException as error:
            # Includes failures while generating fresh theme output.
            recovery = folder/'desktop/before.hfsettings'
            if recovery.exists():
                old, old_blobs = archive.read(recovery)
                archive.restore_files(old, old_blobs, roots, groups, folder/'desktop-rollback')
            archive.atomic(state/'last-result.json', archive.encode({'status': 'failed', 'error': str(error), 'recovery': str(folder/'before.hfsettings')}))
            # Quarantine, don't retry a broken archive on every subsequent login.
            os.replace(state/'pending.json', folder/'failed-pending.json')
            raise
    return True
