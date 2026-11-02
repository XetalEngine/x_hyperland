"""Portable, validated cursor choices. No shared desktop settings."""
import hashlib
import json
from pathlib import Path
import re
from .art import STYLES
from . import effects

PATH=Path(__file__).with_name('settings.json')
DEFAULTS=dict(style='pearl',size=32,trail='follow',click_ripple=False,color='#38bdf8',duration=560,intensity=65)
TRAILS={'none':'Off','follow':'Follow desktop theme',**{k:v[1] for k,v in effects.STYLES.items()},
        'comet':'Comet','glow':'Soft glow','sparkle':'Stardust'}

def validate(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise ValueError('Invalid cursor settings')
    result={**DEFAULTS,**value}
    if not isinstance(result['style'],str) or result['style'] not in STYLES or not isinstance(result['trail'],str) or result['trail'] not in TRAILS:raise ValueError('Choose a cursor style and trail')
    for key,lo,hi in [('size',20,64),('duration',100,1000),('intensity',10,100)]:
        if type(result[key]) is not int or not lo<=result[key]<=hi:raise ValueError('Invalid cursor '+key)
    if type(result['click_ripple']) is not bool:raise ValueError('Click ripple must be on or off')
    if not isinstance(result['color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',result['color']):raise ValueError('Invalid cursor effect color')
    return result

def load(path=PATH):
    raw=path.read_bytes() if path.exists() else b''
    return validate(json.loads(raw) if raw else {}),hashlib.sha256(raw).hexdigest()

def encode(values):return (json.dumps(validate(values),indent=2)+'\n').encode()
