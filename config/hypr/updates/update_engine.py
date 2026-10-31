"""Profile-only update merging and recoverable file transactions. No network/UI."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

REPOSITORY = 'https://github.com/XetalEngine/x_hyperland.git'
BRANCH = 'main'
META = '.xetal-update.json'
IGNORE = {'__pycache__', 'cache', 'state', 'font-cache', 'qt-settings', 'mozilla', '.git', '.build', 'build'}
# Outputs of the theme editor, and hardware state, belong to the recipient.
KEEP = {'control_center/displays.conf', 'control_center/workspaces.conf',
        'theme/custom-presets.json',
        'wallpaper/selection.json', 'wallpaper/hyprpaper.conf',
        'waybar/style.css', 'waybar/updates.css', 'swaync/style.css', 'theme/current.colors',
        'theme/kitty-colors.conf', 'dolphin/config/kdeglobals',
        'dolphin/data/user-places.xbel', 'dolphin/config/user-dirs.dirs',
        'dolphin/data/konsole/Xetal-Dolphin.profile', 'dolphin/data/konsole/Xetal-Dolphin.colorscheme'}


def now(): return datetime.now(timezone.utc).isoformat()


def sha(data): return hashlib.sha256(data).hexdigest() if data is not None else None


def revision(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError('The update does not identify a complete Git commit.')
    return value


def location(root, relative):
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or '..' in path.parts or str(path) != relative:
        raise ValueError('Invalid update path: '+relative)
    result = root / relative
    # Never write through a user symlink into another desktop or filesystem.
    if root.is_symlink() or any(p.is_symlink() for p in [result, *list(result.parents)[:len(path.parts)-1]]):
        raise ValueError('Update path is a symbolic link: '+relative)
    return result


def read(path): return path.read_bytes() if path.is_file() else None


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, mode); os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally: Path(name).unlink(missing_ok=True)


def write_json(path, value): atomic(path, (json.dumps(value, indent=2)+'\n').encode())


def json_file(path, default=None):
    try: return json.loads(path.read_text())
    except FileNotFoundError: return default


@contextmanager
def locked(state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state.parent/'install.lock').open('a') as installer, (state/'operation.lock').open('a') as lock:
        try:
            fcntl.flock(installer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('An update operation is already running.') from None
        yield


def source_files(root):
    return [p for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()
            and not IGNORE.intersection(p.relative_to(root).parts)
            and p.suffix not in ('.pyc', '.so', '.o', '.lock')
            and p.name not in (META, '.xetal-install.json', 'window-preview', 'version.txt')]


def metadata(root, commit):
    files = {}
    for path in source_files(root):
        data = path.read_bytes(); entry = {'sha256': sha(data), 'mode': path.stat().st_mode & 0o777}
        if len(data) <= 2_000_000 and b'\0' not in data:
            try: entry['text'] = data.decode('utf-8')
            except UnicodeDecodeError: pass
        files[str(path.relative_to(root))] = entry
    result = {'version': 1, 'repository': REPOSITORY, 'branch': BRANCH,
              'revision': revision(commit), 'installed': now(), 'files': files}
    if (root/'runtime/manifest.json').is_file():
        result['runtime'] = json_file(root/'runtime/manifest.json')
        fedora = result['runtime'].get('fedora_manifest')
        if fedora:
            data = json_file(location(root, 'runtime/'+fedora))
            result['runtime']['fedora_packages'] = {p['name']:p['evr']+'.'+p['architecture'] for p in data['packages']}
        debian = result['runtime'].get('debian_manifest')
        if debian:
            data = json_file(location(root, 'runtime/'+debian))
            result['runtime']['debian_packages'] = {p['name']+':'+p['architecture']:p['version'] for p in data['packages']}
    return result


def installed(root):
    value = json_file(root/META)
    if not isinstance(value, dict) or value.get('version') != 1 or value.get('repository') != REPOSITORY:
        raise RuntimeError('This profile needs update registration. Run the current x_hyperinstall.sh first.')
    revision(value.get('revision'))
    if not isinstance(value.get('files'), dict): raise ValueError('Invalid installed file inventory.')
    for name in value['files']: location(root, name)
    return value


_MISSING = object()


def merge_json(base, local, remote):
    """New defaults arrive; overlapping preference edits keep the user's value."""
    if local == base: return remote
    if remote == base or local == remote: return local
    if all(isinstance(v, dict) for v in (base, local, remote)):
        out = {}
        for key in dict.fromkeys([*local, *remote]):
            value = merge_json(base.get(key, _MISSING), local.get(key, _MISSING), remote.get(key, _MISSING))
            if value is not _MISSING: out[key] = value
        return out
    if all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in (base, local, remote)):
        out = [x for x in local if x not in base or x in remote]
        for index, item in enumerate(remote):
            if item in base or item in out: continue
            previous = next((x for x in reversed(remote[:index]) if x in out), None)
            out.insert(out.index(previous)+1 if previous is not None else 0, item)
        return out
    return local


