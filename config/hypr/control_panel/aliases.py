"""Edit recognized aliases without rewriting unrelated shell configuration."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import tempfile
import time

NAME=re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]*$')

def digest(data):return hashlib.sha256(data).hexdigest()

def detect(home=None,environment=None):
    home=Path(home or Path.home());env=dict(os.environ if environment is None else environment)
    executable=env.get('SHELL') or pwd.getpwuid(os.getuid()).pw_shell or '/bin/bash'
    # Kitty can explicitly override the login shell. Read literal shell commands only.
    config=Path(env.get('XETAL_HYPR_ROOT',str(home/'.config/hypr')))/'kitty.conf'
    if config.is_file():
        for line in config.read_text().splitlines():
            if re.match(r'^\s*shell\s+',line):
                command=shlex.split(line,comments=True)[1:]
                if command and Path(command[0]).name in ('bash','zsh','fish','ksh','tcsh','csh'):executable=command[0]
    shell=Path(executable).name
    if shell=='zsh':target=Path(env.get('ZDOTDIR',str(home)))/'.zshrc'
    elif shell=='fish':target=Path(env.get('XDG_CONFIG_HOME',str(home/'.config')))/'fish/config.fish'
    elif shell in ('bash','ksh','csh','tcsh'):target=home/('.bashrc' if shell=='bash' else '.'+shell+'rc')
    else:raise ValueError('Unsupported shell: '+shell+'. Choose Bash, Zsh, Fish, Ksh, Csh or Tcsh in your terminal settings.')
    return shell,target

def parse(line,shell):
    if line.lstrip().startswith('#') or line.rstrip().endswith('\\'):return None
    try:tokens=shlex.split(line,comments=True,posix=True)
    except ValueError:return None
    if not tokens:return None
    if tokens[0]=='alias':
        values=tokens[1:]
        if values[:1]==['--']:values=values[1:]
        if len(values)==1 and '=' in values[0]:name,command=values[0].split('=',1)
        elif shell in ('fish','csh','tcsh') and len(values)==2:name,command=values
        else:return None
    elif shell=='fish' and tokens[0]=='abbr':
        values=tokens[1:]
        if values[:1] in (['-a'],['--add']):values=values[1:]
        if values[:1]==['--']:values=values[1:]
        if len(values)!=2:return None
        name,command=values
    else:return None
    return {'name':name,'command':command} if NAME.fullmatch(name) else None

def load(home=None,environment=None):
    home=Path(home or Path.home());env=dict(os.environ if environment is None else environment)
    shell,target=detect(home,env);files={};entries={};origins={};definitions={}
    def visit(path):
        path=path.expanduser().resolve()
        if str(path) in files or len(files)>=32:return
        if not path.is_relative_to(home.resolve()):return
        data=path.read_bytes() if path.is_file() else b''
        if len(data)>2_000_000:raise ValueError('Shell configuration is too large to edit safely: '+str(path))
        lines=data.decode('utf-8').splitlines(keepends=True);files[str(path)]={'sha256':digest(data),'lines':lines}
        for index,line in enumerate(lines):
            entry=parse(line,shell)
            if entry:
                entries[entry['name']]=entry;origins[entry['name']]={'path':str(path),'line':index}
                definitions.setdefault(entry['name'],[]).append({'path':str(path),'line':index})
            # Follow simple, literal user-owned includes; never evaluate shell code.
            match=re.match(r'^\s*(?:source|\.)\s+(.+?)\s*(?:#.*)?$',line)
            if match:
                value=match.group(1)
                for key in ('HOME','ZDOTDIR','XDG_CONFIG_HOME'):
                    replacement=env.get(key,str(home) if key!='XDG_CONFIG_HOME' else str(home/'.config'))
                    value=value.replace('${'+key+'}',replacement).replace('$'+key,replacement)
                try:parts=shlex.split(value,comments=True)
                except ValueError:continue
                if len(parts)==1 and not any(char in parts[0] for char in '$`*?;|<>'):
                    child=Path(parts[0]).expanduser()
                    if child.is_absolute() and child.is_file():visit(child)
    visit(target)
    if str(target.resolve()) not in files:raise ValueError('The selected shell configuration is outside your home directory.')
    return {'shell':shell,'config':str(target),'entries':list(entries.values()),'files':files,'origins':origins,'definitions':definitions}

def line_for(name,command,shell):
    if not NAME.fullmatch(name) or not command or any(c in command for c in ('\0','\n','\r')):raise ValueError('Use a valid alias name and a single-line command.')
    if shell=='fish':return 'abbr --add -- '+shlex.quote(name)+' '+shlex.quote(command)+'\n'
    if shell in ('tcsh','csh'):return 'alias '+name+' '+shlex.quote(command)+'\n'
    return 'alias '+name+'='+shlex.quote(command)+'\n'

def save(snapshot,state,home=None,environment=None):
    current=load(home,environment)
    if snapshot.get('shell')!=current['shell'] or snapshot.get('config')!=current['config']:
        raise ValueError('The active shell changed. Reload aliases before saving.')
    if {k:v.get('sha256') for k,v in snapshot.get('files',{}).items()}!={k:v['sha256'] for k,v in current['files'].items()}:
        raise ValueError('Shell configuration changed outside Control Panel. Reload before saving.')
    values={}
    for entry in snapshot.get('entries',[]):
        name,command=entry.get('name',''),entry.get('command','');line_for(name,command,current['shell'])
        if name in values:raise ValueError('Alias names must be unique: '+name)
        values[name]=command
    original={v['name']:v['command'] for v in current['entries']};changes={}
    for name,command in original.items():
        if name not in values or values[name]!=command:
            for origin in (current['definitions'][name] if name not in values else [current['origins'][name]]):
                changes.setdefault(origin['path'],{})[origin['line']]=line_for(name,values[name],current['shell']) if name in values else ''
    files={name:list(v['lines']) for name,v in current['files'].items()}
    for path,edits in changes.items():
        for index,line in edits.items():files[path][index]=line
    target=str(Path(current['config']).resolve())
    for name,command in values.items():
        if name not in original:
            if files[target] and not files[target][-1].endswith('\n'):files[target][-1]+='\n'
            files[target].append(line_for(name,command,current['shell']))
    state=Path(state)/'alias-backups';prepared=[]
    try:
        for path,lines in files.items():
            data=''.join(lines).encode();destination=Path(path)
            old=destination.read_bytes() if destination.exists() else b''
            if digest(old)!=current['files'][path]['sha256']:raise ValueError('Shell configuration changed while saving. Reload and try again.')
            if old==data:continue
            state.mkdir(parents=True,exist_ok=True,mode=0o700)
            backup=state/(str(time.time_ns())+'-'+digest(path.encode())[:12]+'-'+destination.name)
            backup.write_bytes(old);backup.chmod(0o600)
            destination.parent.mkdir(parents=True,exist_ok=True)
            fd,temp=tempfile.mkstemp(prefix='.xetal-alias-',dir=destination.parent)
            with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(temp,destination.stat().st_mode&0o777 if destination.exists() else 0o600)
            prepared.append((destination,Path(temp)))
        for destination,temp in prepared:
            before=destination.read_bytes() if destination.exists() else b''
            if digest(before)!=current['files'][str(destination)]['sha256']:raise ValueError('An external edit interrupted saving. Backups were preserved.')
            os.replace(temp,destination)
    finally:
        for _,temp in prepared:temp.unlink(missing_ok=True)
    return load(home,environment)
