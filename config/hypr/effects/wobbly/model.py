"""Original Compiz Wobbly options, in their original units."""
import hashlib
import json
import math
from pathlib import Path
import re

COMPIZ_DEFAULTS = dict(enabled=False, snap_key='<Shift>', snap_inverted=False, shiver=False,
    friction=3.0, spring_k=8.0, grid_resolution=8, min_grid_size=8,
    map_effect=0, focus_effect=0,
    map_window_match='Splash | DropdownMenu | PopupMenu | Tooltip | Notification | Combo | Dnd | Unknown',
    focus_window_match='', grab_window_match='',
    move_window_match='Toolbar | Menu | Utility | Dialog | Normal | Unknown', maximize_effect=True)
DRAG_DEFAULTS = dict(hotkey_drag=True, normal_drag=True)
DEFAULTS = dict(COMPIZ_DEFAULTS, **DRAG_DEFAULTS, enabled=True, spring_k=3.0,
                grid_resolution=3, focus_effect=1)
RANGES = dict(friction=(0.1,10), spring_k=(0.1,10), grid_resolution=(1,64), min_grid_size=(4,128),
              map_effect=(0,1), focus_effect=(0,1))
TYPES = ('Normal','Dialog','Utility','Toolbar','Menu','Splash','DropdownMenu','PopupMenu',
         'Tooltip','Notification','Combo','Dnd','Unknown','Dock','Desktop','Any')
MODIFIERS = ('Shift','Control','Alt','Super','Mod2','Mod3','Mod5')
PATH = Path(__file__).resolve().with_name('settings.json')


def validate_match(expression):
    if not isinstance(expression,str) or len(expression)>1024 or any(not c.isprintable() for c in expression):
        raise ValueError('Window match must be a single line, up to 1024 characters.')
    # Boolean Compiz-style expressions; class/title/role values use shell globs.
    tokens = re.findall(r'[()!&|]|[^()!&|]+',expression)
    tokens = [t.strip() for t in tokens if t.strip()]
    index = 0
    def atom(depth=0):
        nonlocal index
        if depth>32 or index>=len(tokens): raise ValueError('Incomplete window match.')
        token=tokens[index]; index+=1
        if token=='!': atom(depth+1); return
        if token=='(':
            group(depth+1)
            if index>=len(tokens) or tokens[index]!=')': raise ValueError('Unclosed window-match group.')
            index+=1; return
        key,sep,value=token.partition('=')
        if not sep:
            if token not in TYPES: raise ValueError('Unknown window type: '+token)
        elif key=='type':
            if value not in TYPES: raise ValueError('Unknown window type: '+value)
        elif key in ('class','title','role'):
            if not value: raise ValueError('Enter a value for '+key)
        elif key in ('floating','xwayland','override_redirect','rgba'):
            if value not in ('0','1'): raise ValueError(key+' needs 0 or 1.')
        elif key=='state':
            if value not in ('maximized','fullscreen','normal'): raise ValueError('Unknown window state.')
        elif key=='xid':
            if not re.fullmatch(r'(0x[0-9a-fA-F]+|[0-9]+)',value): raise ValueError('Invalid X11 window ID.')
        else: raise ValueError('Unknown window match: '+key)
    def group(depth=0):
        nonlocal index
        atom(depth)
        while index<len(tokens) and tokens[index] in ('&','|'):
            index+=1;atom(depth)
    if tokens:
        group()
        if index!=len(tokens): raise ValueError('Invalid window match.')
    return expression


def validate(values):
    # Existing installations and saved theme snapshots predate the drag switches.
    if isinstance(values,dict) and set(values)==set(COMPIZ_DEFAULTS):
        values=dict(values,**DRAG_DEFAULTS)
    if not isinstance(values,dict) or set(values)!=set(DEFAULTS):
        raise ValueError('Wobbly settings are incomplete or contain unknown options.')
    result={}
    for key,default in DEFAULTS.items():
        value=values[key]
        if type(default) is bool:
            if type(value) is not bool: raise ValueError(key+' must be on or off.')
        elif key.endswith('_match'): value=validate_match(value)
        elif key=='snap_key':
            if not isinstance(value,str) or not re.fullmatch(r'(?:<(?:'+'|'.join(MODIFIERS)+r')>)*',value):
                raise ValueError('Choose snapping modifiers such as <Shift> or <Control><Alt>.')
            if len(re.findall('<',value))!=len(set(re.findall(r'<([^>]+)>',value))):
                raise ValueError('A snapping modifier is repeated.')
        else:
            if type(value) not in (int,float) or not math.isfinite(value) or not RANGES[key][0]<=value<=RANGES[key][1]:
                raise ValueError(f'{key} must be between {RANGES[key][0]} and {RANGES[key][1]}.')
            if type(default) is int and int(value)!=value: raise ValueError(key+' needs a whole number.')
            value=type(default)(value)
        result[key]=value
    return result


def encode(values): return json.dumps(validate(values),indent=2)+'\n'


def decode(content):
    def unique(items):
        result={}
        for k,v in items:
            if k in result: raise ValueError('Duplicate Wobbly setting: '+k)
            result[k]=v
        return result
    return validate(json.loads(content,object_pairs_hook=unique))


def load(path=PATH):
    content=path.read_bytes() if path.exists() else b''
    return (decode(content.decode()) if content else validate(DEFAULTS)),hashlib.sha256(content).hexdigest()


def drag_shortcut(root=None):
    from control_center import keys
    root=root or PATH.parents[2]
    try:
        bindings,_=keys.Store(root=root).load()
        variables=keys.variables((root/'hyprland.conf').read_text())
        labels=[b.shortcut(variables) for b in bindings if b.enabled and b.submap=='reset'
                and 'm' in b.flags and b.dispatcher=='movewindow']
        return ' / '.join(dict.fromkeys(labels)) or 'configured drag hotkey'
    except (OSError,ValueError):return 'configured drag hotkey'
