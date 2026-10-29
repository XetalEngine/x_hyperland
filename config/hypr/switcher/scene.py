# SPDX-License-Identifier: GPL-2.0-or-later
"""Themed window textures on Compiz's switcher layouts, rendered without X11."""
import copy
from dataclasses import replace
from pathlib import Path
import sys

from PyQt6.QtCore import Qt, QRectF, QPointF, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPolygonF, QTransform, QLinearGradient, QPixmap
from PyQt6.QtWidgets import QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'theme'))
import runtime as theme_runtime
from . import geometry, preferences


class Scene(QWidget):
    activated = pyqtSignal(int)
    stepped = pyqtSignal(int)
    dismissed = pyqtSignal()

    def __init__(self, parent=None, interactive=True):
        super().__init__(parent)
        self.options = preferences.normalize({}); self.clients = []; self.selected = 0; self.position = 0.
        self.pictures = {}; self.hitboxes = []; self.interactive = interactive
        self.stack_from = {}; self.stack_progress = 1.
        self.setMinimumSize(180, 100); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(False)
        self.setStyleSheet('background:transparent; border:none;')
        self.setAccessibleName('Task switcher window previews')
        self.animation = QVariantAnimation(self); self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.frame)
        self.stack_animation = QVariantAnimation(self); self.stack_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.stack_animation.valueChanged.connect(self.stack_frame)

    def configure(self, options, clients=None):
        if options['style'] != self.options['style']:
            self.animation.stop(); self.stack_animation.stop(); self.stack_from = {}
        self.options = copy.deepcopy(options)
        if clients is not None:
            self.animation.stop(); self.stack_animation.stop(); self.stack_from = {}
            self.clients = clients; self.selected = 0; self.position = 0.
            self.hitboxes = []
        self.update()

    def select(self, index, animate=True):
        if not self.clients: return
        previous = {t.index: t for t in self.tiles()}
        index %= len(self.clients); self.selected = index
        self.animation.stop()
        self.stack_animation.stop(); self.stack_from = {}
        target = self.position+geometry.distance(index, self.position, len(self.clients))
        if animate and self.options['duration'] and self.options['style'] in ('ring', 'cover', 'flip', 'application'):
            self.animation.setStartValue(self.position); self.animation.setEndValue(target)
            self.animation.setDuration(self.options['duration']); self.animation.start()
        else:
            self.position = float(index)
            if animate and self.options['duration'] and self.options['style'] == 'stack':
                self.stack_from = previous; self.stack_progress = 0.
                self.stack_animation.setStartValue(0.); self.stack_animation.setEndValue(1.)
                self.stack_animation.setDuration(self.options['duration']); self.stack_animation.start()
            self.update()

    def frame(self, value):
        self.position = float(value); self.update()

    def stack_frame(self, value):
        self.stack_progress = float(value); self.update()

    def tiles(self):
        tiles = geometry.layout(self.clients, self.position, self.selected, self.options)
        if self.options['style'] == 'stack' and self.stack_from and self.stack_progress < 1:
            for i, tile in enumerate(tiles):
                before = self.stack_from.get(tile.index)
                if before:
                    tiles[i] = replace(tile, **{key: getattr(before, key)+(getattr(tile, key)-getattr(before, key))*self.stack_progress
                                                for key in ('x', 'y', 'width', 'height', 'rotate_x')})
        return tiles

    def visible_addresses(self):
        if not self.clients: return []
        tiles = sorted(self.tiles(), key=lambda t: (t.index != self.selected, -t.depth))
        return [self.clients[t.index]['address'] for t in tiles]

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.paint_colors = theme_runtime.colors(); self.interface_font = theme_runtime.ui_font()
        self.corner_radius = 3 if theme_runtime.design() == 'binaryknife' else 8
        self.hitboxes = []; tiles = self.tiles()
        if not tiles: return
        shapes = [(t, QPolygonF([QPointF(x, y) for x, y in t.polygon()])) for t in tiles]
        extent = QRectF(0, 0, 1000, 480)
        for tile, poly in shapes: extent = extent.united(poly.boundingRect())
        cfg = self.options['profiles'][self.options['style']]
        reflection = cfg.get('reflection', False)
        if reflection: extent.setBottom(max(extent.bottom(), 400))
        factor = max(.05, min((self.width()-20)/extent.width(), (self.height()-16)/extent.height()))
        offset = QPointF((self.width()-extent.width()*factor)/2-extent.left()*factor,
                         (self.height()-extent.height()*factor)/2-extent.top()*factor)
        for tile, poly in shapes:
            target = QPolygonF([point*factor+offset for point in poly])
            if reflection:
                baseline = max(point.y() for point in target)+4
                reflected = QPolygonF([QPointF(point.x(), baseline+(baseline-point.y())*.45) for point in target])
                self.paint_tile(p, tile, reflected, cfg['reflection_intensity']/100*.55, reflected=True)
            self.paint_tile(p, tile, target)
            self.hitboxes.append((tile.index, target))

    def paint_tile(self, p, tile, target, opacity=1., reflected=False):
        selected = tile.index == self.selected; colors = self.paint_colors
        w, h = max(1., tile.width), max(1., tile.height)
        source = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
        transform = QTransform()
        if not QTransform.quadToQuad(source, target, transform): return
        client = self.clients[tile.index]; style = self.options['style']; cfg = self.options['profiles'][style]
        p.save(); p.setOpacity(opacity*tile.opacity*(1. if selected else self.options['inactive_opacity']/100))
        p.setTransform(transform, True)
        rect = QRectF(0, 0, w, h); radius = self.corner_radius
        path = QPainterPath(); path.addRoundedRect(rect, radius, radius)
        shadow = QColor('#000000'); shadow.setAlpha(100)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(shadow); p.drawRoundedRect(rect.translated(0, 5), radius, radius)
        p.setClipPath(path)
        fill = QLinearGradient(0, 0, w, h)
        fill.setColorAt(0, QColor(colors['AlternateBase'])); fill.setColorAt(1, QColor(colors['Base']))
        p.fillRect(rect, fill)
        icon = client.get('_icon', QIcon.fromTheme('application-x-executable'))
        picture = self.pictures.get(client['address'])
        icons_only = style == 'fusion' or cfg.get('icon_only', False)
        titles = self.options['show_titles']; band = min(30., h*.2) if titles else 0.
        if not icons_only and picture is not None and not picture.isNull():
            # Preserve the source aspect ratio; the title sits over its lower edge.
            area = QRectF(1, 1, w-2, h-2)
            fit = min(area.width()/picture.width(), area.height()/picture.height())
            image_rect = QRectF(0, 0, picture.width()*fit, picture.height()*fit); image_rect.moveCenter(area.center())
            p.drawPixmap(image_rect, picture, QRectF(picture.rect()))
        elif self.options['show_icons']:
            size = max(18., min(62., w*.28, (h-band)*.52))
            icon.paint(p, round((w-size)/2), round((h-band-size)/2), round(size), round(size))
        else:
            p.setPen(QColor(colors['PlaceholderText'])); p.setFont(QFont(self.interface_font, 11))
            p.drawText(rect.adjusted(8, 8, -8, -band), Qt.AlignmentFlag.AlignCenter,
                       client.get('class') or 'Window')
        if tile.brightness < 1:
            p.fillRect(rect, QColor(0, 0, 0, round(255*(1-tile.brightness))))
        if titles and not reflected:
            shade = QColor(colors['Window']); shade.setAlpha(232)
            title_rect = QRectF(0, h-band, w, band); p.fillRect(title_rect, shade)
            p.setFont(QFont(self.interface_font, 9, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
            inset = 9
            if self.options['show_icons'] and not icons_only:
                sz = max(10, round(band-8)); icon.paint(p, 6, round(h-band+4), sz, sz); inset = sz+12
            p.setPen(QColor(colors['Text']))
            text = p.fontMetrics().elidedText(client.get('title') or client.get('class', 'Window'),
                                             Qt.TextElideMode.ElideRight, max(1, round(w-inset-8)))
            p.drawText(title_rect.adjusted(inset, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, text)
        p.setClipping(False); p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(colors['Accent'] if selected else colors['Midlight']), 2.5 if selected else 1.))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius); p.restore()

    def mouseReleaseEvent(self, event):
        if self.interactive and event.button() == Qt.MouseButton.LeftButton:
            for index, polygon in reversed(self.hitboxes):
                if polygon.containsPoint(event.position(), Qt.FillRule.OddEvenFill):
                    self.activated.emit(index); event.accept(); return
            self.dismissed.emit(); event.accept(); return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if not self.interactive: event.ignore(); return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta: self.stepped.emit(-1 if delta > 0 else 1)
        event.accept()

    def hideEvent(self, event):
        self.animation.stop(); self.stack_animation.stop(); super().hideEvent(event)


