"""The wallpaper shelf: bounded thumbnail painting, scrolling and reversible flights."""
import math
import json
import uuid

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, QMimeData, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QAbstractButton, QHBoxLayout, QMenu, QScrollBar, QSizePolicy, QToolButton, QToolTip, QWidget

import runtime
from wallpaper.carousel import Thumbnails, color, cover
from wallpaper.tabs import HiddenTabs, MIME


class HideButton(QAbstractButton):
    """A real keyboard-accessible button with a small animated downward cue."""
    def __init__(self, parent):
        super().__init__(parent)
        self.picture = None; self.amount = 0.; self.reduced_motion = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(78, 32)
        self.animation = QVariantAnimation(self); self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.animate)

    def animate(self, value): self.amount = float(value); self.update()
    def highlight(self, active):
        self.animation.stop()
        if self.reduced_motion: self.animate(float(active)); return
        self.animation.setStartValue(self.amount); self.animation.setEndValue(float(active)); self.animation.start()
    def enterEvent(self, event): self.highlight(True); super().enterEvent(event)
    def leaveEvent(self, event): self.highlight(self.hasFocus()); super().leaveEvent(event)
    def focusInEvent(self, event): self.highlight(True); super().focusInEvent(event)
    def focusOutEvent(self, event): self.highlight(self.underMouse()); super().focusOutEvent(event)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(QColor(9, 17, 26, 235)); p.setPen(QPen(color('Accent', round(100 + 155*self.amount)), 1.3))
        p.drawRoundedRect(rect, 9, 9)
        p.setPen(QPen(QColor('#ffffff'), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        y = 11 + self.amount*3
        p.drawLine(QPointF(17, y-3), QPointF(17, y+6))
        p.drawLine(QPointF(13, y+2), QPointF(17, y+6)); p.drawLine(QPointF(17, y+6), QPointF(21, y+2))
        p.setFont(QFont(runtime.ui_font(), 10, QFont.Weight.DemiBold))
        p.drawText(rect.adjusted(28, 0, -5, 0), Qt.AlignmentFlag.AlignCenter, 'Hide')


class DockFoldButton(QAbstractButton):
    """A centered chevron that follows the shelf's expand/collapse animation."""
    def __init__(self, parent, item_label):
        super().__init__(parent); self.item_label=item_label; self.angle=0.
        self.setFixedSize(36,28); self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.animation=QVariantAnimation(self); self.animation.setDuration(330)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.animate); self.set_collapsed(False)

    def nextCheckState(self): pass  # The owner confirms the change after saving.
    def animate(self,value): self.angle=float(value); self.update()
    def set_collapsed(self,collapsed,animate=False):
        self.setChecked(collapsed); self.animation.stop()
        label=('Expand' if collapsed else 'Collapse')+' hidden '+self.item_label
        self.setAccessibleName(label); self.setToolTip(label+(' dock' if collapsed else ' to a strip'))
        end=180. if collapsed else 0.
        if animate:
            self.animation.setStartValue(self.angle); self.animation.setEndValue(end); self.animation.start()
        else:self.animate(end)
    def enterEvent(self,event):self.update();super().enterEvent(event)
    def leaveEvent(self,event):self.update();super().leaveEvent(event)
    def focusInEvent(self,event):self.update();super().focusInEvent(event)
    def focusOutEvent(self,event):self.update();super().focusOutEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        active=self.underMouse() or self.hasFocus() or self.isDown()
        p.setBrush(color('Button',230 if active else 90));p.setPen(QPen(color('Accent' if active else 'Midlight'),1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),7,7)
        p.translate(self.width()/2,self.height()/2);p.rotate(self.angle)
        p.setPen(QPen(color('Text'),1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(-4,-2),QPointF(0,2));p.drawLine(QPointF(0,2),QPointF(4,-2))


class HiddenDock(QWidget):
    restored = pyqtSignal(object)
    tabChosen = pyqtSignal(str)
    tabAdded = pyqtSignal()
    tabRenamed = pyqtSignal(str)
    tabDeleted = pyqtSignal(str)
    moved = pyqtSignal(str,str)
    collapseRequested = pyqtSignal(bool)

    def __init__(self, parent=None, *, item_label='wallpapers', show_titles=False, collapsible=False):
        super().__init__(parent)
        self.item_label = item_label; self.show_titles = show_titles
        self.collapsible=collapsible;self.collapsed=False;self.fold_button=None
        # Small shelf previews cannot evict the gallery's full-size images.
        self.thumbnails = Thumbnails(self,maximum_size=QSize(280,180),capacity=96)
        self.pictures = []; self.omitted = set()
        self.tabs = [{'id':'hidden','name':'Hidden','paths':[]}]; self.active_tab = 'hidden'
        self.drag_token = uuid.uuid4().hex; self.drag_path = ''; self.drop_hint = ''; self.press_path = ''
        self.reduced_motion = False; self.compact = False; self.tiny = False
        self.hover = -1; self.focus_index = 0; self.press = None; self.dragged = False
        self.offsets = {}; self.mix = 0.; self.setFixedHeight(74)
        self.setMouseTracking(True); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Hidden '+item_label)
        self.setAccessibleDescription('Two rows of hidden '+item_label+' in named tabs. Scroll to browse. Click or press Enter to restore. Drag a thumbnail up to another tab to move it.')
        self.header = QWidget(self)
        self.tab_group=QWidget(self.header) if collapsible else self.header
        row = QHBoxLayout(self.tab_group); row.setContentsMargins(0,0,0,0); row.setSpacing(6)
        self.tabbar = HiddenTabs(self); self.tabbar.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        self.tabbar.chosen.connect(self.tabChosen); self.tabbar.renameRequested.connect(self.tabRenamed)
        self.tabbar.deleteRequested.connect(self.tabDeleted); self.tabbar.pictureDropped.connect(self.moved)
        row.addWidget(self.tabbar)
        def action(caption, tip, callback, width, layout=row):
            button = QToolButton(layout.parentWidget()); button.setText(caption); button.setToolTip(tip); button.setAccessibleName(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor); button.setFixedSize(width,30)
            button.setStyleSheet('QToolButton {padding:2px 6px; min-height:0; border:1px solid '+color('Midlight').name()+'; border-radius:7px;}'
                                'QToolButton:hover {border-color:'+color('Accent').name()+';}')
            button.clicked.connect(lambda _=False:callback()); layout.addWidget(button); return button
        self.add_tab = action('+','Create hidden '+item_label+' tab',self.tabAdded.emit,32)
        row.addStretch()
        actions=row
        if collapsible:
            self.action_group=QWidget(self.header);actions=QHBoxLayout(self.action_group);actions.setContentsMargins(0,0,0,0);actions.setSpacing(6);actions.addStretch()
            self.fold_button=DockFoldButton(self.header,item_label)
            self.fold_button.clicked.connect(lambda:self.collapseRequested.emit(not self.collapsed))
        self.rename_tab = action('Rename','Rename active tab',lambda:self.tabRenamed.emit(self.active_tab),70,actions)
        self.delete_tab = action('Delete','Delete active tab and transfer its '+item_label,lambda:self.tabDeleted.emit(self.active_tab),64,actions)
        self.set_tabs(self.tabs,self.active_tab)
        self.scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        self.scroll.setAccessibleName('Scroll hidden '+item_label)
        self.scroll.setStyleSheet('QScrollBar:horizontal {height:6px; background:transparent;}'
            'QScrollBar::handle:horizontal {background:'+color('Midlight').name()+'; min-width:32px; border-radius:3px;}'
            'QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {width:0;}'
            'QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal {background:transparent;}')
        self.scroll.valueChanged.connect(self.update)
        self.height_animation = QVariantAnimation(self); self.height_animation.setDuration(330)
        self.height_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.height_animation.valueChanged.connect(lambda value: self.setFixedHeight(round(value)))
        self.reflow = QVariantAnimation(self); self.reflow.setDuration(360); self.reflow.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.reflow.valueChanged.connect(self.animate)
        self.scrolling = QVariantAnimation(self); self.scrolling.setDuration(240); self.scrolling.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scrolling.valueChanged.connect(lambda value: self.scroll.setValue(round(value)))
        self.thumbnails.changed.connect(lambda _: self.update())

    def metrics(self):
        width = 84 if self.tiny else 104 if self.compact else 124
        return width, round(width*9/16), 10

    def expanded_height(self):
        if not self.pictures: return 74
        _, height, gap = self.metrics()
        return 50 + 2*height + gap + 18

    def target_height(self):return 46 if self.collapsed else self.expanded_height()

    def set_collapsed(self,collapsed,animate=False):
        if not self.collapsible or self.collapsed==collapsed:return
        self.collapsed=collapsed;self.press=None;self.hover=-1;QToolTip.hideText()
        self.height_animation.stop();self.scrolling.stop();self.reflow.stop();self.mix=0.
        if collapsed and self.hasFocus():self.fold_button.setFocus()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus if collapsed else Qt.FocusPolicy.StrongFocus)
        self.fold_button.set_collapsed(collapsed,animate and not self.reduced_motion)
        if animate and not self.reduced_motion:
            self.height_animation.setStartValue(float(self.height()));self.height_animation.setEndValue(float(self.target_height()));self.height_animation.start()
        else:self.setFixedHeight(self.target_height())
        self.arrange();self.update()

    def set_tabs(self, tabs, active):
        self.tabs = tabs; self.active_tab = active; self.tabbar.populate(tabs,active)
        self.delete_tab.setEnabled(len(tabs)>1)
        self.delete_tab.setToolTip('Delete active tab and transfer its '+self.item_label if len(tabs)>1 else 'Create another tab to transfer '+self.item_label+' before deleting this one.')
        self.add_tab.setEnabled(len(tabs)<64)

    def fit(self, height):
        compact, tiny = height < 800, height < 640
        if (compact, tiny) == (self.compact, self.tiny): return
        self.compact, self.tiny = compact, tiny
        self.height_animation.stop(); self.setFixedHeight(self.target_height()); self.arrange()

    def animate(self, value): self.mix = float(value); self.update()

    def populate(self, pictures, animate=False, reveal=''):
        previous = {p.path: self.picture_rect(i) for i, p in enumerate(self.pictures)}
        self.reflow.stop(); self.height_animation.stop(); self.scrolling.stop()
        self.pictures = list(pictures); self.hover = -1
        self.focus_index = min(self.focus_index, max(0, len(pictures)-1))
        self.offsets = {}; self.mix = 0.; self.arrange()
        if reveal:
            index = next((i for i,p in enumerate(pictures) if p.path == reveal), 0)
            self.focus_index = index; self.ensure_visible(index, False)
        target = self.target_height()
        if animate and not self.reduced_motion and not self.collapsed:
            for i, picture in enumerate(pictures):
                if picture.path in previous:
                    self.offsets[picture.path] = previous[picture.path].topLeft() - self.picture_rect(i).topLeft()
            self.mix = 1.; self.reflow.setStartValue(1.); self.reflow.setEndValue(0.); self.reflow.start()
            self.height_animation.setStartValue(float(self.height())); self.height_animation.setEndValue(float(target)); self.height_animation.start()
        else: self.setFixedHeight(target)
        self.update()

    def arrange(self):
        self.header.setGeometry(12,7,max(1,self.width()-24),32)
        if self.collapsible:
            center=self.header.width()//2
            self.tab_group.setGeometry(0,0,max(1,center-24),32)
            self.action_group.setGeometry(center+24,0,max(1,self.header.width()-center-24),32)
            self.fold_button.move(center-18,2)
        width, _, gap = self.metrics(); count = len(self.pictures)
        extent = (math.ceil(count/2)*(width+gap) + (width+gap)/2 if count>1 else width) + 36
        self.scroll.setRange(0, max(0, math.ceil(extent-self.width())))
        self.scroll.setPageStep(max(1, self.width()-36)); self.scroll.setSingleStep(width+gap)
        self.scroll.setGeometry(18, self.height()-12, max(1, self.width()-36), 6)
        self.scroll.setVisible(not self.collapsed and self.scroll.maximum()>0 and self.height()>80)

    def resizeEvent(self, event): self.arrange(); super().resizeEvent(event)

    def picture_rect(self, index):
        width, height, gap = self.metrics(); row = index % 2; column = index//2
        return QRectF(18 + column*(width+gap) + row*(width+gap)/2 - self.scroll.value(),
                      48 + row*(height+gap), width, height)

    def visible_indices(self):
        width, _, gap = self.metrics(); stride = width+gap
        first = max(0, (self.scroll.value()-18)//stride-2)
        last = math.ceil((self.scroll.value()+self.width())/stride)+2
        return range(first*2,min(len(self.pictures),last*2))

    def location(self, path):
        index = next((i for i,p in enumerate(self.pictures) if p.path == path), None)
        if index is not None and self.collapsed:
            tab=self.tabbar.currentIndex()
            return QRectF(self.tabbar.tabRect(tab)).translated(QPointF(self.tabbar.mapTo(self,QPoint())))
        return self.picture_rect(index) if index is not None else QRectF()

    def scroll_to(self, value, animate=True):
        self.scrolling.stop(); value = max(0, min(self.scroll.maximum(), value))
        if self.reduced_motion or not animate: self.scroll.setValue(round(value)); return
        self.scrolling.setStartValue(float(self.scroll.value())); self.scrolling.setEndValue(float(value)); self.scrolling.start()

    def ensure_visible(self, index, animate=True):
        rect = self.picture_rect(index)
        if rect.left()<18: self.scroll_to(self.scroll.value()+rect.left()-18, animate)
        elif rect.right()>self.width()-18: self.scroll_to(self.scroll.value()+rect.right()-self.width()+18, animate)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        panel = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(color('Window', 242)); p.setPen(QPen(color('Midlight', 170), 1)); p.drawRoundedRect(panel, 15, 15)
        if self.collapsible:
            amount=max(0.,min(1.,(self.height()-46)/(self.expanded_height()-46)))
            if amount<=0:return
            p.setOpacity(amount)
        p.setFont(QFont(runtime.ui_font(), 9)); p.setPen(color('Text', 190))
        if not self.pictures:
            p.drawText(QRectF(18, 44, self.width()-36, 21), Qt.AlignmentFlag.AlignVCenter, 'Hide '+self.item_label+' into this tab, or drag thumbnails here from another tab.'); return
        p.setClipRect(QRectF(10, 44, self.width()-20, self.height()-58))
        for i in self.visible_indices():
            picture = self.pictures[i]
            rect = self.picture_rect(i).translated(self.offsets.get(picture.path, QPointF())*self.mix)
            if rect.right()<10 or rect.left()>self.width()-10: continue
            active = i == self.hover or (self.hasFocus() and i == self.focus_index)
            if active: rect.translate(0, -2)
            shape = QPainterPath(); shape.addRoundedRect(rect, 8, 8)
            p.save(); p.setClipPath(shape, Qt.ClipOperation.IntersectClip)
            p.fillRect(rect, color('Base'))
            if picture.path not in self.omitted:
                pixmap = self.thumbnails.get(picture.path)
                cover(p, rect, pixmap)
                if pixmap.isNull():
                    p.setPen(color('Text', 170)); p.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'No preview' if picture.path in self.thumbnails.failed else '…')
                if active:
                    p.fillRect(rect, QColor(0, 0, 0, 110)); p.setPen(QColor('#ffffff'))
                    p.setFont(QFont(runtime.ui_font(), 10, QFont.Weight.DemiBold)); p.drawText(rect, Qt.AlignmentFlag.AlignCenter, '↑ Restore')
                elif self.show_titles:
                    caption=QRectF(rect.left(),rect.bottom()-18,rect.width(),18)
                    p.fillRect(caption,QColor(8,10,18,205));p.setPen(QColor('#ffffff'));p.setFont(QFont(runtime.ui_font(),8))
                    title=p.fontMetrics().elidedText(picture.title,Qt.TextElideMode.ElideRight,round(rect.width()-8))
                    p.drawText(caption.adjusted(4,0,-4,0),Qt.AlignmentFlag.AlignCenter,title)
            p.restore(); p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color('Accent' if active else 'Midlight', 240 if active else 165), 2 if active else 1)); p.drawPath(shape)
        p.setClipping(False)
        if self.scroll.maximum()>0:
            p.setPen(color('Text', 180)); p.drawText(QRectF(4, 35, 12, self.height()-52), Qt.AlignmentFlag.AlignCenter, '‹' if self.scroll.value() else '')
            p.drawText(QRectF(self.width()-16, 35, 12, self.height()-52), Qt.AlignmentFlag.AlignCenter, '›' if self.scroll.value()<self.scroll.maximum() else '')
        if self.drop_hint:
            rect = QRectF(18,self.height()-43,min(self.width()-36,p.fontMetrics().horizontalAdvance(self.drop_hint)+28),28)
            p.setBrush(color('Window',245)); p.setPen(QPen(color('Accent'),1)); p.drawRoundedRect(rect,7,7)
            p.setPen(color('Text')); p.drawText(rect,Qt.AlignmentFlag.AlignCenter,self.drop_hint)

    def hit(self, point):
        if self.collapsed:return -1
        if point.y()<44 or point.y()>self.height()-14: return -1
        return next((i for i in self.visible_indices() if self.picture_rect(i).contains(point)), -1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.scrolling.stop(); self.setFocus(); self.press = event.position(); self.start_scroll = self.scroll.value(); self.dragged = False
            index = self.hit(self.press); self.press_path = self.pictures[index].path if index>=0 else ''

    def mouseMoveEvent(self, event):
        if self.press is not None:
            delta = event.position().x()-self.press.x(); vertical = event.position().y()-self.press.y()
            # Horizontal gestures keep the existing shelf panning. Lifting a
            # thumbnail toward the tab row starts a native drag instead.
            if self.press_path and len(self.tabs)>1 and abs(vertical)>=QApplication.startDragDistance() and (abs(vertical)>abs(delta)*.35 or event.position().y()<44):
                self.start_drag(self.press_path); return
            self.dragged |= abs(delta)>7
            if self.dragged: self.scroll_to(self.start_scroll-delta, False)
        else:
            index = self.hit(event.position())
            if index != self.hover:
                self.hover = index; self.update()
                self.setToolTip(self.pictures[index].title+'\nClick to restore · Drag up to a tab to move · Right-click for options' if index>=0 else '')
            self.setCursor(Qt.CursorShape.PointingHandCursor if index>=0 else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.press is None or event.button() != Qt.MouseButton.LeftButton: return
        initial = self.hit(self.press); self.press = None
        index = self.hit(event.position())
        if not self.dragged and index>=0 and index == initial:
            self.focus_index = index; QToolTip.hideText(); self.restored.emit(self.pictures[index])

    def leaveEvent(self, event): self.hover = -1; self.update(); super().leaveEvent(event)

    def drag_mime(self, path):
        mime = QMimeData(); mime.setData(MIME,json.dumps({'token':self.drag_token,'path':path,'tab':self.active_tab}).encode())
        return mime

    def start_drag(self, path):
        self.press = None; self.press_path = ''; self.dragged = True; self.drag_path = path
        self.reflow.stop(); self.mix = 0.; self.scrolling.stop(); QToolTip.hideText()
        drag = QDrag(self); drag.setMimeData(self.drag_mime(path))
        pixmap = self.thumbnails.get(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(124,76,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            drag.setPixmap(pixmap); drag.setHotSpot(QPoint(pixmap.width()//2,pixmap.height()//2))
        try: drag.exec(Qt.DropAction.MoveAction)
        finally:
            self.drag_path = ''; self.tabbar.clear_drop(); self.update(); drag.deleteLater()

    def contextMenuEvent(self, event):
        if self.collapsed:return
        index = self.hit(QPointF(event.pos())) if event.reason()!=event.Reason.Keyboard else self.focus_index
        if not 0<=index<len(self.pictures): return
        picture = self.pictures[index]; menu = QMenu(self)
        menu.addAction('Restore to gallery',lambda:self.restored.emit(picture))
        move = menu.addMenu('Move to tab'); move.setEnabled(len(self.tabs)>1)
        for tab in self.tabs:
            action = move.addAction(tab['name'].replace('&','&&'),lambda _=False,identity=tab['id']:self.moved.emit(picture.path,identity))
            action.setEnabled(tab['id']!=self.active_tab)
        menu.exec(event.globalPos()); menu.deleteLater()
    def wheelEvent(self, event):
        if self.collapsed:event.ignore();return
        delta = event.pixelDelta().x() or event.pixelDelta().y()
        if not delta: delta = (event.angleDelta().x() or event.angleDelta().y())*.9
        target = self.scrolling.endValue() if self.scrolling.state() == QVariantAnimation.State.Running else self.scroll.value()
        self.scroll_to(float(target)-delta); event.accept()

    def keyPressEvent(self, event):
        if self.collapsed:return super().keyPressEvent(event)
        if not self.pictures: return super().keyPressEvent(event)
        delta = {Qt.Key.Key_Left:-2, Qt.Key.Key_Right:2, Qt.Key.Key_Up:-1, Qt.Key.Key_Down:1}.get(event.key())
        if delta is not None:
            self.focus_index = max(0, min(len(self.pictures)-1, self.focus_index+delta)); self.ensure_visible(self.focus_index); self.update()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space): self.restored.emit(self.pictures[self.focus_index])
        elif event.key() in (Qt.Key.Key_Home, Qt.Key.Key_End):
            self.focus_index = 0 if event.key() == Qt.Key.Key_Home else len(self.pictures)-1
            self.ensure_visible(self.focus_index); self.update()
        else: super().keyPressEvent(event)

    def stop(self):
        self.tabbar.clear_drop()
        for animation in (self.height_animation, self.reflow, self.scrolling): animation.stop()
        if self.fold_button:
            self.fold_button.set_collapsed(self.collapsed);self.setFixedHeight(self.target_height())


class ThumbnailFlight(QWidget):
    """One temporary, non-interactive surface flying between gallery and shelf."""
    finished = pyqtSignal()

    def __init__(self, parent, pixmap, source, destination, source_skew=0., destination_skew=lambda:0.):
        super().__init__(parent); self.pixmap = pixmap; self.source = source; self.destination = destination; self.progress = 0.
        self.source_skew = source_skew; self.destination_skew = destination_skew
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(parent.rect()); self.show(); self.raise_()
        self.animation = QVariantAnimation(self); self.animation.setDuration(440)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.animate); self.animation.finished.connect(self.finished)

    def animate(self, value): self.progress = float(value); self.setGeometry(self.parentWidget().rect()); self.update()
    def start(self): self.animation.setStartValue(0.); self.animation.setEndValue(1.); self.animation.start()

    def paintEvent(self, _):
        end = self.destination(); t = self.progress
        if end.isEmpty(): return
        rect = QRectF(*(a+(b-a)*t for a,b in zip(self.source.getRect(), end.getRect())))
        rect.translate(0, -math.sin(t*math.pi)*24)
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        skew = rect.width()*(self.source_skew*(1-t)+self.destination_skew()*t)
        shape = QPainterPath()
        if skew<.5: shape.addRoundedRect(rect, 8, 8)
        else:
            shape.moveTo(rect.left()+skew,rect.top()); shape.lineTo(rect.right(),rect.top())
            shape.lineTo(rect.right()-skew,rect.bottom()); shape.lineTo(rect.left(),rect.bottom()); shape.closeSubpath()
        p.save(); p.translate(0, 7); p.fillPath(shape, QColor(0,0,0,100)); p.restore()
        p.setClipPath(shape); p.fillRect(rect, color('Base')); cover(p, rect, self.pixmap)
        p.setClipping(False); p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(color('Accent'), 1.5)); p.drawPath(shape)