def merge_file(name, base, local, remote):
    if name in KEEP and local is not None: return local
    old_hash = base.get('sha256') if base else None
    if sha(local) == old_hash or local == remote: return remote
    if sha(remote) == old_hash: return local
    if remote is None or local is None: return local
    if base is None: raise RuntimeError('A new update file already exists locally: '+name)
    ancestor = base.get('text')
    if ancestor is not None:
        try:
            a, b = local.decode('utf-8'), remote.decode('utf-8')
            if name.endswith('.json'):
                return (json.dumps(merge_json(json.loads(ancestor), json.loads(a), json.loads(b)), indent=2)+'\n').encode()
            with tempfile.TemporaryDirectory(prefix='xetal-merge-') as temp:
                paths = [Path(temp)/s for s in ('local', 'base', 'update')]
                for path, text in zip(paths, (a, ancestor, b)): path.write_text(text)
                result = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
                if result.returncode == 0: return result.stdout
        except (UnicodeDecodeError, ValueError): pass
    raise RuntimeError('Local edits overlap this update: '+name+'. Your files were kept. Resolve the difference before retrying.')


def merge_profile(live, upstream, stage, commit):
    old = installed(live); new = metadata(upstream, commit)
    stage.mkdir(parents=True)
    # Build a review tree of managed files and custom Hyprland includes only.
    # Browser profiles, Dolphin caches, recordings, etc. are never copied or changed.
    names = set(old['files']) | set(new['files'])
    extras = [p for p in live.rglob('*.conf') if not IGNORE.intersection(p.relative_to(live).parts)
              and not str(p.relative_to(live)).startswith('dolphin/')]
    for path in extras:
        relative = str(path.relative_to(live)); destination = location(stage, relative)
        if not path.is_symlink(): destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, destination)
    expected = {}
    for name in sorted(names):
        current = location(live, name); local = read(current); incoming = read(location(upstream, name))
        expected[name] = sha(local)
        merged = merge_file(name, old['files'].get(name), local, incoming)
        destination = location(stage, name)
        if merged is None: destination.unlink(missing_ok=True); continue
        mode = (current.stat().st_mode & 0o777) if local is not None else new['files'][name]['mode']
        atomic(destination, merged, mode)
    write_json(stage/META, new)
    expected[META] = sha(read(live/META))
    # Reuse compiler caches only inside the review tree. Builders check source
    # and installed-library fingerprints before accepting these binaries.
    for relative in ('theme/qt5', 'theme/qt6', 'theme/gtk3', 'effects/burn/.build', 'effects/cube/.build', 'effects/minimize/.build'):
        source = live/relative
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, stage/relative, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('*.lock', 'build.log'), symlinks=True)
    return expected


