#!/usr/bin/env python3
"""Own a display preview outside the GUI; timeout/parent EOF always reverts it."""
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import socket
import sys
import time

import desktop_settings as settings


def emit(event, **values):
    try: print(json.dumps({'event': event, **values}), flush=True)
    except BrokenPipeError: pass


def decide(stream, session, seconds):
    deadline = time.monotonic()+seconds
    while (remaining := deadline-time.monotonic()) > 0:
        readable, _, _ = select.select([stream, session], [], [], remaining)
        if session in readable and not session.recv(65536): return 'session-ended'
        if stream in readable:
            line = stream.readline()
            if not line: return 'revert'
            return 'keep' if line.strip() == 'keep' else 'revert'
    return 'timeout'


def trial(request, stream, session, emit=emit, seconds=20):
    store = settings.Store('displays')
    old, token = store.load()
    if token != request['token']: raise ValueError('Display configuration changed. Reload the page.')
    before = settings.display_models(settings.monitors())
    if settings.layout_state(before) != request['baseline']:
        raise ValueError('Displays changed while you were editing. Reload the page before applying.')
    draft = request['models']
    settings.validate_displays(draft, before)
    content = settings.display_config(draft, old)
    store.check(content, token)
    changed = False
    kept = False
    session_ended = False
    try:
        changed = True
        settings.apply_runtime(draft)
        deadline = time.monotonic()+4
        while not settings.matches_layout(draft, settings.display_models(settings.monitors())):
            if time.monotonic() >= deadline:
                raise ValueError('The display driver did not accept this mode or scale. Previous settings restored.')
            time.sleep(.15)
        emit('preview', seconds=seconds)
        action = decide(stream, session, seconds)
        if action == 'session-ended': session_ended = True; return
        if action == 'keep':
            if not settings.matches_layout(draft, settings.display_models(settings.monitors())):
                raise ValueError('Display layout changed during the preview. Nothing was saved.')
            store.save(content, token)
            kept = True
            emit('kept')
        else:
            settings.apply_runtime(before)
            changed = False
            emit('reverted', reason='Timed out' if action == 'timeout' else 'Previous display settings restored')
    finally:
        if changed and not kept and not session_ended:
            settings.apply_runtime(before)


def main():
    sig = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not sig: raise ValueError('Display changes require the active Hyprland session.')
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/sig
    with (runtime/'display-preview.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another display preview is already running.')
        with socket.socket(socket.AF_UNIX) as session:
            session.connect(str(runtime/'.socket2.sock'))
            # SIGTERM is treated like a cancelled preview, so finally can restore.
            signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Preview cancelled')))
            request = json.loads(sys.stdin.readline())
            trial(request, sys.stdin, session)


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        emit('error', message=str(exc)); raise SystemExit(1)