def sample_clients():
    return [dict(address=f'0x{i+1:x}', mapped=True, title=title, **{'class': icon},
                 size=size, workspace={'id': i//2+1, 'name': str(i//2+1)}, monitor=i%3,
                 _icon=QIcon.fromTheme(icon))
            for i, (title, icon, size) in enumerate([
                ('Code · workspace', 'code', [1200, 760]), ('Terminal · build', 'kitty', [900, 600]),
                ('Files · projects', 'system-file-manager', [1000, 700]), ('Browser · reference', 'web-browser', [1200, 800]),
                ('Music · library', 'multimedia-player', [760, 700]), ('Settings · desktop', 'preferences-system', [1000, 650])])]


def sample_pictures(clients):
    """Clearly fictional, theme-aware window contents for the settings preview."""
    colors = theme_runtime.colors(); result = {}
    for index, client in enumerate(clients):
        picture = QPixmap(640, 400); picture.fill(QColor(colors['Base']))
        p = QPainter(picture); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0, 0, 640, 30, QColor(colors['AlternateBase']))
        p.setPen(QColor(colors['Text'])); p.setFont(QFont(theme_runtime.ui_font(), 10))
        p.drawText(12, 21, client['title']); p.fillRect(0, 32, 118, 368, QColor(colors['Window']))
        for row in range(8):
            p.setPen(QColor(colors['Accent'] if row == index else colors['PlaceholderText']))
            p.drawText(12, 62+row*29, ('Workspace', 'Projects', 'Library', 'Favorites', 'Recent', 'Tools', 'Settings', 'About')[row])
        if index in (0, 1):
            p.setFont(QFont('JetBrains Mono', 11))
            lines = ['// HYPER FUSION', '', 'void create_workspace() {', '    auto desktop = Fusion();',
                     '    desktop.open("possibilities");', '    desktop.animate();', '}', '', '> ready to build_']
            for row, line in enumerate(lines):
                p.setPen(QColor(colors['Accent'] if row%3 == 0 else colors['Text'])); p.drawText(140, 65+row*31, line)
        else:
            for row in range(2):
                for col in range(3):
                    rect = QRectF(140+col*160, 58+row*150, 142, 126)
                    p.setPen(QPen(QColor(colors['Midlight']), 1)); p.setBrush(QColor(colors['AlternateBase'])); p.drawRoundedRect(rect, 8, 8)
                    icon = clients[(col+row+index)%len(clients)]['_icon']; icon.paint(p, round(rect.x()+47), round(rect.y()+25), 48, 48)
                    p.setPen(QColor(colors['Text'])); p.drawText(rect.adjusted(5, 85, -5, -5), Qt.AlignmentFlag.AlignCenter, ['Projects', 'Workspace', 'Collection'][col])
        p.end(); result[client['address']] = picture
    return result
