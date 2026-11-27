"""Named hidden-wallpaper tabs, explicit transfer dialogs and native drop targets."""
import json

from PyQt6.QtCore import Qt, QRectF, QTimer, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit,
    QMenu, QTabBar, QToolButton, QVBoxLayout)

from wallpaper import library
from wallpaper.carousel import color

MIME = 'application/x-hyperfusion-hidden-wallpaper'


class HiddenTabs(QTabBar):
    chosen = pyqtSignal(str)
    renameRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    pictureDropped = pyqtSignal(str,str)

    def __init__(self, dock):
        super().__init__(dock); self.dock = dock; self.drop_index = -1; self.glow = 0.
        self.setAccessibleName('Hidden '+dock.item_label+' tabs')
        self.setExpanding(False); self.setDrawBase(False); self.setUsesScrollButtons(True)
        self.setElideMode(Qt.TextElideMode.ElideRight); self.setAcceptDrops(True)
        self.setChangeCurrentOnDrag(False)
        self.setStyleSheet('QTabBar {background:transparent;}'
            'QTabBar::tab {padding:4px 12px; margin-right:5px; min-width:48px; max-width:180px;'
            'border:1px solid '+color('Midlight').name()+'; border-radius:8px; background:'+color('Base').name()+';}'
            'QTabBar::tab:selected {border-color:'+color('Accent').name()+'; color:'+color('Text').name()+'; background:'+color('Button').name()+';}'
            'QTabBar::tab:hover {border-color:'+color('Accent').name()+';}'
            'QTabBar QToolButton {min-width:0; min-height:0; padding:0; margin:0; border-radius:4px; background:'+color('Window').name()+';}')
        self.animation = QVariantAnimation(self); self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.animate)
        self.scroll_button = None; self.scroll_timer = QTimer(self); self.scroll_timer.setInterval(240)
        self.scroll_timer.timeout.connect(lambda:self.scroll_button.click() if self.scroll_button and self.scroll_button.isEnabled() else None)
        self.currentChanged.connect(lambda i:self.chosen.emit(self.tabData(i)) if i>=0 else None)
        self.tabBarDoubleClicked.connect(lambda i:self.renameRequested.emit(self.tabData(i)) if i>=0 else None)

    def minimumTabSizeHint(self, index):
        # Scroll a row of readable names instead of squeezing every name into
        # a few letters when more tabs are created.
        return self.tabSizeHint(index)

    def populate(self, tabs, active):
        self.clear_drop(); self.blockSignals(True)
        ids = [self.tabData(i) for i in range(self.count())]
        if ids != [t['id'] for t in tabs]:
            while self.count(): self.removeTab(0)
            for tab in tabs: self.setTabData(self.addTab(''),tab['id'])
        for i,tab in enumerate(tabs):
            self.setTabText(i,tab['name'].replace('&','&&')+f" · {len(tab['paths'])}")
            self.setTabToolTip(i,tab['name']+'\nDrop a hidden thumbnail here to move it. Double-click to rename.')
            if tab['id']==active: self.setCurrentIndex(i)
        self.blockSignals(False)

    def contextMenuEvent(self, event):
        index = self.tabAt(event.pos()) if event.reason()!=event.Reason.Keyboard else self.currentIndex()
        if index<0: return
        identity = self.tabData(index); menu = QMenu(self)
        menu.addAction('Rename tab…',lambda:self.renameRequested.emit(identity))
        delete = menu.addAction('Delete tab…',lambda:self.deleteRequested.emit(identity)); delete.setEnabled(self.count()>1)
        menu.exec(event.globalPos()); menu.deleteLater()

    def drag_path(self, mime):
        if not mime.hasFormat(MIME): return ''
        payload = bytes(mime.data(MIME))
        if len(payload)>16384: return ''
        try: value = json.loads(payload)
        except (ValueError,UnicodeError): return ''
        if (not isinstance(value,dict) or value.get('token')!=self.dock.drag_token or
                value.get('path')!=self.dock.drag_path or not self.dock.drag_path or
                value.get('tab')!=self.dock.active_tab): return ''
        return self.dock.drag_path if any(p.path==self.dock.drag_path for p in self.dock.pictures) else ''

    def highlight(self, index):
        if index==self.drop_index: return
        self.animation.stop(); self.drop_index = index; self.glow = 0.
        if index>=0:
            name = self.dock.tabs[index]['name']
            self.dock.drop_hint = 'Release to move to “'+name+'”'
            if self.dock.reduced_motion: self.glow = 1.
            else: self.animation.setStartValue(0.); self.animation.setEndValue(1.); self.animation.start()
        else: self.dock.drop_hint = ''
        self.update(); self.dock.update()

    def animate(self, value): self.glow = float(value); self.update()
    def clear_drop(self):
        self.animation.stop(); self.scroll_timer.stop(); self.scroll_button = None; self.highlight(-1)

    def dragEnterEvent(self, event):
        if self.drag_path(event.mimeData()): event.setDropAction(Qt.DropAction.MoveAction); event.accept()
        else: event.ignore()

    def target_index(self, point):
        # Scroll arrows cover clipped tabs. They are navigation, never a drop
        # target for the tab that happens to be painted underneath them.
        if any(b.isVisible() and b.geometry().contains(point) for b in self.findChildren(QToolButton)): return -1
        return self.tabAt(point)

    def dragMoveEvent(self, event):
        index = self.target_index(event.position().toPoint())
        path = self.drag_path(event.mimeData())
        self.scroll_button = next((b for b in self.findChildren(QToolButton) if path and b.isVisible() and b.isEnabled() and b.geometry().contains(event.position().toPoint())),None)
        if self.scroll_button:
            if not self.scroll_timer.isActive(): self.scroll_timer.start()
        else: self.scroll_timer.stop()
        valid = path and index>=0 and self.tabData(index)!=self.dock.active_tab
        self.highlight(index if valid else -1)
        if valid or self.scroll_button: event.setDropAction(Qt.DropAction.MoveAction); event.accept()
        else: event.ignore()

    def dragLeaveEvent(self, event): self.clear_drop(); event.accept()

    def dropEvent(self, event):
        path = self.drag_path(event.mimeData()); index = self.target_index(event.position().toPoint())
        self.clear_drop()
        if path and index>=0 and self.tabData(index)!=self.dock.active_tab:
            destination = self.tabData(index)
            self.pictureDropped.emit(path,destination)
            event.setDropAction(Qt.DropAction.MoveAction); event.accept()
        else: event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drop_index<0: return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.tabRect(self.drop_index)).adjusted(1,1,-5,-1)
        p.setBrush(color('Accent',round(30+45*self.glow))); p.setPen(QPen(color('Accent'),2))
        p.drawRoundedRect(rect,8,8)


