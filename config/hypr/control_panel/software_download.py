#!/usr/bin/env python3
"""Save a published Xetal artifact, independently of browser MIME handling."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from software_catalog import vendor_release, VENDOR_MANIFESTS


def official_url(url):
    value = urllib.parse.urlsplit(url)
    return value.scheme == 'https' and value.hostname == 'www.xetal.net' and not value.username and not value.password and value.port in (None,443)


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        if not official_url(url):
            raise ValueError('The download redirected away from the official Xetal host.')
        return super().redirect_request(request, fp, code, message, headers, url)


def open_download(request, timeout):
    return urllib.request.build_opener(OfficialRedirect).open(request, timeout=timeout)


def emit(value):
    print(json.dumps(value), flush=True)


def download(artifact, destination, *, opener=open_download, progress=lambda *_: None):
    if not official_url(artifact['url']):
        raise ValueError('The download is not from the official Xetal host.')
    size = artifact['size']; expected = artifact['sha256'].lower()
    if type(size) is not int or not 0 < size <= 8 * 1024**3 or not re.fullmatch('[0-9a-f]{64}',expected):
        raise ValueError('Invalid download size or checksum.')
    destination = Path(destination).absolute()
    if not destination.parent.is_dir() or destination.is_dir() or destination.is_symlink():
        raise ValueError('Choose a regular file in an existing download folder.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.'+destination.name+'-', suffix='.part',
                                         dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            request = urllib.request.Request(artifact['url'], headers={
                'User-Agent': 'HyperFusion-Software/1', 'Accept': 'application/octet-stream'})
            with opener(request, timeout=30) as response:
                if not official_url(response.geturl()):
                    raise ValueError('The download redirected away from the official Xetal host.')
                checksum = hashlib.sha256(); received = 0; last = 0
                progress(0, size)
                while chunk := response.read(256 * 1024):
                    received += len(chunk)
                    if received > size:
                        raise RuntimeError('The download is larger than its published size. Please refresh the release.')
                    output.write(chunk); checksum.update(chunk)
                    now = time.monotonic()
                    if now-last >= .15:
                        progress(received, size); last = now
                if received != size or checksum.hexdigest() != expected:
                    raise RuntimeError('Download verification failed. The incomplete file was discarded; please retry.')
            output.flush(); os.fsync(output.fileno())
        # Commit only verified bytes. A failed/cancelled download preserves an
        # existing destination and never changes permissions to executable.
        os.replace(temporary, destination)
        progress(received, size)
        return destination
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, choices=tuple(VENDOR_MANIFESTS))
    parser.add_argument('--filename', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    def cancel(*_): raise InterruptedError('Download cancelled.')
    signal.signal(signal.SIGTERM, cancel)
    try:
        release = vendor_release(args.vendor)
        artifact = next((a for a in release['choices'] if a['filename'] == args.filename), None)
        if artifact is None:
            raise RuntimeError('This release changed. Close downloads and check the latest version again.')
        result = download(artifact, args.output,
                          progress=lambda current,total: emit(dict(type='progress', current=current, total=total)))
        emit(dict(type='downloaded', path=str(result)))
        return 0
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as error:
        emit(dict(type='error', message=str(error) or 'Download cancelled.'))
        return 1


if __name__ == '__main__': sys.exit(main())
