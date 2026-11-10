"""Pinned 7-Zip engine, structured events, and archive format capabilities."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import selectors
import signal
import sqlite3
import stat
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
FORMATS = {
    '7z': ('7z', ('LZMA2', 'LZMA', 'PPMd', 'BZip2', 'Deflate', 'Deflate64', 'Copy')),
    'zip': ('zip', ('Deflate', 'Deflate64', 'BZip2', 'LZMA', 'PPMd', 'Copy')),
    'tar': ('tar', ('Copy',)),
    'tar.gz': ('gzip', ('Deflate',)),
    'tar.xz': ('xz', ('LZMA2',)),
    'tar.bz2': ('bzip2', ('BZip2',)),
    'gz': ('gzip', ('Deflate',)),
    'xz': ('xz', ('LZMA2',)),
    'bz2': ('bzip2', ('BZip2',)),
    'wim': ('wim', ('Copy',)),
}
LEVELS = {'Store': 0, 'Fastest': 1, 'Fast': 3, 'Normal': 5, 'Maximum': 7, 'Ultra': 9}


class Cancelled(Exception): pass
class PasswordRequired(Exception): pass
class ArchiveError(Exception): pass


def binary():
    manifest = json.loads((ROOT/'vendor/manifest.json').read_text())
    path = ROOT/'vendor'/manifest['engine']['file']
    if os.uname().machine != manifest['engine']['architecture']:
        raise ArchiveError('This bundled 7-Zip engine requires x86-64 Linux.')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024*1024): digest.update(chunk)
    if digest.hexdigest() != manifest['engine']['sha256']:
        raise ArchiveError('The bundled 7-Zip engine failed its integrity check. Repair HyperFusion before retrying.')
    return path


def format_arguments(options):
    kind = options.get('format', '7z')
    if kind not in FORMATS: raise ArchiveError('Choose a supported archive format.')
    native, methods = FORMATS[kind]
    method = options.get('method') or methods[0]
    if method not in methods: raise ArchiveError(f'{method} is not supported when creating {kind} archives.')
    level = int(options.get('level', 5))
    if level not in LEVELS.values(): raise ArchiveError('Choose a supported compression level.')
    args = ['-t'+native, '-sae']
    if native not in ('tar', 'wim'):
        args += [f'-mx={level}', f'-mmt={max(1, int(options.get("threads", os.cpu_count() or 1)))}']
    if native == '7z':
        args += ['-m0='+method, '-ms='+('on' if options.get('solid', True) else 'off')]
    elif native == 'zip': args += ['-mm='+method]
    dictionary = options.get('dictionary', '')
    if dictionary:
        if not re.fullmatch(r'[1-9][0-9]*[bkmgt]?', str(dictionary), re.I):
            raise ArchiveError('Dictionary size must be a number with an optional B, K, M or G suffix.')
        if method in ('LZMA', 'LZMA2', 'PPMd'):
            if native == '7z':
                args[args.index('-m0='+method)] += (':mem=' if method == 'PPMd' else ':d=')+str(dictionary)
            else: args += [('-mmem=' if method == 'PPMd' else '-md=')+str(dictionary)]
    if options.get('password') is not None:
        if native not in ('7z', 'zip'): raise ArchiveError('Password encryption is available for 7z and ZIP.')
        if native == 'zip' and any(ord(c) < 32 or ord(c) > 126 for c in options['password']):
            raise ArchiveError('7-Zip requires printable ASCII passwords for ZIP. Choose 7z to use a Unicode password.')
        if native == 'zip' and options.get('encryption') != 'ZipCrypto' and len(options['password']) > 99:
            raise ArchiveError('The pinned 7-Zip engine supports at most 99 characters for ZIP AES passwords. Choose 7z for a longer password.')
        args += ['-p']  # Secret supplied over an inherited anonymous descriptor, never argv.
        if native == '7z': args += ['-mhe='+('on' if options.get('encrypt_names', True) else 'off')]
        else: args += ['-mem='+('ZipCrypto' if options.get('encryption') == 'ZipCrypto' else 'AES256')]
    volume = str(options.get('volume', '')).strip()
    if volume:
        if not re.fullmatch(r'[1-9][0-9]*[bkmgt]?', volume, re.I):
            raise ArchiveError('Volume size must be a number with an optional B, K, M or G suffix.')
        args += ['-v'+volume]
    if options.get('symlinks', True): args += ['-snl']
    return args


class Control:
    def __init__(self):
        self.cancelled = False
        self.paused = False
        self.process = None
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)

    def check(self):
        with self.condition:
            while self.paused and not self.cancelled: self.condition.wait(.1)
            if self.cancelled: raise Cancelled()

    def request(self, action):
        with self.condition:
            if action == 'cancel': self.cancelled = True; self.paused = False
            elif action == 'suspend': self.paused = True
            elif action == 'resume': self.paused = False
            process = self.process
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGCONT if action in ('cancel', 'resume') else signal.SIGSTOP)
                    if action == 'cancel': os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError: pass
            self.condition.notify_all()


@dataclass
class Result:
    code: int
    output: str
    errors: list


class Runner:
    def __init__(self, control=None, emit=lambda event: None):
        self.control = control or Control()
        self.emit = emit
        self.executable = binary()

    def run(self, arguments, cwd=None, password=None, entry=None):
        self.control.check()
        incoming, outgoing = os.pipe2(os.O_CLOEXEC)
        secret = None
        process = None
        env = dict(os.environ, LC_ALL='C.UTF-8', FUSION_7ZIP_EVENT_FD=str(outgoing))
        env.pop('FUSION_7ZIP_PASSWORD_FD', None)
        inherited = [outgoing]
        if password is not None:
            if '\x00' in password: raise ArchiveError('A password cannot contain a NUL character.')
            secret = os.memfd_create('fusion-archive-secret', os.MFD_CLOEXEC)
            os.write(secret, password.encode('utf-8')); os.lseek(secret, 0, os.SEEK_SET)
            inherited.append(secret); env['FUSION_7ZIP_PASSWORD_FD'] = str(secret)
        errors, needs_password = [], False
        pending = b''
        try:
            with tempfile.TemporaryFile() as log, selectors.DefaultSelector() as selector:
                # File-manager selections are literal paths, including Unix
                # names containing * or ?. Apply this once for every command.
                process = subprocess.Popen([str(self.executable), '-spd', '-bsp1', '-bso0', '-bse2', '-sccUTF-8', '-scsUTF-8', *arguments],
                    cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    pass_fds=tuple(inherited), start_new_session=True)
                os.close(outgoing); outgoing = None
                if secret is not None: os.close(secret); secret = None
                with self.control.lock: self.control.process = process
                if self.control.paused: self.control.request('suspend')
                os.set_blocking(incoming, False); selector.register(incoming, selectors.EVENT_READ)
                cancelling = None
                while selector.get_map() or process.poll() is None:
                    if self.control.cancelled:
                        if cancelling is None: cancelling = time.monotonic(); self.control.request('cancel')
                        if time.monotonic()-cancelling > 3 and process.poll() is None: process.kill()
                    for key, _ in selector.select(.1):
                        chunk = os.read(key.fd, 262144)
                        if not chunk: selector.unregister(key.fd); continue
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            event = json.loads(line)
                            if event['event'] == 'entry':
                                if entry: entry(event)
                            elif event['event'] == 'password': needs_password = True
                            elif event['event'] == 'error': errors.append(event); self.emit(event)
                            else: self.emit(event)
                code = process.wait()
                log.seek(0, os.SEEK_END); end = log.tell(); log.seek(max(0, end-65536))
                output = log.read().decode('utf-8', errors='replace')
            self.control.check()
            if needs_password: raise PasswordRequired('Enter the archive password.')
            return Result(code, output, errors)
        finally:
            if process and process.poll() is None:
                process.kill(); process.wait()
            with self.control.lock: self.control.process = None
            os.close(incoming)
            if outgoing is not None: os.close(outgoing)
            if secret is not None: os.close(secret)


def safe_member(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ArchiveError('The archive contains an invalid member name.')
    normalized = value.replace('\\', '/')
    if normalized.startswith('/') or re.match(r'^[a-zA-Z]:', normalized):
        raise ArchiveError('The archive contains an absolute path: '+value)
    parts = PurePosixPath(normalized).parts
    if '..' in parts: raise ArchiveError('The archive contains a path outside its destination: '+value)
    return str(PurePosixPath(normalized))


class Index:
    """Disk-backed member index; archives with many entries don't fill RAM."""
    def __init__(self, path):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY, path TEXT, directory INTEGER, size INTEGER, packed INTEGER, data TEXT)')
        self.db.execute('CREATE INDEX IF NOT EXISTS member_path ON members(path)')

    def add(self, event):
        self.db.execute('INSERT INTO members(path,directory,size,packed,data) VALUES(?,?,?,?,?)',
            (event['path'], bool(event['directory']), event['size'], event['packed'], json.dumps(event)))

    def validate(self):
        self.db.commit()
        links = set()
        for (data,) in self.db.execute('SELECT data FROM members'):
            item = json.loads(data); path = safe_member(item['path'])
            for key in ('symlink', 'hardlink'):
                target = item.get(key)
                if target:
                    if '\x00' in target or target.startswith(('/', '\\')) or re.match(r'^[a-zA-Z]:', target):
                        raise ArchiveError('Archive link points outside the destination: '+item['path'])
                    base = PurePosixPath(path).parent if key == 'symlink' else PurePosixPath('.')
                    normalized = os.path.normpath(str(base/target.replace('\\', '/')))
                    safe_member(normalized); links.add(path)
            mode = item.get('mode') or 0
            if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                raise ArchiveError('This archive contains a device or runtime endpoint: '+item['path'])
        for (path,) in self.db.execute('SELECT path FROM members'):
            if any(str(parent) in links for parent in PurePosixPath(safe_member(path)).parents):
                raise ArchiveError('Archive entries descend through a link: '+path)

    def close(self): self.db.close()


def list_archive(runner, archive, database, password=None):
    index = Index(database)
    try:
        result = runner.run(['l', '-slt', '--', str(archive)], password=password, entry=index.add)
        index.db.commit()
        if result.code: raise ArchiveError(result.output.strip() or 'The archive could not be opened.')
        return index
    except BaseException:
        index.close(); raise
