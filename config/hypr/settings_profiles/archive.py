"""Versioned settings archives; validated extraction and journaled file changes."""
from contextlib import contextmanager
import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import uuid
import zipfile

from . import catalog

FORMAT = 'hyperfusion-settings'
VERSION = 1
MAX_FILE = 2 * 1024**3
MAX_TOTAL = 8 * 1024**3
MAX_ENTRIES = 100000
SECRET = re.compile(r'password|passwd|passphrase|secret|token|private.?key|preshared.?key|credential|authorization|cookie|'
                    r'(?:^|[ .\[\]/_-])(?:key|psk|pin)(?:$|[ .\[\]/_-])', re.I)
ARTWORK = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.avif', '.mp4', '.webm', '.mkv',
           '.wav', '.ogg', '.mp3', '.flac', '.ttf', '.otf', '.woff2'}


def encode(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
def digest(value): return hashlib.sha256(value).hexdigest()


def atomic(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fchmod(stream.fileno(), mode); os.fsync(stream.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally: Path(name).unlink(missing_ok=True)


@contextmanager
def locked(directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'operation.lock').open('a') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another Save, Load or Reset operation is still running.')
        yield


def walk(path):
    """Never descend through symlinks (including a symlink at a scan root)."""
    if path.is_symlink() or path.is_file(): yield path
    elif path.is_dir():
        for current, directories, files in os.walk(path, followlinks=False):
            directories[:] = sorted(d for d in directories if d not in catalog.TRANSIENT_PARTS)
            for name in directories[:]:
                entry = Path(current) / name
                if entry.is_symlink():
                    yield entry; directories.remove(name)
            for name in sorted(files): yield Path(current) / name


def read_stable(path):
    """Fail visibly if a writer races export; never label a torn file a backup."""
    for _ in range(3):
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode): raise ValueError('Not a regular settings file: ' + str(path))
            if before.st_size > MAX_FILE: raise ValueError('Settings file exceeds the 2 GiB limit: ' + str(path))
            with os.fdopen(fd, 'rb', closefd=False) as stream: data = stream.read(MAX_FILE + 1)
            after = os.fstat(fd)
        finally: os.close(fd)
        current = path.lstat()
        signature = lambda s: (s.st_ino, s.st_dev, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if signature(before) == signature(after) == signature(current) and len(data) == after.st_size: return data
    raise RuntimeError('Settings changed while saving: ' + str(path) + '. Try Save again.')


def collect(roots, groups, scopes=('profile', 'home')):
    groups = set(catalog.selected(groups)); records = []; blobs = {}; seen = set()
    for scope in scopes:
        root = roots[scope].absolute()
        for base in catalog.scan_roots(scope, root):
            # A symlink ancestor is not silently followed by explicit scan paths.
            relative = base.relative_to(root)
            if any((root / Path(*relative.parts[:n])).is_symlink() for n in range(1, len(relative.parts))):
                raise ValueError('Settings directory is a symbolic link: ' + str(base))
            for path in walk(base):
                name = path.relative_to(root).as_posix(); key = scope, name
                group = catalog.category(scope, name)
                if key in seen or group not in groups: continue
                seen.add(key); info = path.lstat()
                entry = dict(scope=scope, path=name, category=group, mode=stat.S_IMODE(info.st_mode) & 0o777)
                if scope == 'system': entry.update(uid=info.st_uid, gid=info.st_gid)
                if stat.S_ISLNK(info.st_mode):
                    entry.update(kind='link', target=os.readlink(path))
                elif stat.S_ISREG(info.st_mode):
                    data = read_stable(path); sha = digest(data)
                    entry.update(kind='file', sha256=sha, size=len(data)); blobs[sha] = data
                else: continue
                records.append(entry)
    check_limits(records)
    return records, blobs


def check_limits(records):
    if len(records) > MAX_ENTRIES: raise ValueError('Too many settings files.')
    if sum(r.get('size', 0) for r in records) > MAX_TOTAL: raise ValueError('Selected settings exceed 8 GiB. Save fewer categories at a time.')


def referenced_artwork(records, blobs, roots):
    """Make a custom wallpaper/sound portable even when it lives outside XDG."""
    result = []; seen = set(); home = str(roots['home'])
    existing = {str(roots[r['scope']] / r['path']) for r in records if r['scope'] in roots}
    for entry in list(records):
        if entry['scope'] != 'profile' or entry['category'] not in ('appearance', 'audio', 'launcher', 'desktop'): continue
        if entry['kind'] != 'file' or entry['size'] > 2_000_000: continue
        try: text = blobs[entry['sha256']].decode('utf-8')
        except UnicodeDecodeError: continue
        # JSON strings are decoded so filenames with spaces / escaping survive.
        try:
            document = json.loads(text)
            def strings(value):
                if isinstance(value, str): yield value
                elif isinstance(value, dict):
                    for v in value.values(): yield from strings(v)
                elif isinstance(value, list):
                    for v in value: yield from strings(v)
            candidates = strings(document)
        except ValueError: candidates = [line.split('=', 1)[-1].strip().strip('"\'') for line in text.splitlines()]
        for name in candidates:
            name = name.replace('~/', home + '/', 1) if name.startswith('~/') else name
            path = Path(name)
            identity = name, entry['category']
            if not path.is_absolute() or path.suffix.lower() not in ARTWORK or identity in seen or name in existing: continue
            seen.add(identity)
            # Shipped artwork is release-owned and already installed; private
            # assets are embedded, never copied back to arbitrary source paths.
            try:
                rel = path.relative_to(roots['profile']).as_posix()
                if catalog.profile_category(rel) is None and not rel.startswith('settings_profiles/imported-assets/') and path.is_file(): continue
            except ValueError: pass
            if not path.is_file(): raise FileNotFoundError('Referenced artwork is missing: ' + name)
            data = read_stable(path.resolve()); sha = digest(data); blobs[sha] = data
            result.append(dict(scope='asset', path=sha + '/' + entry['category'] + '/' + path.name, category=entry['category'], kind='file',
                               source=name, sha256=sha, size=len(data), mode=0o600))
    check_limits(records + result)
    return result


def manifest(groups, records, **metadata):
    return dict(format=FORMAT, version=VERSION, created=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                categories=catalog.selected(groups), files=records, **metadata)


def write(path, document, blobs):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    validate(document, blobs)
    fd, temporary = tempfile.mkstemp(prefix='.fusion-settings-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w+b') as stream:
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as output:
                output.writestr('manifest.json', encode(document))
                for sha in sorted({r['sha256'] for r in document['files'] if r['kind'] == 'file'}):
                    output.writestr('objects/' + sha, blobs[sha])
            stream.flush(); os.fchmod(stream.fileno(), 0o600); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)


def read(path):
    blobs = {}
    with zipfile.ZipFile(path) as source:
        entries = source.infolist(); names = [e.filename for e in entries]
        if len(names) != len(set(names)) or len(names) > MAX_ENTRIES + 1: raise ValueError('Duplicate or excessive archive members.')
        if 'manifest.json' not in names or source.getinfo('manifest.json').file_size > 32 * 1024**2:
            raise ValueError('Missing or oversized settings manifest.')
        if sum(e.file_size for e in entries) > MAX_TOTAL + 32 * 1024**2: raise ValueError('Archive is too large.')
        for entry in entries:
            if entry.filename != 'manifest.json' and not re.fullmatch(r'objects/[0-9a-f]{64}', entry.filename):
                raise ValueError('Unrecognized archive member.')
            if entry.file_size > MAX_FILE: raise ValueError('Oversized archive member.')
        document = json.loads(source.read('manifest.json'))
        for entry in entries:
            if entry.filename.startswith('objects/'):
                data = source.read(entry); sha = entry.filename[8:]
                if digest(data) != sha: raise ValueError('Damaged settings archive: checksum mismatch.')
                blobs[sha] = data
    validate(document, blobs)
    return document, blobs


def validate(document, blobs):
    if not isinstance(document, dict) or document.get('format') != FORMAT or document.get('version') != VERSION:
        raise ValueError('This is not a supported Hyper Fusion settings archive.')
    groups = catalog.selected(document.get('categories', [])); seen = set()
    files = document.get('files')
    if not isinstance(files, list): raise ValueError('Missing settings inventory.')
    for r in files:
        if not isinstance(r, dict): raise ValueError('Invalid settings record.')
        name = catalog.safe_name(r.get('path')); scope = r.get('scope'); key = scope, name
        if key in seen: raise ValueError('Duplicate settings destination.')
        seen.add(key)
        if r.get('category') not in groups: raise ValueError('File outside selected categories.')
        if scope == 'asset':
            if (r.get('kind') != 'file' or not re.fullmatch(r'[0-9a-f]{64}/(?:[a-z-]+/)?[^/]+', name)
                    or not isinstance(r.get('source'), str) or not Path(r['source']).is_absolute()):
                raise ValueError('Invalid artwork record.')
        elif catalog.category(scope, name) != r['category']: raise ValueError('Unregistered settings destination: ' + name)
        if type(r.get('mode')) is not int or not 0 <= r['mode'] <= 0o777: raise ValueError('Invalid file permissions.')
        if scope == 'system' and any(type(r.get(k, 0)) is not int or not 0 <= r.get(k, 0) < 2**32-1 for k in ('uid', 'gid')):
            raise ValueError('Invalid system file ownership.')
        if r.get('kind') == 'file':
            sha = r.get('sha256'); data = blobs.get(sha)
            if data is None or len(data) != r.get('size') or digest(data) != sha: raise ValueError('Missing or damaged settings content.')
        elif r.get('kind') == 'link':
            target = r.get('target')
            if not isinstance(target, str) or not target or '\x00' in target: raise ValueError('Invalid symbolic link.')
        else: raise ValueError('Unsupported settings entry type.')
    check_limits(files)
    links = {(r['scope'], r['path']) for r in files if r['kind'] == 'link'}
    for scope, name in seen:
        if any((scope, p.as_posix()) in links for p in Path(name).parents):
            raise ValueError('A symbolic link conflicts with a settings directory.')


def destination(roots, entry):
    scope = entry['scope']; name = catalog.safe_name(entry['path'])
    if scope == 'asset':
        root = roots['profile']; name = 'settings_profiles/imported-assets/' + name
    else: root = roots[scope]
    root = root.absolute(); result = root / name
    if root.is_symlink(): raise ValueError('The settings root is a symbolic link: ' + str(root))
    for parent in result.parents:
        if parent == root: break
        if parent.is_symlink(): raise ValueError('Refusing to write through a symbolic-link directory: ' + str(parent))
    if result.is_dir() and not result.is_symlink(): raise ValueError('A settings file has become a directory: ' + str(result))
    return result


def link_allowed(path, target, roots, scope):
    absolute = Path(os.path.normpath(str(path.parent / target))) if not target.startswith('/') else Path(os.path.normpath(target))
    base = roots[scope].absolute()
    if str(absolute).startswith(('/usr/share/', '/usr/lib/')): return
    if scope in ('home', 'profile'):
        generated = roots['profile']/'cursors/.build/data/icons'
        if absolute.parent == generated and re.fullmatch(r'Xetal-Cursor-[a-z0-9-]+', absolute.name): return
    if scope == 'system':
        # System service aliases commonly point into the package-owned unit tree.
        if target == '/dev/null' or str(absolute).startswith(('/usr/', '/lib/', '/run/')): return
    try: name = absolute.relative_to(base).as_posix()
    except ValueError: raise ValueError('Symbolic link escapes the settings root: ' + str(path))
    if catalog.category(scope, name) is None: raise ValueError('Symbolic link targets an unmanaged file: ' + str(path))


def relocated(entry, document, roots):
    entry = dict(entry)
    if entry['scope'] in ('home', 'profile') and entry['kind'] == 'link':
        for key in ('profile', 'home'):
            old = document.get(key)
            if old and (entry['target'] == old or entry['target'].startswith(old + '/')):
                entry['target'] = str(roots[key]) + entry['target'][len(old):]
    return entry


def ownership(path, entry):
    if entry and entry['scope'] == 'system':
        os.chown(path, entry.get('uid', 0), entry.get('gid', 0), follow_symlinks=False)


def recover_transaction(directory, roots):
    """Rollback a transaction interrupted by power loss / SIGKILL before retry."""
    directory = Path(directory); path = directory/'journal.json'
    if not path.is_file(): return False
    journal = json.loads(path.read_text())
    if journal.get('status') not in ('applying', 'rollback-failed'): return False
    if journal.get('roots') != {k:str(v) for k,v in roots.items()}: raise ValueError('Interrupted settings transaction has different target roots.')
    document, blobs = read(directory/'before.hfsettings')
    previous = {(r['scope'], r['path']):r for r in document['files']}
    planned = journal.get('paths')
    if not isinstance(planned, list): raise ValueError('Interrupted settings journal is incomplete.')
    for key in reversed(planned):
        if not isinstance(key, list) or len(key) != 2: raise ValueError('Invalid recovery destination.')
        scope, name = key; safe = catalog.category(scope, name) if scope != 'asset' else 'asset'
        if not safe: raise ValueError('Unregistered recovery destination.')
        entry = previous.get((scope, name)); target = destination(roots, entry or {'scope':scope, 'path':name})
        if entry is None: target.unlink(missing_ok=True)
        elif entry['kind'] == 'file': atomic(target, blobs[entry['sha256']], entry['mode'])
        else:
            link_allowed(target, entry['target'], roots, scope)
            temp = target.with_name('.recover-' + uuid.uuid4().hex)
            try: os.symlink(entry['target'], temp); os.replace(temp, target)
            finally: temp.unlink(missing_ok=True)
        ownership(target, entry)
    atomic(path, encode({'status':'recovered'}))
    return True


def values(document, blobs):
    """Full expandable leaf inventory. Secret values are saved but never displayed."""
    def flatten(value, prefix=''):
        if isinstance(value, dict):
            if not value: yield prefix or '(value)', '{}'
            for key, item in value.items(): yield from flatten(item, prefix + ('.' if prefix else '') + str(key))
        elif isinstance(value, list):
            if not value: yield prefix or '(value)', '[]'
            for index, item in enumerate(value): yield from flatten(item, f'{prefix}[{index}]')
        else: yield prefix or '(value)', str(value)
    for r in document['files']:
        label = r['scope'] + '/' + r['path']; rows = []
        if r['kind'] == 'link': rows = [('Link target', r['target'])]
        elif SECRET.search(label) or any(x in label for x in ('keyrings/', 'kwalletd/', '/shadow', 'tls-key', 'kdeconnect/',
                                                             'NetworkManager/system-connections/', 'var/lib/bluetooth/')):
            rows = [('Private content', 'Included · hidden in this list')]
        elif r['size'] > 2_000_000: rows = [('File', f"{r['size']:,} bytes · SHA-256 {r['sha256']}")]
        else:
            data = blobs[r['sha256']]
            try:
                text = data.decode('utf-8')
                if '\0' in text: raise UnicodeDecodeError('utf-8', b'\0', 0, 1, 'binary')
                try: rows = list(flatten(json.loads(text)))
                except ValueError:
                    section = ''
                    for index, line in enumerate(text.splitlines(), 1):
                        clean = line.strip()
                        if not clean or clean.startswith(('#', ';')): continue
                        if clean.startswith('[') and clean.endswith(']'): section = clean; continue
                        key, sep, value = clean.partition('=')
                        rows.append(((section + ' ' + key.strip()) if sep else 'Line ' + str(index), value.strip() if sep else clean))
                if not rows: rows = [('File', 'Empty / comments only')]
            except UnicodeDecodeError: rows = [('Binary file', f"{r['size']:,} bytes · SHA-256 {r['sha256']}")]
        yield r['category'], label, [(key, 'Included · hidden' if SECRET.search(key) else value) for key, value in rows]


def restore_files(document, blobs, roots, groups, journal_dir, scopes=('profile', 'home')):
    """All destinations preflighted; every replacement journaled before mutation.

    Files missing from a selected category in the archive are removed. This is
    essential for Reset and also restores explicit absence on normal Load.
    """
    validate(document, blobs); groups = set(catalog.selected(groups))
    if groups - set(document['categories']): raise ValueError('The archive does not contain every selected category.')
    recover_transaction(journal_dir, roots)
    existing, old_blobs = collect(roots, list(groups), scopes)
    desired = [relocated(r, document, roots) for r in document['files'] if r['category'] in groups and (r['scope'] in scopes or (r['scope'] == 'asset' and 'profile' in scopes))]
    incoming = {(r['scope'], r['path']): r for r in desired}
    operations = {**{(r['scope'], r['path']): None for r in existing}, **incoming}
    destinations = {}
    for key, r in operations.items():
        entry = r or {'scope': key[0], 'path': key[1]}
        path = destination(roots, entry); destinations[key] = path
        if r and r['kind'] == 'link': link_allowed(path, r['target'], roots, r['scope'])
    # A symlink installed by this archive cannot become another entry's parent.
    all_paths = set(destinations.values())
    for key, r in operations.items():
        if r and r['kind'] == 'link' and any(destinations[key] in p.parents for p in all_paths):
            raise ValueError('A symbolic link conflicts with a settings directory.')
    previous = {(r['scope'], r['path']): r for r in existing}
    # Assets can already exist from a previous import. Journal those as well.
    for key, r in incoming.items():
        if key in previous or r['scope'] != 'asset': continue
        path = destinations[key]
        if path.exists() or path.is_symlink():
            if path.is_symlink(): raise ValueError('Imported artwork was replaced by a symbolic link.')
            data = read_stable(path); sha = digest(data); old_blobs[sha] = data
            previous[key] = {**r, 'sha256': sha, 'size': len(data), 'mode': stat.S_IMODE(path.stat().st_mode)}
    journal_dir = Path(journal_dir); journal_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    recovery = manifest(list(groups), list(previous.values()), home=str(roots['home']), profile=str(roots['profile']))
    write(journal_dir/'before.hfsettings', recovery, old_blobs)
    atomic(journal_dir/'journal.json', encode({'status': 'applying', 'paths': [list(k) for k in operations], 'roots': {k:str(v) for k,v in roots.items()}}))
    replacements = {r['source']: str(destination(roots, r)) for r in desired if r['scope'] == 'asset'}
    old_home = document.get('home', str(roots['home'])); old_profile = document.get('profile', str(roots['profile']))
    def put(path, entry, content):
        if entry is None: path.unlink(missing_ok=True); return
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755 if entry['scope'] == 'system' else 0o700)
        if entry['kind'] == 'link':
            temp = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
            try: os.symlink(entry['target'], temp); os.replace(temp, path)
            finally: temp.unlink(missing_ok=True)
        else: atomic(path, content, entry['mode'])
        ownership(path, entry)
    changed = []
    try:
        for key, entry in sorted(operations.items()):
            data = blobs[entry['sha256']] if entry and entry['kind'] == 'file' else b''
            if entry and entry['kind'] == 'file' and entry['scope'] == 'profile':
                try:
                    value = data.decode('utf-8')
                    for source, target in replacements.items(): value = value.replace(source, target)
                    value = value.replace(old_profile, str(roots['profile'])).replace(old_home, str(roots['home']))
                    data = value.encode()
                except UnicodeDecodeError: pass
            changed.append(key)
            put(destinations[key], entry, data)
        atomic(journal_dir/'journal.json', encode({'status': 'complete', 'files': len(changed)}))
    except BaseException as error:
        failures = []
        for key in reversed(changed):
            entry = previous.get(key)
            try: put(destinations[key], entry, old_blobs[entry['sha256']] if entry and entry['kind'] == 'file' else b'')
            except Exception as failure: failures.append(str(failure))
        atomic(journal_dir/'journal.json', encode({'status': 'rollback-failed' if failures else 'rolled-back', 'error': str(error), 'rollback_errors': failures,
            'paths': [list(k) for k in operations], 'roots': {k:str(v) for k,v in roots.items()}}))
        if failures: raise RuntimeError('Restore failed; recovery needs attention at ' + str(journal_dir)) from error
        raise
    return len(changed)
