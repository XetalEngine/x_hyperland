"""A theme-aware session dashboard; sampling never blocks the settings UI."""
from collections import deque
import getpass
import math
from pathlib import Path
import socket
import subprocess
import time

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QWidget, QLabel, QPushButton, QAbstractButton, QVBoxLayout,
                            QHBoxLayout, QGridLayout, QScrollArea, QFrame, QSizePolicy, QMessageBox)
import keys
import runtime
from icons import icon
from sounds.actions import before_power


def snapshot():
    import psutil
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home()))
    temperatures = []
    try:
        for name, values in psutil.sensors_temperatures().items():
            if name not in ('k10temp', 'coretemp', 'amdgpu', 'nvidia', 'cpu_thermal'): continue
            if values and math.isfinite(values[0].current):
                temperatures.append(f'{"GPU" if name in ("amdgpu", "nvidia") else "CPU"} {values[0].current:.0f}°C')
    except (AttributeError, OSError):
        pass
    minutes = max(0, int(time.time()-psutil.boot_time())) // 60
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return dict(cpu=psutil.cpu_percent(interval=.12), memory=memory.percent, disk=disk.percent,
                cpu_detail=f'{psutil.cpu_count() or 1} logical processors',
                memory_detail=f'{memory.used/2**30:.1f} / {memory.total/2**30:.1f} GiB in use',
                disk_detail=f'{disk.free/2**30:.0f} GiB free of {disk.total/2**30:.0f} GiB',
                uptime=(f'{days}d ' if days else '')+f'{hours}h {minutes:02d}m',
                temperatures='  ·  '.join(temperatures))


def color(value, alpha=1.):
    result = QColor(value); result.setAlphaF(alpha); return result


def font(size, bold=False):
    result = QFont(runtime.ui_font()); result.setPixelSize(size)
    result.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return result


def text(painter, rect, value, size, shade, bold=False, align=Qt.AlignmentFlag.AlignLeft):
    painter.setFont(font(size, bold)); painter.setPen(QColor(shade))
    value = painter.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, max(0, int(rect.width())))
    painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, value)


