"""A fluid ribbon of angled image cards, painted from bounded thumbnail caches."""
from collections import OrderedDict
import math
from pathlib import Path

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImageReader, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient, QRadialGradient
from PyQt6.QtWidgets import QWidget
from wallpaper.jobs import Jobs
import runtime


def color(key, alpha=255):
    result = QColor(runtime.colors()[key]); result.setAlpha(alpha); return result


def cover(painter, rect, pixmap, opacity=1):
    if pixmap.isNull(): return
    ratio = max(rect.width()/pixmap.width(), rect.height()/pixmap.height())
    source = QRectF(0, 0, rect.width()/ratio, rect.height()/ratio); source.moveCenter(QRectF(pixmap.rect()).center())
    painter.save(); painter.setOpacity(opacity); painter.drawPixmap(rect, pixmap, source); painter.restore()


class Thumbnails(QWidget):
    changed = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent); self.hide(); self.cache = OrderedDict(); self.pending = set(); self.failed = set(); self.jobs = Jobs(self)

    def get(self, path):
        if path in self.cache:
            self.cache.move_to_end(path); return self.cache[path]
        if path and path not in self.pending and path not in self.failed and len(self.pending) < 18:
            self.pending.add(path)
            self.jobs.run(lambda: self.read(path), lambda image: self.ready(path, image), lambda _: self.bad(path))
        return QPixmap()

    @staticmethod
    def read(path):
        reader = QImageReader(path); reader.setAutoTransform(True)
        size = reader.size()
        if size.width()*size.height() > 100_000_000: raise ValueError('Image too large to preview')
        if size.isValid(): reader.setScaledSize(size.scaled(QSize(1100, 800), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull(): raise ValueError(reader.errorString())
        return image

    def ready(self, path, image):
        self.pending.discard(path); self.cache[path] = QPixmap.fromImage(image)
        while len(self.cache) > 32: self.cache.popitem(last=False)
        self.changed.emit(path)

    def bad(self, path):
        self.pending.discard(path); self.failed.add(path); self.changed.emit(path)


class Carousel(QWidget):
    activated = pyqtSignal(object)
    selected = pyqtSignal(object)
    interacted = pyqtSignal()

    def __init__(self, thumbnails, parent=None):
        super().__init__(parent); self.thumbnails = thumbnails; self.pictures = []; self.position = 0.; self.index = 0; self.boxes = []
        self.press = None; self.dragged = False; self.start_position = 0.; self.reduced_motion = False; self.backdrop = True
        self.setMinimumHeight(250); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setMouseTracking(True)
        self.setAccessibleName('Wallpaper carousel'); self.setAccessibleDescription('Use Left and Right to browse. Enter selects a wallpaper. Scroll or drag to browse.')
        self.animation = QVariantAnimation(self); self.animation.setDuration(430); self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.animate); self.animation.finished.connect(self.settled)
        self.thumbnails.changed.connect(lambda _: self.update())

    def populate(self, pictures, selected=''):
        self.animation.stop(); self.pictures = pictures
        self.index = next((i for i, p in enumerate(pictures) if p.path == selected), 0)
        self.position = float(self.index); self.settled(); self.update()

    def current(self):
        return self.pictures[self.index % len(self.pictures)] if self.pictures else None

    def animate(self, value): self.position = float(value); self.update()

    def settled(self):
        if self.current(): self.selected.emit(self.current())

    def go(self, index, manual=True):
        if not self.pictures: return
        if manual: self.interacted.emit()
        self.index = index; self.animation.stop()
        if self.reduced_motion:
            self.position = float(self.index); self.settled(); self.update(); return
        self.animation.setStartValue(self.position); self.animation.setEndValue(float(self.index)); self.animation.start()
        self.settled()

    def step(self, amount, manual=True): self.go(self.index+amount, manual)

    def activate(self):
        if self.current(): self.activated.emit(self.current())

    def paintEvent(self, _):
        painter = QPainter(self); painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.boxes = []
        if not self.pictures:
            painter.setPen(color('Disabled')); painter.setFont(QFont(runtime.ui_font(), 14))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'No wallpapers here yet\nAdd a folder or clear your search.'); return
        w, h = self.width(), self.height()
        hero = min(640., w*.47); small = min(190., w*.145); height = min(h*.79, hero*.74)
        center_y = h*.46
        if self.backdrop:
            glow = QRadialGradient(QPointF(w/2, center_y+height/2), hero*.85)
            glow.setColorAt(0, color('Accent', 45)); glow.setColorAt(1, color('Accent', 0))
            painter.fillRect(self.rect(), glow)
        cards = []
        first = math.floor(self.position)-min(5,(len(self.pictures)-1)//2)
        for i in range(first, first+min(11,len(self.pictures))):
            delta = i-self.position; weight = max(0., 1-abs(delta)); weight = weight*weight*(3-2*weight)
            width = small+(hero-small)*weight; ch = height*(.86+.14*weight)
            x = w/2+(small+14)*delta+math.copysign((hero-small)/2*min(abs(delta), 1), delta) if delta else w/2
            rect = QRectF(x-width/2, center_y-ch/2, width, ch)
            slant = min(66., width*.24)
            path = QPainterPath(); path.moveTo(rect.left()+slant, rect.top()); path.lineTo(rect.right()+slant, rect.top())
            path.lineTo(rect.right()-slant, rect.bottom()); path.lineTo(rect.left()-slant, rect.bottom()); path.closeSubpath()
            cards.append((abs(delta), i, rect, path, weight))
        for distance, i, rect, path, weight in sorted(cards, reverse=True):
            picture = self.pictures[i % len(self.pictures)]; pixmap = self.thumbnails.get(picture.path)
            painter.save(); painter.translate(0, 12); painter.fillPath(path, QColor(0, 0, 0, 90)); painter.restore()
            painter.save(); painter.setClipPath(path); painter.fillRect(path.boundingRect(), color('Base'))
            if not pixmap.isNull(): cover(painter, path.boundingRect(), pixmap)
            else:
                painter.setPen(color('Disabled')); painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'Cannot preview' if picture.path in self.thumbnails.failed else 'Loading…')
            painter.fillRect(path.boundingRect(), QColor(0, 0, 0, round(75*(1-weight))))
            shade = QLinearGradient(0, rect.bottom()-95, 0, rect.bottom()); shade.setColorAt(0, QColor(0, 0, 0, 0)); shade.setColorAt(1, QColor(0, 0, 0, 175))
            painter.fillRect(path.boundingRect(), shade)
            if weight > .6:
                painter.setPen(QColor('#ffffff')); painter.setFont(QFont(runtime.ui_font(), 11, QFont.Weight.DemiBold))
                painter.drawText(rect.adjusted(24, 0, -38, -18), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, picture.collection)
            painter.restore()
            painter.setPen(QPen(color('Accent', round(90+150*weight)), 1+weight)); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawPath(path)
            # A subtle floor reflection joins the cards to the background.
            if not pixmap.isNull():
                painter.save(); painter.setClipRect(QRectF(0, rect.bottom()+10, w, 48)); painter.translate(0, 2*rect.bottom()+12); painter.scale(1, -1)
                painter.setClipPath(path, Qt.ClipOperation.IntersectClip); cover(painter, path.boundingRect(), pixmap, .10); painter.restore()
            self.boxes.append((i, path))
        if self.hasFocus():
            painter.setPen(color('Accent', 100)); painter.drawLine(round(w/2-24), h-14, round(w/2+24), h-14)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(); self.interacted.emit(); self.animation.stop(); self.press = event.position(); self.start_position = self.position; self.dragged = False

    def mouseMoveEvent(self, event):
        if self.press is not None:
            delta = event.position().x()-self.press.x(); self.dragged |= abs(delta)>7
            if self.dragged:
                self.position = self.start_position-delta/max(100, self.width()*.22); self.update()
        else:
            hit = any(path.contains(event.position()) for _, path in self.boxes)
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.press is None: return
        self.press = None
        if self.dragged: self.go(round(self.position)); return
        for index, path in reversed(self.boxes):
            if path.contains(event.position()):
                # Every card is selectable. The expanded card also has a keyboard action.
                self.index = index; self.go(index); self.activate(); return

    def wheelEvent(self, event):
        delta = event.pixelDelta().x() or event.pixelDelta().y() or event.angleDelta().y() or event.angleDelta().x()
        if delta: self.step(-1 if delta>0 else 1)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left: self.step(-1)
        elif event.key() == Qt.Key.Key_Right: self.step(1)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self.activate()
        elif event.key() == Qt.Key.Key_Home: self.go(0)
        elif event.key() == Qt.Key.Key_End: self.go(len(self.pictures)-1)
        else: super().keyPressEvent(event)
