"""Account artwork and wallpaper-backed cards; no account settings are written."""
import getpass
import json
import os
from pathlib import Path
import socket

from PyQt6.QtCore import Qt, QRectF, QSize, pyqtSignal
from PyQt6.QtGui import QMovie, QPainter, QPainterPath, QPixmap, QColor, QLinearGradient, QPen
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout
import runtime


def avatar_path(choice=None):
    choice = runtime.state().get('avatar', 'assets/account.gif') if choice is None else choice
    if choice and choice != 'auto':
        path = Path(choice).expanduser()
        if not path.is_absolute(): path = runtime.ROOT / path
        if path.is_file(): return path
    for path in (Path.home()/'.face.icon', Path.home()/'.face',
                 Path('/var/lib/AccountsService/icons')/getpass.getuser(),
                 runtime.ROOT/'assets/account.gif', runtime.ROOT.parent/'startup/assets/xetal-mascot.png'):
        if path.is_file(): return path
    return None


def wallpaper_path(connector=None):
    try:
        choices = json.loads((runtime.ROOT.parent/'wallpaper/selection.json').read_text())
        if not isinstance(choices,dict):raise ValueError('Invalid wallpaper selection')
        ordered=([choices[connector]] if connector in choices else [])+list(choices.values())
        for item in ordered:
            if not isinstance(item,dict) or not isinstance(item.get('path'),str):continue
            path = Path(item['path']).expanduser()
            if path.is_file(): return path
    except (OSError, ValueError, KeyError, TypeError): pass
    try:
        choice = json.loads((runtime.ROOT.parent/'wallpaper/default.json').read_text())
        path = runtime.ROOT.parent/'wallpaper'/choice['image']
        if path.is_file(): return path
    except (OSError, ValueError, KeyError, TypeError): pass
    return None


def launcher_background_path(connector=None,choice=None):
    choice=runtime.launcher_background() if choice is None else choice
    if choice:
        path=Path(choice).expanduser()
        if not path.is_absolute():path=runtime.ROOT/path
        if path.is_file():return path
    return wallpaper_path(connector)