class TabNameDialog(QDialog):
    def __init__(self, options, parent, identity=None, *, model=library):
        super().__init__(parent); self.options = options; self.identity = identity; self.model = model
        self.setWindowTitle('Rename hidden tab' if identity else 'New hidden tab'); self.resize(460,210)
        body = QVBoxLayout(self); body.setContentsMargins(24,20,24,20); body.setSpacing(14)
        title = QLabel('Rename this tab' if identity else 'Name your new tab'); title.setObjectName('sectionTitle'); body.addWidget(title)
        self.name = QLineEdit(model.hidden_tab(options,identity)['name'] if identity else '')
        self.name.setAccessibleName('Tab name'); self.name.setPlaceholderText('e.g. Landscapes'); self.name.setMaxLength(48); body.addWidget(self.name)
        self.error = QLabel(); self.error.setObjectName('error'); self.error.setWordWrap(True); self.error.hide(); body.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Rename' if identity else 'Create tab')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); body.addWidget(buttons)
        self.name.selectAll(); self.name.setFocus()

    def accept(self):
        try:
            value = (self.model.rename_hidden_tab(self.options,self.identity,self.name.text()) if self.identity else
                     self.model.add_hidden_tab(self.options,self.name.text()))
            self.options = self.model.save(value,self.options,fields=self.model.HIDDEN_FIELDS)
        except (OSError,ValueError) as error: self.error.setText(str(error)); self.error.show(); return
        super().accept()


class DeleteTabDialog(QDialog):
    def __init__(self, options, identity, parent, *, model=library, item_label='wallpapers'):
        super().__init__(parent); self.options = options; self.identity = identity; self.model = model
        tab = model.hidden_tab(options,identity)
        self.setWindowTitle('Transfer '+item_label+' and delete tab'); self.resize(480,250)
        body = QVBoxLayout(self); body.setContentsMargins(24,20,24,20); body.setSpacing(14)
        heading = QLabel('Delete “'+tab['name']+'”?'); heading.setObjectName('sectionTitle'); heading.setWordWrap(True); body.addWidget(heading)
        message = QLabel(f"Choose which tab should receive its {len(tab['paths'])} hidden {item_label}. They will stay hidden.")
        message.setWordWrap(True); body.addWidget(message)
        self.destination = QComboBox(); self.destination.setAccessibleName('Transfer '+item_label+' to tab')
        self.destination.addItem('Choose a destination tab…',None)
        for other in options['hidden_tabs']:
            if other['id']!=identity: self.destination.addItem(other['name']+f" · {len(other['paths'])} {item_label}",other['id'])
        body.addWidget(self.destination)
        self.error = QLabel(); self.error.setObjectName('error'); self.error.setWordWrap(True); self.error.hide(); body.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.confirm = buttons.addButton('Transfer && delete tab',QDialogButtonBox.ButtonRole.AcceptRole)
        self.confirm.setEnabled(False); self.destination.currentIndexChanged.connect(lambda _:self.confirm.setEnabled(self.destination.currentData() is not None))
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); body.addWidget(buttons)

    def accept(self):
        if self.destination.currentData() is None: return
        try:
            value = self.model.transfer_hidden_tab(self.options,self.identity,self.destination.currentData())
            self.options = self.model.save(value,self.options,fields=self.model.HIDDEN_FIELDS)
        except (OSError,ValueError) as error: self.error.setText(str(error)); self.error.show(); return
        super().accept()
