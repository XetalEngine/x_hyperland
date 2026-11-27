"""Verified avatar assets and narrowly scoped account-picture updates."""
from __future__ import annotations
import configparser
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile

ASSETS = Path(__file__).with_name('assets')

def icons():
    return json.loads((ASSETS/'icons.json').read_text())['icons']

def selected(key):
    for item in icons():
        if item['id']==key: return item
    raise ValueError('Choose a picture from the account gallery.')

def verify(key):
    item=selected(key); name=item['file']
    if not re.fullmatch(r'[a-z0-9-]+\.(png|gif)',name):
        raise ValueError('Invalid account-picture filename.')
    path=ASSETS/name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise ValueError('This account picture is damaged. Please choose another.')
    return path

def atomic(path, data, mode=0o644, owner=None):
    path=Path(path)
    if path.is_symlink(): raise ValueError('Account-picture files cannot be symbolic links.')
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix='.avatar-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.fchmod(stream.fileno(),mode)
            if owner is not None: os.fchown(stream.fileno(),*owner)
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)

@contextmanager
def account_access(account, enabled):
    """Even an authenticated helper writes home files with that user's access."""
    elevated=enabled and os.geteuid()==0 and account.pw_uid!=0
    if not elevated:
        yield;return
    previous_gid=os.getegid();previous_groups=os.getgroups()
    try:
        os.setgroups([account.pw_gid]);os.setegid(account.pw_gid);os.seteuid(account.pw_uid)
        yield
    finally:
        os.seteuid(0);os.setegid(previous_gid);os.setgroups(previous_groups)

def update(account, key, *, root=Path('/'), administrator=False, caller_uid=None):
    """Update one account, preserving other theme and AccountsService settings.

    Tests pass a disposable root and passwd record. Ordinary callers may update
    only their own home; system account metadata is written only after elevation.
    No groups, passwords, login shell, or other account identity is changed.
    """
    if caller_uid is None: caller_uid=os.getuid()
    if not administrator and account.pw_uid!=caller_uid:
        raise PermissionError('Administrator authentication is required for another account.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*\$?',account.pw_name):
        raise ValueError('Invalid account name.')
    source=verify(key); data=source.read_bytes(); root=Path(root).resolve()
    if not Path(account.pw_dir).is_absolute() or '..' in Path(account.pw_dir).parts:
        raise ValueError('Invalid account home.')
    home=root/account.pw_dir.lstrip('/')
    if home.is_symlink() or not home.resolve().is_relative_to(root):
        raise ValueError('The account home must stay inside the system.')
    theme=home/'.config/hypr/theme'; state=theme/'state.json'
    updates=[(home/'.face',data,0o644),(home/'.face.icon',data,0o644)]
    if theme.is_dir():
        current=json.loads(state.read_text()) if state.exists() else {}
        if not isinstance(current,dict): raise ValueError('The saved desktop theme is invalid.')
        relative='state/account-avatar'+source.suffix
        current['avatar']=relative
        updates.insert(0,(theme/relative,data,0o644))
        updates.append((state,(json.dumps(current,indent=2)+'\n').encode(),0o644))
    for path,_,_ in updates:
        if path.is_symlink() or not path.resolve().is_relative_to(home.resolve()):
            raise ValueError('An account-picture destination leaves the account home.')
    if administrator:
        icon=root/'var/lib/AccountsService/icons'/account.pw_name
        config=root/'var/lib/AccountsService/users'/account.pw_name
        settings=configparser.ConfigParser(interpolation=None);settings.optionxform=str
        if config.exists(): settings.read(config)
        if not settings.has_section('User'):settings.add_section('User')
        settings['User']['Icon']='/var/lib/AccountsService/icons/'+account.pw_name
        stream=io.StringIO();settings.write(stream,space_around_delimiters=False)
        updates += [(icon,data,0o644),(config,stream.getvalue().encode(),0o600)]
    for path,_,_ in updates:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('An account-picture destination is a symbolic link.')
    originals={path:(path.read_bytes(),path.stat().st_mode&0o777,path.stat().st_uid,path.stat().st_gid)
               if path.exists() else None for path,_,_ in updates}
    written=[]
    try:
        for path,content,mode in updates:
            with account_access(account,administrator and path.is_relative_to(home)):
                atomic(path,content,mode)
            written.append(path)
    except Exception:
        for path in reversed(written):
            before=originals[path]
            with account_access(account,administrator and path.is_relative_to(home)):
                if before is None:path.unlink(missing_ok=True)
                else:atomic(path,before[0],before[1],before[2:] if os.geteuid()==0 else None)
        raise
    return {'ok':True,'message':'Account picture updated for '+account.pw_name+'.',
            'picture':str(source),'animated':source.suffix=='.gif'}

def main(args):
    if len(args)!=3 or args[0] not in ('apply','--apply'):
        raise ValueError('Use apply USER PICTURE.')
    action,username,key=args
    account=pwd.getpwnam(username);verify(key)
    if account.pw_uid!=os.getuid() and os.geteuid()!=0:
        os.execv('/usr/bin/pkexec',['/usr/bin/pkexec','--disable-internal-agent',
            '/usr/bin/python3','-I',str(Path(__file__).resolve()),'--apply',username,key])
    if action=='--apply' and os.geteuid()!=0:
        raise PermissionError('Administrator authentication was not completed.')
    result=update(account,key,administrator=os.geteuid()==0)
    if os.geteuid()!=0:
        # AccountsService owns the sign-in copy. Self-service changes use its
        # normal authorization policy; no shell, terminal, or settings app opens.
        try:
            call=subprocess.run(['/usr/bin/busctl','--system','--allow-interactive-authorization=yes',
                'call','org.freedesktop.Accounts',f'/org/freedesktop/Accounts/User{account.pw_uid}',
                'org.freedesktop.Accounts.User','SetIconFile','s',str(Path(account.pw_dir)/'.face')],
                capture_output=True,text=True,timeout=90)
            if call.returncode and not any(value in call.stderr for value in
                    ('not provided by any .service','not activatable','No such file or directory','not found')):
                result['message']+=' The sign-in service could not update its copy; your desktop picture was saved.'
        except (OSError,subprocess.TimeoutExpired):
            result['message']+=' Your desktop picture was saved; the sign-in service is unavailable.'
    return result

if __name__=='__main__':
    import sys
    try:print(json.dumps(main(sys.argv[1:])),flush=True)
    except Exception as error:
        print(json.dumps({'ok':False,'message':str(error)}),flush=True);raise SystemExit(1)
