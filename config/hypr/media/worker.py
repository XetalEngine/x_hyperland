#!/usr/bin/env python3
"""One owned process group per job, including its ffmpeg children."""
import argparse
import ctypes
import json
import os
import signal
import sys
import backend
import updater


def emit(event):
    print(json.dumps(event, ensure_ascii=True), flush=True)


def own_process_group():
    parent = os.getppid()
    if os.getpgrp() != os.getpid():
        os.setsid()
    def terminate(_signal, _frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.killpg(os.getpgrp(), signal.SIGTERM)
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    # Stop yt-dlp and ffmpeg even if the popup crashes or Wayland disconnects.
    if sys.platform == 'linux':
        libc = ctypes.CDLL(None)
        if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            raise OSError('Cannot attach the download to this desktop session.')
        if os.getppid() != parent or parent == 1:
            terminate(signal.SIGTERM, None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['download', 'update', 'info'])
    parser.add_argument('--format', choices=['mp3', 'mp4'])
    parser.add_argument('--url')
    args = parser.parse_args()
    own_process_group()
    try:
        if args.action == 'download':
            if not args.format or not args.url:
                raise ValueError('Choose a format and a YouTube address.')
            backend.download(args.url, args.format, emit)
        elif args.action == 'update':
            updater.update(emit)
        else:
            emit({'type': 'version', 'text': backend.version(),
                  'source': 'Private copy' if backend.PRIVATE_TOOL.is_file() else 'System package'})
    except Exception as error:
        emit({'type': 'error', 'text': str(error)}); return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
