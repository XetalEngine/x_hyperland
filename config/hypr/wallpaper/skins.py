"""Native artwork for the film studio and orbital wallpaper galleries."""
import math

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient, QTransform)
from PyQt6.QtWidgets import QWidget, QStyledItemDelegate, QStyle

from wallpaper.carousel import Carousel, cover


PALETTES = {
    'frame-lab': dict(base='#120f0d', panel='#211c17', edge='#70553c', accent='#ffb436',
                      bright='#ffe1a2', text='#f4e6cf', muted='#bcaa91'),
    'orbit-atlas': dict(base='#07131c', panel='#10222c', edge='#395761', accent='#9aefdd',
                        bright='#dbfff2', text='#e9f4ef', muted='#a5bdc0'),
}


def ink(palette, name, alpha=255):
    value = QColor(palette[name]); value.setAlpha(alpha); return value


def font(size, *, serif=False, bold=False):
    result = QFont('Noto Serif' if serif else 'Noto Sans')
    result.setPixelSize(size)
    if bold: result.setWeight(QFont.Weight.DemiBold)
    return result


def rounded(rect, radius=8):
    path = QPainterPath(); path.addRoundedRect(rect, radius, radius); return path


def glow(painter, path, palette, strength=1):
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for width, alpha in ((18, 7), (10, 12), (5, 23)):
        painter.setPen(QPen(ink(palette, 'accent', round(alpha * strength)), width)); painter.drawPath(path)


def image_card(painter, rect, pixmap, palette, active=False, radius=8):
    path = rounded(rect, radius)
    if active: glow(painter, path, palette)
    painter.save(); painter.setClipPath(path); painter.fillRect(rect, ink(palette, 'base'))
    if not pixmap.isNull(): cover(painter, rect, pixmap)
    painter.restore()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(ink(palette, 'bright' if active else 'edge', 235), 1.6 if active else 1))
    painter.drawPath(path)
    return path


def background(painter, rect, palette, thumbnails, picture):
    painter.fillRect(rect, ink(palette, 'base'))
    if picture:
        pixmap = thumbnails.get(picture.path)
        if not pixmap.isNull():
            soft = pixmap.scaled(32, 24, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            cover(painter, rect, soft, .16)
    shade = QLinearGradient(rect.topLeft(), rect.bottomRight())
    shade.setColorAt(0, ink(palette, 'base', 220)); shade.setColorAt(.55, ink(palette, 'base', 145))
    shade.setColorAt(1, ink(palette, 'base', 235)); painter.fillRect(rect, shade)
    halo = QRadialGradient(QPointF(rect.width() * .45, rect.height() * .82), rect.width() * .65)
    halo.setColorAt(0, ink(palette, 'accent', 23)); halo.setColorAt(1, ink(palette, 'accent', 0))
    painter.fillRect(rect, halo)
    painter.setPen(QPen(ink(palette, 'edge', 150), 1)); painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(.5, .5, -.5, -.5), 14, 14)


