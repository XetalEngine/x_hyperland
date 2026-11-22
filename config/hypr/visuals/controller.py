"""Transactional visual preferences and a timed, session-only preview lease."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from visuals import model


def atomic(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally: Path(name).unlink(missing_ok=True)


def instance():
    signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE',''); runtime=os.environ.get('XDG_RUNTIME_DIR','')
    if not signature or '/' in signature or not runtime: raise ValueError('Open visual controls inside Hyper Fusion.')
    path=Path(runtime)/'hypr'/signature
    if not (path/'.socket.sock').is_socket(): raise ValueError('The Hyprland session has ended.')
    return path


def ctl(*args):
    proc=subprocess.run([sys.executable,str(ROOT/'compat/bin/hyprctl'),*args],capture_output=True,text=True,timeout=15)
    if proc.returncode: raise ValueError((proc.stderr or proc.stdout).strip() or 'Hyprland did not accept the request.')
    return proc.stdout.strip()


@contextmanager
def lock(root=ROOT):
    path=Path(root)/'visuals';path.mkdir(parents=True,exist_ok=True)
    with (path/'.settings.lock').open('w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX);yield


def runtime_settings(root=ROOT):
    settings=model.load(root)[0]
    try:
        lease=json.loads((instance()/'fusion-visuals/preview.json').read_text())
        if lease['root']==str(Path(root).resolve()) and time.time()<lease['expires']:
            os.kill(lease['pid'],0)
            settings=model.validate(lease['settings'])
    except (OSError,ValueError,KeyError,TypeError): pass
    return model.active_settings(settings)


def quiet_active():
    try:
        state=json.loads((instance()/'fusion-presentation-active').read_text())
        os.kill(state['pid'],0);return True
    except (OSError,ValueError,KeyError,TypeError): return False


def preview_owner(path):
    try:
        value=json.loads(path.read_text())
        if value['expires']<=time.time() or type(value['pid']) is not int or value['pid']<=0:return None
        os.kill(value['pid'],0);return value['pid']
    except (OSError,ValueError,KeyError,TypeError):return None


def verify(settings,root=ROOT):
    from compat.hypr_compat import Renderer
    model.validate(settings)
    if model.EXPERIMENTAL_VISUALS and model.theme_settings(settings,model.theme_name(root))['material']['proportional']:
        monitors=json.loads(ctl('-j','monitors'))
        if any(m.get('transform',0) for m in monitors):
            raise ValueError('Proportional blur is experimental and cannot be enabled with rotated displays.')
    with tempfile.TemporaryDirectory(prefix='fusion-visual-check-') as directory:
        path=Path(directory)/'hyprland.lua'
        path.write_text(Renderer(root,visual_settings=settings).render())
        checked=subprocess.run(['Hyprland','--verify-config','--config',str(path)],capture_output=True,text=True,timeout=25)
        if checked.returncode: raise ValueError('Visual configuration check failed: '+(checked.stderr+checked.stdout)[-3000:])


def reload():
    ctl('reload')
    errors=ctl('configerrors')
    if errors and errors not in ('ok','[]'): raise ValueError('Hyprland configuration: '+errors)


def save(settings,expected,root=ROOT):
    settings=model.validate(settings);verify(settings,root)
    path=Path(root)/'visuals/settings.json'
    with lock(root):
        if model.load(root)[1]!=expected: raise ValueError('Visual preferences changed in another window. Reload before applying.')
        lease=instance()/'fusion-visuals/preview.json'
        if preview_owner(lease) not in (None,os.getpid()):raise ValueError('Another visual preview is open. Finish that preview first.')
        before=path.read_text() if path.exists() else None
        lease.unlink(missing_ok=True)
        atomic(path,json.dumps(settings,indent=2)+'\n')
        try: reload()
        except Exception:
            if before is None:path.unlink(missing_ok=True)
            else:atomic(path,before)
            try:reload()
            except Exception:pass
            raise
    return model.load(root)


def preview(settings,root=ROOT,seconds=20):
    settings=model.validate(settings);verify(settings,root)
    with lock(root):
        path=instance()/'fusion-visuals/preview.json'
        if preview_owner(path) not in (None,os.getpid()):
            raise ValueError('Another visual preview is open. Finish that preview first.')
        token=uuid.uuid4().hex
        atomic(path,json.dumps(dict(token=token,pid=os.getpid(),expires=time.time()+seconds,
                                    root=str(Path(root).resolve()),settings=settings)))
        try:
            # A separate guardian restores saved settings even if this settings window crashes.
            subprocess.Popen([sys.executable,str(ROOT/'visuals/controller.py'),'--expire',token,str(root)],
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            reload()
        except Exception:
            path.unlink(missing_ok=True)
            try:reload()
            except Exception:pass
            raise
    return token


def discard(token,root=ROOT):
    if not token:return
    with lock(root):
        path=instance()/'fusion-visuals/preview.json'
        try: lease=json.loads(path.read_text())
        except (FileNotFoundError,ValueError):return
        if lease.get('token')==token:
            path.unlink();reload()


def expire(token,root):
    while True:
        try:
            lease=json.loads((instance()/'fusion-visuals/preview.json').read_text())
            if lease.get('token')!=token:return
            alive=True
            try:os.kill(lease['pid'],0)
            except ProcessLookupError:alive=False
            if not alive or time.time()>=lease['expires']:discard(token,root);return
        except (OSError,ValueError,KeyError,TypeError):return
        time.sleep(.5)


def guard_quiet(pid):
    """Restore effects if the capture-indicator process is forcibly killed."""
    while True:
        try:
            path=instance()/'fusion-presentation-active'
            state=json.loads(path.read_text())
            if state.get('pid')!=pid:return
            try:os.kill(pid,0)
            except ProcessLookupError:
                path.unlink(missing_ok=True);reload();return
        except (OSError,ValueError):return
        time.sleep(.5)


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--expire':expire(sys.argv[2],Path(sys.argv[3]))
    elif len(sys.argv)==3 and sys.argv[1]=='--guard-quiet':guard_quiet(int(sys.argv[2]))
