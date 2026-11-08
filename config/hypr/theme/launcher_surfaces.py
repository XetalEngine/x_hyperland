"""Launcher surface preferences and shared painting for Apps and Design previews."""
from pathlib import Path
import math

from PyQt6.QtCore import QObject, QEvent, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImageReader, QLinearGradient, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

import runtime

DEFAULTS = {
    'atomicafterglow': {'tile_opacity': 100, 'group_opacity': 45, 'sidebar_opacity': 100, 'group_image': ''},
    'blackwood': {'tile_opacity': 100, 'group_opacity': 45, 'sidebar_opacity': 100, 'group_image': ''},
    'midnighttransit': {'tile_opacity': 100, 'group_opacity': 40, 'sidebar_opacity': 100, 'group_image': ''},
    'hyperfusionblue': {'tile_opacity': 100, 'group_opacity': 38, 'sidebar_opacity': 94, 'group_image': ''},
    'gildedhollow': {'tile_opacity': 94, 'group_opacity': 35, 'sidebar_opacity': 82, 'group_image': ''},
    'hollowgrove': {'tile_opacity': 82, 'group_opacity': 25, 'sidebar_opacity': 70, 'group_image': ''},
    'shadowedge': {'tile_opacity': 100, 'group_opacity': 30, 'sidebar_opacity': 82, 'group_image': ''},
    'raw': {'tile_opacity': 45, 'group_opacity': 0, 'sidebar_opacity': 45, 'group_image': ''},
    'modern': {'tile_opacity': 100, 'group_opacity': 100, 'sidebar_opacity': 100, 'group_image': ''},
    'breakpoint': {'tile_opacity': 94, 'group_opacity': 0, 'sidebar_opacity': 45, 'group_image': ''},
    'binaryknife': {'tile_opacity': 94, 'group_opacity': 32, 'sidebar_opacity': 60, 'group_image': ''},
    'tidalglass': {'tile_opacity': 86, 'group_opacity': 22, 'sidebar_opacity': 38, 'group_image': ''},
    'candycloud': {'tile_opacity': 100, 'group_opacity': 30, 'sidebar_opacity': 64, 'group_image': ''},
    'obsidianforge': {'tile_opacity': 100, 'group_opacity': 62, 'sidebar_opacity': 90, 'group_image': ''},
    'porcelainink': {'tile_opacity': 24, 'group_opacity': 28, 'sidebar_opacity': 60, 'group_image': ''},
}


def normalize(value, strict=False):
    """Return independent, complete settings; tolerate old/malformed saved state."""
    if not isinstance(value, dict):
        if strict: raise ValueError('Choose valid Apps surface settings.')
        value = {}
    result = {style: dict(defaults) for style, defaults in DEFAULTS.items()}
    for style, defaults in DEFAULTS.items():
        entry = value.get(style, {})
        if not isinstance(entry, dict):
            if strict: raise ValueError('Choose valid Apps surface settings.')
            continue
        for key, default in defaults.items():
            choice = entry.get(key, default)
            valid = (isinstance(choice, str) and not any(c in choice for c in '\r\n\0')) if key == 'group_image' else (type(choice) is int and 0 <= choice <= 100)
            if not valid:
                if strict: raise ValueError('Opacity must be between 0 and 100; choose a valid group-strip image.')
                choice = default
            result[style][key] = choice
    return result


def image_path(choice):
    if not choice: return None
    path = Path(choice).expanduser()
    return path if path.is_absolute() else runtime.ROOT / path


class StripImage(QObject):
    """One scaled decoder shared by all strips in a view, paused while hidden."""
    changed = pyqtSignal()

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.path = None
        self.signature = None
        self.movie = None
        self.frame = QPixmap()
        self.enabled = True
        self.error = ''
        host.installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.stop)

    def load(self, choice):
        path = image_path(choice)
        try:
            info = path.stat() if path else None
            signature = (path, info.st_mtime_ns, info.st_size) if info else None
        except OSError: signature = (path, None, None)
        if signature == self.signature: return
        self.signature = signature
        self.path = path
        if self.movie:
            self.movie.stop()
            self.movie.frameChanged.disconnect(self.frame_changed)
            self.movie.deleteLater()
            self.movie = None
        self.frame = QPixmap()
        self.error = ''
        if path:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid(): size = size.scaled(1280, 720, Qt.AspectRatioMode.KeepAspectRatio)
            if reader.supportsAnimation():
                self.movie = QMovie(str(path), parent=self)
                if size.isValid(): self.movie.setScaledSize(size)
                self.movie.frameChanged.connect(self.frame_changed)
                self.movie.jumpToFrame(0)
                self.sync()
            else:
                if size.isValid(): reader.setScaledSize(size)
                self.frame = QPixmap.fromImage(reader.read())
            if self.frame.isNull(): self.error = 'This image could not be read. Choose another image.'
        self.changed.emit()

    def frame_changed(self, _):
        if self.movie:
            self.frame = self.movie.currentPixmap()
            self.changed.emit()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.sync()

    def sync(self):
        if not self.movie: return
        if self.host.isVisible() and self.enabled:
            if self.movie.state() == QMovie.MovieState.NotRunning: self.movie.start()
            else: self.movie.setPaused(False)
        elif self.movie.state() == QMovie.MovieState.Running:
            self.movie.setPaused(True)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide): self.sync()
        return False

    def stop(self):
        if self.movie: self.movie.stop()


