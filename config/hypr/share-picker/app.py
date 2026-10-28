#!/usr/bin/env python3
"""Hyprland screen-share chooser with local, updating thumbnails."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, QProcess, QSocketNotifier, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QIcon, QPixmap, QShortcut, QKeySequence
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QAbstractButton, QTabWidget, QScrollArea, QGridLayout, QLineEdit, QCheckBox, QComboBox, QSizeGrip, QSizePolicy)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'theme'))
import runtime as theme_runtime
from model import portal_windows, logical_size, match_windows, selection

STYLE = '''
QWidget { color: #d4e2f4; font-family: "Noto Sans"; font-size: 13px; }
QWidget#picker { background: #171c24; }
QLabel#eyebrow { color: #76ddd0; font-size: 11px; letter-spacing: 2px; }
QLabel#title { color: #eff5fc; font-size: 27px; font-weight: 700; }
QLabel#subtitle, QLabel#hint { color: #91a3bd; }
QTabWidget::pane { border: none; border-top: 1px solid #344355; padding-top: 16px; }
QTabBar::tab { background: #171c24; padding: 12px 22px; margin-right: 6px; color: #91a3bd; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #76ddd0; border-bottom: 2px solid #76ddd0; background: #202b37; }
QScrollArea, QWidget#grid { border: none; background: transparent; }
QScrollBar:vertical { background: #171c24; width: 8px; }
QScrollBar::handle:vertical { background: #3b4e63; border-radius: 4px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLineEdit, QComboBox { background: #10151e; border: 1px solid #35475b; border-radius: 7px; padding: 9px 12px; }
QComboBox QAbstractItemView { background: #202b37; color: #d4e2f4; selection-background-color: #345e6a; }
QPushButton { background: #273544; border: 1px solid #405269; border-radius: 7px; padding: 10px 23px; }
QPushButton:hover { background: #34495b; border-color: #76ddd0; }
QPushButton:focus { border-color: #76ddd0; }
QPushButton#share { background: #76ddd0; color: #11262c; border-color: #76ddd0; font-weight: 700; }
QPushButton#share:hover { background: #a2eade; }
QPushButton#share:disabled { background: #29434b; color: #729399; border-color: #29434b; }
QPushButton#close { padding: 4px; min-width: 30px; max-width: 30px; border: none; background: transparent; color: #91a3bd; font-size: 21px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #5c7189; background: #10151e; }
QCheckBox::indicator:checked { background: #76ddd0; border: 2px solid #b6fff0; }
'''


def ctl(command):
    try:
        return json.loads(subprocess.check_output(['hyprctl','-j',command], timeout=2, stderr=subprocess.DEVNULL))
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def color(value):
    return QColor(theme_runtime.recolor(value, theme_runtime.mode()))


class PreviewCard(QAbstractButton):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = source; self.pixmap = QPixmap(); self.updated = 0.0
        self.last_attempt = 0.0; self.error = False
        self.setCheckable(True); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(220, 224)
        self.setAccessibleName(source.get('title', source['name']))
        self.setToolTip(source.get('title', source['name']))
        self.icon = QIcon.fromTheme(source.get('app','video-display'), QIcon.fromTheme('application-x-executable'))

    def sizeHint(self): return QSize(300, 242)

    def preview_rect(self): return QRectF(10, 10, self.width()-20, self.height()-76)

    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected=self.isChecked(); hover=self.underMouse() or self.hasFocus()
        p.setBrush(color('#223743' if selected else '#202934' if hover else '#1c2430'))
        p.setPen(QPen(color('#76ddd0' if selected else '#51697d' if hover else '#344355'),2 if selected else 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),12,12)
        area=self.preview_rect(); path=QPainterPath(); path.addRoundedRect(area,7,7)
        p.save(); p.setClipPath(path); p.fillRect(area,color('#0d131b'))
        if not self.pixmap.isNull():
            size=self.pixmap.size().scaled(area.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
            box=QRectF(0,0,size.width(),size.height()); box.moveCenter(area.center())
            p.drawPixmap(box.toRect(),self.pixmap)
        else:
            icon=self.icon.pixmap(46,46); p.drawPixmap(int(area.center().x()-23),int(area.center().y()-32),icon)
            p.setPen(color('#91a3bd')); p.setFont(QFont('Noto Sans',10))
            p.drawText(area.adjusted(8,50,-8,0),Qt.AlignmentFlag.AlignCenter,'Preview unavailable' if self.error else 'Loading preview…')
        p.restore()
        if not self.pixmap.isNull():
            live=time.monotonic()-self.updated<3
            badge=QRectF(area.x()+8,area.y()+8,54 if live else 73,21)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(theme_runtime.qcolor(10,19,28,225)); p.drawRoundedRect(badge,8,8)
            p.setBrush(theme_runtime.qcolor('#76ddd0' if live else '#91a3bd'));p.drawEllipse(QPointF(badge.x()+10,badge.center().y()),2.5,2.5)
            p.setPen(theme_runtime.qcolor('#e6f0f9'));p.setFont(QFont('Noto Sans',8));p.drawText(badge.adjusted(18,0,0,0),Qt.AlignmentFlag.AlignVCenter,'LIVE' if live else 'PAUSED')
        title=self.source.get('title',self.source['name'])
        p.setFont(QFont('Noto Sans',11,QFont.Weight.DemiBold));p.setPen(color('#e6effc'))
        p.drawText(QRectF(14,self.height()-59,self.width()-48,23),Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,self.width()-62))
        p.setFont(QFont('Noto Sans',9));p.setPen(color('#91a3bd'))
        detail=self.source.get('detail',self.source.get('app',''))
        p.drawText(QRectF(14,self.height()-34,self.width()-28,20),Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(detail,Qt.TextElideMode.ElideRight,self.width()-28))
        if selected:
            p.setPen(QPen(color('#76ddd0'),2.2));x=self.width()-29;y=self.height()-47
            p.drawLine(QPointF(x-5,y),QPointF(x-1,y+4));p.drawLine(QPointF(x-1,y+4),QPointF(x+6,y-5))


class RegionCanvas(PreviewCard):
    regionChanged=pyqtSignal(object)
    def __init__(self):
        super().__init__({'kind':'screen','name':'','title':'Draw a region'})
        self.setMinimumHeight(310);self.origin=None;self.region=None
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def image_rect(self):
        area=self.preview_rect()
        size=self.pixmap.size() if not self.pixmap.isNull() else QSize(*map(round,logical_size(self.source['monitor_data'])))
        size.scale(area.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
        result=QRectF(0,0,size.width(),size.height());result.moveCenter(area.center());return result

    def point(self, position):
        area=self.image_rect()
        return QPointF(max(area.left(),min(area.right(),position.x())),max(area.top(),min(area.bottom(),position.y())))

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.image_rect().contains(event.position()):
            self.origin=self.point(event.position());self.region=None;self.regionChanged.emit(None);self.update()

    def mouseMoveEvent(self,event):
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.region=QRectF(self.origin,self.point(event.position())).normalized();self.update()

    def mouseReleaseEvent(self,event):
        if self.origin is None:return
        self.region=QRectF(self.origin,self.point(event.position())).normalized();self.origin=None
        if self.region.width()<5 or self.region.height()<5:
            self.region=None;self.regionChanged.emit(None);self.update();return
        area=self.image_rect();w,h=logical_size(self.source['monitor_data'])
        x=max(0,round((self.region.x()-area.x())/area.width()*w));y=max(0,round((self.region.y()-area.y())/area.height()*h))
        rw=min(round(w)-x,max(1,round(self.region.width()/area.width()*w)))
        rh=min(round(h)-y,max(1,round(self.region.height()/area.height()*h)))
        self.regionChanged.emit({'kind':'region','name':self.source['name'],'rect':(x,y,rw,rh)})
        self.update()

    def resizeEvent(self,event):
        if self.region is not None:
            self.region=None;self.regionChanged.emit(None)
        super().resizeEvent(event)

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.region:
            p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(color('#76ddd0'),2));p.setBrush(theme_runtime.qcolor(118,221,208,45));p.drawRect(self.region)


class PreviewQueue:
    def __init__(self, window):
        self.window=window;self.running={};self.stopped=False
        self.timer=QTimer(window);self.timer.timeout.connect(self.tick);self.timer.start(100)

    def tick(self):
        if self.stopped or not self.window.isVisible():return
        wanted=[]
        for card in self.window.visible_cards():
            if card.isEnabled() and time.monotonic()-card.last_attempt >= (.6 if card.isChecked() else 1):wanted.append(card)
        for card in sorted(wanted,key=lambda c:c.last_attempt):
            if len(self.running)>=2:break
            if card in self.running:continue
            source=card.source;kind=source['kind']
            if kind=='window':
                if not source.get('address'):card.error=True;card.update();continue
                args=[str(ROOT/'window-preview'),source['address']]
            else:
                width=source.get('monitor_data',{}).get('width',1920)
                args=['grim','-l','1','-s',str(min(.5,640/max(1,width))),'-o',source['name'],'-']
            card.last_attempt=time.monotonic()
            process=QProcess(self.window);self.running[card]=process
            captured_source=(source['kind'],source['name'])
            process.finished.connect(lambda code,status,c=card,p=process,k=captured_source:self.finished(c,p,k,code))
            process.errorOccurred.connect(lambda error,c=card,p=process,k=captured_source:self.finished(c,p,k,1) if error==QProcess.ProcessError.FailedToStart else None)
            process.start(args[0],args[1:])
            QTimer.singleShot(2200,lambda p=process:self.expire(p))

    def expire(self,process):
        if process in self.running.values() and process.state()!=QProcess.ProcessState.NotRunning:process.kill()

    def finished(self,card,process,key,code):
        if self.running.get(card) is not process:return
        del self.running[card]
        data=process.readAllStandardOutput();process.deleteLater()
        if self.stopped or key!=(card.source['kind'],card.source['name']):return
        pixmap=QPixmap()
        if code==0 and pixmap.loadFromData(data):
            card.pixmap=pixmap;card.updated=time.monotonic();card.error=False
        else:card.error=True
        card.update()

    def stop(self):
        self.stopped=True;self.timer.stop()
        for process in tuple(self.running.values()):
            process.kill();process.waitForFinished(300)
        self.running.clear()


class Picker(QWidget):
    def __init__(self, allow_token=False, preview=False, monitors=None, clients=None, source_text=None):
        super().__init__();self.setObjectName('picker');self.setWindowTitle('Choose what to share · Xetal')
        self.setMinimumSize(760,600);self.resize(1080,720)
        self.preview=preview;self.chosen=None;self.output='';self.cards=[];self.columns=0
        self.monitors=monitors if monitors is not None else ctl('monitors')
        self.clients=clients if clients is not None else ctl('clients')
        self.sources=portal_windows(os.environ.get('XDPH_WINDOW_SHARING_LIST','') if source_text is None else source_text)
        if preview and not self.sources:
            self.sources=[{'kind':'window','id':str(i+1),'address':c['address'],'app':c['class'],
                           'title':c['title'],'name':c['title']} for i,c in enumerate(self.clients)
                          if c.get('mapped') and c.get('pid')!=os.getpid()]
        root=QVBoxLayout(self);root.setContentsMargins(26,22,26,18);root.setSpacing(8)
        top=QHBoxLayout();eyebrow=QLabel('XETAL  /  SCREEN SHARING');eyebrow.setObjectName('eyebrow');top.addWidget(eyebrow);top.addStretch()
        close=QPushButton('×');close.setObjectName('close');close.setAccessibleName('Cancel sharing');close.clicked.connect(self.close);top.addWidget(close);root.addLayout(top)
        title=QLabel('Choose what to share');title.setObjectName('title');root.addWidget(title)
        subtitle=QLabel('Select a screen, a window, or part of one screen.');subtitle.setObjectName('subtitle');root.addWidget(subtitle)
        root.addSpacing(12)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        self.screen_page,self.screen_grid,self.screen_scroll=self.grid_page()
        self.tabs.addTab(self.screen_page,f'Screens  ·  {len(self.monitors)}')
        self.window_page,self.window_grid,self.window_scroll=self.grid_page(True)
        self.tabs.addTab(self.window_page,f'Windows  ·  {len(self.sources)}')
        self.screen_cards=[];self.window_cards=[]
        for number,monitor in enumerate(sorted(self.monitors,key=lambda m:(m['x'],m['y'])),1):
            source={'kind':'screen','name':monitor['name'],'title':f'{number}  ·  {monitor["name"]}',
                    'monitor_data':monitor,'detail':f'{monitor["width"]} × {monitor["height"]}  ·  {monitor.get("model") or monitor.get("description", "Monitor")}'}
            card=PreviewCard(source);card.clicked.connect(lambda checked,c=card:self.choose(c));self.screen_cards.append(card)
        for source in match_windows(self.sources,self.clients):
            source['detail']=source['app']+('  ·  Workspace '+source['workspace'].removeprefix('special:') if source.get('workspace') else '')
            card=PreviewCard(source);card.setEnabled(source.get('available',True));card.clicked.connect(lambda checked,c=card:self.choose(c));self.window_cards.append(card)
        self.cards=self.screen_cards+self.window_cards
        self.region_page=QWidget();region_layout=QVBoxLayout(self.region_page);region_layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();row.addWidget(QLabel('Screen'));self.region_monitor=QComboBox()
        for card in self.screen_cards:self.region_monitor.addItem(card.source['title'],card.source)
        row.addWidget(self.region_monitor,1);row.addWidget(QLabel('Drag inside the preview to select an area.'));region_layout.addLayout(row)
        self.region=RegionCanvas();region_layout.addWidget(self.region,1)
        self.region.setEnabled(bool(self.monitors))
        self.region.regionChanged.connect(self.choose_region);self.region_monitor.currentIndexChanged.connect(self.change_region)
        self.tabs.addTab(self.region_page,'Region');self.change_region()
        self.tabs.currentChanged.connect(self.tab_changed)
        self.hint=QLabel('Choose a source to continue.');self.hint.setObjectName('hint');self.hint.setMinimumHeight(30);self.hint.setWordWrap(True);root.addWidget(self.hint)
        footer=QHBoxLayout();self.remember=QCheckBox('Remember this selection');self.remember.setChecked(allow_token)
        self.remember.setToolTip('Allow this application to reuse this source without asking again.');footer.addWidget(self.remember);footer.addStretch()
        cancel=QPushButton('Cancel');cancel.clicked.connect(self.close);footer.addWidget(cancel)
        self.share=QPushButton('Share selected');self.share.setObjectName('share');self.share.setEnabled(False);self.share.clicked.connect(self.confirm);footer.addWidget(self.share)
        footer.addWidget(QSizeGrip(self));root.addLayout(footer)
        QShortcut(QKeySequence('Escape'),self,activated=self.close);QShortcut(QKeySequence('Return'),self,activated=self.confirm)
        self.queue=PreviewQueue(self);self.layout_cards()
        self.refresh_timer=QTimer(self);self.refresh_timer.timeout.connect(self.refresh_sources);self.refresh_timer.start(2000)
        self.session=None;self.notifier=None
        if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
            try:
                self.session=socket.socket(socket.AF_UNIX);self.session.connect(str(Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']/'.socket2.sock'))
                self.notifier=QSocketNotifier(self.session.fileno(),QSocketNotifier.Type.Read,self);self.notifier.activated.connect(self.session_event)
            except (OSError,KeyError):self.session=None

    def grid_page(self,search=False):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,0,0,0);layout.setSpacing(12)
        if search:
            self.search=QLineEdit();self.search.setPlaceholderText('Find a window or application…');self.search.textChanged.connect(lambda _:self.layout_cards());layout.addWidget(self.search)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget();content.setObjectName('grid');grid=QGridLayout(content);grid.setContentsMargins(0,0,10,0);grid.setSpacing(14);grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content);layout.addWidget(scroll,1)
        return page,grid,scroll

    def layout_cards(self):
        if not hasattr(self,'screen_cards'):return
        columns=max(1,min(3,(self.width()-70)//265))
        query=self.search.text().casefold()
        for grid,cards in ((self.screen_grid,self.screen_cards),(self.window_grid,self.window_cards)):
            while grid.count():grid.takeAt(0)
            shown=[c for c in cards if cards is self.screen_cards or query in (c.source['title']+' '+c.source.get('app','')).casefold()]
            for card in cards:card.setVisible(card in shown)
            for n,card in enumerate(shown):grid.addWidget(card,n//columns,n%columns)
            for column in range(3):grid.setColumnStretch(column,1 if column<columns else 0)
        self.columns=columns

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'search'):self.layout_cards()

    def visible_cards(self):
        if self.tabs.currentIndex()==2:return [self.region] if self.monitors else []
        scroll=self.screen_scroll if self.tabs.currentIndex()==0 else self.window_scroll
        viewport=scroll.viewport()
        return [c for c in (self.screen_cards if self.tabs.currentIndex()==0 else self.window_cards)
                if c.isVisible() and viewport.rect().intersects(c.geometry().translated(c.parent().pos()))]

    def choose(self,card):
        self.chosen=card.source
        for other in self.cards:other.setChecked(other is card)
        self.share.setEnabled(True)
        self.hint.setText(('Entire screen: ' if card.source['kind']=='screen' else 'One window: ')+card.source.get('title',card.source['name']))

    def choose_region(self,value):
        self.chosen=value
        if not hasattr(self,'share'):return
        self.share.setEnabled(value is not None)
        self.hint.setText(f'{value["rect"][2]} × {value["rect"][3]} area on {value["name"]}' if value else 'Drag inside the preview to choose a region.')

    def change_region(self):
        if self.region_monitor.currentIndex()<0:return
        self.region.source=dict(self.region_monitor.currentData());self.region.source['title']='Drag to select a region'
        self.region.pixmap=QPixmap();self.region.region=None;self.region.last_attempt=0;self.region.update()
        if hasattr(self,'tabs') and self.tabs.currentIndex()==2:self.choose_region(None)

    def tab_changed(self,*_):
        self.chosen=None;self.share.setEnabled(False)
        for card in self.cards:card.setChecked(False)
        self.region.region=None
        self.hint.setText('Drag inside the preview to choose a region.' if self.tabs.currentIndex()==2 else 'Choose a source to continue.')
        self.layout_cards()

    def refresh_sources(self):
        clients=ctl('clients');monitors=ctl('monitors')
        if not clients and not monitors:return
        by_id={s['id']:s for s in match_windows(self.sources,clients)}
        names={m['name'] for m in monitors}
        for card in self.cards:
            if card.source['kind']=='window':
                available=by_id.get(card.source['id'],{}).get('available',False)
            else:available=card.source['name'] in names
            card.setEnabled(available)
            if not available and self.chosen is card.source:
                self.chosen=None;self.share.setEnabled(False);self.hint.setText('That source closed or disconnected. Choose another one.')
        if self.chosen and self.chosen['kind']=='region':
            current=next((m for m in monitors if m['name']==self.chosen['name']),None)
            previous=self.region.source.get('monitor_data',{})
            if current is None or any(current.get(k)!=previous.get(k) for k in ('width','height','scale','transform')):
                self.choose_region(None);self.region.region=None
                self.hint.setText('The screen layout changed. Reopen sharing to draw a new region.')

    def confirm(self):
        if not self.chosen or not self.share.isEnabled():return
        if self.preview:
            self.hint.setText('Preview only — open screen sharing in your app to start a stream.');return
        # Recheck once at confirmation; a closed source must never turn into a different one.
        self.refresh_sources()
        if not self.chosen:return
        try:self.output=selection(self.chosen,self.remember.isChecked())
        except ValueError as error:self.hint.setText(str(error));return
        self.close()

    def session_event(self,*_):
        try:
            if self.session.recv(65536):return
        except OSError:pass
        self.output='';self.close()

    def closeEvent(self,event):
        self.queue.stop();self.refresh_timer.stop()
        if self.notifier:self.notifier.setEnabled(False)
        if self.session:self.session.close();self.session=None
        super().closeEvent(event)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--allow-token',action='store_true');parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    app=QApplication([sys.argv[0]]);app.setApplicationName('xetal-share-picker');app.setDesktopFileName('xetal-share-picker')
    theme_runtime.install(app,STYLE)
    window=Picker(args.allow_token,args.preview)
    screen=app.primaryScreen()
    if screen:
        available=screen.availableGeometry();window.resize(min(1080,available.width()-60),min(720,available.height()-70))
    window.show();app.exec()
    if window.output:sys.stdout.write(window.output);sys.stdout.flush()


if __name__=='__main__':main()
