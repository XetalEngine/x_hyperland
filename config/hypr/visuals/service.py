#!/usr/bin/env python3
"""Session-owned hover previews and an indicator for actual desktop capture."""
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from PyQt6.QtCore import Qt,QTimer,QRect
from PyQt6.QtGui import QPainter,QColor,QPen
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication,QWidget
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'theme'))
import runtime
from visuals import model,controller
from visuals.app import Jobs
from switcher.previews import PreviewQueue


class CaptureState:
    """Ignore one-frame screenshots and local window-thumbnail captures."""
    def __init__(self):self.streams=Counter();self.since={}
    def event(self,line,now):
        if not line.startswith('screencastv2>>'):return
        parts=line.partition('>>')[2].split(',',2)
        if len(parts)!=3 or parts[0] not in ('0','1') or parts[1] not in ('monitor','region','workspace'):return
        key=tuple(parts[1:]);self.streams[key]=max(0,self.streams[key]+(1 if parts[0]=='1' else -1))
        if self.streams[key]:self.since.setdefault(key,now)
        else:self.since.pop(key,None)
        self.streams+=Counter()
    def active(self,now):return any(now-start>=1.0 for start in self.since.values())
    def caption(self):return ', '.join(f'{kind}: {name}' for (kind,name),count in self.streams.items() if count)


def resolve_hover(request,clients):
    """Waybar exposes titles, not addresses. Ambiguous titles never select a window."""
    title=request.get('title','')
    if not title:return None
    candidates=[]
    for client in clients:
        workspace=client.get('workspace',{});name=workspace.get('name','')
        same=workspace.get('id')==request.get('workspace') or name=='special:xetal-minimized-ws-'+str(request.get('workspace'))
        if same and client.get('mapped') and client.get('title','').replace('\n',' ').replace('\r',' ')==title:candidates.append(client)
    return candidates[0] if len(candidates)==1 else None


def current_request(directory):
    try:
        raw=(directory/'fusion-hover.json').read_bytes()
        if len(raw)>32768:return {}
        value=json.loads(raw)
        if not isinstance(value,dict) or not value.get('show') or not 0<=time.time()-value.get('time',0)<1:return {}
        if any(type(value.get(k)) not in (int,float) for k in ('workspace','x','monitor_x','monitor_y')):return {}
        return value
    except (OSError,ValueError,TypeError):return {}


def hover_key(request):return tuple(request.get(k) for k in ('workspace','title','x','y','edge','monitor_x','monitor_y','bottom'))


class Bubble(QWidget):
    def __init__(self,title):
        super().__init__();self.setWindowTitle(title);self.setProperty('xetalOverlay',True)
        self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|
                            Qt.WindowType.WindowDoesNotAcceptFocus|Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.picture=None;self.text='';self.detail='';self.resize(360,245)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setBrush(QColor(17,25,35,247));p.setPen(QPen(QColor(model.palette()['Accent']),1))
        p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),12,12)
        p.setPen(QColor('#edf3fc'));area=self.rect().adjusted(12,12,-12,-48)
        if self.picture is not None and not self.picture.isNull():
            size=self.picture.size().scaled(area.size(),Qt.AspectRatioMode.KeepAspectRatio)
            target=QRect(area);target.setSize(size);target.moveCenter(area.center());p.drawPixmap(target,self.picture)
        elif self.height()>100:p.drawText(area,Qt.AlignmentFlag.AlignCenter,'Preview unavailable')
        p.drawText(self.rect().adjusted(12,self.height()-44,-12,-22),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(self.text,Qt.TextElideMode.ElideRight,self.width()-24))
        p.setPen(QColor('#a9bdd3'));p.drawText(self.rect().adjusted(12,self.height()-23,-12,-3),Qt.AlignmentFlag.AlignVCenter,
                    p.fontMetrics().elidedText(self.detail,Qt.TextElideMode.ElideRight,self.width()-24))


