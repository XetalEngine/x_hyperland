#!/usr/bin/env python3
"""One-shot Linux cache reclamation; never signal apps or change swap/settings."""
import fcntl
import json
import os
from pathlib import Path
import select
import sys

MODES = {'normal': 1, 'aggressive': 3}


def memory_snapshot():
    fields = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, _, value = line.partition(':')
        parts = value.split()
        if len(parts) == 2 and parts[1] == 'kB':
            fields[key] = int(parts[0]) * 1024
    total = fields.get('MemTotal', 0)
    if total <= 0 or 'MemAvailable' not in fields:
        raise ValueError('Linux memory statistics are unavailable.')
    bounded = lambda value: max(0, min(total, value))
    return {
        'total': total,
        'available': bounded(fields['MemAvailable']),
        'free': bounded(fields.get('MemFree', 0)),
        # Cached includes tmpfs/shared memory, which drop_caches cannot free.
        'file_cache': bounded(max(0, fields.get('Cached', 0) - fields.get('Shmem', 0))
                              + fields.get('Buffers', 0)),
        'metadata_cache': bounded(fields.get('SReclaimable', 0)),
        'swap_total': max(0, fields.get('SwapTotal', 0)),
        'swap_used': max(0, fields.get('SwapTotal', 0) - fields.get('SwapFree', 0)),
    }


def emit(value):
    print(json.dumps(value), flush=True)


def check_client():
    # Keep the GUI's stdin pipe open until completion. An authentication prompt
    # that outlives the session must not start a cleanup after the panel exits.
    poll = select.poll()
    poll.register(0, select.POLLHUP | select.POLLERR)
    if poll.poll(0):
        raise RuntimeError('Control Panel closed before cleanup completed.')


def apply(mode):
    if mode not in MODES:
        raise ValueError('Choose Normal or Aggressive cleanup.')
    if os.geteuid() != 0:
        raise PermissionError('Administrator authentication is required.')
    # /run is root-owned; serialize manual requests across desktop sessions.
    fd = os.open('/run/xetal-ram-cleaner.lock',
                 os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another RAM cleanup is already running.') from error
        check_client()
        before = memory_snapshot()
        emit({'stage': 'sync'})
        os.sync()
        check_client()
        emit({'stage': 'reclaim'})
        # Fixed kernel endpoint and allowlisted numeric value, with no shell.
        with open('/proc/sys/vm/drop_caches', 'w') as target:
            target.write(str(MODES[mode]) + '\n')
        return {'ok': True, 'mode': mode, 'before': before, 'after': memory_snapshot()}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if args == ['status']:
            emit(memory_snapshot())
        elif len(args) == 2 and args[0] in ('clean', '--apply') and args[1] in MODES:
            if args[0] == 'clean':
                # Exec keeps this exact process owned by QProcess through the
                # authentication step; Python runs without user site imports.
                os.execv('/usr/bin/pkexec', [
                    '/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/python3',
                    '-I', str(Path(__file__).resolve()), '--apply', args[1]])
            else:
                emit(apply(args[1]))
        else:
            raise ValueError('Use status, or clean normal/aggressive.')
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        emit({'error': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
