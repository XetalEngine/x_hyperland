"""Favorite shortcut associations backed by the same validated binding store as Control desk."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import shlex
import shutil
import sys
from urllib.parse import quote,unquote
import uuid
from PyQt6.QtCore import QObject,QFileSystemWatcher,QTimer,pyqtSignal
import shortcuts

sys.path.insert(0,str(shortcuts.ROOT/'control_center'))
import keys

ROLE=258
LAUNCHER=shortcuts.ROOT/'launcher/launch.py'


def launch_command(app_id):
    # URL encoding protects desktop IDs from Hyprland's variable/comment expansion.
    return shlex.join(['python3',str(LAUNCHER),'--app',quote(app_id,safe='')]).replace('#','##')


def tokens(command,values=None):
    try:argv=shlex.split(keys.expand(command,values or {}).replace('##','#'))
    except ValueError:return []
    return [os.path.expanduser(arg) for arg in argv]


def normalized(argv):
    argv=list(argv)
    if not argv:return ()
    if Path(argv[0]).name=='dolphin':argv[0]=str(shortcuts.ROOT/'scripts/dolphin.sh')
    if Path(argv[0]).name=='kitty' and not any(arg in ('--config','-c') or arg.startswith('--config=') for arg in argv[1:]):
        argv[1:1]=['--config',str(shortcuts.ROOT/'kitty.conf')]
    program=shutil.which(argv[0])
    if program:argv[0]=str(Path(program).resolve())
    return tuple(os.path.expanduser(arg) for arg in argv)


def wrapper_id(argv):
    if len(argv)==4 and Path(argv[0]).name.startswith('python') and argv[1]==str(LAUNCHER) and argv[2]=='--app':
        return unquote(argv[3])
    return None


def matches(entry,records,values):
    result=[]
    try:expected=normalized(entry.argv())
    except ValueError:expected=()
    for binding in records:
        if binding.dispatcher!='exec' or binding.submap!='reset':continue
        argv=tokens(binding.args,values);ident=wrapper_id(argv)
        if ident is not None:
            match=ident==entry.get_id()
        else:
            # A customized working folder or terminal preference needs the saved shortcut wrapper.
            match=bool(expected and not entry.fields['directory'] and not entry.fields['terminal']
                       and not entry.fields.get('floating') and normalized(argv)==expected)
        if match:result.append(binding)
    return result


def display(binding,values):
    names={'SUPER':'Super','CTRL':'Ctrl','SHIFT':'Shift','ALT':'Alt','Return':'Enter','space':'Space'}
    return '+'.join(names.get(part,part) for part in binding.shortcut(values).split(' + '))


def edited(records,entry,selected,mods,key,enabled=True,remove=False):
    result=copy.deepcopy(records)
    if selected:
        binding=next((b for b in result if b.id==selected),None)
        if binding is None:raise keys.ConfigError('That hotkey changed elsewhere. Reload before editing it.')
        if binding.protected:raise keys.ConfigError('This is a protected recovery shortcut.')
        if remove:result.remove(binding);return result
    else:
        binding=keys.Binding(uuid.uuid4().hex,'','Applications',True,'','','exec')
        result.append(binding)
    binding.mods=' '.join(token if token.startswith('$') else token.upper() for token in mods.split())
    binding.key=key.strip();binding.enabled=enabled
    binding.label='Open '+entry.get_display_name();binding.category='Applications'
    binding.dispatcher='exec';binding.args=launch_command(entry.get_id())
    return result


class ShortcutIndex(QObject):
    changed=pyqtSignal()
    def __init__(self,parent=None,store=None):
        super().__init__(parent);self.store=store or keys.Store();self.records=[];self.values={};self.error=''
        self.watcher=QFileSystemWatcher([str(self.store.root)],self)
        self.delay=QTimer(self);self.delay.setSingleShot(True);self.delay.setInterval(120)
        self.watcher.directoryChanged.connect(lambda _:self.delay.start())
        self.watcher.fileChanged.connect(lambda _:self.delay.start());self.delay.timeout.connect(self.reload)
        self.reload()
    def reload(self):
        for path in (self.store.path,self.store.main):
            if path.exists() and str(path) not in self.watcher.files():self.watcher.addPath(str(path))
        try:
            records,_=self.store.load();values=keys.variables(self.store.main.read_text());error=''
        except (OSError,ValueError,keys.ConfigError) as exc:records=[];values={};error=str(exc)
        changed=(records,values,error)!=(self.records,self.values,self.error)
        self.records,self.values,self.error=records,values,error
        if changed:self.changed.emit()
    def bindings(self,entry):return matches(entry,self.records,self.values)
    def labels(self,entry):return [display(b,self.values) for b in self.bindings(entry) if b.enabled]
