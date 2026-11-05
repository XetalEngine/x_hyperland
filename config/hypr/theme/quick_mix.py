"""A small view of existing preferences, with no separate mix file or preset."""
import copy
import backend
import layouts
import bar_styles
import presets
import runtime
import selection_marker
from cursors import model as cursors, effects
from file_jobs import preferences as transfer
from switcher import preferences as switcher
from effects.minimize import model as minimize

# Label, existing component, existing preference path, available choices.
FIELDS = {
    'waybar': ('Waybar style', 'waybar', ('theme','bar_style'), bar_styles.STYLES),
    'dock': ('Dock design', 'dock', ('minimize','dock_style'), minimize.DOCK_STYLES),
    'launcher': ('Start menu', 'launcher', ('theme','launcher_style'), runtime.LAUNCHER_STYLES),
    'layout': ('Navigation & controls', 'layout', ('theme','layout'), layouts.LAYOUTS),
    'marker': ('Selection marker', 'selection', ('theme','selection_marker'), selection_marker.STYLES),
    'cursor': ('Cursor artwork', 'cursors', ('cursors','style'), {key:entry[0] for key,entry in cursors.STYLES.items()}),
    'trail': ('Mouse trail', 'cursors', ('cursors','trail'), cursors.TRAILS),
    'ripple': ('Ripple when I click', 'cursors', ('cursors','click_ripple'), None),
    'transfer': ('File Transfer style', 'transfer', ('transfer','style'), transfer.STYLES),
    'transfer_animation': ('Animate file transfers', 'transfer', ('transfer','animation','enabled'), None),
    'switcher': ('Task Switcher', 'switcher', ('switcher','style'), switcher.STYLES),
}


def values(config):
    config=copy.deepcopy(config)
    config['theme'].setdefault('launcher_style','follow')
    config['theme'].setdefault('bar_style','follow')
    config.setdefault('cursors',dict(cursors.DEFAULTS))
    config.setdefault('transfer',copy.deepcopy(transfer.DEFAULTS))
    config.setdefault('switcher',copy.deepcopy(switcher.DEFAULTS))
    config.setdefault('minimize',dict(minimize.DEFAULTS))
    result={}
    for key,(_,_,path,_) in FIELDS.items():
        value=config
        for part in path:value=value[part]
        result[key]=value
    return result


def read():
    for _ in range(3):
        token=backend.theme_token();config=presets.current()
        if token==backend.theme_token():return values(config),token,config
    raise ValueError('Appearance is still changing. Try again in a moment.')


def plan(config, baseline, edited):
    if set(edited)!=set(FIELDS):raise ValueError('The quick settings are incomplete.')
    target=copy.deepcopy(config);selected=set()
    target.setdefault('cursors',dict(cursors.DEFAULTS));target.setdefault('transfer',copy.deepcopy(transfer.DEFAULTS))
    target.setdefault('switcher',copy.deepcopy(switcher.DEFAULTS))
    target.setdefault('minimize',dict(minimize.DEFAULTS))
    for key,(_,component,path,choices) in FIELDS.items():
        value=edited[key]
        valid=type(value) is bool if choices is None else isinstance(value,str) and value in choices
        if not valid:raise ValueError('Invalid quick setting: '+FIELDS[key][0])
        if value==baseline[key]:continue
        selected.add(component)
        resource=target
        for part in path[:-1]:resource=resource[part]
        resource[path[-1]]=value
        if key=='trail' and value in effects.STYLES:target['cursors']['color']=effects.STYLES[value][2]
    return presets.validate(target),selected


def apply(edited, baseline, expected):
    _,token,config=read()
    if token!=expected:raise ValueError('Appearance changed elsewhere. Reload the quick settings before applying.')
    target,selected=plan(config,baseline,edited)
    if selected:backend.apply_components(target,selected,expected)
    current,token,_=read()
    return current,token,selected


def merge(baseline, edited, saved):
    result=dict(saved);conflicts=[]
    for key in FIELDS:
        if edited[key]==baseline[key]:continue
        result[key]=edited[key]
        if saved[key]!=baseline[key] and saved[key]!=edited[key]:conflicts.append(key)
    return result,conflicts
