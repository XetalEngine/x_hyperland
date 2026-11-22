"""Live, searchable workspace cards. Captures stay in memory while visible."""
import json
import math
import os
import re
import subprocess
import sys
from PyQt6.QtCore import Qt,QRectF,QTimer,pyqtSignal,QMimeData,QPoint
from PyQt6.QtGui import QPainter,QColor,QPen,QDrag,QKeySequence,QShortcut
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QScrollArea,QPushButton,QGridLayout
from visuals import model,controller
from switcher.previews import PreviewQueue

MIME='application/x-hyperfusion-window'
EXCLUDE={'fusion-overview','fusion-visual-service','fusion-sample','xetal-switcher','xetal-launcher','fusion-clipboard'}


def clients_for_workspace(clients,number):
    result=[]
    for c in clients:
        if not c.get('mapped') or c.get('class') in EXCLUDE or c.get('class','').startswith('xetal-startup'):continue
        if not re.fullmatch(r'0x[0-9a-fA-F]+',c.get('address','')):continue
        workspace=c.get('workspace',{}); minimized=re.fullmatch(r'special:xetal-minimized-ws-(-?\d+)',workspace.get('name',''))
        if workspace.get('id')==number or (minimized and int(minimized[1])==number):result.append(c)
    return sorted(result,key=lambda c:c.get('focusHistoryID',99999))


def snapshot():
    keys={'monitors':('name','id'),'workspaces':('id','name','monitor'),
          'clients':('mapped','hidden','address','pid','title','class','workspace')}
    data={name:[{k:c[k] for k in keys[name] if k in c} for c in json.loads(controller.ctl('-j',name))] for name in keys}
    try:
        lines=(controller.instance()/'xetal-cube-faces').read_text().splitlines()
        if lines and lines[0]=='enabled':
            faces={int(line.split()[0]):line.partition('\t')[2] or line.split()[1] for line in lines[1:] if len(line.split())>=2}
            for w in data['workspaces']:w['display_name']=faces.get(w['id'],w['name'])
    except (OSError,ValueError,KeyError):pass
    return data


def activate(address,pid):
    live=json.loads(controller.ctl('-j','clients'))
    if not any(c.get('address')==address and c.get('pid')==pid and c.get('mapped') for c in live):
        raise ValueError('That window closed. Choose another one.')
    process=subprocess.run([sys.executable,str(model.ROOT/'scripts/activate-window.py'),address],capture_output=True,text=True,timeout=8)
    if process.returncode:raise ValueError(process.stderr.strip() or 'Could not activate the window.')


def move_window(identity,target):
    clients=json.loads(controller.ctl('-j','clients'));workspaces=json.loads(controller.ctl('-j','workspaces'))
    window=next((c for c in clients if c.get('address')==identity.get('address') and c.get('pid')==identity.get('pid') and c.get('mapped')),None)
    if not window:raise ValueError('That window has closed.')
    if window.get('workspace',{}).get('name','').startswith('special:') or window.get('hidden'):
        raise ValueError('Restore the minimized window before moving it.')
    if type(target) is not int or target<=0 or not any(w.get('id')==target for w in workspaces):
        raise ValueError('The destination workspace is no longer available.')
    return controller.ctl('dispatch','movetoworkspacesilent',f'{target},address:'+window['address'])