def surface(painter, rect, palette, design, active=False):
    """Materials share the active theme's palette, including light/contrast modes."""
    radius = 3 if design in ('raw', 'porcelainink', 'obsidianforge') else 12 if design in ('breakpoint', 'binaryknife', 'shadowedge') else 19
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, QColor(palette['Button']))
    gradient.setColorAt(.45, QColor(palette['Window']))
    gradient.setColorAt(1, QColor(palette['Base']))
    painter.setBrush(gradient)
    painter.setPen(QPen(color(palette['Accent' if active else 'Midlight'], 1 if active else .85), 1))
    painter.drawRoundedRect(rect, radius, radius)
    painter.setPen(QPen(color(palette['Accent'], .8 if active else .35), 2, cap=Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(rect.left()+20, rect.top()+1), QPointF(rect.left()+min(76, rect.width()/3), rect.top()+1))
    if design in ('gildedhollow', 'hollowgrove'):
        painter.setPen(QPen(color(palette['Link'], .24), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), max(0, radius-4), max(0, radius-4))


class ResourceCard(QWidget):
    def __init__(self, title, symbol, storage=False):
        super().__init__(); self.title=title; self.symbol=symbol; self.storage=storage
        self.value=None; self.detail='Reading system information…'; self.history=deque(maxlen=60)
        self.setMinimumSize(180, 178); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.update_design()

    def update_design(self):
        self.colors=runtime.colors(); self.design=runtime.design()
        self.symbol_icon=icon(self.symbol, self.colors['Accent'], 24); self.update()

    def set_reading(self, value, detail):
        self.value=max(0., min(100., float(value))); self.detail=detail
        self.history.append(self.value)
        self.setAccessibleName(f'{self.title}: {self.value:.0f}%. {detail}'); self.setToolTip(detail); self.update()

    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c=self.colors; w=self.width(); h=self.height(); surface(p, QRectF(1, 1, w-2, h-2), c, self.design)
        p.drawPixmap(20, 18, self.symbol_icon.pixmap(24, 24))
        text(p, QRectF(54, 18, w-74, 24), self.title.upper(), 11, c['PlaceholderText'], True)
        text(p, QRectF(20, 49, w-40, 49), '—' if self.value is None else f'{self.value:.0f}%', 38, c['Text'], True)
        text(p, QRectF(20, 101, w-40, 22), self.detail, 12, c['PlaceholderText'])
        box=QRectF(20, h-60, w-40, 27)
        if self.storage:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(c['Mid'], .7)); p.drawRoundedRect(box.adjusted(0, 9, 0, -9), 4, 4)
            if self.value:
                gradient=QLinearGradient(box.topLeft(), box.topRight())
                gradient.setColorAt(0, QColor(c['Highlight'])); gradient.setColorAt(1, QColor(c['Accent']))
                p.setBrush(gradient); p.drawRoundedRect(QRectF(box.x(), box.y()+9, box.width()*self.value/100, 9), 4, 4)
        elif self.history:
            p.setPen(QPen(color(c['Midlight'], .4), 1))
            p.drawLine(box.bottomLeft(), box.bottomRight())
            samples=list(self.history); samples=([samples[0]]*(60-len(samples)))+samples
            path=QPainterPath()
            for i, value in enumerate(samples):
                point=QPointF(box.left()+box.width()*i/59, box.bottom()-box.height()*value/100)
                if i==0: path.moveTo(point)
                else: path.lineTo(point)
            area=QPainterPath(path); area.lineTo(box.bottomRight()); area.lineTo(box.bottomLeft()); area.closeSubpath()
            gradient=QLinearGradient(box.topLeft(), box.bottomLeft())
            gradient.setColorAt(0, color(c['Accent'], .35)); gradient.setColorAt(1, color(c['Accent'], .02))
            p.fillPath(area, gradient); p.setPen(QPen(QColor(c['Accent']), 2, cap=Qt.PenCapStyle.RoundCap)); p.drawPath(path)
        text(p, QRectF(20, h-29, w-40, 18), 'HOME STORAGE' if self.storage else 'LIVE ACTIVITY  ·  2.5 MIN', 9, c['PlaceholderText'])
        p.end()


class ActionTile(QAbstractButton):
    def __init__(self, title, detail, symbol, callback, primary=False):
        super().__init__(); self.setText(title); self.detail=detail; self.symbol=symbol; self.primary=primary
        self.setAccessibleName(title); self.setAccessibleDescription(detail); self.setToolTip(detail)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(140, 87); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.clicked.connect(callback); self.update_design()

    def sizeHint(self): return QSize(215, 105)

    def update_design(self):
        self.colors=runtime.colors(); self.design=runtime.design()
        self.symbol_icon=icon(self.symbol, self.colors['Accent'], 26); self.update()

    def enterEvent(self, event): super().enterEvent(event); self.update()
    def leaveEvent(self, event): super().leaveEvent(event); self.update()
    def focusInEvent(self, event): super().focusInEvent(event); self.update()
    def focusOutEvent(self, event): super().focusOutEvent(event); self.update()

    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c=self.colors; w=self.width(); h=self.height()
        if not self.isEnabled(): p.setOpacity(.5)
        surface(p, QRectF(1, 1, w-2, h-2), c, self.design, self.underMouse() or self.hasFocus() or self.primary)
        if self.isDown(): p.translate(0, 1)
        if self.primary:
            y=(h-44)/2
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(color(c['Accent'], .12)); p.drawRoundedRect(QRectF(17, y, 44, 44), 12, 12)
            p.drawPixmap(26, int(y+9), self.symbol_icon.pixmap(26, 26))
            text(p, QRectF(74, y, w-92, 25), self.text(), 16, c['Text'], True)
            text(p, QRectF(74, y+25, w-92, 22), self.detail, 11, c['PlaceholderText'])
        else:
            p.drawPixmap(17, 13, self.symbol_icon.pixmap(26, 26))
            text(p, QRectF(17, h-47, w-34, 24), self.text(), 14, c['Text'], True)
            text(p, QRectF(17, h-24, w-34, 17), self.detail, 10, c['PlaceholderText'])
        p.end()