class Brand(QWidget):
    def __init__(self, style, parent=None):
        super().__init__(parent); self.style = style; self.palette = PALETTES[style]
        self.setFixedSize(294, 66)
        self.setAccessibleName('Frame Lab wallpaper studio' if style == 'frame-lab' else 'Orbit Atlas wallpaper gallery')
        self.setToolTip('Drag to move the wallpaper selector')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        else: super().mousePressEvent(event)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); palette = self.palette
        if self.style == 'frame-lab':
            metal = QRadialGradient(QPointF(23, 15), 55)
            metal.setColorAt(0, ink(palette, 'bright')); metal.setColorAt(.42, QColor('#a38161'))
            metal.setColorAt(1, QColor('#33271f'))
            p.setBrush(metal); p.setPen(QPen(ink(palette, 'muted'), 1)); p.drawEllipse(QPointF(29, 31), 24, 24)
            p.setBrush(ink(palette, 'base')); p.setPen(QPen(QColor('#33271f'), 1))
            for i in range(5):
                angle = i * math.tau / 5 - math.pi / 2
                p.drawEllipse(QPointF(29 + 15 * math.cos(angle), 31 + 15 * math.sin(angle)), 6, 6)
            p.drawEllipse(QPointF(29, 31), 3, 3)
            title, subtitle = 'FRAME LAB', 'W A L L P A P E R   S T U D I O'
        else:
            p.setPen(QPen(ink(palette, 'accent', 130), 1)); p.setBrush(ink(palette, 'panel', 150))
            p.drawEllipse(QPointF(28, 33), 20, 20)
            p.save(); p.translate(28, 33); p.rotate(-43)
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(ink(palette, 'bright'), 1.5))
            p.drawEllipse(QRectF(-32, -11, 64, 22)); p.restore()
            star = QPainterPath(); star.moveTo(51, 3); star.lineTo(53, 10); star.lineTo(60, 12)
            star.lineTo(53, 14); star.lineTo(51, 21); star.lineTo(49, 14); star.lineTo(42, 12)
            star.lineTo(49, 10); star.closeSubpath(); p.fillPath(star, ink(palette, 'bright'))
            title, subtitle = 'ORBIT ATLAS', 'W A L L P A P E R   G A L L E R Y'
        p.setPen(ink(palette, 'text')); p.setFont(font(26, serif=True))
        p.drawText(QRectF(72, 2, 220, 37), Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(ink(palette, 'muted')); p.setFont(font(8))
        p.drawText(QRectF(73, 40, 220, 20), Qt.AlignmentFlag.AlignVCenter, subtitle)


class CollectionDelegate(QStyledItemDelegate):
    def __init__(self, style, parent):
        super().__init__(parent); self.style = style; self.palette = PALETTES[style]

    def sizeHint(self, option, index): return QSize(170, 48)

    def paint(self, p, option, index):
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette; active = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = QRectF(option.rect).adjusted(1, 3, -1, -3); path = rounded(rect, 8 if self.style == 'frame-lab' else 14)
        shade = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if active:
            shade.setColorAt(0, ink(palette, 'accent', 235 if self.style == 'frame-lab' else 62))
            shade.setColorAt(1, ink(palette, 'accent', 150 if self.style == 'frame-lab' else 20))
            glow(p, path, palette, .65)
        else:
            shade.setColorAt(0, ink(palette, 'text', 25 if hover else 13)); shade.setColorAt(.45, ink(palette, 'panel', 180))
            shade.setColorAt(1, ink(palette, 'base', 175))
        p.fillPath(path, shade); p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(ink(palette, 'accent' if active else 'edge', 220 if active else 120), 1)); p.drawPath(path)
        foreground = ink(palette, 'base') if active and self.style == 'frame-lab' else ink(palette, 'text')
        p.setPen(QPen(foreground, 1.2))
        x, y = rect.left() + 12, rect.center().y() - 7
        if not index.data(Qt.ItemDataRole.UserRole):
            for dx in (0, 9):
                for dy in (0, 9): p.drawRoundedRect(QRectF(x + dx, y + dy, 6, 6), 1, 1)
        else:
            p.drawRoundedRect(QRectF(x, y + 2, 16, 12), 2, 2)
            p.drawLine(QPointF(x + 2, y + 2), QPointF(x + 7, y - 1)); p.drawLine(QPointF(x + 7, y - 1), QPointF(x + 12, y + 2))
        p.setFont(font(12, serif=self.style == 'frame-lab', bold=active)); p.setPen(foreground)
        text_rect = rect.adjusted(39, 0, -37, 0)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(index.data(), Qt.TextElideMode.ElideRight, int(text_rect.width())))
        p.setFont(font(10)); badge = QRectF(rect.right() - 32, rect.center().y() - 11, 27, 22)
        p.fillPath(rounded(badge, 6), ink(palette, 'base', 65))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(index.data(Qt.ItemDataRole.UserRole + 1)))
        if option.state & QStyle.StateFlag.State_HasFocus:
            p.setPen(QPen(ink(palette, 'bright'), 1, Qt.PenStyle.DotLine)); p.drawPath(path)
        p.restore()


