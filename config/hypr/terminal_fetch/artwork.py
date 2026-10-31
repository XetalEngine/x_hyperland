"""Palette-driven vector emblem and inline Kitty image cells.

Unicode placements scroll with the welcome instead of hovering over the prompt.
Protocol: https://sw.kovidgoyal.net/kitty/graphics-protocol/#unicode-placeholders
"""
import base64
import hashlib
import os
from pathlib import Path
import secrets
from string import Template
import tempfile

COLUMNS, ROWS = 32, 16
# Kitty's first 32 row/column combining marks (protocol data, not a font).
DIACRITICS = tuple(chr(int(value, 16)) for value in (
    '0305 030D 030E 0310 0312 033D 033E 033F 0346 034A 034B 034C 0350 0351 0352 0357 '
    '035B 0363 0364 0365 0366 0367 0368 0369 036A 036B 036C 036D 036E 036F 0483 0484').split())
_application = None


def png(colors):
    """Rasterize our SVG once per palette; no external images or network fetch."""
    from PyQt6.QtGui import QColor
    accent = QColor(colors['Accent']); background = QColor(colors['Window'])
    foreground = QColor(colors['Text'])
    def mix(a, b, fraction):
        return QColor(*(round(x + (y - x) * fraction) for x, y in
                        zip(a.getRgb()[:3], b.getRgb()[:3]))).name()
    palette = dict(accent=accent.name(), bright=mix(accent, foreground, .8),
                   deep=mix(accent, background, .7))
    source = Template((Path(__file__).parent/'assets/arch-neon.svg').read_text()).substitute(palette).encode()
    key = hashlib.sha256(source).hexdigest()[:20]
    directory = Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'xetal-hyprland/terminal'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory/f'arch-{key}.png'
    if target.is_file(): return target
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    global _application
    if QGuiApplication.instance() is None:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        _application = QGuiApplication([])
    renderer = QSvgRenderer(source)
    if not renderer.isValid(): raise ValueError('The Arch emblem could not be rendered.')
    image = QImage(480, 480, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    fd, temporary = tempfile.mkstemp(prefix='.arch-', suffix='.png', dir=directory)
    os.close(fd)
    try:
        if not image.save(temporary, 'PNG'): raise OSError('Cannot cache the terminal emblem.')
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def kitty_image(colors):
    """Return quiet image transmission, placeholder rows and their ID color."""
    data = base64.b64encode(png(colors).read_bytes()).decode('ascii')
    image_id = secrets.randbelow(0xfffffe) + 1
    chunks = []
    for offset in range(0, len(data), 4096):
        more = int(offset + 4096 < len(data))
        fields = f'a=T,f=100,U=1,c={COLUMNS},r={ROWS},i={image_id},q=2,' if offset == 0 else ''
        chunks.append(f'\x1b_G{fields}m={more};{data[offset:offset+4096]}\x1b\\')
    lines = [''.join('\U0010eeee' + DIACRITICS[row] + DIACRITICS[col] for col in range(COLUMNS))
             for row in range(ROWS)]
    return ''.join(chunks), lines, f'#{image_id:06x}'
