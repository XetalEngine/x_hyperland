"""Modern's overview, using the same session actions and media tools."""
import datetime
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel, QPushButton, QSizePolicy
import runtime
from identity import ProfileCard
from icons import icon


def label(text='',name=''):
    widget=QLabel(text);widget.setTextFormat(Qt.TextFormat.PlainText);widget.setWordWrap(True)
    widget.setObjectName(name);return widget


def media_snapshot():
    try:
        value=subprocess.run(['playerctl','metadata','--format','{{title}}\n{{artist}}\n{{mpris:artUrl}}'],capture_output=True,text=True,timeout=2)
        if value.returncode:return None
        title,artist,art=(value.stdout.strip().split('\n')+['','',''])[:3]
        status=subprocess.run(['playerctl','status'],capture_output=True,text=True,timeout=2).stdout.strip()
        return {'title':title or 'Media player','artist':artist,'art':art,'status':status}
    except (OSError,subprocess.SubprocessError):return None


class HomePage(QWidget):
    def __init__(self,navigate,async_run,launch):
        super().__init__();self.navigate=navigate;self.async_run=async_run;self.launch=launch;self.busy=False;self.art_path=''
        root=QVBoxLayout(self);root.setContentsMargins(6,4,6,6);root.setSpacing(16)
        self.profile=ProfileCard();self.profile.avatar.clicked.connect(lambda:navigate('theme'));root.addWidget(self.profile)
        lower=QHBoxLayout();lower.setSpacing(16)
        left=QVBoxLayout();left.setSpacing(16)
        media=QFrame();media.setObjectName('modernCard');layout=QHBoxLayout(media);layout.setContentsMargins(18,18,18,18);layout.setSpacing(18)
        self.art=QLabel();self.art.setFixedSize(102,102);self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setPixmap(QIcon.fromTheme('audio-x-generic').pixmap(70,70));layout.addWidget(self.art)
        details=QVBoxLayout();details.setSpacing(7);details.addStretch();self.song=label('Nothing playing','section');details.addWidget(self.song)
        self.artist=label('Open a player to see your music here.','muted');details.addWidget(self.artist)
        self.playback=label('','muted');details.addWidget(self.playback)
        buttons=QHBoxLayout();buttons.setSpacing(8)
        self.media_buttons=[]
        for command,title,icon_name in [('previous','Previous','media-skip-backward'),('play-pause','Play / pause','media-playback-start'),('next','Next','media-skip-forward')]:
            control=QPushButton(QIcon.fromTheme(icon_name),'');control.setFixedSize(42,32);control.setToolTip(title);control.setAccessibleName(title)
            control.setEnabled(False)
            control.clicked.connect(lambda _,c=command:launch(['playerctl',c]));buttons.addWidget(control);self.media_buttons.append(control)
        buttons.addStretch();details.addLayout(buttons);details.addStretch();layout.addLayout(details,1);left.addWidget(media,2)
        clock=QFrame();clock.setObjectName('modernCard');clock_layout=QHBoxLayout(clock);clock_layout.setContentsMargins(24,18,24,18)
        self.time=label('','brand');self.time.setStyleSheet('font-size:37px; font-weight:600; color:palette(link); background:transparent;')
        clock_layout.addWidget(self.time)
        clock_text=QVBoxLayout();clock_text.setSpacing(7);clock_text.addStretch();self.date=label('','muted');clock_text.addWidget(self.date)
        self.resources=label('','muted');clock_text.addWidget(self.resources);clock_text.addStretch();clock_layout.addLayout(clock_text,1);left.addWidget(clock,1)
        lower.addLayout(left,3)
        quick=QGridLayout();quick.setSpacing(12);self.quick_buttons=[]
        for index,(title,target,symbol) in enumerate([('Audio','audio','audio'),('Bluetooth','bluetooth','bluetooth'),('Network','network','network'),('Displays','displays','displays'),('Theme','theme','theme'),('Session','system','system')]):
            control=QPushButton();control.setMinimumSize(106,102);control.setAccessibleName(title);control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
            content=QVBoxLayout(control);content.setContentsMargins(10,13,10,13);content.setSpacing(8)
            image=QLabel();image.setAlignment(Qt.AlignmentFlag.AlignCenter);caption=label(title);caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content.addWidget(image);content.addWidget(caption);control.clicked.connect(lambda _,t=target:navigate(t))
            self.quick_buttons.append((image,symbol));quick.addWidget(control,index//2,index%2)
        lower.addLayout(quick,2);root.addLayout(lower,1)
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.tick);self.timer.start();self.ticks=0
        self.tick();self.update_design()

    def update_design(self):
        self.profile.refresh()
        for image,symbol in self.quick_buttons:image.setPixmap(icon(symbol,runtime.colors()['Accent'],24).pixmap(24,24))

    def tick(self):
        now=datetime.datetime.now();self.time.setText(now.strftime('%H:%M'));self.date.setText(now.strftime('%A, %d %B %Y'))
        self.ticks+=1
        if self.isVisible() and self.ticks%4==0:self.refresh()

    def refresh(self):
        self.update_design()
        if self.busy or not self.isVisible():return
        self.busy=True
        def snapshot():
            import psutil
            return media_snapshot(),psutil.cpu_percent(),psutil.virtual_memory().percent
        self.async_run(snapshot,self.loaded,self.failed)

    def loaded(self,result):
        self.busy=False;media,cpu,memory=result
        self.resources.setText(f'CPU {cpu:.0f}%  ·  Memory {memory:.0f}%')
        self.song.setText(media['title'] if media else 'Nothing playing')
        self.artist.setText(media['artist'] if media else 'Open a player to see your music here.')
        self.playback.setText(media['status'] if media else '')
        for control in self.media_buttons:control.setEnabled(bool(media))
        art=media.get('art','') if media else ''
        if art!=self.art_path:
            self.art_path=art;url=urlparse(art)
            picture=QPixmap(unquote(url.path)) if url.scheme=='file' and url.netloc in ('','localhost') else QPixmap()
            self.art.setPixmap(picture.scaled(102,102,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation) if not picture.isNull() else QIcon.fromTheme('audio-x-generic').pixmap(70,70))

    def failed(self,message):self.busy=False;self.resources.setText('System information unavailable')