class WindowCard(QWidget):
    activated=pyqtSignal(dict)
    def __init__(self,client,queue):
        super().__init__();self.client=client;self.queue=queue;self.origin=None
        self.setMinimumSize(140,125);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(client.get('title') or client.get('class') or 'Window')
        self.setToolTip((client.get('title') or '')+'\nApp class: '+client.get('class','')+'\nClick to switch · drag to move workspace')
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        colors=model.palette();box=QRectF(self.rect()).adjusted(1,1,-1,-1)
        p.setPen(QPen(QColor(colors['Accent'] if self.underMouse() or self.hasFocus() else colors['Midlight']),1))
        p.setBrush(QColor(colors['Window']));p.drawRoundedRect(box,9,9)
        area=QRectF(8,8,self.width()-16,self.height()-53);picture=self.queue.cache.get(self.client['address'])
        if picture is not None and not picture.isNull():
            size=picture.size().scaled(area.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
            target=QRectF(0,0,size.width(),size.height());target.moveCenter(area.center());p.drawPixmap(target,picture,QRectF(picture.rect()))
        else:
            p.setPen(QColor(colors['Accent']));p.drawText(area,Qt.AlignmentFlag.AlignCenter,'Minimized' if self.client.get('hidden') else 'Preview unavailable')
        p.setPen(self.palette().text().color());name=self.client.get('title') or self.client.get('class','Window')
        p.drawText(QRectF(9,self.height()-40,self.width()-18,20),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,self.width()-18))
        p.setPen(QColor(colors['Accent']));p.drawText(QRectF(9,self.height()-21,self.width()-18,17),Qt.AlignmentFlag.AlignVCenter,self.client.get('class',''))
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.origin=event.position().toPoint()
    def mouseMoveEvent(self,event):
        if self.origin is None or not event.buttons()&Qt.MouseButton.LeftButton:return
        if (event.position().toPoint()-self.origin).manhattanLength()<12:return
        self.origin=None
        if self.client.get('hidden') or self.client.get('workspace',{}).get('name','').startswith('special:'):return
        drag=QDrag(self);mime=QMimeData();mime.setData(MIME,json.dumps({k:self.client.get(k) for k in ('address','pid')}).encode())
        drag.setMimeData(mime);drag.setPixmap(self.grab().scaledToWidth(180,Qt.TransformationMode.SmoothTransformation))
        window=self.window();window.dragging=True
        try:drag.exec(Qt.DropAction.MoveAction)
        finally:window.dragging=False
    def mouseReleaseEvent(self,event):
        if self.origin is not None and event.button()==Qt.MouseButton.LeftButton:self.origin=None;self.activated.emit(self.client)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):self.activated.emit(self.client)
        else:super().keyPressEvent(event)


