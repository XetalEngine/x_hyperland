"""Only ordinary pointers may initiate the floating-window title grip.

Modern clients provide a named shape. Older Wayland/XWayland clients provide
bitmaps, matched exactly against installed Xcursor arrow artwork. Unrecognized
or unavailable cursors leave the gesture entirely to the application.
"""
import json
import os
from pathlib import Path
import runpy
import struct
import time

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(pixels):
    value = 14695981039346656037
    for byte in pixels:
        value = ((value ^ byte) * 1099511628211) & 0xffffffffffffffff
    return f'{value:016x}'


def arrow_images(data):
    """Read bounded, little-endian Xcursor images, including animation frames."""
    result = set()
    if len(data) < 16 or len(data) > 16*1024*1024: return result
    magic, header, version, count = struct.unpack_from('<4I', data)
    if magic != 0x72756358 or header < 16 or count > 4096 or header+count*12 > len(data): return result
    for i in range(count):
        kind, size, offset = struct.unpack_from('<3I', data, header+i*12)
        if kind != 0xfffd0002 or offset+36 > len(data): continue
        image_header, image_type, subtype, version, width, height, xhot, yhot, delay = struct.unpack_from('<9I', data, offset)
        end = offset+image_header+width*height*4
        if (image_header < 36 or image_type != kind or subtype != size or
                not 1 <= width <= 256 or not 1 <= height <= 256 or
                xhot >= width or yhot >= height or end > len(data)): continue
        result.add((width, height, fingerprint(data[offset+image_header:end])))
    return result


class CursorGuard:
    def __init__(self, hypr, roots=None):
        self.hypr = hypr
        self.roots = roots if roots is not None else [
            ROOT/'cursors/.build/data/icons', Path.home()/'.icons',
            Path.home()/'.local/share/icons', Path('/usr/local/share/icons'), Path('/usr/share/icons'),
            *[Path(p).expanduser() for p in os.environ.get('XCURSOR_PATH', '').split(':') if p]]
        self.images, self.files, self.checked = set(), {}, -float('inf')

    def refresh(self):
        if time.monotonic()-self.checked < 5: return
        self.checked = time.monotonic()
        files = {}
        for root in self.roots:
            for name in ('left_ptr', 'default', 'arrow', 'top_left_arrow'):
                for path in root.glob('*/cursors/'+name):
                    try:
                        path = path.resolve(); stat = path.stat()
                        files[path] = (stat.st_mtime_ns, stat.st_size)
                    except OSError: pass
        if files == self.files: return
        self.files, self.images = files, set()
        for path, (_, size) in files.items():
            if size > 16*1024*1024: continue
            try: self.images.update(arrow_images(path.read_bytes()))
            except OSError: pass

    def ordinary(self, image):
        if not isinstance(image, dict): return False
        if image.get('kind') == 'arrow': return True
        if image.get('kind') != 'bitmap': return False
        self.refresh()
        return (image.get('width'), image.get('height'), image.get('hash')) in self.images

    def allowed(self, serial=None):
        try:
            state = self.hypr.query('xetal-cursor')
            if not isinstance(state, dict) or state.get('down') is not True: return None
            current = state.get('serial')
            if type(current) is not int or current < 1 or (serial is not None and current != serial): return None
            if self.ordinary(state.get('press')) and self.ordinary(state.get('current')): return current
        except (OSError, ValueError, TypeError): pass
        return None


def ensure_probe(hypr):
    """Load once per compositor, never replace/unload an existing native plugin."""
    if any(p.get('name') == 'Xetal Cursor Probe' for p in hypr.query('plugin list')): return
    manifest = json.loads((ROOT/'runtime/manifest.json').read_text())
    if hypr.query('version').get('commit') != manifest['commit']:
        raise RuntimeError('Text-safe title dragging needs the supported Hyprland runtime.')
    build = runpy.run_path(str(ROOT/'runtime/cursor_probe/build.py'))['build']
    answer = hypr.command('plugin load '+str(build())).strip()
    if answer != 'ok': raise RuntimeError('Cursor probe could not load: '+answer)
