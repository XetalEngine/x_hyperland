"""Persistent title-bar reachability, independent of theme and button choices."""
import fcntl
import hashlib
import json
from pathlib import Path
from . import controller

PATH=Path(__file__).with_name('behavior-settings.json')


def load(path=None):
    path=Path(path or PATH);raw=path.read_bytes() if path.exists() else b''
    if len(raw)>1024:raise ValueError('Window behavior settings are too large.')
    data=json.loads(raw) if raw else {'titlebar_protection':True}
    if not isinstance(data,dict) or set(data)!={'titlebar_protection'} or type(data['titlebar_protection']) is not bool:
        raise ValueError('Invalid window behavior settings.')
    return data['titlebar_protection'],hashlib.sha256(raw).hexdigest()


def save(enabled,token,path=None):
    if type(enabled) is not bool:raise ValueError('Invalid title-bar protection choice.')
    path=Path(path or PATH);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if load(path)[1]!=token:raise ValueError('Window behavior changed elsewhere. Reload before applying.')
        old=path.read_bytes() if path.exists() else None
        controller.atomic(path,(json.dumps({'titlebar_protection':enabled},indent=2)+'\n').encode())
        try:controller.start()
        except Exception:
            if old is None:path.unlink(missing_ok=True)
            else:controller.atomic(path,old)
            try:controller.start()
            except Exception:pass
            raise
    return load(path)
