"""Validated, portable desktop cube preferences and imported artwork."""
from copy import deepcopy
import hashlib
import json
import math
import re
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'settings.json'
DEFAULTS = dict(enabled=True, wall_opacity=0.85, zoom=0.64, sensitivity=0.35,
                duration=220, preview_fps=60, sky_mode='gradient', sky_motion=True, sky_speed=0.0,
                top_image='', bottom_image='', sky_image='',
                sky_top=[0.035,0.04,0.065,1.0], sky_bottom=[0.14,0.075,0.095,1.0],
                cap_color=[0.09,0.10,0.14,1.0], edge_color=[0.898,0.224,0.271,1.0],
                windows_3d=True, min_cube_size=60, window_space=10, window_depth=0.3,
                window_color=[0.18,0.19,0.24,1.0])
RANGES = dict(wall_opacity=(0,1), zoom=(0.25,0.95), sensitivity=(0.05,2), duration=(0,1000),
              preview_fps=(1,144), sky_speed=(-20,20), min_cube_size=(10,100), window_space=(0,50), window_depth=(0,1))
IMAGES = ('top_image','bottom_image','sky_image')
COLORS = ('sky_top','sky_bottom','cap_color','edge_color','window_color')


def validate(values):
    if isinstance(values,dict) and 'preview_fps' not in values:
        values = dict(values,preview_fps=60)
    if set(values) != set(DEFAULTS):
        raise ValueError('Cube settings are incomplete or contain unknown options.')
    out = deepcopy(values)
    for key, default in DEFAULTS.items():
        value = values[key]
        if key in IMAGES:
            if not isinstance(value,str) or (value and not re.fullmatch(r'images/[a-f0-9]{64}\.png',value)):
                raise ValueError('Choose cube artwork using the image picker.')
        elif key in COLORS:
            if not isinstance(value,list) or len(value)!=4 or any(type(c) not in (int,float) or not math.isfinite(c) or not 0<=c<=1 for c in value):
                raise ValueError('Cube colors need four RGBA components between 0 and 1.')
        elif key == 'sky_mode':
            if value not in ('gradient','image','sky'):raise ValueError('Unknown cube background mode.')
        elif type(default) is bool:
            if type(value) is not bool:raise ValueError(key+' must be on or off.')
        else:
            if type(value) not in (int,float) or not math.isfinite(value) or not RANGES[key][0]<=value<=RANGES[key][1]:
                raise ValueError('Invalid cube setting: '+key)
            if type(default) is int and int(value)!=value:raise ValueError(key+' requires a whole number.')
            out[key] = type(default)(value)
    return out


def encode(values):return json.dumps(validate(values),indent=2)+'\n'


def load(path=PATH):
    raw = path.read_bytes() if path.exists() else b''
    return validate(json.loads(raw) if raw else DEFAULTS), hashlib.sha256(raw).hexdigest()


def import_image(filename, root=ROOT):
    from PIL import Image, ImageOps
    from .controller import atomic
    filename = Path(filename)
    if filename.stat().st_size > 64*1024*1024:raise ValueError('Choose an image smaller than 64 MB.')
    with Image.open(filename) as original:
        if original.width*original.height>32*1024*1024:raise ValueError('Choose an image smaller than 32 megapixels.')
        original.seek(0)
        picture = ImageOps.exif_transpose(original).convert('RGBA')
        picture.thumbnail((4096,2048),Image.Resampling.LANCZOS)
        import io
        output = io.BytesIO();picture.save(output,format='PNG')
    content = output.getvalue()
    relative = 'images/'+hashlib.sha256(content).hexdigest()+'.png'
    atomic(root/relative,content)
    return relative


def prepare_images(values, root=ROOT):
    """Decode outside the compositor; native code reads bounded RGBA buffers only."""
    from PIL import Image
    from .controller import atomic
    for relative in set(values[k] for k in IMAGES)-{''}:
        source = root/relative
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest()!=source.stem:raise ValueError('Cube image changed; choose it again.')
        target = root/'cache'/(source.stem+'.rgba')
        if target.is_file():continue
        with Image.open(source) as image:
            if not 1<=image.width<=4096 or not 1<=image.height<=2048:raise ValueError('Cube artwork dimensions are too large.')
            rgba=image.convert('RGBA');payload=struct.pack('<8sII',b'XTCUBE1\0',rgba.width,rgba.height)+rgba.tobytes()
        atomic(target,payload)