class SystemPage(QWidget):
    def __init__(self, async_run, launch, navigate):
        super().__init__(); self.async_run=async_run; self.launch=launch; self.navigate=navigate
        self.busy=False; self.power_busy=False
        outer=QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget(); root=QVBoxLayout(content); root.setContentsMargins(20, 14, 20, 14); root.setSpacing(18)
        header=QHBoxLayout(); heading=QVBoxLayout(); heading.setSpacing(6)
        self.title=QLabel('System & session'); self.title.setObjectName('brand'); heading.addWidget(self.title)
        self.identity=QLabel(f'{getpass.getuser()} @ {socket.gethostname()}  ·  Hyprland'); self.identity.setObjectName('muted')
        self.identity.setTextFormat(Qt.TextFormat.PlainText); heading.addWidget(self.identity); header.addLayout(heading, 1)
        self.uptime=QLabel('●  LIVE'); self.uptime.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.uptime.setObjectName('eyebrow'); header.addWidget(self.uptime); root.addLayout(header)
        resources=QHBoxLayout(); resources.setSpacing(14); self.metrics={}
        for name, title, symbol in [('cpu','Processor','chip'), ('memory','Memory','memory'), ('disk','Home disk','drive')]:
            card=ResourceCard(title, symbol, name=='disk'); resources.addWidget(card, 1); self.metrics[name]=card
        root.addLayout(resources, 2)
        self.temperatures=QLabel(''); self.temperatures.setObjectName('muted'); self.temperatures.hide(); root.addWidget(self.temperatures)
        controls=QHBoxLayout(); controls.setSpacing(20); self.tiles=[]; self.power_tiles=[]
        tools=QVBoxLayout(); tools.setSpacing(10)
        title=QLabel('WORKSPACE TOOLS'); title.setObjectName('eyebrow'); tools.addWidget(title)
        grid=QGridLayout(); grid.setSpacing(10)
        self.monitor=ActionTile('System monitor','Super + Esc  ·  View applications and processes','monitor',self.open_monitor,True)
        grid.addWidget(self.monitor,0,0,1,2); self.tiles.append(self.monitor)
        actions=[('Capture selection','Choose a screen area','selection',[str(keys.ROOT/'scripts/screenshot.sh'),'area']),
                 ('Capture displays','Save the whole desktop','displays',[str(keys.ROOT/'scripts/screenshot.sh'),'screen']),
                 ('Notifications','View your notification center','notifications',['swaync-client','-t']),
                 ('Lock screen','Keep your session running','lock',['hyprlock','--config',str(keys.ROOT/'hyprlock.conf')])]
        for i,(title,detail,symbol,argv) in enumerate(actions):
            tile=ActionTile(title,detail,symbol,lambda _,a=argv:self.launch(a))
            grid.addWidget(tile,1+i//2,i%2); self.tiles.append(tile)
        tools.addLayout(grid,1); controls.addLayout(tools,1)
        power=QVBoxLayout(); power.setSpacing(10)
        title=QLabel('SESSION & POWER'); title.setObjectName('eyebrow'); power.addWidget(title)
        grid=QGridLayout(); grid.setSpacing(10)
        for i,(title,detail,symbol,argv) in enumerate([
                ('Suspend','Pause and return later','sleep',['systemctl','suspend']),
                ('Log out','Return to the login screen','logout',['hyprctl','dispatch','exit']),
                ('Restart','Start your computer again','restart',['systemctl','reboot']),
                ('Power off','Shut down your computer','system',['systemctl','poweroff'])]):
            tile=ActionTile(title,detail,symbol,lambda _,t=title,a=argv:self.power(t,a))
            tile.setMinimumHeight(112); grid.addWidget(tile,i//2,i%2); self.tiles.append(tile); self.power_tiles.append(tile)
        power.addLayout(grid,1)
        hint=QLabel('You’ll confirm before changing your session.'); hint.setWordWrap(True); hint.setObjectName('muted'); power.addWidget(hint)
        controls.addLayout(power,1); root.addLayout(controls,3)
        footer=QHBoxLayout(); self.status=QLabel(''); self.status.setObjectName('muted'); self.status.setWordWrap(True); footer.addWidget(self.status,1)
        self.shortcut_button=QPushButton('Customize monitor shortcut…'); self.shortcut_button.clicked.connect(self.edit_shortcut); footer.addWidget(self.shortcut_button)
        root.addLayout(footer); scroll.setWidget(content); outer.addWidget(scroll)
        self.timer=QTimer(self); self.timer.setInterval(2500); self.timer.timeout.connect(self.refresh)
        self.update_design()

    def update_design(self):
        for widget in (*self.metrics.values(), *self.tiles): widget.update_design()

    def monitor_binding(self):
        try:
            records,_=keys.Store().load()
            return next((b for b in records if b.id==keys.MONITOR_ID), None)
        except (OSError, keys.ConfigError): return None

    def edit_shortcut(self):
        self.navigate('hotkeys')
        window=self.window()
        if hasattr(window,'pages'):
            page=window.pages['hotkeys']; page.categories.setCurrentIndex(0)
            page.search.setText(''); page.current_id=keys.MONITOR_ID; page.render()

    def open_monitor(self):
        binding=self.monitor_binding()
        if binding and binding.dispatcher in ('exec','execr'):
            try:
                command=keys.expand(binding.args, keys.variables((keys.ROOT/'hyprland.conf').read_text()))
                self.launch(['hyprctl','dispatch',binding.dispatcher,command])
            except OSError as error: self.status.setText(str(error))
        else:
            self.launch([str(keys.ROOT/'scripts/system-monitor.py')])

    def showEvent(self, event):
        super().showEvent(event); self.timer.start(); self.refresh()

    def hideEvent(self, event):
        self.timer.stop(); super().hideEvent(event)

    def refresh(self):
        if self.busy or not self.isVisible(): return
        binding=self.monitor_binding()
        if binding and binding.enabled:
            shortcut=binding.shortcut().replace('SUPER','Super').replace('Escape','Esc')
        else: shortcut='Choose a shortcut in Hotkeys'
        self.monitor.detail=shortcut+'  ·  Applications and processes'; self.monitor.update()
        self.busy=True; self.async_run(snapshot, self.loaded, self.failed)

    def loaded(self, data):
        self.busy=False
        for name,card in self.metrics.items(): card.set_reading(data[name], data[name+'_detail'])
        self.uptime.setText('●  LIVE  ·  UP '+data['uptime'])
        self.temperatures.setText(data['temperatures']); self.temperatures.setVisible(bool(data['temperatures']))

    def failed(self, message): self.busy=False; self.status.setText('System information: '+message)

    def power(self, title, argv):
        if self.power_busy: return
        if QMessageBox.question(self,title,f'{title} this session now?',QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes: return
        self.power_busy=True; self.status.setText(title+'…')
        for tile in self.power_tiles: tile.setEnabled(False)
        def action():
            before_power(argv)
            result=subprocess.run(argv,text=True,capture_output=True,timeout=20)
            if result.returncode: raise RuntimeError(result.stderr.strip() or 'The system did not accept the request.')
            return result
        def finish(message):
            self.power_busy=False; self.status.setText(message)
            for tile in self.power_tiles: tile.setEnabled(True)
        self.async_run(action,lambda _:finish(title+' requested.'),finish)
