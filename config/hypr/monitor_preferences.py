"""Primary-output preference shared by the display editor and desktop overlays."""
from pathlib import Path
import re

MARKER = '# xetal-primary-monitor: '
PATH = Path(__file__).resolve().parent/'control_center/displays.conf'


def primary_name(path=PATH):
    try:
        for line in path.read_text().splitlines():
            if line.startswith(MARKER):
                name = line[len(MARKER):].strip()
                if re.fullmatch(r'[A-Za-z0-9_.:-]+', name): return name
    except OSError:
        pass
    return ''


def select(monitors, placement='active', primary=None, pointer=None):
    available = [m for m in monitors if not m.get('disabled') and m.get('mirrorOf', 'none') in ('none', '', None)]
    if not available: return None
    active = next((m for m in available if m.get('focused')), available[0])
    if placement == 'primary':
        return next((m for m in available if m['name'] == (primary_name() if primary is None else primary)), min(available, key=lambda m: (abs(m.get('x',0))+abs(m.get('y',0)),m['name'])))
    if placement == 'pointer' and pointer:
        for m in available:
            w, h = m['width']/m.get('scale', 1), m['height']/m.get('scale', 1)
            if m.get('transform', 0) % 2: w, h = h, w
            if m['x'] <= pointer['x'] < m['x']+w and m['y'] <= pointer['y'] < m['y']+h: return m
    return active
