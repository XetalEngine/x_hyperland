"""A compact, draggable file-operation card with an original vector animation."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'theme'))
import runtime as theme_runtime

from PyQt6.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QApplication, QFrame, QMessageBox, QPushButton, QScrollArea, QToolButton, QWidget
try:
    from .model import short_location, amount
    from . import preferences, artwork
    from .questions import QuestionPanel
except ImportError:
    from model import short_location, amount
    import preferences, artwork
    from questions import QuestionPanel


def alpha(color, value):
    result = QColor(color); result.setAlpha(value); return result


class ProgressWindow(QWidget):
    dismissed = pyqtSignal()
    geometry_changed = pyqtSignal()

    def __init__(self, job, *, options=None, preview=False, embedded=False):
        super().__init__(None, Qt.WindowType.Widget if embedded else Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.job = job
        self.preview, self.embedded = preview, embedded
        self.options = preferences.normalize(options if options is not None else preferences.current())
        self.setObjectName('FileOperation')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setProperty('xetalCloseButton', True)
        self.setCursor(Qt.CursorShape.ArrowCursor if embedded else Qt.CursorShape.OpenHandCursor)
        self.setAccessibleName('Xetal file operation')
        self.phase = 0.0
        self.display_percent = 0.0
        self.closed = False
        self.drag_offset = None
        self.base_height = 168
        self.question_panel = None
        self.question_scroll = QScrollArea(self)
        self.question_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.question_scroll.setWidgetResizable(True)
        self.question_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.question_scroll.setStyleSheet('QScrollArea {background:transparent;border:none;}')
        self.question_scroll.viewport().setAutoFillBackground(False)
        self.question_scroll.hide()
        self.expansion = QVariantAnimation(self)
        self.expansion.setDuration(190)
        self.expansion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.expansion.valueChanged.connect(lambda value: self.setFixedHeight(round(value)))
        self.expansion.finished.connect(self.expansion_finished)
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
        self.set_options(self.options)
        self.job.changed.connect(self.refresh)
        self.job.finished.connect(self.completed)
        self.job.question_changed.connect(self.refresh_question)
        if hasattr(QApplication.instance(), 'hypr_theme'):
            QApplication.instance().hypr_theme.changed.connect(self.theme_changed)
        self.refresh()
        self.refresh_question(animate=False)

    def theme_changed(self):
        self.set_options(self.options)

    def set_options(self, options):
        previous = self.options['behavior']
        self.options = preferences.normalize(options)
        self.design = preferences.selected(self.options, theme_runtime.design())
        self.appearance = self.options['profiles'][self.design]
        self.colors = theme_runtime.colors(style=self.design)
        self.accent = QColor(self.appearance['accent'] or self.colors['Accent'])
        if self.question_panel: self.question_panel.accent = self.accent
        self.setPalette(theme_runtime.palette(style=self.design))
        width, height = self.appearance['width'], self.appearance['height']
        if not self.embedded and self.screen():
            area = self.screen().availableGeometry()
            width, height = min(width, max(240, area.width()-24)), min(height, max(148, area.height()-24))
        self.base_height = height
        self.setFixedWidth(width)
        self.resize_question(animate=False)
        p = self.colors
        self.setStyleSheet(f'''
            QWidget#FileOperation {{background:transparent;}}
            QPushButton,QToolButton {{background:{p['Button']}; color:{p['ButtonText']};
                border:1px solid {p['Midlight']}; border-radius:{2 if self.design == 'shadowedge' else 14 if self.design == 'candycloud' else 3 if self.design == 'obsidianforge' else 2 if self.design == 'porcelainink' else 3 if self.design == 'binaryknife' else 9 if self.design == 'modern' else 6}px;
                padding:0; font:11px "{theme_runtime.ui_font(self.design)}";}}
            QPushButton:hover,QToolButton:hover {{background:{p['Highlight']}; color:{p['HighlightedText']}; border-color:{self.accent.name()};}}
            QPushButton:disabled,QToolButton:disabled {{color:{p['Disabled']}; background:transparent;}}
            QToolButton#closeOperation {{background:transparent; border:none; font-size:22px;}}
            QToolButton#closeOperation:hover {{background:{p['Highlight']}; color:{p['Text']};}}
            QWidget#transferQuestion {{background:transparent;}}
            QWidget#transferQuestion QLabel {{background:transparent; border:none; padding:0; color:{p['Text']};
                font:11px "{theme_runtime.ui_font(self.design)}"; font-weight:normal;}}
            QWidget#transferQuestion QLabel#questionHeading {{font-size:14px; font-weight:600;}}
            QWidget#transferQuestion QLabel#choiceTitle {{font-size:12px; font-weight:600;}}
            QWidget#transferQuestion QLabel#choiceDescription,QWidget#transferQuestion QLabel#questionPath {{color:{p['PlaceholderText']};}}
            QPushButton#transferChoice {{background:{p['Button']}; padding:0; text-align:left;}}
            QPushButton#transferChoice:hover,QPushButton#transferChoice:focus {{background:{p['AlternateBase']}; border-color:{self.accent.name()};}}
            QCheckBox {{color:{p['Text']}; font:11px "{theme_runtime.ui_font(self.design)}"; spacing:7px;}}
        ''')
        if not self.options['behavior']['auto_close']: self.dismiss_timer.stop()
        elif (self.job.result is not None and self.job.result != 'failed' and not self.preview
              and self.isVisible() and previous != self.options['behavior']):
            self.dismiss_timer.start(self.options['behavior']['close_delay'])
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
        self.pause.setEnabled(not self.job.pending and not self.job.question)
        suspended = self.job.data.get('suspended', False)
        self.pause.setText('▶' if suspended else 'Ⅱ')
        self.pause.setToolTip('Resume operation' if suspended else 'Pause operation')
        self.pause.setAccessibleName(self.pause.toolTip())
        self.details.setVisible(self.job.result == 'failed')
        self.layout_controls()
        if self.isVisible() and self.job.running and self.options['animation']['enabled']:
            if not self.animation.isActive(): self.clock.restart(); self.animation.start()
        else: self.animation.stop()
        if not self.options['animation']['smooth'] or not self.animation.isActive():
            self.display_percent = self.job.percent or 0
        self.update()

    def layout_controls(self):
        self.close_button.setGeometry(self.width()-40, 8, 28, 28)
        self.cancel.setGeometry(self.width()-78, self.base_height-38, 62, 24)
        self.pause.setGeometry(self.width()-113, self.base_height-38, 28, 24)
        self.details.setGeometry(self.width()-139, self.base_height-38, 54, 24)
        self.question_scroll.setGeometry(8, self.base_height, self.width()-16, max(0, self.height()-self.base_height-8))

    def refresh_question(self, animate=True):
        if self.job.question:
            old = self.question_scroll.takeWidget()
            if old: old.hide(); old.deleteLater()
            self.question_panel = QuestionPanel(self.job, self.accent)
            self.question_scroll.setWidget(self.question_panel)
            self.question_scroll.show()
            self.dismiss_timer.stop()
            if not self.embedded and not self.preview:
                self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
                self.show(); self.raise_(); self.activateWindow()
                self.cancel.setFocus(Qt.FocusReason.OtherFocusReason)
        elif self.question_panel:
            self.question_panel.setEnabled(False)
        self.resize_question(animate)
        self.refresh()

    def resize_question(self, animate=True):
        target = self.base_height
        if self.job.question and self.question_panel:
            self.question_panel.setFixedWidth(max(200, self.width()-32))
            layout = self.question_panel.layout()
            layout.activate()
            target += max(layout.sizeHint().height(), layout.totalHeightForWidth(self.width()-32)) + 8
            if not self.embedded and self.screen(): target = min(target, self.screen().availableGeometry().height()-24)
        self.expansion.stop()
        if animate and self.isVisible() and not self.embedded and self.options['animation']['enabled'] and self.height() != target:
            self.expansion.setStartValue(float(self.height())); self.expansion.setEndValue(float(target)); self.expansion.start()
        else:
            self.setFixedHeight(target); self.expansion_finished()

    def expansion_finished(self):
        if not self.job.question: self.question_scroll.hide()
        self.geometry_changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self.clock.restart()
        self.refresh()

    def hideEvent(self, event):
        self.animation.stop()
        super().hideEvent(event)

    def tick(self):
        elapsed = min(.1, self.clock.restart()/1000)
        self.phase = (self.phase + elapsed / 2.1 * self.options['animation']['speed']/100) % 1
        target = self.job.percent
        if target is not None:
            self.display_percent = (self.display_percent + (target-self.display_percent)*min(1, elapsed*10)
                                    if self.options['animation']['smooth'] else target)
        self.update()

    def completed(self):
        self.animation.stop()
        if self.preview:
            self.display_percent = self.job.percent or 0
        elif self.job.result == 'failed' or not self.options['behavior']['auto_close']:
            self.show()
        elif not self.isVisible():
            QTimer.singleShot(0, self.dismiss)
        else:
            self.display_percent = self.job.percent or 0
            self.dismiss_timer.start(self.options['behavior']['close_delay'])
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
        self.dismiss_timer.stop(); self.animation.stop(); self.expansion.stop()
        self.hide()
        self.dismissed.emit()
        self.deleteLater()

    def closeEvent(self, event):
        event.ignore()
        if self.embedded: return
        if self.preview: self.dismiss(); return
        if self.job.result is not None: self.dismiss()
        else: self.job.request('cancel')

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close(); event.accept()
        else: super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.embedded:
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
        self.geometry_changed.emit()
        super().resizeEvent(event)

    def text(self, painter, rect, text, color, size=11, bold=False, alignment=Qt.AlignmentFlag.AlignLeft):
        painter.setFont(QFont(theme_runtime.ui_font(self.design), size, QFont.Weight.DemiBold if bold else QFont.Weight.Normal))
        painter.setPen(color)
        value = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, int(rect.width()))
        painter.drawText(rect, alignment | Qt.AlignmentFlag.AlignVCenter, value)

    def folder(self, painter, center, accent, archive=False):
        painter.save(); painter.translate(center)
        glow = QRadialGradient(QPointF(0, 4), 34)
        glow.setColorAt(0, alpha(accent, round(72*self.appearance['glow']/55))); glow.setColorAt(1, alpha(accent, 0))
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
        title = self.job.title.lower()
        archive = any(word in title for word in ('compress', 'archiv'))
        extracting = any(word in title for word in ('extract', 'unpack', 'decompress'))
        if self.design != 'raw':
            scene = {'modern': artwork.modern, 'breakpoint': artwork.breakpoint,
                     'binaryknife': artwork.binaryknife, 'tidalglass': artwork.tidalglass, 'porcelainink': artwork.porcelainink,
                     'obsidianforge': artwork.obsidianforge, 'candycloud': artwork.candycloud, 'shadowedge': artwork.shadowedge, 'hollowgrove': artwork.hollowgrove,
                     'mycelium': artwork.mycelium, 'atomicafterglow': artwork.atomicafterglow, 'blackwood': artwork.blackwood, 'midnighttransit': artwork.midnighttransit, 'hyperfusionblue': artwork.hyperfusionblue, 'gildedhollow': artwork.gildedhollow}[self.design]
            scene(painter, box, accent, QColor(self.colors['AlternateBase']), self.phase,
                  self.options['animation']['density'], self.options['animation']['trails'],
                  self.appearance['glow'], archive and not extracting, extracting, self.job.result)
            return
        left, right = QPointF(box.left()+36, box.center().y()+5), QPointF(box.right()-36, box.center().y()+5)
        path = QPainterPath(left); path.cubicTo(left+QPointF(65, -27), right+QPointF(-65, -27), right)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(alpha(accent, 25), 5)); painter.drawPath(path)
        painter.setPen(QPen(alpha(accent, 90), 1, Qt.PenStyle.DotLine)); painter.drawPath(path)
        self.folder(painter, left, accent, extracting)
        self.folder(painter, right, accent, archive and not extracting)
        if self.job.result == 'done':
            painter.setPen(QPen(QColor('#78d7b6'), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            mid = box.center(); painter.drawLine(mid+QPointF(-7, 0), mid+QPointF(-1, 6))
            painter.drawLine(mid+QPointF(-1, 6), mid+QPointF(11, -7)); return
        if self.job.result: return
        count = self.options['animation']['density']
        for i in range(count):
            progress = (self.phase + i/count) % 1
            opacity = min(1, progress*7, (1-progress)*7)
            point = path.pointAtPercent(progress)
            painter.save(); painter.setOpacity(opacity)
            painter.translate(point); painter.rotate(-14+28*progress)
            for trail in range(3 if self.options['animation']['trails'] else 0, 0, -1):
                painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(alpha(accent, 12*(4-trail)))
                painter.drawRoundedRect(QRectF(-8-trail*4, -11+trail, 15, 20), 2, 2)
            page = QPainterPath(); page.moveTo(-7, -11); page.lineTo(3, -11)
            page.lineTo(8, -6); page.lineTo(8, 10); page.lineTo(-7, 10); page.closeSubpath()
            painter.setPen(QPen(accent.lighter(160), .8)); painter.setBrush(accent.lighter(190)); painter.drawPath(page)
            painter.setPen(QPen(accent.darker(180), 1)); painter.drawLine(QPointF(3, -11), QPointF(3, -6))
            painter.drawLine(QPointF(3, -6), QPointF(8, -6))
            for y in (-2, 2, 6): painter.drawLine(QPointF(-4, y), QPointF(4, y))
            painter.restore()

    def summary(self):
        if self.job.result or self.job.pending or self.job.question or self.job.data.get('suspended'):
            return self.job.summary()
        info, data, parts = self.options['information'], self.job.data, []
        total, processed, speed = data.get('totalBytes', 0), data.get('processedBytes', 0), data.get('speed', 0)
        if info['amount']:
            if total: parts.append(f'{amount(processed)} / {amount(total)}')
            elif data.get('totalFiles'): parts.append(f'{data.get("processedFiles", 0):,} / {data["totalFiles"]:,} files')
        if info['speed'] and speed: parts.append(amount(speed)+'/s')
        if info['remaining'] and total and speed:
            seconds = max(0, round((total-processed)/speed))
            remaining = f'{seconds//3600}h {(seconds%3600)//60}m' if seconds >= 3600 else (
                f'{seconds//60}m {seconds%60}s' if seconds >= 60 else f'{seconds}s')
            parts.append('~ '+remaining+' left')
        return ' · '.join(parts) or (data.get('infoMessage', 'Working…') if any(info[k] for k in ('amount', 'speed', 'remaining')) else '')

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.embedded:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        background = alpha(QColor(self.colors['Window']), round(self.appearance['opacity']*2.55))
        accent, foreground = self.accent, QColor(self.colors['Text'])
        radius, muted = self.appearance['radius'], QColor(self.colors['PlaceholderText'])
        w, h = self.width(), self.height()
        surface = QLinearGradient(0, 0, self.width(), self.height())
        surface.setColorAt(0, background.lighter(112 if self.design == 'raw' else 104))
        surface.setColorAt(1, background.darker(110 if self.design == 'raw' else 103))
        painter.setBrush(surface)
        border = self.appearance['border']
        painter.setPen(QPen(alpha(accent, 135 if self.design != 'modern' else 90), border) if border else Qt.PenStyle.NoPen)
        inset = max(.5, border/2)
        if self.design != 'shadowedge':
            painter.drawRoundedRect(QRectF(inset, inset, w-2*inset, h-2*inset), radius, radius)
        if self.design == 'tidalglass':
            from tidalglass import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'porcelainink':
            from porcelainink import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'shadowedge':
            from shadowedge import paint_surface,cut_path
            box=QRectF(inset,inset,w-2*inset,h-2*inset)
            paint_surface(painter,box,self.colors,radius,self.appearance['opacity'])
            painter.setClipPath(cut_path(box,min(16,box.height()*.16)),Qt.ClipOperation.IntersectClip)
        if self.design == 'mycelium':
            from mycelium import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'atomicafterglow':
            from atomicafterglow import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'blackwood':
            from blackwood import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        elif self.design == 'midnighttransit':
            from midnighttransit import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'hyperfusionblue':
            from hyperfusionblue import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'gildedhollow':
            from gildedhollow import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'hollowgrove':
            from hollowgrove import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'candycloud':
            from candycloud import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        if self.design == 'obsidianforge':
            from obsidianforge import paint_surface
            paint_surface(painter,QRectF(inset,inset,w-2*inset,h-2*inset),self.colors,radius,self.appearance['opacity'])
        bloom = QRadialGradient(QPointF(w/2, h/2), w*.4)
        bloom.setColorAt(0, alpha(accent, round(self.appearance['glow']*.35))); bloom.setColorAt(1, alpha(accent, 0))
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(bloom)
        painter.drawRoundedRect(QRectF(2, 2, w-4, h-4), max(0, radius-1), max(0, radius-1))
        if self.design in ('breakpoint','binaryknife'):
            painter.setPen(QPen(alpha(accent, 190), 2))
            painter.drawLine(QPointF(18, 1.5), QPointF(min(w-18, 86), 1.5))
        # The original artwork, track and controls stay in place; questions
        # unfold beneath them inside the same themed surface.
        if h > self.base_height:
            painter.setPen(QPen(alpha(accent, 70), 1))
            painter.drawLine(QPointF(16, self.base_height), QPointF(w-16, self.base_height))
        h = self.base_height
        show_percent = self.options['information']['percentage']
        self.text(painter, QRectF(16, 9, w-(134 if show_percent else 65), 25), self.job.title, foreground, 11, True)
        percentage = self.job.percent
        value = '—' if percentage is None else f'{percentage:.0f}%'
        if show_percent:
            if self.design == 'modern':
                painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(alpha(accent, 25))
                painter.drawRoundedRect(QRectF(w-112, 8, 65, 27), 9, 9)
            self.text(painter, QRectF(w-112, 7, 65, 28), value, accent, 14 if self.design == 'modern' else 16, True,
                      Qt.AlignmentFlag.AlignCenter if self.design == 'modern' else Qt.AlignmentFlag.AlignRight)
        source, destination = self.job.paths
        path_style = self.options['information']['paths']
        if path_style != 'hidden':
            route = '  →  '.join(short_location(p) if path_style == 'names' else p for p in (source, destination) if p)
            self.text(painter, QRectF(16, 35, w-32, 18), route or self.job.application, muted, 9)
        scene_top = 55 if path_style != 'hidden' else 42
        box = QRectF(16, scene_top, w-32, h-61-scene_top)
        if self.job.result == 'failed':
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(alpha(QColor('#e53945'), 18))
            painter.drawRoundedRect(box, 8, 8)
            self.text(painter, box.adjusted(8, 0, -8, 0), self.job.summary(), QColor('#b53351' if theme_runtime.mode() == 'light' else '#ee9aab'), 10)
        else:
            self.transfer(painter, box, accent)
        thickness = self.appearance['track_height']
        track = QRectF(16, h-54, w-32, thickness)
        track_radius = 1 if self.design in ('breakpoint','binaryknife') else thickness/2
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(self.colors['Base']))
        painter.drawRoundedRect(track, track_radius, track_radius)
        painter.save(); clip = QPainterPath(); clip.addRoundedRect(track, track_radius, track_radius); painter.setClipPath(clip)
        if percentage is None and self.job.result is None:
            position = self.phase if self.options['animation']['enabled'] else .5
            fill = QRectF(track.left() + (track.width()+100)*position-100, track.top(), 100, track.height())
        else:
            current = percentage or 0 if not self.job.running else self.display_percent
            fill = QRectF(track.left(), track.top(), track.width()*current/100, track.height())
        beam = QLinearGradient(fill.topLeft(), fill.topRight())
        beam.setColorAt(0, accent.darker(130)); beam.setColorAt(1, accent.lighter(120))
        painter.setBrush(beam); painter.drawRect(fill)
        if self.design == 'breakpoint':
            for x in range(16, w-16, 12): painter.fillRect(QRectF(x, track.top(), 2, thickness), QColor(self.colors['Window']))
        painter.restore()
        reserved = 154 if self.details.isVisible() else 128 if self.pause.isVisible() else 94
        self.text(painter, QRectF(16, h-39, w-reserved-16, 25), self.summary(), muted, 8)
