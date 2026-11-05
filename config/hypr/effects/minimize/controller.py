#!/usr/bin/env python3
"""Transactional, profile-local Minimize settings and session plugin activation."""
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
    import model, build


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


def activate(values, target=None):
    state = instance_dir()/'xetal-minimize.json'
    loaded = next((p for p in json.loads(hypr('-j','plugin','list')) if p.get('name') == 'Xetal Minimize'), None)
    previous_target = loaded_path(state)
    if target is None and (not loaded or loaded.get('version') != '1.3.3'):
        target = build.build()
    replacing = bool(loaded and target and target != previous_target)
    if replacing or not loaded:
        current = json.loads(hypr('-j','version'))
        if current.get('commit') != build.SUPPORTED_COMMIT:
            raise RuntimeError('Minimize needs the supported Hyprland 0.56.2 session. The minimize handler needs an updated adapter.')
    if replacing:
        if previous_target is None or not previous_target.is_file():
            raise RuntimeError('The running minimizer has no recovery path. Start a new Hyprland session to load this update.')
        # Never replace a mapped .so. Unloading restores minimized apps before
        # loading the distinct, content-addressed build.
        hypr('plugin','unload',str(previous_target))
        loaded = None
    if loaded:
        # The compositor restores every minimized window before disabling.
        hypr('dispatch','xetalminimize:reload')
    else:
        target = target or build.build()
        answer = hypr('plugin','load',str(target))
        if answer != 'ok':
            raise RuntimeError('Minimize could not be loaded: '+answer)
        atomic(state,json.dumps({'path':str(target)}).encode())
    status = json.loads(hypr('xetal-minimize'))
    if status.get('enabled') != values['enabled']:
        raise RuntimeError('The compositor did not accept the Minimize setting.')


def loaded_path(state):
    try:
        return Path(json.loads(state.read_text())['path'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save(values, token, path=model.PATH):
    values = model.validate(values)
    previous_target = loaded_path(instance_dir()/'xetal-minimize.json')
    target = build.build() if values['enabled'] else None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous, current_token = model.load(path)
        if token != current_token:
            raise ValueError('Minimize settings changed elsewhere. Reload before applying.')
        old_bytes = path.read_bytes() if path.exists() else None
        atomic(path,model.encode(values).encode())
        try:
            activate(values,target)
        except Exception:
            if old_bytes is None: path.unlink(missing_ok=True)
            else: atomic(path,old_bytes)
            try: activate(previous, previous_target)
            except Exception: pass
            raise
    return model.load(path)


def start():
    values, _ = model.load()
    # Window ordering remains available when the minimize animation is off.
    activate(values)


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
        icons = subprocess.Popen([sys.executable, str(Path(__file__).with_name('icons.py'))],
                                 env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME=''))
        try:
            try:start()
            except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as error:
                print('Minimize: '+str(error),file=sys.stderr,flush=True)
            watcher.join()
        finally:
            icons.terminate()
            try:icons.wait(timeout=3)
            except subprocess.TimeoutExpired:icons.kill(); icons.wait()


if __name__ == '__main__':
    try:
        session() if '--session' in sys.argv else start()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print('Minimize: '+str(error),file=sys.stderr);sys.exit(1)
