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
    'killerinstinct': ('Killer Instinct · Arcade 94', 'Arcade 94', 'Dark arcade synth and metal.', '#c38aff'), 'kitemple': ('Killer Instinct · Jade Temple', 'Jade Temple', 'Jade temple resonances.', '#55d792'), 'kiprimal': ('Killer Instinct · Primal Storm', 'Primal Storm', 'Stormy low growls and strikes.', '#b5a0f3'), 'kifireice': ('Killer Instinct · Fire & Ice', 'Fire & Ice', 'Icy bells with warm fizz.', '#ffad45'), 'starcraft': ('StarCraft II', 'Koprulu comms', 'Space-console energy tones.', '#27c7ff'), 'mortalkombat2': ('Mortal Kombat II', 'Outworld arcade', 'Dark martial arcade tones.', '#3dd489'), 'facadasexu': ('777 Facadas Exu', 'Copper whispers', 'Low resonant bells and smoke-like air.', '#d25a45'),
    'ghostbusters': ('Ghostbusters', 'Ectoplasm echoes', 'Playful ectoplasm and proton zaps.', '#b4ff00'),
    'hp4': ('BMW S1000RR HP4', 'Pit-lane signals', 'Sportbike-inspired mechanical blips.', '#278cff'),
    'amazon': ('Amazon', 'River chimes', 'Wooden taps and rainforest-like chirps.', '#edcd76'),
    'leviathan': ('Leviathan', 'Brass echoes', 'Deep watery sonar.', '#c69ae5'),
    'polaris': ('Polaris', 'Northern lights', 'Cold crystalline starlight.', '#32e1f2'),
    'prisonbreak': ('Prison Break', 'Midnight breakout', 'Arcade steel-lock percussion.', '#e580ff'), 'infernalencore': ('Infernal Encore', 'Backstage signals', 'Distorted power-chord accents.', '#ff472c'),
    'midnightrun': ('Midnight Run', 'After-hours signals', 'Night-drive engine swells.', '#42e5f5'),
    'mystery98': ('Windows 98 Mystery', 'The midnight study', 'Candlelit antique music box.', '#dbb46a'), 'platform95': ('Platform 95', 'Golden departure', 'Nostalgic train-platform chimes.', '#d1aa58'),
    'mycelium': ('Mycelium', 'Spore songs', 'Organic soft bubbling.', '#c9a0e1'),
    'atomicafterglow': ('Atomic Afterglow', 'Phosphor signals', 'Retro radiation-counter textures.', '#b5ed29'),
    'blackwood': ('Blackwood', 'Harbour bells', 'Low walnut knocks.', '#c7af7d'),
    'midnighttransit': ('Midnight Transit', 'Platform chimes', 'Muted rail-station bells.', '#ffb239'),
    'hyperfusionblue': ('HyperFusion Blue', 'Blue horizon', 'Clean blue interface chimes.', '#00baff'),
    'raw': ('Xetal Raw', 'Prismatic notes', 'Dry cyan console ticks.', '#65d9d0'),
    'modern': ('Xetal Modern', 'First light', 'Soft blue glass.', '#87b6da'),
    'breakpoint': ('BreakPoint', 'Red signal', 'Crimson debugger pulses.', '#eb4358'),
    'binaryknife': ('Binary Knife', 'Blue circuit', 'Sharp electric-blue signals.', '#3da8ff'),
    'tidalglass': ('Tidal Glass', 'Waterlight', 'Water droplets and glass.', '#65d4dc'),
    'porcelainink': ('Porcelain Ink', 'Quiet porcelain', 'Porcelain taps and ink-brush hush.', '#ce7560'),
    'obsidianforge': ('Obsidian Forge', 'Emberwork', 'Dark forge strikes.', '#f8a44e'),
    'candycloud': ('Candy Cloud', 'Sugar stars', 'Playful pastel bells.', '#eab4dc'),
    'shadowedge': ('Shadow Edge', 'Moonlit passage', 'Dark blade-like shimmers.', '#b4c0d1'),
    'hollowgrove': ('Hollow Grove', 'Woodland greeting', 'Hollow wood and airy forest.', '#a7bd9a'),
    'gildedhollow': ('The Gilded Hollow', 'Lantern gold', 'Warm golden cavern bells.', '#e9ba64'),
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
    directory = Path(root) / 'sounds/packs' / resolve(pack, root)
    path = directory / (event + '.mp3')
    # An older installation can still contain Ogg assets during an update.
    return path if path.is_file() else directory / (event + '.ogg')
