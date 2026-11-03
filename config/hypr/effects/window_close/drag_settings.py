"""Profile-local activation thresholds for the invisible floating title grip."""
import fcntl
import hashlib
import json
from pathlib import Path

PATH=Path(__file__).with_name('drag-settings.json')
DEFAULTS=dict(distance=2,hold_ms=120)


def validate(values):
    if not isinstance(values,dict) or set(values)!=set(DEFAULTS):
        raise ValueError('Invalid title-drag settings.')
    for key,low,high in (('distance',1,24),('hold_ms',0,500)):
        if type(values[key]) is not int or not low<=values[key]<=high:
            raise ValueError(f'{key} must be between {low} and {high}.')
    return dict(values)


def load(path=None):
    path=Path(path or PATH);raw=path.read_bytes() if path.exists() else b''
    if len(raw)>4096:raise ValueError('Title-drag settings are too large.')
    return validate(json.loads(raw) if raw else DEFAULTS),hashlib.sha256(raw).hexdigest()


def save(values,token,path=None):
    from .controller import atomic
    path=Path(path or PATH);values=validate(values);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if load(path)[1]!=token:raise ValueError('Drag settings changed elsewhere. Reload before applying.')
        atomic(path,(json.dumps(values,indent=2)+'\n').encode())
    return load(path)