class Avatar(QWidget):
    clicked = pyqtSignal()

    def __init__(self, size=64, parent=None, design=None):
        super().__init__(parent)
        self.design=design or runtime.design
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.movie = None; self.picture = QPixmap(); self.path = None
        if QApplication.instance():QApplication.instance().aboutToQuit.connect(self.stop)
        self.refresh()

    def stop(self):
        if self.movie:self.movie.stop()

    def frame_changed(self,*_):self.update()

    def refresh(self, choice=None):
        path = avatar_path(choice)
        if path == self.path: return
        self.path = path
        if self.movie:
            self.movie.stop(); self.movie.deleteLater(); self.movie = None
        self.picture = QPixmap(str(path)) if path else QPixmap()
        if path and path.suffix.lower() in ('.gif', '.webp'):
            movie = QMovie(str(path), parent=self)
            movie.setScaledSize(QSize(self.width()*2, self.height()*2))
            if movie.isValid():
                self.movie = movie; movie.frameChanged.connect(self.frame_changed)
                if self.isVisible(): movie.start()
            else: movie.deleteLater()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self.movie: self.movie.start()

    def hideEvent(self, event):
        if self.movie: self.movie.setPaused(True)
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        box = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path = QPainterPath(); path.addEllipse(box)
        painter.setClipPath(path)
        colors=runtime.colors(style=self.design())
        painter.fillRect(box, QColor(colors['Button']))
        image = self.movie.currentPixmap() if self.movie else self.picture
        if not image.isNull():
            side = min(image.width(), image.height())
            source = QRectF((image.width()-side)/2, (image.height()-side)/2, side, side)
            painter.drawPixmap(box, image, source)
        else:
            painter.setPen(QColor(runtime.colors()['Text']))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, getpass.getuser()[:1].upper())
        painter.setClipping(False); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(colors['Accent']), 2)); painter.drawEllipse(box)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ProfileCard(QWidget):
    def __init__(self, compact=False, parent=None, backdrop=True, design=None):
        super().__init__(parent)
        self.design=design or runtime.design
        self.compact = compact; self.backdrop=backdrop; self.background = QPixmap(); self.background_path = None
        self.setMinimumHeight(100 if compact else 190)
        layout = QVBoxLayout(self) if compact else QHBoxLayout(self)
        layout.setContentsMargins(14 if compact else 26, 14, 14 if compact else 26, 14)
        layout.setSpacing(8 if compact else 22)
        self.avatar = Avatar(54 if compact else 98, self, design=self.design)
        layout.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignLeft if compact else Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout(); text.setSpacing(4)
        self.name = QLabel(getpass.getuser()); self.name.setTextFormat(Qt.TextFormat.PlainText)
        text.addWidget(self.name)
        detail = self.detail = QLabel(runtime.DESIGNS[self.design()] if compact else getpass.getuser()+'@'+socket.gethostname())
        detail.setTextFormat(Qt.TextFormat.PlainText); detail.setWordWrap(True)
        text.addWidget(detail)
        if not compact:
            caption = self.caption = QLabel('Your desktop. Your space.')
            caption.setStyleSheet('background:transparent; color:#c6d8e8; font-size:13px;')
            text.addWidget(caption); text.addStretch()
        layout.addLayout(text, 1)
        self.refresh()

    def refresh(self):
        self.avatar.refresh()
        colors=runtime.colors(style=self.design())
        self.name.setStyleSheet('background:transparent; color:'+('#e5eff9' if self.backdrop else colors['WindowText'])+'; font-size:'+('15' if self.compact else '23')+'px; font-weight:700;')
        self.detail.setStyleSheet('background:transparent; color:'+('#b2cee4' if self.backdrop else colors['PlaceholderText'])+'; font-size:12px;')
        if self.design()=='porcelainink':
            self.name.setStyleSheet('background:transparent; color:'+colors['WindowText']+'; font-family:"Noto Serif"; font-size:'+('15' if self.compact else '23')+'px; font-weight:500;')
            self.detail.setStyleSheet('background:transparent; color:'+colors['PlaceholderText']+'; font-size:12px;')
        if self.design() in ('obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow','mycelium','platform95','midnightrun','infernalencore','polaris'):
            self.name.setStyleSheet('background:transparent; color:'+colors['WindowText']+'; font-size:'+('15' if self.compact else '23')+'px; font-weight:600; letter-spacing:1px;')
            self.detail.setStyleSheet('background:transparent; color:'+colors['PlaceholderText']+'; font-size:12px;')
        if not self.compact:
            self.caption.setStyleSheet('background:transparent; color:'+(colors['PlaceholderText'] if self.design() in ('porcelainink','obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow','mycelium','platform95','midnightrun','infernalencore','polaris') else '#c6d8e8')+'; font-size:13px;')
        if self.compact:self.detail.setText(runtime.DESIGNS[self.design()])
        path = wallpaper_path() if self.backdrop else None
        if path != self.background_path:
            self.background_path = path
            self.background = QPixmap(str(path)) if path else QPixmap()
        self.update()

    def paintEvent(self, event):
        if not self.backdrop:return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ink=self.design()=='porcelainink';colors=runtime.colors(style=self.design())
        radius=12 if self.design()=='polaris' else 5 if self.design()=='infernalencore' else 7 if self.design()=='midnightrun' else 1 if self.design()=='platform95' else 3 if self.design()=='shadowedge' else 26 if self.design()=='candycloud' else 3 if self.design()=='obsidianforge' else 2 if ink else 18
        box = QRectF(self.rect()); clip = QPainterPath(); clip.addRoundedRect(box, radius, radius); p.setClipPath(clip)
        p.fillRect(box, QColor('#203247'))
        if not self.background.isNull():
            ratio=max(box.width()/self.background.width(), box.height()/self.background.height())
            target=QRectF(0,0,self.background.width()*ratio,self.background.height()*ratio);target.moveCenter(box.center())
            p.drawPixmap(target,self.background,QRectF(self.background.rect()))
        overlay=QLinearGradient(box.topLeft(),box.bottomRight())
        if ink or self.design() in ('obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow','mycelium','platform95','midnightrun','infernalencore','polaris'):
            start=QColor(colors['Window']);start.setAlpha(240)
            end=QColor(colors['Window']);end.setAlpha(195)
            overlay.setColorAt(0,start);overlay.setColorAt(1,end)
        else:
            overlay.setColorAt(0,QColor(16,29,44,235 if self.compact else 225))
            overlay.setColorAt(1,QColor(16,29,44,180 if self.compact else 135))
        p.fillRect(box,overlay)
