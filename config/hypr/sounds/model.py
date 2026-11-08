"""Sound catalog and preferences; no shared mixer or desktop settings."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'sounds/settings.json'
PACKS = {
    'atomicafterglow': ('Atomic Afterglow', 'Phosphor signals', 'Soft analog instruments, warm sine chimes and a quiet rising signal.', '#b5ed29'),
    'blackwood': ('Blackwood', 'Harbour bells', 'Low wooden mallets, soft brass overtones and a quiet coastal cadence.', '#c7af7d'),
    'midnighttransit': ('Midnight Transit', 'Platform chimes', 'Soft station bells and a warm descending electric-piano cadence.', '#ffb239'),
    'hyperfusionblue': ('HyperFusion Blue', 'Blue horizon', 'Clear glass notes over a warm, restrained electronic chord.', '#00baff'),
    'raw': ('Xetal Raw', 'Prismatic notes', 'Clean digital plucks and crystalline echoes.', '#65d9d0'),
    'modern': ('Xetal Modern', 'First light', 'Soft electric keys with a warm, airy finish.', '#87b6da'),
    'breakpoint': ('BreakPoint', 'Red signal', 'Low analog pulses and a restrained minor melody.', '#eb4358'),
    'binaryknife': ('Binary Knife', 'Blue circuit', 'Precise glass tones and a cool metallic shimmer.', '#3da8ff'),
    'tidalglass': ('Tidal Glass', 'Waterlight', 'Rounded water bells with drifting, pearly harmonics.', '#65d4dc'),
    'porcelainink': ('Porcelain Ink', 'Quiet porcelain', 'Delicate plucked strings and ceramic resonance.', '#ce7560'),
    'obsidianforge': ('Obsidian Forge', 'Emberwork', 'Deep bronze mallets and a warm forged-metal chord.', '#f8a44e'),
    'candycloud': ('Candy Cloud', 'Sugar stars', 'A tiny music box with bright, sparkling upper notes.', '#eab4dc'),
    'shadowedge': ('Shadow Edge', 'Moonlit passage', 'Breathy flute tones and distant silver bells.', '#b4c0d1'),
    'hollowgrove': ('Hollow Grove', 'Woodland greeting', 'Wooden kalimba notes, soft flute and a gentle echo.', '#a7bd9a'),
    'gildedhollow': ('The Gilded Hollow', 'Lantern gold', 'Hammered strings, warm brass and small golden chimes.', '#e9ba64'),
}
STYLES = {'follow': 'Follow desktop theme', **{k: v[0] for k, v in PACKS.items()}}
EVENTS = {
    'startup': ('Startup', 'A short welcome when your Fusion desktop starts.'),
    'shutdown': ('Shutdown', 'After confirming log out, restart or power off in Fusion.'),
    'error': ('Error', 'Something could not be completed.'),
    'warning': ('Exclamation', 'A warning or something that needs attention.'),
    'info': ('Information', 'An informational dialog or notification.'),
    'question': ('Question', 'A dialog asking you to make a choice.'),
    'success': ('Success', 'A notification marked as completed successfully.'),
    'notification': ('Notification', 'Other desktop notification popups.'),
}
DEFAULTS = {'version': 1, 'enabled': True, 'pack': 'follow', 'volume': 35,
            'respect_dnd': True, 'events': dict.fromkeys(EVENTS, True)}


def validate(value):
    if not isinstance(value, dict) or value.get('version', 1) != 1:
        raise ValueError('Unsupported sound settings.')
    result = copy.deepcopy(DEFAULTS)
    for key in ('enabled', 'respect_dnd'):
        result[key] = value.get(key, result[key])
        if type(result[key]) is not bool: raise ValueError('Invalid sound switch: ' + key)
    result['pack'] = value.get('pack', 'follow')
    if not isinstance(result['pack'], str) or result['pack'] not in STYLES:
        raise ValueError('Choose one of the installed sound packs.')
    result['volume'] = value.get('volume', 35)
    if type(result['volume']) is not int or not 0 <= result['volume'] <= 100:
        raise ValueError('Sound volume must be between 0 and 100%.')
    events = value.get('events', {})
    if not isinstance(events, dict) or set(events) - set(EVENTS): raise ValueError('Unknown sound event.')
    for key, enabled in events.items():
        if type(enabled) is not bool: raise ValueError('Invalid sound event switch.')
        result['events'][key] = enabled
    return result


def load(path=PATH):
    path = Path(path)
    try: data = path.read_bytes()
    except FileNotFoundError: return copy.deepcopy(DEFAULTS), None
    return validate(json.loads(data)), hashlib.sha256(data).hexdigest()


def save(value, expected, path=PATH):
    value = validate(value); path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if load(path)[1] != expected:
            raise ValueError('Sound settings changed in another window. Reload before saving.')
        data = (json.dumps(value, indent=2) + '\n').encode()
        fd, temp = tempfile.mkstemp(prefix='.settings-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    return load(path)


def resolve(pack, root=ROOT):
    if pack in PACKS: return pack
    if pack != 'follow': raise ValueError('Unknown sound pack.')
    try: design = json.loads((Path(root) / 'theme/state.json').read_text()).get('design')
    except (OSError, ValueError): design = None
    return design if design in PACKS else 'hollowgrove'


def asset(pack, event, root=ROOT):
    if event not in EVENTS: raise ValueError('Unknown sound event.')
    return Path(root) / 'sounds/packs' / resolve(pack, root) / (event + '.ogg')
