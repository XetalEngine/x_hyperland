#!/usr/bin/env python3
"""Super+W: animated wallpaper browsing and direct per-monitor selection."""
from __future__ import annotations
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import threading

from PyQt6.QtCore import Qt, QRectF, QTimer, QVariantAnimation, QEasingCurve, QCoreApplication, QEvent
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QLinearGradient, QShortcut
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QDialog, QListWidget, QFileDialog, QCheckBox, QDialogButtonBox,
    QAbstractButton, QSizePolicy)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'theme'), str(ROOT/'control_center')]
import runtime
import backend
import desktop_settings as settings
from wallpaper import library, transitions
from wallpaper.carousel import Carousel, Thumbnails, color, cover
from wallpaper.jobs import Jobs


def label(text, name=''):
    widget = QLabel(text); widget.setObjectName(name); widget.setWordWrap(True); return widget


def button(text, action, primary=False):
    widget = QPushButton(text); widget.clicked.connect(action); widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary: widget.setObjectName('primary')
    return widget


class Folders(QDialog):
    def __init__(self, options, parent):
        super().__init__(parent); self.setWindowTitle('Wallpaper folders'); self.resize(650, 430); self.options = copy.deepcopy(options)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 24, 24, 24); layout.setSpacing(16)
        layout.addWidget(label('Make room for your favorites', 'sectionTitle'))
        layout.addWidget(label('Images in these folders and their subfolders appear in the browser.', 'muted'))
        self.bundled = QCheckBox('Include the bundled wallpaper collection'); self.bundled.setChecked(options['bundled']); layout.addWidget(self.bundled)
        self.folders = QListWidget(); self.folders.addItems(options['folders']); self.folders.setAccessibleName('Wallpaper folders'); layout.addWidget(self.folders, 1)
        actions = QHBoxLayout(); actions.addWidget(button('＋  Add folder…', self.add)); self.remove = button('Remove folder', self.remove_selected); actions.addWidget(self.remove); actions.addStretch(); layout.addLayout(actions)
        self.folders.currentRowChanged.connect(lambda row: self.remove.setEnabled(row>=0)); self.remove.setEnabled(False)
        layout.addWidget(label('Removing a folder only removes it from this browser. Your images stay where they are.', 'muted'))
        self.error = label('', 'error'); self.error.hide(); layout.addWidget(self.error)
        bottom = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        bottom.rejected.connect(self.reject); bottom.accepted.connect(self.accept); layout.addWidget(bottom)

    def add(self):
        path = QFileDialog.getExistingDirectory(self, 'Add a wallpaper folder', str(Path.home()/'Pictures'))
        if path:
            path = str(Path(path).resolve())
            if path not in self.paths(): self.folders.addItem(path); self.folders.setCurrentRow(self.folders.count()-1)

    def paths(self): return [self.folders.item(i).text() for i in range(self.folders.count())]
    def remove_selected(self): self.folders.takeItem(self.folders.currentRow())
    def value(self): return {**self.options, 'bundled': self.bundled.isChecked(), 'folders': self.paths()}

    def accept(self):
        try: self.options = library.save(self.value(), self.options, fields=('folders', 'bundled'))
        except (OSError, ValueError) as error: self.error.setText(str(error)); self.error.show(); return
        super().accept()


class ScreenButton(QAbstractButton):
    def __init__(self, model, current, choice, thumbnails, parent):
        super().__init__(parent); self.model = model; self.current = current; self.choice = choice; self.thumbnails = thumbnails
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setMouseTracking(True)
        self.setAccessibleName(f"Apply wallpaper to display {model['number']}, {model['name']}")
        self.setToolTip(f"{model['name']} · {model['label']}\n{model['width']} × {model['height']} · {model['scale']:g}× scale")

    def enterEvent(self, event): self.update(); super().enterEvent(event)
    def leaveEvent(self, event): self.update(); super().leaveEvent(event)
    def focusInEvent(self, event): self.update(); super().focusInEvent(event)
    def focusOutEvent(self, event): self.update(); super().focusOutEvent(event)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4); path = QPainterPath(); path.addRoundedRect(rect, 8, 8)
        active = self.underMouse() or self.hasFocus(); image = self.choice.path if active else self.current.get('path', '')
        p.save(); p.setClipPath(path); p.fillRect(rect, color('Base')); cover(p, rect, self.thumbnails.get(image))
        shade = QLinearGradient(0, rect.top(), 0, rect.bottom()); shade.setColorAt(0, QColor(0,0,0,40)); shade.setColorAt(.55, QColor(0,0,0,0)); shade.setColorAt(1, QColor(0,0,0,210)); p.fillRect(rect, shade)
        p.setPen(QColor('#ffffff')); p.setFont(QFont(runtime.ui_font(), 18, QFont.Weight.Bold))
        p.drawText(rect.adjusted(16, 10, -12, -12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(self.model['number']))
        p.setFont(QFont(runtime.ui_font(), 11, QFont.Weight.DemiBold))
        p.drawText(rect.adjusted(10, 0, -10, -14), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, self.model['name'])
        if active and rect.width()>140 and rect.height()>100:
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'Apply here')
        p.restore(); p.setPen(QPen(color('Accent') if active else color('Midlight'), 3 if active else 1.5)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)


