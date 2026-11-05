"""Listen, mix and mute the original theme sound packs."""
import copy
import json
import sys
import time
from PyQt6.QtCore import Qt, QRectF, QProcess, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QLinearGradient, QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QCheckBox, QSlider, QScrollArea, QFrame, QSizePolicy)
from sounds import model


def note(text):
    label=QLabel(text); label.setWordWrap(True); label.setObjectName('muted'); return label


class SoundArt(QWidget):
    def __init__(self):
        super().__init__(); self.pack='hollowgrove'; self.event='startup'; self.position=-1; self.catalog={}
        self.setMinimumHeight(92); self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        try: self.catalog=json.loads((model.ROOT/'sounds/packs/catalog.json').read_text())['packs']
        except (OSError,ValueError,KeyError): pass
    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(model.PACKS[self.pack][3]); box=QRectF(self.rect()).adjusted(1,1,-1,-1)
        gradient=QLinearGradient(box.topLeft(),box.bottomRight())
        left=QColor(color);left.setAlpha(35);right=QColor(color);right.setAlpha(3)
        gradient.setColorAt(0,left);gradient.setColorAt(1,right)
        painter.setPen(QPen(color.darker(170),1));painter.setBrush(gradient);painter.drawRoundedRect(box,14,14)
        values=self.catalog.get(self.pack,{}).get('events',{}).get(self.event,{}).get('waveform',[])
        if not values: return
        area=box.adjusted(24,18,-24,-18);step=area.width()/len(values)
        maximum=max(values) or 1
        for i,value in enumerate(values):
            height=max(2,value/maximum*area.height()*.83)
            tint=QColor(color);tint.setAlpha(230 if self.position<0 or i/len(values)<=self.position else 65)
            painter.setPen(QPen(tint,max(1.5,step*.48),Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            x=area.x()+i*step;painter.drawLine(int(x),int(area.center().y()-height/2),int(x),int(area.center().y()+height/2))
    def seconds(self): return self.catalog.get(self.pack,{}).get('events',{}).get(self.event,{}).get('seconds',4.15)


class PackCard(QPushButton):
    def __init__(self,key):
        super().__init__();self.key=key;self.setCheckable(True);self.setMinimumHeight(64)
        self.setAccessibleName(model.PACKS[key][0]+' sound pack');self.setToolTip(model.PACKS[key][2])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(model.PACKS[self.key][3]);r=QRectF(self.rect()).adjusted(1,1,-1,-1)
        bg=QColor(color);bg.setAlpha(42 if self.isChecked() else 15)
        painter.setBrush(bg);painter.setPen(QPen(color if self.isChecked() or self.underMouse() else self.palette().mid().color(),1.5))
        painter.drawRoundedRect(r,10,10)
        painter.setPen(self.palette().text().color());font=QFont(self.font());font.setBold(True);painter.setFont(font)
        painter.drawText(r.adjusted(13,7,-10,-28),Qt.AlignmentFlag.AlignVCenter,model.PACKS[self.key][0])
        painter.setPen(QPen(color,3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));painter.drawLine(6,15,6,self.height()-15)
        font.setBold(False);font.setPointSizeF(max(8,font.pointSizeF()-1));painter.setFont(font)
        painter.setPen(self.palette().text().color());painter.drawText(r.adjusted(13,31,-10,-5),Qt.AlignmentFlag.AlignVCenter,model.PACKS[self.key][1])
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(color,1,Qt.PenStyle.DotLine));painter.drawRoundedRect(r.adjusted(4,4,-4,-4),7,7)


class SoundsPage(QWidget):
    def __init__(self,async_run=None):
        super().__init__();self.busy=False;self.dirty=False;self.loading=False
        self.baseline={};self.draft=copy.deepcopy(model.DEFAULTS);self.token=None;self.player=None;self.started=0
        root=QVBoxLayout(self);root.setContentsMargins(12,12,12,12);root.setSpacing(10)
        header=QHBoxLayout();title=QLabel('The sound of your desktop');title.setObjectName('brand');header.addWidget(title,1)
        self.enabled=QCheckBox('Enable desktop sounds');self.enabled.toggled.connect(lambda v:self.edit('enabled',v));header.addWidget(self.enabled);root.addLayout(header)
        root.addWidget(note('Original little melodies and gentle chimes. Choose any sound pack with any theme.'))
        body=QHBoxLayout();body.setSpacing(18)
        gallery=QScrollArea();gallery.setWidgetResizable(True);gallery.setFrameShape(QFrame.Shape.NoFrame)
        gallery.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);gallery.setMinimumWidth(215);gallery.setMaximumWidth(260)
        items=QWidget();column=QVBoxLayout(items);column.setContentsMargins(0,0,8,0);column.setSpacing(8);self.cards={}
        for key in model.PACKS:
            card=PackCard(key);card.clicked.connect(lambda _,k=key:self.pick(k));column.addWidget(card);self.cards[key]=card
        column.addStretch();gallery.setWidget(items);body.addWidget(gallery)
        right=QWidget();details=QVBoxLayout(right);details.setContentsMargins(0,0,0,0);details.setSpacing(9)
        self.follow=QCheckBox('Follow desktop theme');self.follow.toggled.connect(self.follow_changed);details.addWidget(self.follow)
        self.name=QLabel();self.name.setObjectName('brand');details.addWidget(self.name)
        self.description=note('');details.addWidget(self.description)
        self.art=SoundArt();details.addWidget(self.art,1)
        self.now=note('');details.addWidget(self.now)
        grid=QGridLayout();grid.setHorizontalSpacing(18);grid.setVerticalSpacing(8);self.events={};self.preview_buttons={}
        for i,(key,(caption,description)) in enumerate(model.EVENTS.items()):
            line=QHBoxLayout();toggle=QCheckBox(caption);toggle.setToolTip(description)
            toggle.toggled.connect(lambda v,k=key:self.edit_event(k,v));line.addWidget(toggle,1);self.events[key]=toggle
            preview=QPushButton('▶ Listen');preview.setAccessibleName('Preview '+caption);preview.clicked.connect(lambda _,k=key:self.preview(k))
            self.preview_buttons[key]=preview;line.addWidget(preview);grid.addLayout(line,i//2,i%2)
        details.addLayout(grid)
        levels=QHBoxLayout();levels.addWidget(QLabel('Volume'));self.volume=QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0,100);self.volume.setAccessibleName('Desktop sound volume');self.volume.valueChanged.connect(lambda v:self.edit('volume',v))
        levels.addWidget(self.volume,1);self.readout=QLabel();self.readout.setMinimumWidth(42);levels.addWidget(self.readout)
        self.stop=QPushButton('Stop preview');self.stop.clicked.connect(self.stop_preview);levels.addWidget(self.stop);details.addLayout(levels)
        self.dnd=QCheckBox('Respect Do Not Disturb');self.dnd.toggled.connect(lambda v:self.edit('respect_dnd',v));details.addWidget(self.dnd)
        details.addWidget(note('Listen previews your choices before saving, even when sounds are muted. Shutdown music plays after confirming a session action in Fusion.'))
        body.addWidget(right,1);root.addLayout(body,1)
        self.status=note('');root.addWidget(self.status)
        buttons=QHBoxLayout();defaults=QPushButton('Reset defaults');defaults.clicked.connect(lambda:self.fill(copy.deepcopy(model.DEFAULTS)));buttons.addWidget(defaults)
        buttons.addStretch();self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));buttons.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(lambda:self.fill(self.baseline));buttons.addWidget(self.discard)
        self.apply=QPushButton('Apply sounds');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);buttons.addWidget(self.apply);root.addLayout(buttons)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.tick)
        self.refresh()

    def edit(self,key,value):
        if self.loading:return
        self.draft[key]=value;self.changed()
    def edit_event(self,key,value):
        if self.loading:return
        self.draft['events'][key]=value;self.changed()
    def pick(self,key):
        self.stop_preview();self.draft['pack']=key;self.fill(self.draft)
    def follow_changed(self,value):
        if self.loading:return
        self.stop_preview();self.draft['pack']='follow' if value else model.resolve('follow');self.fill(self.draft)
    def fill(self,value):
        self.loading=True;self.draft=copy.deepcopy(value)
        self.enabled.setChecked(value['enabled']);self.follow.setChecked(value['pack']=='follow');self.volume.setValue(value['volume']);self.dnd.setChecked(value['respect_dnd'])
        for key,toggle in self.events.items():toggle.setChecked(value['events'][key])
        self.loading=False;self.changed()
    def changed(self):
        self.dirty=self.draft!=self.baseline;self.apply.setEnabled(self.dirty);self.discard.setEnabled(self.dirty)
        self.readout.setText(str(self.draft['volume'])+'%');pack=model.resolve(self.draft['pack']);self.art.pack=pack;self.art.update()
        for key,card in self.cards.items():card.setChecked(key==pack);card.update()
        title,motif,description,_=model.PACKS[pack];self.name.setText(title+' · '+motif);self.description.setText(description)
        self.stop.setEnabled(self.player is not None)
    def refresh(self,force=False):
        if self.dirty and not force:return
        try:
            self.baseline,self.token=model.load();self.fill(self.baseline)
            self.status.setText('Sounds follow '+model.PACKS[model.resolve(self.draft['pack'])][0]+'.' if self.draft['pack']=='follow' else 'Your independent sound pack is saved.')
            self.now.setText('Startup · 4.15 s   /   Shutdown · 3.05 s   /   Eight sounds per pack')
        except (OSError,ValueError) as exc:self.status.setText(str(exc))
    def save(self):
        try:
            self.baseline,self.token=model.save(self.draft,self.token);self.fill(self.baseline);self.status.setText('Sound settings saved. New sounds use these choices immediately.')
        except (OSError,ValueError) as exc:self.status.setText(str(exc))
    def preview(self,event):
        self.stop_preview();self.art.event=event;self.art.position=0;self.art.update()
        process=QProcess(self);self.player=process
        process.setStandardOutputFile(QProcess.nullDevice())
        process.finished.connect(lambda code,_:self.finished(process,code));process.errorOccurred.connect(lambda _:self.finished(process,1))
        self.started=time.monotonic();self.now.setText('Playing '+model.EVENTS[event][0]+' · '+str(self.art.seconds())+' s')
        process.start(sys.executable,[str(model.ROOT/'sounds/play.py'),event,'--preview','--pack',model.resolve(self.draft['pack']),'--volume',str(self.draft['volume'])])
        self.timer.start();self.changed()
    def tick(self):
        self.art.position=min(1,(time.monotonic()-self.started)/self.art.seconds());self.art.update()
    def finished(self,process,code):
        if self.player is not process:return
        error=bytes(process.readAllStandardError()).decode(errors='replace').strip()
        self.player=None;self.timer.stop();self.art.position=-1;self.art.update();self.stop.setEnabled(False)
        self.now.setText(error or ('Preview unavailable. Check the audio output.' if code else 'Preview finished.'))
        process.deleteLater()
    def stop_preview(self):
        process,self.player=self.player,None;self.timer.stop();self.art.position=-1;self.art.update()
        if process:
            process.terminate()
            # The helper terminates only its own player. Reap it before a new
            # preview attempts the same session lock (normally under 50 ms).
            if not process.waitForFinished(350):process.kill();process.waitForFinished(150)
            process.deleteLater()
        self.stop.setEnabled(False)
    def hideEvent(self,event):self.stop_preview();super().hideEvent(event)
    def showEvent(self,event):self.refresh();super().showEvent(event)