class Service:
    def __init__(self,app):
        self.app=app;self.directory=controller.instance();self.jobs=Jobs(app);self.busy=False;self.request_key=None
        self.preview=Bubble('Fusion window preview');self.badge=Bubble('Fusion capture indicator');self.badge.resize(380,58)
        self.queue=PreviewQueue(self.preview);self.queue.changed.connect(self.frame);self.address=''
        self.capture=CaptureState();self.quiet=False;self.quiet_busy=False;self.buffer=b'';self.stopping=False
        self.socket=QLocalSocket(app);self.socket.readyRead.connect(self.events);self.socket.disconnected.connect(app.quit)
        self.socket.connectToServer(str(self.directory/'.socket2.sock'))
        self.timer=QTimer(app);self.timer.setInterval(150);self.timer.timeout.connect(self.tick);self.timer.start()
        try:self.settings=controller.runtime_settings()
        except (OSError,ValueError):self.settings=model.validate(model.DEFAULTS)
        self.read_at=0;self.last_indicator=False
        self.cleanup_stale()
    def cleanup_stale(self):
        path=self.directory/'fusion-presentation-active'
        if path.exists():path.unlink();controller.reload()
    def events(self):
        self.buffer+=bytes(self.socket.readAll())
        if len(self.buffer)>1024*1024:self.buffer=b'';return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1);self.capture.event(line.decode('utf-8','replace'),time.monotonic())
    def tick(self):
        if self.stopping:return
        now=time.monotonic()
        if now-self.read_at>1:
            try:
                settings=controller.runtime_settings()
                if settings!=self.settings:self.request_key=None
                self.settings=settings
            except (OSError,ValueError):pass
            self.read_at=now
        active=self.capture.active(now)
        self.badge.text='Screen capture active';self.badge.detail=self.capture.caption();self.badge.update()
        if active!=self.last_indicator:
            self.last_indicator=active
            if active:self.badge.show()
            else:self.badge.hide()
        quiet=active and self.settings['quiet_sharing']
        if quiet!=self.quiet and not self.quiet_busy:
            self.quiet=quiet;self.quiet_busy=True
            path=self.directory/'fusion-presentation-active'
            if quiet:
                controller.atomic(path,json.dumps({'pid':os.getpid()}))
                subprocess.Popen([sys.executable,str(ROOT/'visuals/controller.py'),'--guard-quiet',str(os.getpid())],
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            else:path.unlink(missing_ok=True)
            self.jobs.run(controller.reload,self.quiet_done,self.quiet_failed)
        request=current_request(self.directory)
        if not self.settings['hover_previews'] or not request:
            self.preview.hide();self.queue.stop();self.request_key=None;return
        key=hover_key(request)
        if key==self.request_key or self.busy:return
        self.request_key=key;self.busy=True
        def done(result):
            self.busy=False
            if key!=hover_key(current_request(self.directory)) or self.stopping:
                self.request_key=None;return
            client=resolve_hover(request,result['clients'])
            if client is None:self.preview.hide();self.queue.stop();return
            self.address=client['address'];self.preview.text=client.get('title','')
            self.preview.detail='Workspace '+str(request['workspace'])+' · '+client.get('class','')+' · click its taskbar icon to restore'
            width,fps=model.preview_limits(self.settings);self.preview.resize(width,round(width*.625)+48)
            self.preview.hide();self.preview.picture=None
            commands=self.preview_commands(request,result['monitors'])
            if not commands:self.queue.stop();return
            self.busy=True
            def placed(_):
                self.busy=False
                if key!=hover_key(current_request(self.directory)) or self.stopping:
                    self.request_key=None;return
                self.preview.show();self.queue.stop();self.queue.start(fps);self.queue.request([self.address]);self.preview.update()
            self.jobs.run(lambda:[controller.ctl(*args) for args in commands],placed,self.failed)
        self.jobs.run(lambda:{name:json.loads(controller.ctl('-j',name)) for name in ('clients','monitors')},done,self.failed)
    def quiet_done(self,_):self.quiet_busy=False;self.request_key=None
    def quiet_failed(self,message):self.quiet_busy=False;print(message,file=sys.stderr)
    def failed(self,message):self.busy=False;self.preview.hide();self.queue.stop();print(message,file=sys.stderr)
    def preview_commands(self,request,monitors):
        m=next((m for m in monitors if m.get('x')==request.get('monitor_x') and m.get('y')==request.get('monitor_y')),None)
        if not m:return
        width,height=m['width']/m.get('scale',1),m['height']/m.get('scale',1)
        if m.get('transform',0)%2:width,height=height,width
        x=max(8,min(width-self.preview.width()-8,request['x']-m['x']-self.preview.width()/2))
        y=height-self.preview.height()-50 if request.get('bottom') else 50
        if request.get('edge') in ('left','right') and type(request.get('y')) in (int,float):
            x=60 if request['edge']=='left' else width-self.preview.width()-60
            y=max(8,min(height-self.preview.height()-8,request['y']-m['y']-self.preview.height()/2))
        from compat.hypr_compat import call
        rule=model.overlay_rule('fusion-window-preview','Fusion window preview',f'{round(max(8,x))} {round(max(8,y))}')
        rule['monitor']=str(m['id'])
        return [('eval',call('window_rule',rule))]
    def frame(self,address):
        if address==self.address:self.preview.picture=self.queue.cache.get(address);self.preview.update()
    def close(self):
        self.stopping=True;self.timer.stop();self.socket.abort();self.queue.shutdown()
        for worker in tuple(self.jobs.workers):worker.wait()
        self.preview.close();self.badge.close()
        if self.quiet:
            (self.directory/'fusion-presentation-active').unlink(missing_ok=True)
            try:controller.reload()
            except (OSError,ValueError):pass


def main():
    # These workspace/hover tools are hidden; Focus needs no background service.
    if not model.EXPERIMENTAL_VISUALS:return 0
    directory=controller.instance()
    with (directory/'fusion-visuals.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        app=QApplication(sys.argv[:1]);app.setApplicationName('fusion-visual-service');app.setDesktopFileName('fusion-visual-service')
        app.setQuitOnLastWindowClosed(False);runtime.install(app)
        service=Service(app);signal.signal(signal.SIGTERM,lambda *_:app.quit());signal.signal(signal.SIGINT,lambda *_:app.quit())
        try:return app.exec()
        finally:service.close()


if __name__=='__main__':sys.exit(main())