class MonitorMap(QWidget):
    def __init__(self, models, current, choice, thumbnails, callback, parent=None):
        super().__init__(parent); self.models = models; self.buttons = []; self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for model in library.active_screens(models):
            widget = ScreenButton(model, current.get(model['name'], {}), choice, thumbnails, self)
            widget.clicked.connect(lambda checked=False, m=model: callback(m)); self.buttons.append(widget)
        thumbnails.changed.connect(self.repaint_screens)

    def repaint_screens(self, _):
        for widget in self.buttons: widget.update()

    def resizeEvent(self, event):
        boxes = library.screen_rectangles(self.models, self.width(), self.height())
        for widget in self.buttons:
            x,y,w,h = boxes[widget.model['name']]; widget.setGeometry(round(x),round(y),max(1,round(w)),max(1,round(h)))
        super().resizeEvent(event)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(QPen(color('Midlight', 55), 1))
        for x in range(24, self.width(), 26):
            for y in range(24, self.height(), 26): p.drawPoint(x,y)


class ScreenPicker(QDialog):
    def __init__(self, models, current, picture, thumbnails, parent):
        super().__init__(parent); self.selected = None; self.setWindowTitle('Choose a display'); self.resize(min(1000,parent.width()-80), min(620,parent.height()-80))
        layout = QVBoxLayout(self); layout.setContentsMargins(30,24,30,24); layout.setSpacing(12)
        layout.addWidget(label('Where should it live?', 'sectionTitle'))
        layout.addWidget(label('Your screens, just as they are arranged. Click one to apply the wallpaper.', 'muted'))
        layout.addWidget(MonitorMap(models,current,picture,thumbnails,self.choose,self),1)
        row = QHBoxLayout(); row.addWidget(label(picture.title+'  ·  '+picture.collection, 'muted'),1)
        row.addWidget(button('Back to wallpapers',self.reject)); layout.addLayout(row)

    def choose(self, model): self.selected = model; self.accept()


