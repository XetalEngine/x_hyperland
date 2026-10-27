"""Persistent companion choice, terminal mouse input and Kitty PNG placement."""
import base64
import fcntl
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile
import termios
import time


ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state' / 'companion.json'
ART = ROOT / 'assets' / 'xetal-mascot.png'
MOUSE_ON = '\033[?1002h\033[?1006h'
MOUSE_OFF = '\033[?1002l\033[?1006l'


class Choice:
    def __init__(self, path=STATE):
        self.path = Path(path)
        self.view = 'ascii'
        self.notice = ''
        self.notice_until = 0
        try:
            data = json.loads(self.path.read_text())
            if data.get('version') == 1 and data.get('view') in ('ascii', 'mascot'):
                self.view = data['view']
        except (OSError, ValueError, AttributeError):
            pass

    def switch(self):
        self.view = 'mascot' if self.view == 'ascii' else 'ascii'
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent,
                                             prefix='.companion-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'version': 1, 'view': self.view}, stream)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.notice = ''
        except OSError:
            self.warn('View changed, but the startup preference could not be saved')
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def warn(self, message):
        self.notice = message
        self.notice_until = time.monotonic() + 6

    def hint(self):
        if self.notice and time.monotonic() < self.notice_until:
            return self.notice
        target = 'mascot' if self.view == 'ascii' else 'ASCII'
        return f'Click companion or press Space for {target}'


class Input:
    """Parse split/coalesced terminal reports without mistaking them for Escape."""
    mouse = re.compile(rb'\x1b\[<(\d+);(\d+);(\d+)([mM])')
    csi = re.compile(rb'\x1b\[[0-?]*[ -/]*[@-~]')

    def __init__(self):
        self.pending = b''
        self.since = 0
        self.pressed = None

    def feed(self, data, now=None):
        now = time.monotonic() if now is None else now
        if not self.pending:
            self.since = now
        self.pending += data
        events = []
        while self.pending:
            if self.pending[0] != 27:
                key, self.pending = self.pending[:1], self.pending[1:]
                if key in (b'q', b'Q'):
                    events.append(('hide', 0, 0))
                elif key == b' ':
                    events.append(('switch', 0, 0))
                continue
            if self.pending == b'\x1b':
                if now - self.since >= .08:
                    events.append(('hide', 0, 0))
                    self.pending = b''
                break
            if self.pending.startswith(b'\x1b['):
                match = self.csi.match(self.pending)
                if not match:
                    break
                report = self.mouse.fullmatch(match[0])
                self.pending = self.pending[len(match[0]):]
                if report:
                    button, x, y = map(int, report.group(1, 2, 3))
                    point = (x - 1, y - 1)
                    if button == 0 and report[4] == b'M':
                        self.pressed = point
                    elif button == 0 and report[4] == b'm':
                        if self.pressed == point:
                            events.append(('click', *point))
                        self.pressed = None
                    else:
                        # Dragging, scrolling and other buttons never cycle views.
                        self.pressed = None
                continue
            if self.pending.startswith(b'\x1b_'):
                end = self.pending.find(b'\x1b\\', 2)
                if end < 0:
                    break
                self.pending = self.pending[end + 2:]
                continue
            self.pending = self.pending[2:]
        if len(self.pending) > 4096 or now - self.since > .5:
            self.pending = b''
        return events


def pixel_size(fd, cols, rows):
    try:
        _, _, width, height = struct.unpack('HHHH', fcntl.ioctl(fd, termios.TIOCGWINSZ, b'\0' * 8))
        if width >= cols and height >= rows:
            return width, height
    except (OSError, ValueError):
        pass
    return cols * 8, rows * 16


class Artwork:
    """Display the original PNG centered and static, preserving its pixels."""
    image_id = 1480938572

    def __init__(self, path=ART):
        self.path = Path(path)
        self.loaded = False
        self.placed = False
        self.ratio = 1
        self.last_placement = None

    @staticmethod
    def command(payload='', **keys):
        params = ','.join(f'{key}={value}' for key, value in keys.items())
        return f'\033_G{params};{payload}\033\\'

    def load(self):
        with self.path.open('rb') as stream:
            header = stream.read(24)
        if len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
            raise ValueError('The companion artwork is not a PNG')
        width, height = struct.unpack('>II', header[16:24])
        if not width or not height:
            raise ValueError('The companion artwork has invalid dimensions')
        self.ratio = width / height
        payload = base64.b64encode(os.fsencode(self.path.resolve())).decode('ascii')
        self.loaded = True
        return self.command(payload, a='t', f=100, t='f', i=self.image_id, q=2)

    def placement(self, area, cells, pixels):
        left, top, width, height = area
        cols, rows = cells
        cw, ch = max(1, pixels[0] // cols), max(1, pixels[1] // rows)
        # Leave a full cell of padding, preserving the image's aspect ratio.
        image_rows = min(height - 2, int((width - 2) * cw / self.ratio / ch))
        if image_rows < 1:
            return None
        ph = image_rows * ch
        pw = math.ceil(ph * self.ratio)
        margin_x, margin_y = (width * cw - pw) / 2, (height * ch - ph) / 2
        x = round(left * cw + margin_x)
        y = round(top * ch + margin_y)
        return (x // cw, y // ch, x % cw, y % ch, image_rows)

    def draw(self, area, cells, pixels):
        result = '' if self.loaded else self.load()
        placement = self.placement(area, cells, pixels)
        if placement is None:
            return result + self.hide()
        if placement != self.last_placement:
            col, row, x, y, height = placement
            result += '\0337' + f'\033[{row + 1};{col + 1}H'
            result += self.command(a='p', i=self.image_id, p=1, q=2,
                                   r=height, X=x, Y=y, C=1)
            result += '\0338'
            self.last_placement = placement
            self.placed = True
        return result

    def hide(self, release=False):
        result = ''
        if self.placed or (release and self.loaded):
            result = self.command(a='d', d='I' if release else 'i', i=self.image_id, q=2)
        self.placed = False
        self.last_placement = None
        if release:
            self.loaded = False
        return result
