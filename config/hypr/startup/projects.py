#!/usr/bin/env python3
"""Theme-aware, perspective-rendered project cubes for the Super+D dashboard."""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
import time

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, QProcess, QObject, QSocketNotifier, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPalette, QPen, QPolygonF,
                         QIcon, QTransform, QLinearGradient, QRadialGradient, QKeySequence, QShortcut)
from PyQt6.QtWidgets import (QApplication, QAbstractButton, QWidget, QLabel, QVBoxLayout,
                            QHBoxLayout, QGridLayout, QScrollArea, QSizePolicy, QCheckBox)
from projects_model import catalog, hide_dashboard, open_project, WORKSPACE
import login_settings

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'theme'))
import runtime as theme_runtime
from window_chrome import window_controls


def alpha(value, opacity):
    color = QColor(value); color.setAlphaF(opacity); return color


def font(size, weight=QFont.Weight.Normal, mono=False):
    result = QFont('JetBrains Mono' if mono else QApplication.instance().font().family())
    result.setPixelSize(size); result.setWeight(weight); return result


def projected_faces(size, center, yaw, pitch):
    """Perspective projection of a real cube, ordered from rear to front."""
    vertices = []
    for x, y, z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                    (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]:
        x, z = x*math.cos(yaw)+z*math.sin(yaw), -x*math.sin(yaw)+z*math.cos(yaw)
        y, z = y*math.cos(pitch)-z*math.sin(pitch), y*math.sin(pitch)+z*math.cos(pitch)
        perspective = 5/(5-z)
        vertices.append((QPointF(center.x()+x*size*.5*perspective,
                                center.y()+y*size*.5*perspective), z))
    faces = [(4,5,6,7), (1,0,3,2), (0,4,7,3), (5,1,2,6), (0,1,5,4), (7,6,2,3)]
    return sorted([(sum(vertices[i][1] for i in ids)/4, n,
                    QPolygonF([vertices[i][0] for i in ids])) for n,ids in enumerate(faces)])


