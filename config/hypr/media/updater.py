"""Atomically update a private official yt-dlp copy; never modify system packages."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.request import Request, urlopen
import backend

API = 'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'
RELEASES = 'https://github.com/yt-dlp/yt-dlp/releases/download/'
MAX_BINARY = 40*1024*1024


def response(url, opener=urlopen):
    return opener(Request(url, headers={'User-Agent': 'Xetal-Media', 'Accept': 'application/vnd.github+json' if url == API else '*/*'}), timeout=15)


def read(url, limit, opener=urlopen):
    with response(url, opener) as stream:
        data = stream.read(limit+1)
    if len(data) > limit:
        raise ValueError('The update response exceeded its size limit.')
    return data


def date_version(value):
    match = re.match(r'^(\d{4}\.\d{2}\.\d{2}(?:\.\d+)*)', value)
    return tuple(map(int, match[1].split('.'))) if match else (0, 0, 0)


def update(emit, private=backend.PRIVATE_TOOL, opener=urlopen, version_reader=backend.version):
    private = Path(private)
    private.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (private.parent/'update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another downloader update is already running.')
        emit({'type': 'log', 'text': 'Checking the latest official yt-dlp release…'})
        release = json.loads(read(API, 2*1024*1024, opener))
        tag = release.get('tag_name', '')
        if not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}(?:\.\d+)?', tag) or release.get('draft') or release.get('prerelease'):
            raise ValueError('GitHub did not return a valid stable yt-dlp release.')
        names = {asset.get('name') for asset in release.get('assets', [])}
        if not {'yt-dlp', 'SHA2-256SUMS'} <= names:
            raise ValueError('The official release is missing its downloader or checksum file.')
        try:
            current = version_reader(backend.tool(private))
        except (ValueError, OSError):
            current = ''
        if current and date_version(current) >= date_version(tag):
            emit({'type': 'success', 'text': 'yt-dlp '+current+' is already up to date.'}); return
        base = RELEASES+tag+'/'
        checksums = read(base+'SHA2-256SUMS', 1024*1024, opener).decode('utf-8')
        match = re.search(r'^([a-fA-F0-9]{64})\s+\*?yt-dlp\s*$', checksums, re.M)
        if not match:
            raise ValueError('The official release has no yt-dlp SHA-256 checksum.')
        fd, temporary = tempfile.mkstemp(prefix='.yt-dlp-', dir=private.parent)
        try:
            digest = hashlib.sha256(); total = 0; last = -1
            with os.fdopen(fd, 'wb') as target, response(base+'yt-dlp', opener) as stream:
                size = int(stream.headers.get('Content-Length', '0'))
                if size > MAX_BINARY:
                    raise ValueError('The downloader update is unexpectedly large.')
                while chunk := stream.read(256*1024):
                    total += len(chunk)
                    if total > MAX_BINARY:
                        raise ValueError('The downloader update exceeded its size limit.')
                    target.write(chunk); digest.update(chunk)
                    percent = min(99, int(total/size*100)) if size else 0
                    if percent != last:
                        emit({'type': 'progress', 'percent': percent if size else None,
                              'text': f'Downloading yt-dlp {tag} · {total/1048576:.1f} MiB'})
                        last = percent
                target.flush(); os.fsync(target.fileno())
            if digest.hexdigest() != match[1].lower():
                raise ValueError('The update checksum did not match. The previous downloader is still installed.')
            emit({'type': 'log', 'text': 'Checksum verified. Checking the new downloader…'})
            if version_reader([sys.executable, temporary]) != tag:
                raise ValueError('The new downloader reported an unexpected version.')
            if private.is_file():
                shutil.copy2(private, private.with_suffix('.previous'))
            os.chmod(temporary, 0o700); os.replace(temporary, private)
        finally:
            Path(temporary).unlink(missing_ok=True)
        emit({'type': 'success', 'text': 'Updated this popup to yt-dlp '+tag+'.'})
