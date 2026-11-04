"""One source of truth for persistent app choices and session window overrides."""
import copy
import hashlib
import json
import re
from pathlib import Path

PATH = Path(__file__).with_name('rules.json')
MODES = {'super': 'Only while holding the modifier', 'always': 'Always',
         'nearby': 'When the pointer is nearby', 'off': 'Off'}
ANCHORS = {'top-right': 'Top right', 'top-center': 'Top center', 'top-left': 'Top left',
           'bottom-right': 'Bottom right', 'bottom-center': 'Bottom center', 'bottom-left': 'Bottom left'}
BACKGROUNDS = {'auto': 'Auto · match the window underneath', 'manual': 'Manual · choose a color'}
DEFAULTS = dict(mode='super', size=18, anchor='top-right', x=8, y=8, proximity=80,
                background='auto', background_color='#20242b')
LEGACY_KEYS = DEFAULTS.keys() - {'background', 'background_color'}


def validate(rule):
    if not isinstance(rule, dict) or rule.keys() not in (DEFAULTS.keys(), LEGACY_KEYS):
        raise ValueError('Window button options are incomplete or contain unknown fields.')
    rule = dict(DEFAULTS, **rule)  # Existing rules gain Auto without changing their saved geometry.
    if rule['mode'] not in MODES or rule['anchor'] not in ANCHORS:
        raise ValueError('Choose a supported display mode and position.')
    for key, low, high in [('size',10,64), ('x',0,4000), ('y',0,4000), ('proximity',12,400)]:
        if type(rule[key]) is not int or not low <= rule[key] <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
    if rule['background'] not in BACKGROUNDS:
        raise ValueError('Choose Auto or Manual background.')
    if not isinstance(rule['background_color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',rule['background_color']):
        raise ValueError('Choose an opaque RGB background color.')
    rule['background_color'] = rule['background_color'].lower()
    return dict(rule)


def validate_document(data, section='apps'):
    if not isinstance(data, dict) or set(data) != {'version',section} or type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Unsupported window button rules file.')
    entries = data[section]
    if not isinstance(entries, dict) or len(entries) > 512:
        raise ValueError('Too many window button rules.')
    result = copy.deepcopy(data)
    for key, value in entries.items():
        if not isinstance(key,str) or not key or len(key.encode()) > 512 or any(ord(c)<32 for c in key):
            raise ValueError('Invalid application or window identity.')
        if section == 'windows' and (not key.isascii() or not key.isdecimal()):
            raise ValueError('Invalid window identity.')
        result[section][key] = validate(value)
    return result


def encode(data, section='apps'):
    return json.dumps(validate_document(data,section),ensure_ascii=False,indent=2)+'\n'


def load(path=PATH, section='apps'):
    raw = path.read_bytes() if path.exists() else b''
    if len(raw)>1024*1024: raise ValueError('Window button rules file is too large.')
    data = json.loads(raw) if raw else {'version':1,section:{}}
    return validate_document(data,section), hashlib.sha256(raw).hexdigest()


def effective(settings, app_rule=None, window_rule=None):
    return validate(window_rule or app_rule or dict(DEFAULTS,size=settings['size'],x=settings['inset'],y=settings['inset']))