class ProjectCube(QAbstractButton):
    def __init__(self, project, index, parent=None):
        super().__init__(parent)
        self.project, self.index = project, index
        self.setText(project.name); self.setAccessibleName('Explore '+project.name)
        self.setAccessibleDescription(project.description+'. Opens the project website.')
        self.setToolTip(project.name+' — '+project.description+'\n'+project.url)
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # QIcon chooses the largest ICO frame; QPixmap would use its tiny first frame.
        self.pixmap = QIcon(str(project.icon)).pixmap(384,384)
        if not self.pixmap.isNull():
            self.pixmap = self.pixmap.scaled(384,384,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self.hover = 0.; self.t = 0.; self.pointer = QPointF(); self.over = False

    def advance(self, elapsed):
        self.t = elapsed
        self.hover += ((1 if self.over or self.hasFocus() else 0)-self.hover)*.16
        self.update()

    def enterEvent(self,event): self.over=True; super().enterEvent(event)
    def leaveEvent(self,event): self.over=False; self.pointer=QPointF(); super().leaveEvent(event)
    def mouseMoveEvent(self,event):
        self.pointer = QPointF((event.position().x()/max(1,self.width())-.5)*2,
                               (event.position().y()/max(1,self.height())-.5)*2)
        super().mouseMoveEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
            if not event.isAutoRepeat():self.click()
            event.accept();return
        super().keyPressEvent(event)

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
        w,h=self.width(),self.height(); tone=QColor(self.project.accent)
        text=self.palette().color(QPalette.ColorRole.Text); muted=self.palette().color(QPalette.ColorRole.PlaceholderText)
        surface=self.palette().color(QPalette.ColorRole.Base)
        phase=self.t*.7+self.index*1.14
        size=min(w*.42,h*.38,230)*(1+self.hover*.035)
        baseline=h*.66
        center=QPointF(w/2, h*.31+math.sin(phase)*5-self.hover*7+(3 if self.isDown() else 0))
        glow=QRadialGradient(QPointF(0,0),1)
        glow.setColorAt(0,alpha(tone,.19+self.hover*.14));glow.setColorAt(1,alpha(tone,0))
        p.save();p.translate(w/2,baseline+4);p.scale(size*.74,17)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(glow);p.drawEllipse(QRectF(-1,-1,2,2));p.restore()
        yaw=-.55+math.sin(phase*.7)*.055+self.pointer.x()*.13*self.hover
        pitch=-.35+math.cos(phase*.8)*.035-self.pointer.y()*.09*self.hover
        faces=projected_faces(size,center,yaw,pitch)
        for depth,number,polygon in faces:
            path=QPainterPath();path.addPolygon(polygon);path.closeSubpath()
            gradient=QLinearGradient(polygon.boundingRect().topLeft(),polygon.boundingRect().bottomRight())
            if number==0:
                gradient.setColorAt(0,surface.lighter(165));gradient.setColorAt(1,surface)
            else:
                gradient.setColorAt(0,surface.lighter(220 if number==4 else 150))
                gradient.setColorAt(1,surface.lighter(120))
            p.setBrush(gradient);p.setPen(QPen(alpha(tone,.35+self.hover*.4),1.15));p.drawPath(path)
            if number==0:
                quad=QPolygonF([QPointF(0,0),QPointF(1,0),QPointF(1,1),QPointF(0,1)])
                transform=QTransform()
                if QTransform.quadToQuad(quad,polygon,transform):
                    p.save();p.setClipPath(path);p.setTransform(transform,True)
                    if self.pixmap.isNull():
                        p.setPen(tone);p.setFont(font(1));p.drawText(QRectF(.1,.1,.8,.8),Qt.AlignmentFlag.AlignCenter,self.project.name[:1])
                    else:
                        p.drawPixmap(QRectF(.12,.12,.76,.76),self.pixmap,QRectF(self.pixmap.rect()))
                    p.restore()
                sheen=QLinearGradient(polygon[0],polygon[2]);sheen.setColorAt(0,QColor(255,255,255,22));sheen.setColorAt(.55,QColor(255,255,255,0))
                p.setBrush(sheen);p.setPen(Qt.PenStyle.NoPen);p.drawPath(path)
        # Text stays level and still while the cube floats above it.
        title=QRectF(7,h*.73,w-14,31);p.setPen(text);p.setFont(font(max(15,min(24,int(w/17))),QFont.Weight.DemiBold))
        p.drawText(title,Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter,self.project.name)
        p.setPen(muted);p.setFont(font(max(11,min(14,int(w/29)))))
        description=p.fontMetrics().elidedText(self.project.description,Qt.TextElideMode.ElideRight,int(w-22))
        p.drawText(QRectF(11,title.bottom()+3,w-22,21),Qt.AlignmentFlag.AlignCenter,description)
        p.setPen(QPen(alpha(tone,.4+self.hover*.5),2))
        length=20+self.hover*32;p.drawLine(QPointF(w/2-length/2,h-13),QPointF(w/2+length/2,h-13))
        if self.hasFocus():
            p.setPen(QPen(alpha(tone,.7),1));p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(5,5,w-10,h-10),12,12)