def prepare_plan(live, stage, expected, commit, automatic=True):
    """Include freshly built libraries, but do not touch any live file yet."""
    changes = {}
    for path in sorted(stage.rglob('*')):
        if not path.is_file() or path.is_symlink(): continue
        name = str(path.relative_to(stage))
        if name.startswith('control_panel/.build/') and name != 'control_panel/.build/xetal-control-panel': continue
        if '__pycache__' in path.parts or path.suffix in ('.lock', '.pyc', '.o') or path.name == 'build.log': continue
        current = location(live, name); old = read(current); data = path.read_bytes()
        if data != old or (current.exists() and path.stat().st_mode & 0o777 != current.stat().st_mode & 0o777):
            expected.setdefault(name, sha(old))
            changes[name] = {'sha256': sha(data), 'mode': path.stat().st_mode & 0o777}
    new = installed(stage)
    for name, entry in installed(live)['files'].items():
        if name not in new['files'] and not (stage/name).exists() and sha(read(location(live, name))) == entry['sha256']:
            changes[name] = None
    return {'version': 1, 'revision': revision(commit), 'created': now(), 'automatic': automatic,
            'expected': expected, 'changes': changes}


def check_plan(live, stage, plan):
    if plan.get('version') != 1: raise ValueError('Unsupported update transaction.')
    revision(plan['revision'])
    for name, digest in plan['expected'].items():
        if sha(read(location(live, name))) != digest:
            raise RuntimeError('Your settings changed after preparation: '+name+'. The update will be prepared again.')
    for name, entry in plan['changes'].items():
        location(live, name)
        if entry is not None and sha(read(location(stage, name))) != entry['sha256']:
            raise RuntimeError('Prepared update failed its integrity check: '+name)


def apply_plan(live, stage, plan, state):
    check_plan(live, stage, plan)
    backup = state/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup.mkdir(parents=True, mode=0o700)
    before = {}
    for name in plan['changes']:
        path = location(live, name); data = read(path)
        before[name] = None if data is None else {'sha256': sha(data), 'mode': path.stat().st_mode & 0o777}
        if data is not None: atomic(location(backup/'files', name), data, before[name]['mode'])
    journal = {'version': 1, 'target': str(live), 'stage': str(stage), 'revision': plan['revision'],
               'before': before, 'after': plan['changes'], 'completed': False}
    write_json(backup/'transaction.json', journal)
    write_json(state/'transaction.json', {'backup': str(backup)})
    try:
        for name, entry in plan['changes'].items():
            path = location(live, name)
            if entry is None: path.unlink(missing_ok=True)
            else: atomic(path, (stage/name).read_bytes(), entry['mode'])
        journal['completed'] = True; write_json(backup/'transaction.json', journal)
        write_json(state/'last-backup.json', {'backup': str(backup)})
        (state/'transaction.json').unlink(missing_ok=True)
        return backup
    except BaseException:
        recover(live, state)
        raise


def recover(live, state):
    active = json_file(state/'transaction.json')
    if not active: return
    backup = Path(active['backup']); record = json_file(backup/'transaction.json')
    if record['target'] != str(live): raise ValueError('Update recovery belongs to a different profile.')
    if not record['completed']:
        for name, before in record['before'].items():
            path = location(live, name); current = sha(read(path)); after = record['after'][name]
            if current not in (before['sha256'] if before else None, after['sha256'] if after else None):
                raise RuntimeError('Recovery kept an independently changed file: '+name)
            if before is None: path.unlink(missing_ok=True)
            else:
                data = location(backup/'files', name).read_bytes()
                if sha(data) != before['sha256']: raise ValueError('Damaged rollback copy: '+name)
                atomic(path, data, before['mode'])
    else:
        # A process can stop after committing files but before recording the
        # rollback pointer. Complete that bookkeeping on the next login.
        write_json(state/'last-backup.json', {'backup': str(backup)})
    (state/'transaction.json').unlink(missing_ok=True)


def rollback_plan(live, backup):
    record = json_file(backup/'transaction.json')
    if not record or record['target'] != str(live) or not record['completed']:
        raise ValueError('This backup is not a completed update for this profile.')
    expected = {name: (entry['sha256'] if entry else None) for name, entry in record['after'].items()}
    previous = json_file(backup/'files'/META)
    return {'version': 1, 'revision': revision(previous['revision']), 'created': now(),
            'automatic': False, 'expected': expected, 'changes': record['before'], 'runtime': previous.get('runtime')}