class GalleryStage(Carousel):
    """Same selection model as the ribbon, with an explicit preview/apply action."""
    def __init__(self, thumbnails, style, parent=None):
        super().__init__(thumbnails, parent); self.style = style; self.palette = PALETTES[style]
        self.setMinimumSize(260, 230)
        self.setAccessibleName('Film preview' if style == 'frame-lab' else 'Orbit wallpaper gallery')
        self.setAccessibleDescription('Click a thumbnail to preview. Left and Right browse; Enter applies. Drag or scroll to browse.')

    def mouseReleaseEvent(self, event):
        if self.press is None: return
        self.press = None
        if self.dragged: self.go(round(self.position)); return
        for index, path in reversed(self.boxes):
            if path.contains(event.position()): self.go(index); return

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.current():
            for index, path in reversed(self.boxes):
                if path.contains(event.position()) and index % len(self.pictures) == self.index % len(self.pictures):
                    self.activate(); return

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.boxes = []
        if not self.pictures:
            p.setPen(ink(self.palette, 'muted')); p.setFont(font(14))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'No wallpapers here yet\nAdd a folder or clear your search.'); return
        if self.style == 'frame-lab': self.film_preview(p)
        else: self.orbit_preview(p)

    def film_preview(self, p):
        palette = self.palette; outer = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        edge = QLinearGradient(outer.topLeft(), outer.bottomRight())
        edge.setColorAt(0, ink(palette, 'bright', 150)); edge.setColorAt(.2, ink(palette, 'edge', 160))
        edge.setColorAt(.7, ink(palette, 'edge', 30)); edge.setColorAt(1, ink(palette, 'accent', 180))
        path = rounded(outer, 14); p.fillPath(path, ink(palette, 'base', 235))
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(edge, 2)); p.drawPath(path)
        p.setPen(QPen(ink(palette, 'edge', 80), 1)); p.drawPath(rounded(outer.adjusted(4, 4, -4, -4), 10))
        top = outer.adjusted(17, 7, -17, 0); top.setHeight(22)
        p.setFont(font(10)); p.setPen(ink(palette, 'accent'))
        p.drawText(top, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f'▸  FRAME {self.index % len(self.pictures) + 1:04d}')
        p.drawText(top, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, 'FRAME LAB  /  PREVIEW')
        image_rect = outer.adjusted(12, 34, -12, -35)
        picture = self.current(); pixmap = self.thumbnails.get(picture.path)
        self.boxes.append((self.index, image_card(p, image_rect, pixmap, palette, radius=5)))
        if pixmap.isNull():
            p.setPen(ink(palette, 'muted')); p.drawText(image_rect, Qt.AlignmentFlag.AlignCenter,
                'Cannot preview this image' if picture.path in self.thumbnails.failed else 'Loading preview…')
        bottom = QRectF(outer.left() + 17, outer.bottom() - 28, outer.width() - 34, 20)
        p.setPen(ink(palette, 'muted')); p.setFont(font(10))
        p.drawText(bottom, Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(picture.collection.upper(), Qt.TextElideMode.ElideRight, int(bottom.width() * .7)))
        p.drawText(bottom, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 'IMAGE WALLPAPER')

    def orbit_preview(self, p):
        w, h = self.width(), self.height(); palette = self.palette
        ellipse = QRectF(w * .07, h * .10, w * .86, h * .80)
        halo = QRadialGradient(QPointF(w * .5, h * .57), max(w, h) * .56)
        halo.setColorAt(0, ink(palette, 'accent', 32)); halo.setColorAt(1, ink(palette, 'accent', 0))
        p.fillRect(self.rect(), halo)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for thickness, alpha in ((12, 5), (6, 12), (2, 60), (1, 175)):
            p.setPen(QPen(ink(palette, 'accent', alpha), thickness)); p.drawEllipse(ellipse)
        for angle in (0.15, 2.1, 3.9, 5.25):
            angle += self.position * .13
            point = QPointF(ellipse.center().x() + ellipse.width() / 2 * math.cos(angle),
                            ellipse.center().y() + ellipse.height() / 2 * math.sin(angle))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(ink(palette, 'accent', 28)); p.drawEllipse(point, 7, 7)
            p.setBrush(ink(palette, 'bright')); p.drawEllipse(point, 2, 2)
        slots = [(.12, .26), (.39, .13), (.75, .17), (.90, .81), (.61, .85), (.18, .81)]
        offsets = (-3, -2, -1, 1, 2, 3); seen = {self.index % len(self.pictures)}
        card_width = min(168., w * .22); card_height = card_width * .5625
        for (sx, sy), offset in zip(slots, offsets):
            index = self.index + offset; identity = index % len(self.pictures)
            if identity in seen: continue
            seen.add(identity); picture = self.pictures[identity]
            drift = math.sin((self.position - self.index) * math.pi) * 12
            cy = max(card_height / 2 + 34, min(h - card_height / 2 - 32, sy * h))
            rect = QRectF(sx * w - card_width / 2 + drift, cy - card_height / 2, card_width, card_height)
            path = image_card(p, rect, self.thumbnails.get(picture.path), palette)
            self.boxes.append((index, path))
            p.setPen(QPen(ink(palette, 'accent', 105), 1))
            stem = QPointF(rect.left() + 7, rect.top() - 6 if sy < .5 else rect.bottom() + 6)
            end = stem + QPointF(0, -14 if sy < .5 else 14); p.drawLine(stem, end)
            p.setBrush(ink(palette, 'bright')); p.drawEllipse(end, 2, 2)
            p.setFont(font(10)); p.setPen(ink(palette, 'text'))
            caption = p.fontMetrics().elidedText(picture.title, Qt.TextElideMode.ElideRight, int(card_width - 24))
            p.drawText(QRectF(rect.left() + 18, rect.top() - 29 if sy < .5 else rect.bottom() + 9,
                             card_width - 18, 22), Qt.AlignmentFlag.AlignVCenter, caption)
        hero_width = min(w * .68, h * .56 * 16 / 9); hero_height = hero_width * 9 / 16
        hero = QRectF((w - hero_width) / 2, h * .51 - hero_height / 2, hero_width, hero_height)
        picture = self.current(); path = image_card(p, hero, self.thumbnails.get(picture.path), palette, active=True, radius=12)
        self.boxes.append((self.index, path))
        if picture.path in self.thumbnails.failed:
            p.setPen(ink(palette, 'muted')); p.drawText(hero, Qt.AlignmentFlag.AlignCenter, 'Cannot preview this image')
        if self.hasFocus():
            p.setPen(QPen(ink(palette, 'bright', 160), 1)); p.drawLine(QPointF(hero.center().x() - 20, hero.bottom() + 9), QPointF(hero.center().x() + 20, hero.bottom() + 9))


