#!/usr/bin/env python3
"""Transactional, profile-local Window Close settings and session plugin activation."""
import fcntl
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if __package__:
    from . import model, build, rules
else:
    import model, build, rules


def hypr(*args, timeout=15):
    result = subprocess.run(['hyprctl',*args],capture_output=True,text=True,timeout=timeout)
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
    state = instance_dir()/'xetal-windowclose.json'
    loaded = any(p.get('name') == 'Xetal Window Close' for p in json.loads(hypr('-j','plugin','list')))
    if loaded:
        # Disabling hides the button immediately without changing any windows.
        hypr('dispatch','xetalwindowclose:reload')
    else:
        if not values['enabled']:
            from workspaces import model as workspace_model
            workspaces, _ = workspace_model.load()
            if not any(p['controls']=='on' or p['layout']=='kde' for p in workspaces['workspaces'].values()): return
        current = json.loads(hypr('-j','version'))
        if current.get('commit') != build.SUPPORTED_COMMIT:
            raise RuntimeError('Window Close needs the supported Hyprland 0.56.2 session. The windowclose handler needs an updated adapter.')
        target = target or build.build()
        answer = hypr('plugin','load',str(target))
        if answer != 'ok':
            raise RuntimeError('Window Close could not be loaded: '+answer)
        atomic(state,json.dumps({'path':str(target)}).encode())
    status = json.loads(hypr('xetal-windowclose'))
    if status.get('enabled') != values['enabled']:
        raise RuntimeError('The compositor did not accept the Window Close setting.')


def save(values, token, path=model.PATH):
    values = model.validate(values)
    instance_dir()
    target = build.build() if values['enabled'] else None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous, current_token = model.load(path)
        if token != current_token:
            raise ValueError('Window Close settings changed elsewhere. Reload before applying.')
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
    values, _ = model.load()
    activate(values)


def window_info(window_id):
    if not str(window_id).isascii() or not str(window_id).isdecimal():
        raise ValueError('Invalid window identity.')
    result = json.loads(hypr('xetal-windowbuttons',str(window_id)))
    if result.get('error'): raise ValueError(result['error'])
    return result


def rule_file(scope, profile='standard'):
    if profile not in ('standard', 'kde'): raise ValueError('Unknown window controls profile.')
    if scope == 'app': return rules.PATH.with_name('kde-rules.json') if profile=='kde' else rules.PATH, 'apps'
    if scope == 'window': return instance_dir()/('xetal-windowbuttons-kde-rules.json' if profile=='kde' else 'xetal-windowbuttons-rules.json'), 'windows'
    raise ValueError('Choose this window or this application.')


def save_rule(window_id, scope, rule, token, window_token=None, *, profile='standard'):
    """Save a choice; app-editor saves may also clear this window's override.

    Both files are checked, locked and rolled back together. Other windows'
    explicit overrides remain independent of the application choice.
    """
    info = window_info(window_id)
    if info.get('control_profile', 'standard') != profile:
        raise ValueError('The workspace mode changed. Reload the editor before applying.')
    if info.get('workspace_controls', 'individual') != 'individual':
        raise ValueError('Workspace controls changed. Reload the editor before applying.')
    path, section = rule_file(scope, profile) if profile!='standard' else rule_file(scope)
    key = info['app'] if scope == 'app' else str(window_id)
    if not key: raise ValueError('This window has no application identity. Use a window-specific choice.')
    if rule is not None:
        rule = rules.validate(rule)
        if rule['mode']=='auto' and profile!='kde': raise ValueError('Automatic controls are available in KDE mode.')
        if 'titlebar' in rule:
            if profile!='kde': raise ValueError('The extra title bar is available only in KDE mode.')
            if not info.get('kde_titlebar_supported'):
                raise ValueError('Log out and back in to load the updated KDE title bar adapter.')
    changes = [(path,section,key,rule,token)]
    if scope == 'app' and window_token is not None:
        window_path,window_section = rule_file('window',profile) if profile!='standard' else rule_file('window')
        changes.append((window_path,window_section,str(window_id),None,window_token))
    with ExitStack() as stack:
        for target in sorted({change[0] for change in changes}):
            target.parent.mkdir(parents=True,exist_ok=True)
            lock=stack.enter_context(target.with_suffix('.lock').open('w'))
            fcntl.flock(lock,fcntl.LOCK_EX)
        documents=[]
        for target,kind,identity,value,expected in changes:
            document,current=rules.load(target,kind)
            if current != expected: raise ValueError('These choices changed elsewhere. Reload before applying.')
            old=target.read_bytes() if target.exists() else None
            if value is None: document[kind].pop(identity,None)
            else: document[kind][identity]=value
            if kind == 'windows':
                live=set(json.loads(hypr('xetal-windowbuttons'))['windows'])
                document[kind]={k:v for k,v in document[kind].items() if k in live}
            documents.append((target,kind,document,old))
        # Recheck after acquiring the lock; never apply an address recycled by
        # another window. Stable IDs last for exactly this compositor session.
        latest = window_info(window_id)
        if latest['app'] != info['app']: raise ValueError('The application identity changed. Reopen its settings.')
        if latest.get('control_profile','standard')!=profile or latest.get('workspace_controls','individual')!='individual':
            raise ValueError('The workspace mode changed. Reload the editor before applying.')
        try:
            for target,kind,document,old in documents:
                # Removing a nonexistent override need not create a file.
                if old is not None or document[kind]:atomic(target,rules.encode(document,kind).encode())
            hypr('dispatch','xetalwindowclose:reload')
        except Exception:
            for target,kind,document,old in documents:
                if old is None: target.unlink(missing_ok=True)
                else: atomic(target,old)
            try: hypr('dispatch','xetalwindowclose:reload')
            except Exception: pass
            raise
    return rules.load(path,section)


def preview_payload(window_id, token, rule=None, workspace=None, *, profile='standard'):
    if not str(window_id).isascii() or not str(window_id).isdecimal():
        raise ValueError('Invalid window identity.')
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Invalid preview identity.')
    data=dict(action='end' if rule is None else 'update',id=str(window_id),token=token)
    if profile not in ('standard','kde'): raise ValueError('Unknown window controls profile.')
    if rule is not None: data['profile']=profile
    if rule is not None:data.update(owner=os.getpid(),rule=rules.validate(rule))
    if workspace is not None:
        from workspaces.model import identity
        data['workspace']=int(identity(workspace))
    return json.dumps(data,separators=(',',':'))


def end_preview(window_id,token):
    hypr('dispatch','xetalwindowclose:preview',preview_payload(window_id,token),timeout=2)


def session():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from effects.session import run
    run('window_close', start)


if __name__ == '__main__':
    try:
        session() if '--session' in sys.argv else start()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print('Window Close: '+str(error),file=sys.stderr);sys.exit(1)
