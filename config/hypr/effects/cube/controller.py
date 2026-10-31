#!/usr/bin/env python3
"""Transactional, profile-local Desktop Cube settings and session plugin activation."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import signal
import socket
import sys
import tempfile
import threading

if __package__:
    from . import model, build
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from effects.cube import model, build


def hypr(*args):
    result = subprocess.run(['hyprctl',*args],capture_output=True,text=True,timeout=15)
    if result.returncode or result.stdout.strip().lower().startswith(('error','invalid','couldn\'t','failed')):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Hyprland is unavailable.')
    return result.stdout.strip()


def instance_dir():
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')
    runtime = os.environ.get('XDG_RUNTIME_DIR','')
    if not signature or not runtime or '/' in signature:
        raise RuntimeError('Open these controls inside the Hyprland session.')
    path = Path(runtime)/'hypr'/signature
    if not (path/'.socket.sock').is_socket():
        raise RuntimeError('The Hyprland session has ended.')
    return path


def atomic(path, content):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def activate(values, target=None, previews=False):
    if values['enabled']:model.prepare_images(values)
    state = instance_dir()/'xetal-cube.json'
    loaded = any(p.get('name') == 'Xetal Desktop Cube' for p in json.loads(hypr('-j','plugin','list')))
    if loaded:
        # Finish any gesture before swapping saved settings and artwork.
        hypr('dispatch','xetalcube:reload')
    elif values['enabled'] or previews:
        current = json.loads(hypr('-j','version'))
        if current.get('commit') != build.SUPPORTED_COMMIT:
            raise RuntimeError('Desktop Cube needs the supported Hyprland 0.56.2 session. Ordinary workspace switching remains available.')
        target = target or build.build()
        answer = hypr('plugin','load',str(target))
        if answer != 'ok':
            raise RuntimeError('Desktop Cube could not be loaded: '+answer)
        atomic(state,json.dumps({'path':str(target)}).encode())
    if values['enabled'] or loaded or previews:
        status = json.loads(hypr('xetal-cube'))
        if status.get('enabled') != values['enabled']:
            raise RuntimeError('The compositor did not accept the Desktop Cube setting.')


def save(values, token, path=model.PATH):
    values = model.validate(values)
    instance_dir()
    target = build.build() if values['enabled'] else None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous, current_token = model.load(path)
        if token != current_token:
            raise ValueError('Desktop Cube settings changed elsewhere. Reload before applying.')
        old_bytes = path.read_bytes() if path.exists() else None
        atomic(path,model.encode(values).encode())
        try:
            activate(values,target)
        except Exception:
            if old_bytes is None: path.unlink(missing_ok=True)
            else: atomic(path,old_bytes)
            try: activate(previous)
            except Exception: pass
            raise
    return model.load(path)


def start():
    from cursors.controller import prepare
    try: prepare()
    except (OSError,subprocess.SubprocessError) as error:
        print('Cursor artwork: '+str(error),file=sys.stderr)
    values, _ = model.load()
    # The same native adapter wakes inactive-workspace windows while their
    # task-switcher thumbnails are captured. Loading it does not enable Cube.
    activate(values, previews=True)


def session():
    # Remain owned by session.sh until the compositor ends; never leave a
    # stale short-lived PID in its child list. No services or shared env writes.
    def stop(*_):raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.connect(str(instance_dir()/'.socket2.sock'))
        def watch():
            try:
                while connection.recv(65536):pass
            finally:os.kill(os.getpid(),signal.SIGTERM)
        watcher=threading.Thread(target=watch,daemon=True);watcher.start()
        try:start()
        except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as error:
            print('Desktop Cube: '+str(error),file=sys.stderr,flush=True)
        watcher.join()


if __name__ == '__main__':
    try:
        session() if '--session' in sys.argv else start()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print('Desktop Cube: '+str(error),file=sys.stderr);sys.exit(1)