class Browser(QWidget):
    def __init__(self, preview=False, style=None):
        super().__init__(); self.preview = preview; self.pictures = []; self.busy = False; self.cancel_scan = threading.Event(); self.scanning = False
        self.monitor_name = ''; self.center_current = True
        self.background = None; self.previous_background = None; self.background_mix = 1.; self.dialog = None; self.reduced_motion = False; self.compact = None; self.narrow = False
        error = ''; self.error_options = False
        try: self.options = library.read()
        except (ValueError, OSError) as problem:
            self.options = library.normalize(library.DEFAULTS); self.error_options = True; error = str(problem)
        self.style = style or self.options['style']; self.floating = self.style == 'overlay'
        self.setWindowTitle('Wallpapers · Floating cards' if self.floating else 'Wallpapers')
        self.setObjectName('wallpaperBrowser'); self.setProperty('xetalOverlay', True)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint); self.resize(1440, 850)
        if self.floating:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.NoDropShadowWindowHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setAutoFillBackground(False)
            self.setStyleSheet('QWidget#wallpaperBrowser {background:transparent; border:none;}')
        self.jobs = Jobs(self); self.thumbnails = Thumbnails(self); self.thumbnails.changed.connect(lambda _: self.update())
        self.background_animation = QVariantAnimation(self); self.background_animation.setDuration(500); self.background_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.background_animation.valueChanged.connect(self.blend_background)
        layout = QVBoxLayout(self); layout.setContentsMargins(40,30,40,22); layout.setSpacing(14)
        self.count = label('Opening your collection…', 'muted'); self.count.setWordWrap(False)
        close = button('✕', self.close); close.setFixedWidth(42); close.setToolTip('Close · Esc / Super+W'); close.setAccessibleName('Close wallpaper browser')
        self.hero=label('Find your next view.', 'hero'); self.subtitle=label('A little change of scenery.', 'subtitle')
        if not self.floating:
            top = QHBoxLayout(); brand = label('YOUR DESKTOP / WALLPAPERS', 'eyebrow'); brand.setWordWrap(False); top.addWidget(brand); top.addStretch()
            top.addWidget(self.count); top.addWidget(close); layout.addLayout(top)
            layout.addSpacing(6); layout.addWidget(self.hero); layout.addWidget(self.subtitle); layout.addSpacing(8)
        else:
            for widget in (self.count, self.hero, self.subtitle): widget.setParent(self); widget.hide()
        toolbar = QFrame(); toolbar.setObjectName('wallpaperToolbar'); bar = QHBoxLayout(toolbar); bar.setContentsMargins(14,10,14,10); bar.setSpacing(10)
        self.play = button('▶  Slideshow', self.toggle_play); self.play.setToolTip('Preview each image in the carousel. Wallpapers change only when you select one.'); bar.addWidget(self.play)
        self.collection = QComboBox(); self.collection.addItem('All collections', ''); self.collection.setMinimumWidth(150); self.collection.currentIndexChanged.connect(self.filter); bar.addWidget(self.collection)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search wallpapers…'); self.search.setClearButtonEnabled(True); self.search.setAccessibleName('Search wallpapers')
        self.search.textChanged.connect(self.filter); bar.addWidget(self.search,1)
        self.folder_button = button('＋  Add / remove folders', self.folders); bar.addWidget(self.folder_button)
        self.toolbar = toolbar
        if self.floating:
            bar.addWidget(close); toolbar.setMaximumWidth(1200)
            centered = QHBoxLayout(); centered.addStretch(); centered.addWidget(toolbar, 1); centered.addStretch(); layout.addLayout(centered)
        else: layout.addWidget(toolbar)
        self.carousel = Carousel(self.thumbnails); self.carousel.activated.connect(self.choose); self.carousel.selected.connect(self.selected); self.carousel.interacted.connect(self.pause)
        self.carousel.backdrop = not self.floating
        self.search.returnPressed.connect(self.carousel.activate)
        layout.addWidget(self.carousel,1)
        info = QHBoxLayout(); self.previous = button('←',lambda:self.carousel.step(-1)); self.previous.setAccessibleName('Previous wallpaper'); self.previous.setFixedWidth(46); info.addWidget(self.previous)
        self.next = button('→',lambda:self.carousel.step(1)); self.next.setAccessibleName('Next wallpaper'); self.next.setFixedWidth(46); info.addWidget(self.next)
        details = QVBoxLayout(); self.title = label('Your wallpaper collection','imageTitle'); self.meta = label('','muted'); details.addWidget(self.title); details.addWidget(self.meta); info.addLayout(details,1)
        effects = QVBoxLayout(); effects.addWidget(label('TRANSITION','eyebrow')); self.transition = QComboBox()
        for key, title in library.TRANSITIONS.items(): self.transition.addItem(title,key)
        self.transition.setMinimumWidth(125 if self.floating else 155); self.transition.setAccessibleName('Wallpaper transition'); effects.addWidget(self.transition); info.addLayout(effects)
        self.apply = button('Use wallpaper  ↗',lambda:self.choose(self.carousel.current()),True); self.apply.setMinimumWidth(170); self.apply.setMinimumHeight(48); info.addWidget(self.apply)
        bottom = QHBoxLayout(); self.status = label('Scroll or drag to explore · Click an image to choose its display','muted'); bottom.addWidget(self.status,1)
        self.hint=label('← → Browse    Enter Select    Esc Close','muted'); self.hint.setWordWrap(False); bottom.addWidget(self.hint)
        if self.floating:
            self.apply.setMinimumWidth(140)
            self.previous.setFixedWidth(36); self.next.setFixedWidth(36)
            self.footer = QFrame(); self.footer.setObjectName('wallpaperToolbar')
            footer = QVBoxLayout(self.footer); footer.setContentsMargins(18, 12, 18, 12); footer.setSpacing(10)
            footer.addLayout(info); footer.addLayout(bottom); self.footer.setMaximumWidth(1200)
            centered = QHBoxLayout(); centered.addStretch(); centered.addWidget(self.footer, 1); centered.addStretch(); layout.addLayout(centered)
        else:
            layout.addLayout(info); layout.addSpacing(6); layout.addLayout(bottom)
        self.slideshow = QTimer(self); self.slideshow.setInterval(3500); self.slideshow.timeout.connect(self.advance)
        self.shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape),self); self.shortcut.activated.connect(self.escape)
        self.focus_search = QShortcut(QKeySequence('Ctrl+F'),self); self.focus_search.activated.connect(self.search.setFocus)
        self.space = QShortcut(QKeySequence(Qt.Key.Key_Space),self.carousel); self.space.setContext(Qt.ShortcutContext.WidgetShortcut); self.space.activated.connect(self.toggle_play)
        if error: self.status.setText(error)
        self.transition.setCurrentIndex(self.transition.findData(self.options['transition'])); self.transition.currentIndexChanged.connect(self.change_transition)
        QTimer.singleShot(0,self.scan)

    def resizeEvent(self,event):
        self.fit_layout(event.size().width(), event.size().height())
        super().resizeEvent(event)

    def fit_layout(self, width, height):
        compact=height<760; self.narrow=width<1000
        self.folder_button.setText('Folders…' if self.narrow else '＋  Add / remove folders')
        self.collection.setMinimumWidth(115 if self.narrow else 150); self.hint.setVisible(not self.narrow)
        if compact!=self.compact:
            self.compact=compact; self.subtitle.setVisible(not compact and not self.floating); self.carousel.setMinimumHeight(150 if compact else 250)
            self.hero.setStyleSheet('font-size:26px;font-weight:700;' if compact else '')
            self.layout().setContentsMargins(24 if compact else 40,18 if compact else 30,24 if compact else 40,14 if compact else 22)
            self.layout().setSpacing(9 if compact else 14)
        if self.floating:
            self.layout().setContentsMargins(24, 24, 24, 24)
        self.play.setText(('Ⅱ' if self.slideshow.isActive() else '▶') if self.narrow else ('Ⅱ  Pause slideshow' if self.slideshow.isActive() else '▶  Slideshow'))

    def paintEvent(self, _):
        if self.floating: return
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform); rect=QRectF(self.rect()); p.fillRect(rect,color('Window'))
        for picture, opacity in ((self.previous_background,1-self.background_mix),(self.background,self.background_mix)):
            if picture:
                pixmap=self.thumbnails.get(picture.path)
                if not pixmap.isNull():
                    blurred=pixmap.scaled(40,30,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
                    cover(p,rect,blurred,.20*opacity)
        shade=QLinearGradient(0,0,0,self.height()); shade.setColorAt(0,color('Window',210)); shade.setColorAt(.45,color('Window',80)); shade.setColorAt(1,color('Window',230)); p.fillRect(rect,shade)
        p.setPen(QPen(color('Accent',100),1)); p.drawRect(rect.adjusted(.5,.5,-.5,-.5))

    def blend_background(self, value): self.background_mix=float(value); self.update()

    def scan(self):
        self.cancel_scan.set(); token=threading.Event(); self.cancel_scan=token; self.scanning=True; self.count.setText('Finding wallpapers…')
        options=copy.deepcopy(self.options); monitor=self.monitor_name
        def collect():
            pictures,notices=library.scan(options,cancelled=token.is_set); selected=''
            if monitor and not self.preview and not token.is_set():
                try:
                    current=backend.read_wallpapers()
                    pictures,selected=library.include_current(pictures,current.get(monitor,current.get('',{})))
                except (OSError,ValueError): pass
            return pictures,notices,selected
        self.jobs.run(collect,lambda result:self.scanned(token,result),self.failure)

    def scanned(self, token, result):
        if token is not self.cancel_scan or token.is_set(): return
        self.scanning=False; self.pictures,notices,selected=result
        previous=self.collection.currentData(); self.collection.blockSignals(True); self.collection.clear(); self.collection.addItem('All collections','')
        for name in dict.fromkeys(p.collection for p in self.pictures): self.collection.addItem(name,name)
        self.collection.setCurrentIndex(max(0,self.collection.findData(previous))); self.collection.blockSignals(False)
        self.filter(initial=selected if self.center_current else ''); self.center_current=False
        if notices: self.status.setText(notices[0]); self.status.setToolTip('\n'.join(notices))

    def filter(self, *_, initial=''):
        if self.busy: return
        self.pause(); search=self.search.text().strip().casefold(); collection=self.collection.currentData()
        pictures=[p for p in self.pictures if (not collection or p.collection==collection) and (not search or search in (p.title+' '+p.collection+' '+Path(p.path).name).casefold())]
        current=self.carousel.current(); self.carousel.populate(pictures,initial or (current.path if current else ''))
        self.count.setText(f'{len(pictures)} wallpapers  /  {len(set(p.collection for p in pictures))} collections')
        self.apply.setEnabled(bool(pictures)); self.play.setEnabled(len(pictures)>1)
        self.previous.setEnabled(len(pictures)>1); self.next.setEnabled(len(pictures)>1)
        if not pictures: self.title.setText('No matching wallpapers'); self.meta.setText('Try another collection, search or folder.')

    def selected(self, picture):
        self.title.setText(picture.title); self.title.setToolTip(picture.path); self.meta.setText(f'{picture.collection}  ·  {self.carousel.index%len(self.carousel.pictures)+1:02d} / {len(self.carousel.pictures):02d}')
        if not self.floating and picture!=self.background:
            self.previous_background=self.background; self.background=picture; self.background_animation.stop()
            self.background_animation.setStartValue(0.); self.background_animation.setEndValue(1.)
            if self.reduced_motion: self.background_mix=1.; self.update()
            else: self.background_animation.start()

    def toggle_play(self):
        if self.slideshow.isActive(): self.pause()
        elif len(self.carousel.pictures)>1:
            self.slideshow.start(); self.play.setText('Ⅱ' if self.narrow else 'Ⅱ  Pause slideshow'); self.status.setText('Slideshow preview · Select an image to set your wallpaper')

    def advance(self): self.carousel.step(1,False)
    def pause(self): self.slideshow.stop(); self.play.setText('▶' if self.narrow else '▶  Slideshow')

    def folders(self):
        self.pause()
        try: options=library.read()
        except (OSError,ValueError) as error: self.failure(str(error)); return
        self.dialog=Folders(options,self)
        if self.dialog.exec()==QDialog.DialogCode.Accepted: self.options=self.dialog.options; self.scan()
        self.dialog=None

    def change_transition(self):
        try:
            value={**self.options,'transition':self.transition.currentData()}; self.options=library.save(value,self.options,fields=('transition',))
        except (OSError,ValueError) as error:
            self.transition.blockSignals(True); self.transition.setCurrentIndex(self.transition.findData(self.options['transition'])); self.transition.blockSignals(False); self.failure(str(error))

    def set_busy(self, value):
        self.busy=value
        for widget in (self.carousel,self.apply,self.play,self.search,self.collection,self.folder_button,self.transition,self.previous,self.next): widget.setEnabled(not value)

    def choose(self, picture):
        if self.busy or not picture: return
        self.pause(); self.set_busy(True); self.status.setText('Reading your displays…')
        if self.preview:
            self.pick_screen(picture,(sample_monitors(),{})); return
        self.jobs.run(lambda:(settings.display_models(settings.monitors()),backend.read_wallpapers()),lambda result:self.pick_screen(picture,result),self.failure)

    def pick_screen(self, picture, result):
        models,current=result; screens=library.active_screens(models)
        if not screens: self.failure('No active display was found. Connect a display and try again.'); return
        if len(screens)==1: self.begin_apply(picture,screens[0],current); return
        self.dialog=ScreenPicker(models,current,picture,self.thumbnails,self)
        accepted=self.dialog.exec()==QDialog.DialogCode.Accepted; selected=self.dialog.selected; self.dialog=None
        if accepted: self.begin_apply(picture,selected,current)
        else: self.set_busy(False); self.status.setText('Choose another image, or select a display when you are ready.')

    def begin_apply(self, picture, monitor, current):
        if self.preview: self.set_busy(False); self.status.setText('Preview · Wallpaper would be applied to '+monitor['name']); return
        choice={'path':picture.path,'original':picture.path,'fit':'cover'}; self.status.setText('Preparing '+monitor['name']+'…')
        style='none' if self.reduced_motion else self.options['transition']
        self.jobs.run(lambda:transitions.prepare(monitor,current.get(monitor['name'],{}),choice,style),
                      lambda overlay:self.prepared(overlay,monitor,choice,current),self.failure,
                      discard=lambda overlay:overlay.close() if overlay else None)

    def prepared(self, overlay, monitor, choice, current):
        self.hide()
        self.jobs.run(lambda:transitions.commit(overlay,lambda:backend.apply_wallpapers({monitor['name']:choice},current)),lambda _:self.applied(),self.failure)

    def applied(self):
        self.busy=False; self.cancel_scan.set(); QApplication.instance().quit()

    def failure(self, message):
        self.set_busy(False); self.status.setText(message); self.status.setToolTip(message)
        if not self.isVisible(): self.show(); self.raise_(); self.activateWindow()

    def escape(self):
        if self.dialog: self.dialog.reject()
        elif not self.busy: self.close()

    def closeEvent(self, event):
        if self.busy: event.ignore(); return
        self.cancel_scan.set(); self.pause(); self.background_animation.stop(); self.carousel.animation.stop(); event.accept(); QApplication.instance().quit()

    def shutdown(self):
        self.cancel_scan.set(); self.pause(); self.background_animation.stop(); self.carousel.animation.stop()
        # Let any wallpaper transaction finish before tearing down its Qt owner.
        self.jobs.shutdown(); self.thumbnails.jobs.shutdown(cancel_queued=True)


STYLE = '''
QWidget {font:13px "Noto Sans"; color:#d4e8f4;}
QWidget#wallpaperBrowser {background:transparent;}
QLabel {background:transparent;}
QLabel#hero {font-size:34px;font-weight:700;}
QLabel#subtitle {font-size:15px;color:#93abc0;}
QLabel#eyebrow {font-size:10px;font-weight:600;color:#7dcfff;}
QLabel#imageTitle {font-size:20px;font-weight:600;}
QLabel#sectionTitle {font-size:23px;font-weight:600;}
QLabel#muted {color:#93abc0;font-size:12px;}
QLabel#error {color:#ee8196;}
QFrame#wallpaperToolbar {background:#192530;border:1px solid #344859;border-radius:16px;}
QPushButton,QComboBox,QLineEdit {padding:10px 14px;min-height:20px;border-radius:10px;}
QPushButton#primary {background:#39a9ff;color:#07121a;font-weight:600;}
'''


def sample_monitors():
    return [dict(name='DP-1',label='Main display',number=1,width=2560,height=1440,x=0,y=0,scale=1,transform=0,enabled=True,mirror=''),
            dict(name='DP-2',label='Portrait display',number=2,width=1920,height=1080,x=2560,y=-240,scale=1,transform=1,enabled=True,mirror='')]


def place(window):
    from launcher.placement import selected_monitor
    monitors=json.loads(settings.ctl('-j','monitors')); cursor=json.loads(settings.ctl('-j','cursorpos')); monitor=selected_monitor(monitors,cursor)
    w,h=monitor['width']/monitor['scale'],monitor['height']/monitor['scale']
    if monitor.get('transform',0)%2: w,h=h,w
    left,top,right,bottom=monitor.get('reserved') or (0,0,0,0)
    width=max(640,min(1700,round((w-left-right)*.96))); height=max(520,min(1040,round((h-top-bottom)*.94)))
    width=min(width,round(w-left-right)); height=min(height,round(h-top-bottom))
    x=round(left+(w-left-right-width)/2); y=round(top+(h-top-bottom-height)/2)
    values={'monitor':int(monitor['id']),'size':f'{width} {height}','move':f'{x} {y}'}
    rule = 'fusion-wallpaper-overlay' if window.floating else 'fusion-wallpaper-browser'
    reply=settings.ctl('--batch',';'.join(f'keyword windowrule[{rule}]:{key} {value}' for key,value in values.items()))
    if any(line.strip()!='ok' for line in reply.splitlines() if line.strip()): raise ValueError('Could not position the wallpaper browser: '+reply)
    window.fit_layout(width,height); window.resize(width,height)
    window.monitor_name=monitor['name']
    try: window.reduced_motion=json.loads(settings.ctl('-j','getoption','animations:enabled')).get('int')==0
    except (OSError,ValueError): pass
    window.carousel.reduced_motion=window.reduced_motion


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--preview'); parser.add_argument('--preview-monitors',action='store_true')
    parser.add_argument('--preview-style', choices=library.STYLES); parser.add_argument('--show', action='store_true'); args=parser.parse_args()
    if args.preview_style and not args.preview: parser.error('--preview-style requires --preview')
    app=QApplication(sys.argv[:1]); app.setApplicationName('xetal-wallpaper-browser'); app.setDesktopFileName('xetal-wallpaper-browser'); app.setQuitOnLastWindowClosed(False)
    runtime.install(app,STYLE); app.setWindowIcon(QIcon.fromTheme('preferences-desktop-wallpaper'))
    server=None; lifetime=None; lock=None; instance=None
    if not args.preview:
        if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'): raise SystemExit('Open Wallpapers inside the Hyper Fusion session.')
        instance=Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']
        lock=(instance/'wallpaper-browser.lock').open('a')
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return 0
    window=Browser(bool(args.preview), args.preview_style)
    if not args.preview:
        place(window)
        endpoint=str(instance/'wallpaper.sock'); QLocalServer.removeServer(endpoint); server=QLocalServer(app)
        if not server.listen(endpoint): raise RuntimeError(server.errorString())
        def present():
            nonlocal window
            if window.busy: return
            if window.dialog:
                window.dialog.raise_(); window.dialog.activateWindow(); return
            try:
                options = library.read()
                if options['style'] != window.style:
                    replacement = Browser()
                    try: place(replacement)
                    except Exception:
                        replacement.shutdown(); replacement.deleteLater(); raise
                    previous = window; window = replacement
                    previous.hide(); previous.shutdown(); previous.deleteLater()
                else:
                    rescan = any(options[key] != window.options[key] for key in ('folders', 'bundled'))
                    window.options = options
                    window.transition.blockSignals(True); window.transition.setCurrentIndex(window.transition.findData(options['transition'])); window.transition.blockSignals(False)
                    if rescan: window.scan()
                window.show(); window.raise_(); window.activateWindow(); window.carousel.setFocus()
            except (OSError, ValueError) as error: window.failure(str(error))
        def incoming():
            while server.hasPendingConnections():
                peer=server.nextPendingConnection()
                def read(peer=peer):
                    if not peer.canReadLine(): return
                    command = bytes(peer.readLine()).strip()
                    if command == b'show': present()
                    elif command == b'toggle' and not window.busy: window.close()
                    peer.disconnectFromServer()
                peer.readyRead.connect(read); peer.disconnected.connect(peer.deleteLater)
                if peer.bytesAvailable(): read()
        server.newConnection.connect(incoming)
        lifetime=QLocalSocket(app); lifetime.connectToServer(str(instance/'.socket2.sock')); lifetime.readyRead.connect(lambda:lifetime.readAll()); lifetime.disconnected.connect(app.quit)
        signal.signal(signal.SIGTERM,lambda *_:app.quit()); signal.signal(signal.SIGINT,lambda *_:app.quit())
        heartbeat=QTimer(app); heartbeat.timeout.connect(lambda:None); heartbeat.start(500)
    window.show(); window.carousel.setFocus()
    if args.preview:
        def capture():
            if args.preview_monitors:
                current={m['name']:{'path':window.pictures[i].path} for i,m in enumerate(sample_monitors())}
                dialog=ScreenPicker(sample_monitors(),current,window.pictures[3],window.thumbnails,window); dialog.show()
                QTimer.singleShot(600,lambda:(dialog.grab().save(args.preview),app.quit()))
            else: window.grab().save(args.preview); app.quit()
        QTimer.singleShot(1800,capture)
    try: return app.exec()
    finally:
        window.hide()
        window.shutdown()
        if server: server.close()
        if lock: lock.close()
        # Destroy animated widgets while Qt and its Python callbacks are alive.
        window.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__=='__main__': raise SystemExit(main())