class Gallery(QWidget):
    activated=pyqtSignal(object)
    def __init__(self,projects):
        super().__init__();self.setObjectName('projectGallery')
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setHorizontalSpacing(10);self.grid.setVerticalSpacing(10)
        self.buttons=[];self.columns=0;self.available_height=600
        for index,project in enumerate(projects):
            button=ProjectCube(project,index,self);button.clicked.connect(lambda _,p=project:self.activated.emit(p));self.buttons.append(button)
        self.arrange()

    def arrange(self):
        columns=max(1,min(3,self.width()//225))
        if self.width()<950 and self.available_height>self.width()*1.15:columns=min(columns,2)
        rows=math.ceil(len(self.buttons)/columns)
        height=max(205,min(520,(self.available_height-10*(rows-1))//rows))
        if columns!=self.columns:
            self.columns=columns
            for b in self.buttons:self.grid.removeWidget(b)
            for index,b in enumerate(self.buttons):self.grid.addWidget(b,index//columns,index%columns)
            for col in range(3):self.grid.setColumnStretch(col,1 if col<columns else 0)
        for b in self.buttons:b.setFixedHeight(height)
        self.setMinimumHeight(rows*height+(rows-1)*10)

    def resizeEvent(self,event): super().resizeEvent(event);self.arrange()


class Dashboard(QWidget):
    def __init__(self,projects):
        super().__init__();self.setWindowTitle('Xetal / Projects');self.setObjectName('projectsWindow')
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1120,820);self.setMinimumSize(390,410)
        self.started=time.monotonic();self.motion=QTimer(self);self.motion.setInterval(33);self.motion.timeout.connect(self.animate)
        layout=QVBoxLayout(self);layout.setContentsMargins(30,19,30,20);layout.setSpacing(7)
        top=QHBoxLayout();brand=QLabel('04 / XETAL ENGINE');brand.setObjectName('projectEyebrow');brand.setFont(font(12,QFont.Weight.DemiBold,True))
        top.addWidget(brand);top.addStretch();count=QLabel(f'{len(projects):02d} PROJECTS');count.setFont(font(11,mono=True));count.setObjectName('projectMuted');top.addWidget(count)
        top.addWidget(window_controls(self,self.hide_dashboard,'Hide dashboard'));layout.addLayout(top)
        self.title=QLabel('Try my other projects :D');self.title.setObjectName('projectTitle');layout.addSpacing(13);layout.addWidget(self.title)
        self.subtitle=QLabel('Pick a cube. Discover something new.');self.subtitle.setObjectName('projectMuted');self.subtitle.setFont(font(14));layout.addWidget(self.subtitle)
        self.scroll=QScrollArea();self.scroll.setObjectName('projectScroll');self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gallery=Gallery(projects);self.scroll.setWidget(self.gallery);layout.addWidget(self.scroll,1)
        self.login_toggle=QCheckBox('Show this dashboard at login');self.login_toggle.setObjectName('dashboardLoginEnabled')
        self.login_toggle.setToolTip('Start all four dashboard windows when you log in. Super + D always opens them manually.')
        layout.addWidget(self.login_toggle)
        self.login_status=QLabel();self.login_status.setObjectName('projectMuted');self.login_status.setFont(font(11));self.login_status.setWordWrap(True)
        layout.addWidget(self.login_status)
        self.login_saved=True;self.refresh_login_preference()
        self.login_toggle.toggled.connect(self.save_login_preference)
        footer=QHBoxLayout();self.message=QLabel('Made by Xetal');self.message.setObjectName('projectMuted');self.message.setFont(font(11,mono=True));footer.addWidget(self.message,1)
        site=QLabel('xetal.net  ↗');site.setObjectName('projectMuted');site.setFont(font(12));footer.addWidget(site);layout.addLayout(footer)
        self.worker=QProcess(self);self.worker.finished.connect(self.opened);self.worker.errorOccurred.connect(lambda _:self.message.setText('Could not open the project page.'))
        self.gallery.activated.connect(lambda p:self.run_action('--open',p.id))
        self.escape=QShortcut(QKeySequence('Escape'),self);self.escape.activated.connect(self.hide_dashboard)
        self.motion.start();self.apply_theme()

    def apply_theme(self):
        QApplication.instance().setFont(QFont(theme_runtime.ui_font()))
        colors=theme_runtime.colors()
        self.setStyleSheet('QLabel {background:transparent;} '
            f'QLabel#projectEyebrow {{color:{colors["Accent"]};}} '
            f'QLabel#projectMuted {{color:{colors["PlaceholderText"]};}} '
            'QWidget#projectGallery,QScrollArea#projectScroll,QScrollArea#projectScroll>QWidget {background:transparent;border:0;} '
            f'QScrollBar:vertical {{background:transparent;width:7px;}} QScrollBar::handle:vertical {{background:{colors["Midlight"]};border-radius:3px;min-height:25px;}} '
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}')
        self.update()

    def refresh_login_preference(self):
        with QSignalBlocker(self.login_toggle):
            try:
                self.login_saved=login_settings.enabled();self.login_toggle.setChecked(self.login_saved);self.login_toggle.setEnabled(True)
                self.login_status.setText('Super + D opens or hides all four windows anytime.')
            except (OSError,ValueError) as error:
                self.login_toggle.setEnabled(False);self.login_status.setText('Could not read startup preference: '+str(error))

    def save_login_preference(self,enabled):
        try:
            login_settings.save(enabled);self.login_saved=enabled
            self.login_status.setText('Saved. All four windows will open at login.' if enabled else
                                     'Saved. All four windows will stay closed at login. Super + D still opens them.')
        except (OSError,ValueError) as error:
            with QSignalBlocker(self.login_toggle):self.login_toggle.setChecked(self.login_saved)
            self.login_status.setText('Could not save startup preference: '+str(error))

    def set_motion(self,visible):
        if visible:self.refresh_login_preference();self.motion.start()
        else:self.motion.stop()

    def animate(self):
        elapsed=time.monotonic()-self.started
        for button in self.gallery.buttons:button.advance(elapsed)

    def run_action(self,*args):
        if self.worker.state()!=QProcess.ProcessState.NotRunning:return
        self.message.setText('Opening project page…' if args[0]=='--open' else 'Made by Xetal')
        self.worker.start(sys.executable,[str(ROOT/'projects.py'),*args])

    def opened(self,code,status):
        self.message.setText('Made by Xetal' if code==0 else 'Could not open the page. Try again.')

    def hide_dashboard(self): self.run_action('--hide')

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.title.setFont(font(max(21,min(46,int(self.width()/25))),QFont.Weight.Bold))
        QTimer.singleShot(0,self.fit_gallery)

    def fit_gallery(self):
        self.gallery.available_height=self.scroll.viewport().height();self.gallery.arrange()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette=self.palette();rect=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
        p.setPen(QPen(alpha(palette.color(QPalette.ColorRole.Midlight),.9),1))
        p.setBrush(alpha(palette.color(QPalette.ColorRole.Window),.94));p.drawRoundedRect(rect,12,12)
        p.setPen(QPen(alpha(palette.color(QPalette.ColorRole.Accent),.3),1))
        p.drawLine(QPointF(30,60),QPointF(self.width()-30,60))

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and event.position().y()<150 and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(event)


class SessionVisibility(QObject):
    """Pause hidden cubes from compositor events; exit with their session."""
    def __init__(self,window):
        super().__init__(window);self.window=window;self.buffer=b'';self.socket=None
        self.query=QProcess(self);self.query.finished.connect(self.received)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(50);self.debounce.timeout.connect(self.refresh)
        signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')
        if not signature:return
        path=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/'hypr'/signature/'.socket2.sock'
        try:
            self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.socket.settimeout(1);self.socket.connect(str(path));self.socket.setblocking(False)
            self.notifier=QSocketNotifier(self.socket.fileno(),QSocketNotifier.Type.Read,self);self.notifier.activated.connect(self.events)
            self.refresh()
        except OSError:
            if self.socket:self.socket.close()
            self.socket=None

    def events(self,*_):
        try:
            chunk=self.socket.recv(65536)
            if not chunk:
                self.notifier.setEnabled(False);QApplication.instance().quit();return
            self.buffer+=chunk
            while b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                if line.startswith((b'activespecial',b'monitoradded',b'monitorremoved',b'focusedmon')):self.debounce.start()
        except BlockingIOError:pass
        except OSError:self.notifier.setEnabled(False);QApplication.instance().quit()

    def refresh(self):
        if self.query.state()==QProcess.ProcessState.NotRunning:self.query.start('hyprctl',['-j','monitors'])
        else:self.debounce.start()

    def received(self,*_):
        try:
            monitors=json.loads(bytes(self.query.readAllStandardOutput()))
            self.window.set_motion(any(m.get('specialWorkspace',{}).get('name')==WORKSPACE for m in monitors))
        except (ValueError,TypeError):pass

    def close(self):
        if self.socket:self.notifier.setEnabled(False);self.socket.close()
        if self.query.state()!=QProcess.ProcessState.NotRunning:self.query.kill();self.query.waitForFinished(1000)


STYLE='QToolTip {padding:8px; border:1px solid palette(midlight); border-radius:6px;}'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--open');parser.add_argument('--hide',action='store_true');args=parser.parse_args()
    if args.open or args.hide:
        try:
            if args.open:
                project=next(p for p in catalog() if p.id==args.open)
                open_project(project,theme_runtime.environment())
            else:hide_dashboard()
        except Exception as error:
            print(str(error),file=sys.stderr);return 1
        return 0
    app=QApplication(sys.argv[:1]);app.setApplicationName('Xetal Projects');app.setDesktopFileName('xetal-startup-projects')
    live_theme=theme_runtime.install(app,STYLE)
    window=Dashboard(catalog());live_theme.changed.connect(window.apply_theme)
    visibility=SessionVisibility(window);app.aboutToQuit.connect(visibility.close)
    window.show();return app.exec()


if __name__=='__main__':sys.exit(main())