class WorkspaceCard(QWidget):
    moved=pyqtSignal(dict,int);activated=pyqtSignal(int)
    def __init__(self,workspace,clients,queue,choose):
        super().__init__();self.workspace=workspace;self.setAcceptDrops(True)
        root=QVBoxLayout(self);root.setContentsMargins(10,10,10,10)
        title=QPushButton('Workspace '+str(workspace.get('display_name',workspace.get('name',workspace['id'])))+' · '+workspace.get('monitor',''))
        title.clicked.connect(lambda:self.activated.emit(workspace['id']));root.addWidget(title)
        body=QWidget();grid=QGridLayout(body);grid.setContentsMargins(0,0,0,0);self.cards=[]
        for i,client in enumerate(clients):
            card=WindowCard(client,queue);card.activated.connect(choose);grid.addWidget(card,i//2,i%2);self.cards.append(card)
        if not clients:
            empty=QLabel('Empty workspace · drop a window here');empty.setWordWrap(True);empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(125);grid.addWidget(empty,0,0)
        root.addWidget(body);root.addStretch();self.setMinimumWidth(320)
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(MIME):event.acceptProposedAction()
    def dropEvent(self,event):
        try:
            data=json.loads(bytes(event.mimeData().data(MIME)))
            if not isinstance(data,dict) or set(data)!= {'address','pid'}:return
            self.moved.emit(data,self.workspace['id']);event.acceptProposedAction()
        except (ValueError,TypeError):return


class Overview(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=False;self.polling=False;self.data=None;self.signature=None;self.cards=[];self.dragging=False;self.columns=2
        self.setWindowTitle('Fusion Overview');self.resize(1180,760)
        root=QVBoxLayout(self);heading=QHBoxLayout();title=QLabel('Fusion Overview');title.setObjectName('brand');heading.addWidget(title)
        self.monitor=QComboBox();self.monitor.addItem('All displays',None);self.monitor.currentIndexChanged.connect(self.rebuild);heading.addWidget(self.monitor)
        close=QPushButton('Close');close.clicked.connect(self.close);heading.addWidget(close);root.addLayout(heading)
        self.search=QLineEdit();self.search.setPlaceholderText('Find a window or app…');self.search.textChanged.connect(self.rebuild);root.addWidget(self.search)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);root.addWidget(self.scroll,1)
        self.body=QWidget();self.grid=QGridLayout(self.body);self.scroll.setWidget(self.body)
        self.status=QLabel('Click a window or workspace · drag windows between workspaces · Escape closes');self.status.setWordWrap(True);root.addWidget(self.status)
        self.queue=PreviewQueue(self);self.queue.changed.connect(self.frame)
        self.poll=QTimer(self);self.poll.setInterval(1000);self.poll.timeout.connect(self.refresh)
        self.capture=QTimer(self);self.capture.setInterval(250);self.capture.timeout.connect(self.request)
        QShortcut(QKeySequence('Escape'),self,activated=self.close)
        self.columns=2
    def showEvent(self,event):
        super().showEvent(event)
        try:settings=controller.runtime_settings()
        except (OSError,ValueError):settings=model.DEFAULTS
        self.queue.start(model.preview_limits(settings)[1]);self.poll.start();self.capture.start();self.refresh();self.search.setFocus()
    def hideEvent(self,event):
        self.poll.stop();self.capture.stop();self.queue.stop();super().hideEvent(event)
    def closeEvent(self,event):self.queue.shutdown();super().closeEvent(event)
    def refresh(self):
        if self.busy or self.polling or not self.isVisible():return
        self.polling=True;self.async_run(snapshot,self.loaded,self.poll_failed)
    def poll_failed(self,message):
        self.polling=False
        if not self.busy:self.status.setText(message)
    def failed(self,message):self.busy=False;self.status.setText(message)
    def loaded(self,data):
        self.polling=False
        if not self.isVisible() or self.dragging or self.busy:return
        signature=json.dumps(data,sort_keys=True)
        if signature==self.signature:return
        self.signature=signature;self.data=data
        current=self.monitor.currentData();self.monitor.blockSignals(True);self.monitor.clear();self.monitor.addItem('All displays',None)
        for m in data['monitors']:self.monitor.addItem(m['name'],m['name'])
        self.monitor.setCurrentIndex(max(0,self.monitor.findData(current)));self.monitor.blockSignals(False);self.rebuild()
    def rebuild(self,*_):
        if self.data is None or self.dragging:return
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.cards=[];term=self.search.text().strip().casefold();monitor=self.monitor.currentData()
        workspaces=[w for w in self.data['workspaces'] if w.get('id',0)>0 and (not monitor or w.get('monitor')==monitor)]
        workspaces.sort(key=lambda w:(w.get('monitor',''),w['id']))
        for i,w in enumerate(workspaces):
            clients=[c for c in clients_for_workspace(self.data['clients'],w['id']) if not term or term in (c.get('title','')+' '+c.get('class','')).casefold()]
            card=WorkspaceCard(w,clients,self.queue,self.choose);card.moved.connect(self.move);card.activated.connect(self.workspace)
            self.grid.addWidget(card,i//self.columns,i%self.columns);self.cards.extend(card.cards)
        if not workspaces:self.grid.addWidget(QLabel('No numbered workspaces on this display.'),0,0)
        QTimer.singleShot(0,self.request)
    def resizeEvent(self,event):
        super().resizeEvent(event);columns=max(1,min(4,(self.width()-45)//440))
        if columns!=self.columns:self.columns=columns;self.rebuild()
    def request(self):
        if not self.isVisible():return
        view=self.scroll.viewport();wanted=[]
        for card in self.cards:
            rect=card.rect().translated(card.mapTo(view,QPoint(0,0)))
            if view.rect().intersects(rect):wanted.append(card.client['address'])
        self.queue.request(wanted)
    def frame(self,address):
        for card in self.cards:
            if card.client['address']==address:card.update()
    def choose(self,client):
        if self.busy:return
        self.busy=True;self.async_run(lambda:activate(client['address'],client.get('pid')),lambda _:self.close(),self.failed)
    def workspace(self,number):
        if self.busy:return
        self.busy=True;self.async_run(lambda:controller.ctl('dispatch','workspace',str(number)),lambda _:self.close(),self.failed)
    def move(self,identity,number):
        if self.busy:return
        self.busy=True
        def done(_):self.busy=False;self.status.setText('Window moved.');self.refresh()
        self.async_run(lambda:move_window(identity,number),done,self.failed)
