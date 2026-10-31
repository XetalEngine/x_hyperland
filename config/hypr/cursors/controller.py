"""Apply through the session adapter, which never synchronizes shared GSettings."""
import fcntl
import os
import subprocess
import sys
from . import model
from effects.cube import controller as cube


def prepare():
    subprocess.run([sys.executable,str(model.PATH.with_name('build.py'))],
                   env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,check=True,timeout=120)


def apply():
    cube.hypr('dispatch','xetalcube:cursor')


def save(values,token,path=model.PATH):
    values=model.validate(values);prepare();cube.instance_dir()
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous,current=model.load(path)
        if current!=token:raise ValueError('Cursor settings changed elsewhere. Reload before applying.')
        cube.atomic(path,model.encode(values))
        try:apply()
        except Exception:
            cube.atomic(path,model.encode(previous))
            try:apply()
            except Exception:pass
            raise
    return model.load(path)
