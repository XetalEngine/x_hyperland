"""A compact, draggable file-operation card with an original vector animation."""
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'theme'))
import runtime as theme_runtime

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton, QToolButton, QWidget
from model import short_location


def alpha(color, value):
    result = QColor(color); result.setAlpha(value); return result


class ProgressWindow(QWidget):
    dismissed = pyqtSignal()

    def __init__(self, job):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.job = job
        self.setObjectName('FileOperation')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setProperty('xetalCloseButton', True)
        self.setFixedSize(448, 168)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAccessibleName('Xetal file operation')
        self.phase = 0.0
        self.display_percent = 0.0
        self.closed = False
        self.drag_offset = None
        self.clock = QElapsedTimer(); self.clock.start()
        self.animation = QTimer(self); self.animation.setInterval(33)
        self.animation.timeout.connect(self.tick)
        self.dismiss_timer = QTimer(self); self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)
        self.cancel = QPushButton('Cancel', self)
        self.cancel.setObjectName('cancelOperation')
        self.cancel.clicked.connect(self.close)
        self.pause = QToolButton(self)
        self.pause.clicked.connect(self.toggle_pause)
        self.close_button = QToolButton(self); self.close_button.setText('×')
        self.close_button.setObjectName('closeOperation'); self.close_button.clicked.connect(self.close)
        self.details = QPushButton('Details', self); self.details.clicked.connect(self.show_error)
        self.details.hide()
        for button in (self.cancel, self.pause, self.close_button, self.details):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('''
            QWidget#FileOperation {background:transparent;}
            QPushButton,QToolButton {background:palette(button); color:palette(button-text);
                border:1px solid palette(mid); border-radius:6px; padding:0; font:11px "Noto Sans";}
            QPushButton:hover,QToolButton:hover {background:palette(highlight); color:palette(highlighted-text);}
            QPushButton:disabled,QToolButton:disabled {color:palette(placeholder-text); background:transparent;}
            QToolButton#closeOperation {background:transparent; border:none; font-size:22px;}
            QToolButton#closeOperation:hover {background:#803b51; color:#fff1f4;}
        ''')
        self.job.changed.connect(self.refresh)
        self.job.finished.connect(self.completed)
        self.refresh()

    def refresh(self):
        self.setWindowTitle(self.job.title + ' — Xetal Files')
        self.setAccessibleDescription(self.job.summary())
        paths = [p for p in self.job.paths if p]
        self.setToolTip('\n→ '.join(paths))
        done = self.job.result is not None
        cancelable = bool(self.job.capabilities & 1)
        self.cancel.setText('Close' if done else 'Cancel')
        self.cancel.setEnabled(done or (cancelable and self.job.pending != 'cancel'))
        self.close_button.setEnabled(self.cancel.isEnabled())
        caption = 'Close progress' if done else 'Cancel operation'
        self.cancel.setToolTip(caption); self.close_button.setToolTip(caption)
        self.close_button.setAccessibleName(caption)
        self.pause.setVisible(bool(self.job.capabilities & 2) and not done)
        self.pause.setEnabled(not self.job.pending)
        suspended = self.job.data.get('suspended', False)
        self.pause.setText('▶' if suspended else 'Ⅱ')
        self.pause.setToolTip('Resume operation' if suspended else 'Pause operation')
        self.pause.setAccessibleName(self.pause.toolTip())
        self.details.setVisible(self.job.result == 'failed')
        self.layout_controls()
        if self.isVisible() and self.job.running: self.animation.start()
        elif done or not self.job.running: self.animation.stop()
        self.update()

    def layout_controls(self):
        self.close_button.setGeometry(self.width()-40, 8, 28, 28)
        self.cancel.setGeometry(self.width()-78, 130, 62, 24)
        self.pause.setGeometry(self.width()-113, 130, 28, 24)
        self.details.setGeometry(self.width()-139, 130, 54, 24)

    def showEvent(self, event):
        super().showEvent(event)
        self.clock.restart()
        if self.job.running: self.animation.start()

    def hideEvent(self, event):
        self.animation.stop()
        super().hideEvent(event)

    def tick(self):
        elapsed = min(.1, self.clock.restart()/1000)
        self.phase = (self.phase + elapsed / 2.1) % 1
        target = self.job.percent
        if target is not None:
            self.display_percent += (target - self.display_percent) * min(1, elapsed*10)
        self.update()

    def completed(self):
        self.animation.stop()
        if self.job.result == 'failed':
            self.show()
        elif not self.isVisible():
            QTimer.singleShot(0, self.dismiss)
        else:
            self.display_percent = self.job.percent or 0
            self.dismiss_timer.start(1600 if self.job.result == 'done' else 800)
        self.refresh()

    def toggle_pause(self):
        self.job.request('resume' if self.job.data.get('suspended') else 'suspend')

    def show_error(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle('File operation')
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(self.job.summary())
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.exec()

    def dismiss(self):
        if self.closed: return
        self.closed = True
        self.dismiss_timer.stop(); self.animation.stop()
        self.hide()
        self.dismissed.emit()
        self.deleteLater()

    def closeEvent(self, event):
        event.ignore()
        if self.job.result is not None: self.dismiss()
        else: self.job.request('cancel')

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close(); event.accept()
        else: super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.windowHandle() and self.windowHandle().startSystemMove():
                event.accept(); return
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint()-self.drag_offset); event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        self.layout_controls()
        super().resizeEvent(event)

    def text(self, painter, rect, text, color, size=11, bold=False, alignment=Qt.AlignmentFlag.AlignLeft):
        painter.setFont(QFont(theme_runtime.ui_font(), size, QFont.Weight.DemiBold if bold else QFont.Weight.Normal))
        painter.setPen(color)
        value = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, int(rect.width()))
        painter.drawText(rect, alignment | Qt.AlignmentFlag.AlignVCenter, value)

    def folder(self, painter, center, accent, archive=False):
        painter.save(); painter.translate(center)
        glow = QRadialGradient(QPointF(0, 4), 34)
        glow.setColorAt(0, alpha(accent, 72)); glow.setColorAt(1, alpha(accent, 0))
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(glow); painter.drawEllipse(QRectF(-34, -30, 68, 68))
        back = QPainterPath(); back.moveTo(-20, 13); back.lineTo(-20, -14)
        back.quadTo(-20, -17, -16, -17); back.lineTo(-7, -17); back.lineTo(-2, -12)
        back.lineTo(17, -12); back.quadTo(20, -12, 20, -8); back.lineTo(20, 13); back.closeSubpath()
        painter.setPen(QPen(alpha(accent.lighter(140), 180), 1))
        painter.setBrush(accent.darker(180)); painter.drawPath(back)
        front = QPainterPath(); front.moveTo(-19, 14); front.lineTo(-23, -3)
        front.quadTo(-24, -7, -19, -7); front.lineTo(19, -7)
        front.quadTo(24, -7, 23, -3); front.lineTo(19, 14); front.closeSubpath()
        fill = QLinearGradient(0, -8, 0, 17)
        fill.setColorAt(0, accent.lighter(120)); fill.setColorAt(1, accent.darker(140))
        painter.setBrush(fill); painter.drawPath(front)
        if archive:
            painter.setPen(QPen(QColor('#f4cf87'), 2))
            for y in range(-10, 12, 4): painter.drawLine(QPointF(-1, y), QPointF(3, y))
        painter.restore()

    def transfer(self, painter, box, accent):
        left, right = QPointF(box.left()+36, box.center().y()+5), QPointF(box.right()-36, box.center().y()+5)
        path = QPainterPath(left); path.cubicTo(left+QPointF(65, -27), right+QPointF(-65, -27), right)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(alpha(accent, 25), 5)); painter.drawPath(path)
        painter.setPen(QPen(alpha(accent, 90), 1, Qt.PenStyle.DotLine)); painter.drawPath(path)
        self.folder(painter, left, accent)
        self.folder(painter, right, accent, any(word in self.job.title.lower() for word in ('compress', 'archiv')))
        if self.job.result == 'done':
            painter.setPen(QPen(QColor('#78d7b6'), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            mid = box.center(); painter.drawLine(mid+QPointF(-7, 0), mid+QPointF(-1, 6))
            painter.drawLine(mid+QPointF(-1, 6), mid+QPointF(11, -7)); return
        if self.job.result: return
        for i in range(3):
            progress = (self.phase + i/3) % 1
            opacity = min(1, progress*7, (1-progress)*7)
            point = path.pointAtPercent(progress)
            painter.save(); painter.setOpacity(opacity)
            painter.translate(point); painter.rotate(-14+28*progress)
            for trail in range(3, 0, -1):
                painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(alpha(accent, 12*(4-trail)))
                painter.drawRoundedRect(QRectF(-8-trail*4, -11+trail, 15, 20), 2, 2)
            page = QPainterPath(); page.moveTo(-7, -11); page.lineTo(3, -11)
            page.lineTo(8, -6); page.lineTo(8, 10); page.lineTo(-7, 10); page.closeSubpath()
            painter.setPen(QPen(accent.lighter(160), .8)); painter.setBrush(accent.lighter(190)); painter.drawPath(page)
            painter.setPen(QPen(accent.darker(180), 1)); painter.drawLine(QPointF(3, -11), QPointF(3, -6))
            painter.drawLine(QPointF(3, -6), QPointF(8, -6))
            for y in (-2, 2, 6): painter.drawLine(QPointF(-4, y), QPointF(4, y))
            painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        palette = QApplication.palette(); background = palette.window().color()
        accent = palette.highlight().color(); foreground = palette.windowText().color()
        breakpoint=theme_runtime.design()=='breakpoint';radius=12 if breakpoint else 16
        if breakpoint:accent=QColor(theme_runtime.colors()['Accent']);background.setAlpha(240)
        muted = palette.placeholderText().color()
        surface = QLinearGradient(0, 0, self.width(), self.height())
        surface.setColorAt(0, background.lighter(112)); surface.setColorAt(1, background.darker(110))
        painter.setBrush(surface); painter.setPen(QPen(alpha(accent, 135), 1))
        painter.drawRoundedRect(QRectF(.5, .5, self.width()-1, self.height()-1), radius, radius)
        bloom = QRadialGradient(QPointF(self.width()/2, 75), 155)
        bloom.setColorAt(0, alpha(accent, 19)); bloom.setColorAt(1, alpha(accent, 0))
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(bloom)
        painter.drawRoundedRect(QRectF(2, 2, self.width()-4, self.height()-4), radius-1, radius-1)
        self.text(painter, QRectF(16, 9, self.width()-134, 25), self.job.title, foreground, 11, True)
        percentage = self.job.percent
        value = '—' if percentage is None else f'{percentage:.0f}%'
        self.text(painter, QRectF(self.width()-112, 7, 65, 28), value, accent.lighter(125), 16, True,
                  Qt.AlignmentFlag.AlignRight)
        source, destination = self.job.paths
        route = '  →  '.join(short_location(p) for p in (source, destination) if p)
        self.text(painter, QRectF(16, 35, self.width()-32, 18), route or self.job.application, muted, 9)
        if self.job.result == 'failed':
            self.text(painter, QRectF(20, 61, self.width()-40, 37), self.job.summary(), QColor('#ee9aab'), 10)
        else:
            self.transfer(painter, QRectF(16, 55, self.width()-32, 52), accent)
        track = QRectF(16, 114, self.width()-32, 5)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(palette.base()); painter.drawRoundedRect(track, 2.5, 2.5)
        painter.save(); clip = QPainterPath(); clip.addRoundedRect(track, 2.5, 2.5); painter.setClipPath(clip)
        if percentage is None and self.job.result is None:
            fill = QRectF(track.left() + (track.width()+100)*self.phase-100, track.top(), 100, track.height())
        else:
            current = percentage or 0 if not self.job.running else self.display_percent
            fill = QRectF(track.left(), track.top(), track.width()*current/100, track.height())
        beam = QLinearGradient(fill.topLeft(), fill.topRight())
        beam.setColorAt(0, accent.darker(130)); beam.setColorAt(1, accent.lighter(150))
        painter.setBrush(beam); painter.drawRect(fill); painter.restore()
        reserved = 128 if self.pause.isVisible() or self.details.isVisible() else 94
        self.text(painter, QRectF(16, 129, self.width()-reserved-16, 25), self.job.summary(), muted, 8)
