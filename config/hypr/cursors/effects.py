"""Mouse-trail identities, independent of cursor artwork and desktop palette."""
import json
from pathlib import Path

# Theme, title, accent, secondary, description. Stable IDs are saved in presets.
STYLES = {
    'plasma': ('raw','Plasma weave','#32e7ee','#c4ff76','Twin electric ribbons twist around a trail of bright nodes.'),
    'orbit': ('modern','Orbital bloom','#83bfff','#dfbdff','Expanding orbital rings carry little satellite pearls.'),
    'fracture': ('breakpoint','Faultline','#ff405d','#ffd8b0','Angular glass shards break away and tumble into sparks.'),
    'circuit': ('binaryknife','Data stream','#32adff','#bcf1ff','Right-angle circuit traces shed drifting binary digits.'),
    'tidal': ('tidalglass','Bioluminescence','#68dfed','#d2faff','A watery wake releases rising bubbles and luminous plankton.'),
    'ink': ('porcelainink','Living ink','#bb3b30','#f0e4cc','A tapered brush stroke scatters vermilion petals and ink flecks.'),
}
THEMES = {value[0]:key for key,value in STYLES.items()}
GENERAL = {
    'comet': ('Comet', 'The original trail of fading dots, in your chosen color.'),
    'glow': ('Soft glow', 'The original soft luminous wake. Choose any accent color.'),
    'sparkle': ('Stardust', 'The original sparkling trail. Independent of every desktop theme.'),
}

def current_theme():
    try:return json.loads((Path(__file__).resolve().parents[1]/'theme/state.json').read_text()).get('design','raw')
    except (OSError,ValueError):return 'raw'

def resolve(trail,design=None):
    return THEMES.get(design or current_theme(),'plasma') if trail=='follow' else trail

def colors(values,design=None):
    style=resolve(values['trail'],design)
    entry=STYLES.get(style)
    accent=entry[2] if entry and values['trail']=='follow' else values['color']
    return accent,entry[3] if entry else accent
