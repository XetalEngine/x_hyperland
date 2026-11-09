#!/usr/bin/env python3
"""Opt-in real UID/cross-filesystem test; root touches only disposable fixtures.

Run with sudo -n env FUSION_TRANSFER_PRIVILEGED_TEST=1 python3 <this file>.
The controller supplies an already-authorized helper instead of interacting
with the desktop's actual PolicyKit prompt. No authorization policy is changed.
"""
import json
import os
from pathlib import Path
import pwd
import selectors
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent


def exercise(request, uid, gid, groups, before_auth=None):
    process = subprocess.Popen(['/usr/bin/python3', '-I', str(ROOT/'transfer_worker.py')],
                               user=uid, group=gid, extra_groups=groups,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdin.write((json.dumps(request)+'\n').encode()); process.stdin.flush()
    authorizations, helpers, result = 0, [], None
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    pending = bytearray(); deadline = time.monotonic()+20
    try:
        while process.poll() is None or selector.select(0):
            if time.monotonic() > deadline: raise RuntimeError('Fixture transfer timed out.')
            if not selector.select(.2): continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk: break
            pending.extend(chunk)
            while b'\n' in pending:
                line, _, rest = pending.partition(b'\n'); pending = bytearray(rest)
                value = json.loads(line)
                if value['event'] == 'authenticate':
                    authorizations += 1
                    if before_auth: before_auth()
                    helper = subprocess.Popen(['/usr/bin/python3', '-I', str(ROOT/'transfer_authority.py')],
                                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              env=dict(os.environ, PKEXEC_UID=str(uid)))
                    helper.stdin.write(json.dumps(value).encode()); helper.stdin.close(); helpers.append(helper)
                elif value['event'] == 'question':
                    raise AssertionError('No conflicts are expected in this fixture.')
                elif value['event'] == 'result': result = value
        process.wait(timeout=3)
        assert process.returncode == 0 and result and result.get('ok'), (result, process.stderr.read().decode())
        for helper in helpers:
            assert helper.wait(timeout=3) == 0, helper.stderr.read().decode()
        return authorizations
    finally:
        selector.close()
        if process.poll() is None: process.kill(); process.wait()
        for helper in helpers:
            if helper.poll() is None: helper.kill(); helper.wait()


def main():
    if os.geteuid() != 0 or os.environ.get('FUSION_TRANSFER_PRIVILEGED_TEST') != '1':
        raise SystemExit('This test requires explicit root-fixture opt-in.')
    account = pwd.getpwnam(os.environ.get('SUDO_USER', 'nobody'))
    uid, gid = account.pw_uid, account.pw_gid
    assert uid > 0
    groups = os.getgrouplist(account.pw_name, gid)
    with tempfile.TemporaryDirectory(prefix='fusion-authority-fixture-') as raw:
        base = Path(raw); os.chown(base, uid, gid)
        target = base/'target'; target.mkdir(); os.chown(target, uid, gid)
        first = base/'first'; first.write_bytes(b'copied before authentication'); os.chown(first, uid, gid)
        sources = [first]
        for name in ('private-a', 'private-b'):
            directory = base/name; directory.mkdir(mode=0o700)
            item = directory/'secret'; item.write_bytes(name.encode()); item.chmod(0o600)
            sources.append(directory)
        request = dict(operation='copy', sources=list(map(str, sources)), destination=str(target), journal=str(base/'copy.sqlite'))
        calls = exercise(request, uid, gid, groups,
                         lambda: (target/'first').read_bytes() == b'copied before authentication' or (_ for _ in ()).throw(AssertionError('Copy did not start before authentication')))
        assert calls == 1, calls
        for path in sources[1:]:
            copied = target/path.name/'secret'
            assert copied.read_bytes() == path.name.encode() and copied.stat().st_uid == uid
            assert (path/'secret').exists()
        print('Protected-source copy: started before authentication, one helper for both protected folders, user-owned copies, helper exited.')
        # A genuinely different filesystem, not a mocked EXDEV.
        with tempfile.TemporaryDirectory(prefix='fusion-cross-device-', dir='/dev/shm') as ram:
            destination = Path(ram); os.chown(destination, uid, gid)
            assert destination.stat().st_dev != base.stat().st_dev
            source = base/'move'; source.mkdir(); os.chown(source, uid, gid)
            for name in ('one', 'two'):
                file = source/name; file.write_bytes(name.encode()*8192); os.chown(file, uid, gid)
            request = dict(operation='move', sources=[str(source)], destination=ram, journal=str(base/'move.sqlite'))
            assert exercise(request, uid, gid, groups) == 0
            assert not source.exists()
            for name in ('one', 'two'): assert (destination/'move'/name).read_bytes() == name.encode()*8192
            print('Real cross-filesystem move: complete data verified, originals removed, no authentication needed.')


if __name__ == '__main__': main()