class Filmstrip(QWidget):
    def __init__(self, stage, parent=None):
        super().__init__(parent); self.stage = stage; self.boxes = []; self.press = None; self.dragged = False
        self.setFixedHeight(174); self.setMouseTracking(True); self.setAccessibleName('Wallpaper filmstrip')
        stage.animation.valueChanged.connect(lambda _: self.update()); stage.selected.connect(lambda _: self.update())
        stage.thumbnails.changed.connect(lambda _: self.update())

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height(); palette = self.stage.palette; self.boxes = []
        bend = 21; top = 4; bottom = h - 18
        belt = QPainterPath(); belt.moveTo(0, top + bend)
        belt.cubicTo(w * .22, top - 5, w * .78, top - 5, w, top + bend)
        belt.lineTo(w, bottom + bend); belt.cubicTo(w * .78, bottom - 5, w * .22, bottom - 5, 0, bottom + bend); belt.closeSubpath()
        metal = QLinearGradient(0, 0, 0, h)
        metal.setColorAt(0, QColor('#61401f')); metal.setColorAt(.15, ink(palette, 'base'))
        metal.setColorAt(.8, ink(palette, 'base')); metal.setColorAt(1, QColor('#59381c'))
        p.fillPath(belt, metal); p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(ink(palette, 'edge'), 1)); p.drawPath(belt)
        for x in range(8, w, 21):
            y = top + bend * ((x - w / 2) / max(1, w / 2)) ** 2
            for yy in (y + 5, y + h - 32):
                p.setBrush(ink(palette, 'base')); p.setPen(QPen(ink(palette, 'edge', 180), .7))
                p.drawRoundedRect(QRectF(x, yy, 10, 10), 2, 2)
        if not self.stage.pictures: return
        count = len(self.stage.pictures); card_height = h - 64; card_width = card_height * 16 / 9; spacing = card_width + 14
        first = math.floor(self.stage.position) - min(4, (count - 1) // 2)
        for index in range(first, first + min(count, 9)):
            delta = index - self.stage.position; x = w / 2 + delta * spacing
            y = 34 + bend * ((x - w / 2) / max(1, w / 2)) ** 2
            rect = QRectF(x - card_width / 2, y, card_width, card_height)
            transform = QTransform(); transform.translate(rect.center().x(), rect.center().y())
            transform.rotate(3.3 * (x - w / 2) / max(1, w / 2)); transform.translate(-rect.center().x(), -rect.center().y())
            p.save(); p.setTransform(transform, True)
            picture = self.stage.pictures[index % count]; active = index % count == self.stage.index % count
            path = image_card(p, rect, self.stage.thumbnails.get(picture.path), palette, active=active, radius=4)
            p.setFont(font(10, bold=active)); p.setPen(ink(palette, 'bright' if active else 'muted'))
            p.drawText(QRectF(rect.left(), rect.top() - 18, rect.width(), 15), Qt.AlignmentFlag.AlignCenter, f'{index % count + 1:03d}')
            p.restore(); self.boxes.append((index, transform.map(path)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.stage.setFocus(); self.stage.interacted.emit(); self.stage.animation.stop()
            self.press = event.position(); self.start = self.stage.position; self.dragged = False

    def mouseMoveEvent(self, event):
        if self.press is not None:
            delta = event.position().x() - self.press.x(); self.dragged |= abs(delta) > 7
            if self.dragged:
                self.stage.position = self.start - delta / max(80, (self.height() - 64) * 16 / 9 + 14)
                self.stage.update(); self.update()
        else:
            hit = any(path.contains(event.position()) for _, path in self.boxes)
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.press is None: return
        self.press = None
        if self.dragged: self.stage.go(round(self.stage.position)); return
        for index, path in reversed(self.boxes):
            if path.contains(event.position()): self.stage.go(index); return

    def wheelEvent(self, event): self.stage.wheelEvent(event)
