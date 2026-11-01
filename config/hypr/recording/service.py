#!/usr/bin/env python3
"""On-demand recording controller, owned by one Hyprland session."""
import argparse
import fcntl
import html
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recording import backend


def instance_dir():
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not runtime or not signature or '/' in signature or signature in ('.', '..'):
        raise RuntimeError('Screen recording requires an active Hyprland session.')
    instance = Path(runtime)/'hypr'/signature
    if not (instance/'.socket2.sock').is_socket():
        raise RuntimeError('The Hyprland session has ended.')
    return instance


def exchange(path, message, timeout):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(json.dumps(message).encode()+b'\n')
        pending = b''
        while b'\n' not in pending:
            chunk = client.recv(65536)
            if not chunk: raise RuntimeError('The recording controller disconnected.')
            pending += chunk
            if len(pending) > 131072: raise RuntimeError('Invalid recording response.')
    result = json.loads(pending.split(b'\n', 1)[0])
    if 'failure' in result: raise RuntimeError(result['failure'])
    return result


def request(action, monitor=None):
    # Capture the pointer now, before daemon startup or encoder discovery.
    if action == 'toggle' and monitor is None:
        try: monitor = backend.pointer_monitor()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError): pass
    path = instance_dir()/'recorder.sock'
    message = dict(action=action, monitor=monitor)
    try: return exchange(path, message, 25 if action == 'toggle' else 2)
    except (FileNotFoundError, ConnectionRefusedError):
        if action != 'toggle': return {'phase': 'idle'}
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    until = time.monotonic()+5
    while time.monotonic() < until:
        try: return exchange(path, message, 25)
        except (FileNotFoundError, ConnectionRefusedError): time.sleep(.05)
    raise RuntimeError('The recording controller could not start.')


def elapsed(state):
    seconds = max(0, int(time.time()-state.get('started', time.time())))
    return f'{seconds//60:02d}:{seconds%60:02d}'


def bar_status(state):
    phase = state.get('phase', 'idle')
    text = {'starting': '● Starting…', 'recording': '● REC '+elapsed(state),
            'stopping': '● Stopping…', 'saving': '● Saving…', 'error': '● Recording error'}.get(phase, '')
    details = state.get('error') if phase == 'error' else (
        f"{state.get('monitor', '')} · {state.get('fps', 64)} FPS · {state.get('audio', 'desktop')} audio\n"
        'Click or Alt + F9: stop and save\nRight-click: recording settings')
    return {'text': text, 'class': phase, 'tooltip': html.escape(details or '')}


def dispatch(recorder, message):
    action = message.get('action')
    if action == 'toggle':
        if recorder.state['phase'] in ('starting', 'recording'):
            recorder.stop()
        elif recorder.busy:
            raise RuntimeError('The previous recording is still being saved.')
        else:
            monitor = message.get('monitor')
            if not isinstance(monitor, str) or not monitor:
                raise RuntimeError('Could not find the display under the pointer.')
            recorder.start(monitor, backend.load()[0])
    elif action == 'stop': recorder.stop()
    elif action != 'status': raise ValueError('Unknown recording action.')
    return recorder.state


def serve():
    instance = instance_dir()
    path = instance/'recorder.sock'
    with (instance/'recorder.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        recorder = backend.Recorder()
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(number, stop)
        with socket.socket(socket.AF_UNIX) as events, socket.socket(socket.AF_UNIX) as server:
            events.connect(str(instance/'.socket2.sock'))
            path.unlink(missing_ok=True)
            server.bind(str(path)); path.chmod(0o600); server.listen(8)
            pending = b''
            try:
                while not stopping:
                    readable = select.select([events, server], [], [], .15)[0]
                    if events in readable:
                        chunk = events.recv(65536)
                        if not chunk: break
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            event = line.decode(errors='replace')
                            if event.startswith(('monitorremoved>>', 'monitorremovedv2>>')):
                                if recorder.state.get('monitor') in event.split('>>', 1)[1].split(','):
                                    recorder.stop('The recorded display disconnected.')
                    if server in readable:
                        with server.accept()[0] as client:
                            client.settimeout(1)
                            if struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1] != os.getuid(): continue
                            try:
                                data = b''
                                while b'\n' not in data and len(data) < 4096:
                                    chunk = client.recv(4096)
                                    if not chunk: break
                                    data += chunk
                                message = json.loads(data.split(b'\n', 1)[0])
                                if not isinstance(message, dict): raise ValueError('Invalid recording request.')
                                response = dispatch(recorder, message)
                            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                                response = {'failure': str(error)}
                            try: client.sendall(json.dumps(response).encode()+b'\n')
                            except OSError: pass  # A closed settings page does not stop recording.
                    try: recorder.tick()
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                        recorder.abort(str(error))
            finally:
                recorder.shutdown()
                path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Hyper Fusion screen recorder')
    group = parser.add_mutually_exclusive_group(required=True)
    for option in ('toggle', 'stop', 'status', 'bar', 'serve'): group.add_argument('--'+option, action='store_true')
    args = parser.parse_args()
    try:
        if args.serve: serve(); return 0
        state = request('toggle' if args.toggle else 'stop' if args.stop else 'status')
        print(json.dumps(bar_status(state) if args.bar else state))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        if args.bar: print(json.dumps({'text': ''})); return 0
        if args.toggle or args.stop: backend.notify('Screen recording', str(error))
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