def paint_tile(p, box, colors, style, mode, opacity, selected=False, hover=0, radius=None):
    """Opacity affects the card only; icons, text and focus remain independent."""
    if style=='atomicafterglow':
        from atomicafterglow import paint_tile
        paint_tile(p,box,colors,opacity,selected,hover>0)
        return
    if style=='blackwood':
        from blackwood import paint_tile
        paint_tile(p,box,colors,opacity,selected,hover>0)
        return
    if style=='midnighttransit':
        from midnighttransit import paint_tile
        paint_tile(p,box,colors,opacity,selected,hover>0)
        return
    if style=='hyperfusionblue':
        from hyperfusionblue import paint_tile
        paint_tile(p,box,colors,opacity,selected,hover>0)
        return
    if style=='gildedhollow':
        from gildedhollow import paint_tile
        paint_tile(p,box,colors,opacity,selected,hover>0)
        return
    if style=='hollowgrove':
        from hollowgrove import paint_tile
        paint_tile(p,box,colors,opacity,selected,hover>0)
        return
    if style=='shadowedge':
        from shadowedge import paint_tile as shadow_tile
        shadow_tile(p,box,colors,opacity,selected,bool(hover))
        return
    if style=='candycloud':
        from candycloud import paint_tile as cloud_tile
        cloud_tile(p,box,colors,opacity,selected,bool(hover))
        return
    if style=='obsidianforge':
        from obsidianforge import paint_tile as forge_tile
        forge_tile(p,box,colors,opacity,selected,bool(hover))
        return
    if style=='porcelainink':
        from porcelainink import paint_tile as ink_tile
        ink_tile(p,box,colors,opacity,selected,bool(hover))
        return
    if style=='tidalglass':
        from tidalglass import paint_surface
        paint_surface(p,box,colors,18 if radius is None else radius,opacity,selected or bool(hover))
        return
    p.save()
    gradient = QLinearGradient(box.topLeft(), box.bottomRight())
    modern = style != 'raw'
    if modern:
        surface = (colors['Highlight'] if selected else colors['Mid'] if hover else colors['AlternateBase']) if style in ('breakpoint','binaryknife') else (colors['Button'] if selected or hover else colors['AlternateBase'])
        start = end = QColor(surface)
    elif mode == 'light':
        start, end = QColor('#d7e8eb' if selected else '#edf3f9'), QColor('#dbe8f1')
    else:
        start, end = QColor(55, 83, 111), QColor(20, 34, 52)
        if selected or hover: start = start.lighter(round(100 + 12 * hover + 8 * selected))
    start.setAlphaF(opacity / 100)
    end.setAlphaF(opacity / 100)
    gradient.setColorAt(0, start); gradient.setColorAt(1, end)
    border = QColor(colors['Accent'] if selected or (style in ('breakpoint','binaryknife') and hover) else colors['Midlight']) if modern else QColor(113, 218, 205)
    border.setAlphaF(1 if modern and selected else .61 if selected else max(.37 * hover, opacity / 100 * (1 if modern else .22)))
    p.setBrush(gradient); p.setPen(QPen(border, 1))
    radius = (4 if style=='binaryknife' else 12 if style=='breakpoint' else 15 if modern else 10) if radius is None else radius
    p.drawRoundedRect(box, radius, radius)
    p.restore()


def paint_group(p, box, colors, style, opacity, image=None, focused=False, hovered=False):
    p.save()
    radius = 2 if style == 'shadowedge' else 22 if style == 'candycloud' else 3 if style == 'obsidianforge' else 2 if style == 'porcelainink' else 16 if style == 'tidalglass' else 4 if style == 'binaryknife' else 10 if style == 'modern' else 8
    clip = QPainterPath(); clip.addRoundedRect(box, radius, radius)
    p.setClipPath(clip, Qt.ClipOperation.IntersectClip)
    p.setOpacity(p.opacity() * opacity / 100)
    if image is not None and not image.isNull():
        # Composite first, then fade once: 50% means 50% even with a photo,
        # a solid underlay and the text-legibility tint stacked together.
        ratio = p.device().devicePixelRatioF()
        layer = QPixmap(math.ceil(box.width() * ratio), math.ceil(box.height() * ratio))
        layer.setDevicePixelRatio(ratio); layer.fill(QColor(colors['Button']))
        brush = QPainter(layer); brush.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale = max(box.width() / image.width(), box.height() / image.height())
        target = QRectF(0, 0, image.width() * scale, image.height() * scale)
        target.moveCenter(QRectF(0, 0, box.width(), box.height()).center())
        brush.drawPixmap(target, image, QRectF(image.rect()))
        shade = QColor(colors['Window']); shade.setAlpha(160)
        brush.fillRect(QRectF(0, 0, box.width(), box.height()), shade); brush.end()
        p.drawPixmap(box, layer, QRectF(layer.rect()))
    else:
        p.fillRect(box, QColor(colors['Button']))
    p.restore()
    if focused or hovered:
        p.save(); p.setBrush(Qt.BrushStyle.NoBrush)
        color = QColor(colors['Accent']); color.setAlpha(200 if focused else 85)
        p.setPen(QPen(color, 1)); p.drawRoundedRect(box.adjusted(.5, .5, -.5, -.5), radius, radius)
        p.restore()
