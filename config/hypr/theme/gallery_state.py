"""Preset visibility and named containers, independent of the selected theme."""
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

import runtime

HIDDEN_FIELDS = ('hidden', 'hidden_tabs', 'active_hidden_tab', 'hidden_dock_collapsed')
DEFAULTS = {'version':1,'hidden':[], 'hidden_tabs':[{'id':'hidden','name':'Hidden','paths':[]}], 'active_hidden_tab':'hidden', 'hidden_dock_collapsed':False}


def path(): return runtime.STATE.parent/'state/preset-gallery.json'


def name(value):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>48 or not value.isprintable():
        raise ValueError('Give the tab a name of 1–48 characters.')
    return value.strip()


def normalize(value):
    if not isinstance(value,dict) or value.get('version')!=1: raise ValueError('The saved preset gallery needs repair.')
    collapsed=value.get('hidden_dock_collapsed',False)
    if not isinstance(collapsed,bool):raise ValueError('Invalid hidden dock visibility.')
    hidden=value.get('hidden',[]);tabs=value.get('hidden_tabs',DEFAULTS['hidden_tabs'])
    valid=lambda item:isinstance(item,str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',item)
    if not isinstance(hidden,list) or len(hidden)>4096 or not all(valid(item) for item in hidden):
        raise ValueError('Invalid hidden theme list.')
    if not isinstance(tabs,list) or not 1<=len(tabs)<=64: raise ValueError('Keep between 1 and 64 hidden theme tabs.')
    hidden=list(dict.fromkeys(hidden));available=set(hidden);owned=set();ids=set();names=set();result=[]
    for tab in tabs:
        if not isinstance(tab,dict) or not valid(tab.get('id')):raise ValueError('Invalid hidden theme tab.')
        title=name(tab.get('name'))
        if tab['id'] in ids or title.casefold() in names:raise ValueError('Each tab needs its own name.')
        ids.add(tab['id']);names.add(title.casefold());items=tab.get('paths',[])
        if not isinstance(items,list) or len(items)>4096 or not all(valid(item) for item in items):raise ValueError('Invalid themes in this tab.')
        items=[item for item in items if item in available]
        if len(set(items))!=len(items) or owned.intersection(items):raise ValueError('A hidden theme can belong to only one tab.')
        owned.update(items);result.append({'id':tab['id'],'name':title,'paths':items})
    active=value.get('active_hidden_tab','hidden')
    if not isinstance(active,str) or active not in ids:active=result[0]['id']
    next(tab for tab in result if tab['id']==active)['paths'].extend(item for item in hidden if item not in owned)
    return {'version':1,'hidden':hidden,'hidden_tabs':result,'active_hidden_tab':active,'hidden_dock_collapsed':collapsed}


def read():
    target=path()
    return normalize(json.loads(target.read_text()) if target.exists() else DEFAULTS)


def save(value, expected, fields=HIDDEN_FIELDS):
    if set(fields)!=set(HIDDEN_FIELDS):raise ValueError('Save the complete gallery organization together.')
    value=normalize(value);expected=normalize(expected);target=path();target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with target.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if read()!=expected:raise ValueError('Hidden themes changed elsewhere. Reopen Presets and try again.')
        fd,pending=tempfile.mkstemp(prefix='.preset-gallery-',dir=target.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
            os.replace(pending,target)
        finally:Path(pending).unlink(missing_ok=True)
    return value


def hidden_tab(options, identity=None):
    identity=identity or options['active_hidden_tab']
    tab=next((tab for tab in options['hidden_tabs'] if tab['id']==identity),None)
    if tab is None:raise ValueError('That hidden theme tab no longer exists.')
    return tab


def add_hidden_tab(options, title):
    value=normalize(options);identity=uuid.uuid4().hex
    value['hidden_tabs'].append({'id':identity,'name':name(title),'paths':[]});value['active_hidden_tab']=identity
    return normalize(value)


def rename_hidden_tab(options, identity, title):
    value=normalize(options);hidden_tab(value,identity)['name']=name(title);return normalize(value)


def transfer_hidden_tab(options, source, destination):
    value=normalize(options)
    if source==destination:raise ValueError('Choose a different tab for these themes.')
    if len(value['hidden_tabs'])<2:raise ValueError('Create another tab before deleting this one.')
    origin=hidden_tab(value,source);target=hidden_tab(value,destination)
    target['paths'].extend(origin['paths']);value['hidden_tabs'].remove(origin);value['active_hidden_tab']=destination
    return normalize(value)


def move_hidden_picture(options, item, destination):
    # Shared tab widgets call the same contract for wallpaper and theme thumbnails.
    value=normalize(options);target=hidden_tab(value,destination)
    if item not in value['hidden']:raise ValueError('That theme is no longer hidden.')
    for tab in value['hidden_tabs']:
        if item in tab['paths']:tab['paths'].remove(item)
    target['paths'].append(item);value['active_hidden_tab']=destination
    return normalize(value)
