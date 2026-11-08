"""Profile-local minimize preferences; effects can be extended without changing the handler."""
import hashlib
import re
from pathlib import Path

SHAPES = {'random': 'Random per window', 'bloom': 'Bloom', 'star': 'Starburst',
          'spill': 'Spill', 'claw': 'Tendrils', 'wide': 'Wide splash', 'coral': 'Coral',
          'web': 'Webbed splash', 'droplets': 'Heavy droplets'}
SURFACES = {'slime': 'Living slime', 'membrane': 'Alien membrane', 'paint': 'Glossy paint'}
EDGES = {'left': 'Left', 'right': 'Right'}
PRESENTATIONS = {'dock': 'Animated dock', 'stack': 'Classic edge stack'}
DOCK_EDGES = {'auto': 'Opposite Waybar', 'bottom': 'Bottom', 'top': 'Top', 'left': 'Left', 'right': 'Right'}
DOCK_STYLES = {'follow': 'Follow desktop theme', 'raw': 'Xetal Raw · circuit rail', 'modern': 'Xetal Modern · floating glass',
               'breakpoint': 'BreakPoint · reactor console', 'binaryknife': 'Binary Knife · cut crystal',
               'tidalglass': 'Tidal Glass · ocean glass', 'porcelainink': 'Porcelain Ink · ink tray',
               'obsidianforge': 'Obsidian Forge · forged metal', 'candycloud': 'Candy Cloud · pearl pillows',
               'shadowedge': 'Shadow Edge · smoked steel', 'hollowgrove': 'Hollow Grove · moonlit vines',
               'gildedhollow': 'The Gilded Hollow · lantern brass',
               'hyperfusionblue': 'HyperFusion Blue · Blue Vault',
               'midnighttransit': 'Midnight Transit · Platform Twelve',
               'blackwood': 'Blackwood · Harbour Cabinet',
               'atomicafterglow': 'Atomic Afterglow · Containment Bay',
               'mycelium': 'Mycelium · Spore Cradle',
               'platform95': 'Platform 95 · Parcel Shelf'}
ORDERS = {'bottom-to-top': 'Bottom to top', 'top-to-bottom': 'Top to bottom'}
HIDE_ANIMATIONS = {'slide':'Slide away', 'burn':'Burn away'}
DEFAULTS = dict(enabled=True, effect='fireball', duration=420, size=76,
                follow_theme=True, color='#39a9ff', shape='random', speed=100, bubbles=70, surface='paint',
                edge='left', order='bottom-to-top', presentation='dock', dock_edge='auto', dock_style='follow',
                auto_hide=True, hide_delay=1200, dock_duration=320, proximity=12, dock_zoom=125,
                hide_animation='burn',fire_indicator=True)
RANGES = dict(duration=(150, 1200), size=(48, 160), speed=(25, 200), bubbles=(0, 100),
              hide_delay=(200,10000), dock_duration=(100,1000), proximity=(2,64), dock_zoom=(100,150))
DOCK_KEYS = {'presentation','dock_edge','dock_style','auto_hide','hide_delay','dock_duration','proximity','dock_zoom'}
HIDE_KEYS = {'hide_animation','fire_indicator'}
PRE_BURN = set(DEFAULTS)-HIDE_KEYS
PRE_DOCK = PRE_BURN-DOCK_KEYS
LEGACY = {'enabled', 'effect', 'duration', 'size'}
PATH = Path(__file__).resolve().with_name('settings.conf')


def validate(values):
    if set(values)==PRE_DOCK:values=dict(DEFAULTS,**values,presentation='stack',hide_animation='slide',fire_indicator=False)
    if set(values)==PRE_BURN:values=dict(DEFAULTS,**values,hide_animation='slide',fire_indicator=False)
    if set(values) != set(DEFAULTS):
        raise ValueError('Minimize settings are incomplete or contain unknown options.')
    if any(type(values[key]) is not bool for key in ('enabled', 'follow_theme', 'auto_hide','fire_indicator')):
        raise ValueError('Invalid Minimize switch.')
    if values['effect'] not in ('fireball', 'splat') or not isinstance(values['shape'], str) or values['shape'] not in SHAPES:
        raise ValueError('Choose a supported effect and splat shape.')
    if not isinstance(values['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', values['color']):
        raise ValueError('Choose a valid effect color.')
    if not isinstance(values['surface'], str) or values['surface'] not in SURFACES:
        raise ValueError('Choose a supported Splat surface.')
    if values['edge'] not in EDGES or values['order'] not in ORDERS:
        raise ValueError('Choose a screen edge and stacking direction.')
    if values['presentation'] not in PRESENTATIONS or values['dock_edge'] not in DOCK_EDGES or values['dock_style'] not in DOCK_STYLES:
        raise ValueError('Choose an available dock style and position.')
    if values['hide_animation'] not in HIDE_ANIMATIONS:raise ValueError('Choose a supported dock hide animation.')
    for key, (lo, hi) in RANGES.items():
        if type(values[key]) is not int or not lo <= values[key] <= hi:
            raise ValueError(f'{key} must be a whole number between {lo} and {hi}.')
    # Splat is parked for now. Read its old preferences without losing them,
    # but use Fireball until the effect is enabled again in a future release.
    return dict(values, color=values['color'].lower(), effect='fireball')


def encode(values):
    return '# Xetal Minimize\n' + ''.join(
        f'{key}={int(value) if type(value) is bool else value}\n'
        for key, value in validate(values).items())


def decode(text):
    values = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or key not in DEFAULTS or key in values:
            raise ValueError('Invalid or duplicate Minimize setting.')
        if key in ('enabled', 'follow_theme', 'auto_hide','fire_indicator'):
            if value not in ('0', '1'):
                raise ValueError('Invalid Minimize switch.')
            value = value == '1'
        elif key in RANGES:
            value = int(value)
        values[key] = value
    # Upgrade the original four-field format without discarding preferences.
    if set(values) in (LEGACY, PRE_DOCK-{'surface','edge','order'}, PRE_DOCK-{'edge','order'}, PRE_DOCK):
        values = dict(DEFAULTS, **values, presentation='stack', hide_animation='slide', fire_indicator=False)
    return validate(values)


def load(path=PATH):
    data = path.read_bytes() if path.exists() else b''
    return (decode(data.decode()) if data else dict(DEFAULTS)), hashlib.sha256(data).hexdigest()
