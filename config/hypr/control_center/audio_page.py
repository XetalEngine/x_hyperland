"""Device controls and horizontally scrolling application mixer columns."""
from __future__ import annotations

from collections import OrderedDict
import copy
import math

from PyQt6 import sip
from PyQt6.QtCore import Qt,QTimer,QProcess,QProcessEnvironment,pyqtSignal,QPointF
from PyQt6.QtGui import QIcon,QPainter,QPen
from PyQt6.QtWidgets import (QApplication,QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,
    QComboBox,QSlider,QPushButton,QCheckBox,QScrollArea,QSizePolicy,QTabBar,QGroupBox)
import audio_backend as backend

STYLE='''
QFrame#audioColumn { background: #1c2530; border: 1px solid #344557; border-radius: 10px; }
QFrame#audioColumn QLabel, QFrame#audioColumn QSlider { background: transparent; border: none; }
QLabel#audioApp { font-size: 14px; font-weight: 600; }
QLabel#audioLevel { color: #95e5d8; font-size: 24px; font-weight: 600; }
QPushButton#audioMute { border-radius: 5px; padding: 5px 12px; }
QPushButton#audioMute:checked { color: #ffbdc8; background: #542b3a; border-color: #af687f; }
QScrollArea#audioScroll, QWidget#audioColumns { background: #131a23; border: none; }
QSlider::groove:vertical { width: 7px; background: #344455; border-radius: 3px; }
QSlider::add-page:vertical { background: #58afa8; border-radius: 3px; }
QSlider::sub-page:vertical { background: #344455; border-radius: 3px; }
QSlider::handle:vertical { background: #a8e8dd; border: 1px solid #c8fff1; height: 11px; margin: 0 -9px; border-radius: 3px; }
QScrollBar:horizontal { background: #131a23; height: 11px; margin: 0; }
QScrollBar::handle:horizontal { background: #507483; min-width: 35px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background: #78c9bd; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
'''


def text(value,name=''):
    label=QLabel(value);label.setTextFormat(Qt.TextFormat.PlainText)
    if name:label.setObjectName(name)
    return label


class DeviceCombo(QComboBox):
    def __init__(self):
        super().__init__();self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(10);self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setStyleSheet('QComboBox::down-arrow {image:none; width:0; height:0;}')
    def wheelEvent(self,event):event.ignore()
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().buttonText().color(),1.5))
        x,y=self.width()-13,self.height()/2
        painter.drawLine(QPointF(x-4,y-2),QPointF(x,y+2));painter.drawLine(QPointF(x,y+2),QPointF(x+4,y-2))


class ColumnsScroll(QScrollArea):
    def wheelEvent(self,event):
        bar=self.horizontalScrollBar()
        if bar.maximum()>0:
            pixel=event.pixelDelta();angle=event.angleDelta()
            delta=(pixel.x() or pixel.y()) if not pixel.isNull() else (angle.x() or angle.y())//2
            bar.setValue(bar.value()-delta);event.accept()
        else:super().wheelEvent(event)


class VolumeControl(QSlider):
    committed=pyqtSignal(int)
    def __init__(self,orientation):
        super().__init__(orientation);self.setRange(0,100);self.setPageStep(5)
        self.delay=QTimer(self);self.delay.setSingleShot(True);self.delay.setInterval(100)
        self.delay.timeout.connect(lambda:self.committed.emit(self.value()))
        self.valueChanged.connect(lambda _:self.delay.start())
        self.sliderReleased.connect(self.commit)
    def commit(self):self.delay.stop();self.committed.emit(self.value())
    def sync(self,value):
        if self.isSliderDown() or self.delay.isActive():return
        self.blockSignals(True);self.setMaximum(max(100,math.ceil(value/10)*10));self.setValue(value);self.blockSignals(False)


def fill_devices(combo,devices,current,mixed=False):
    if combo.view().isVisible():return
    combo.blockSignals(True);combo.clear()
    if mixed:combo.addItem('Multiple devices',None)
    for device in devices:
        title=device.get('description',device['name'])
        combo.addItem(title,device['name']);combo.setItemData(combo.count()-1,title,Qt.ItemDataRole.ToolTipRole)
    index=0 if mixed else combo.findData(current)
    if index<0 and not mixed:
        combo.insertItem(0,'Device unavailable',None);index=0
    combo.setCurrentIndex(max(0,index));combo.setToolTip(combo.currentText());combo.blockSignals(False)


class AppColumn(QFrame):
    changed=pyqtSignal(object,str,object)
    def __init__(self,group):
        super().__init__();self.group=group;self.setObjectName('audioColumn');self.setFixedWidth(214)
        self.setMinimumHeight(294)
        layout=QVBoxLayout(self);layout.setContentsMargins(14,12,14,12);layout.setSpacing(6)
        header=QHBoxLayout();self.icon=text('');self.icon.setFixedSize(30,30);header.addWidget(self.icon)
        self.name=text(group['name'],'audioApp');self.name.setWordWrap(True);self.name.setMaximumHeight(42)
        self.name.setToolTip(group['name']);header.addWidget(self.name,1);layout.addLayout(header)
        self.activity=text('','muted');layout.addWidget(self.activity)
        self.percent=text('0%','audioLevel');self.percent.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.percent)
        fader=QHBoxLayout();fader.addStretch()
        self.volume=VolumeControl(Qt.Orientation.Vertical);self.volume.setFixedWidth(35);self.volume.setMinimumHeight(75)
        self.volume.setAccessibleName(group['name']+' volume');self.volume.setToolTip('100% is the original level. Drag the slider or use arrow keys to adjust volume. The mouse wheel scrolls the mixer.')
        fader.addWidget(self.volume);fader.addStretch();layout.addLayout(fader,1)
        self.mute=QPushButton('Mute');self.mute.setObjectName('audioMute');self.mute.setCheckable(True)
        self.mute.setAccessibleName('Mute '+group['name']);layout.addWidget(self.mute)
        layout.addWidget(text('Output device' if group['kind']=='playback' else 'Input device','muted'))
        self.route=DeviceCombo();self.route.setAccessibleName(group['name']+' audio device');layout.addWidget(self.route)
        self.volume.valueChanged.connect(lambda value:self.percent.setText(f'{value}%'))
        self.volume.committed.connect(lambda value:self.changed.emit(copy.deepcopy(self.group),'volume',value))
        self.mute.clicked.connect(lambda checked:self.changed.emit(copy.deepcopy(self.group),'mute',checked))
        self.route.activated.connect(self.route_changed)
    def route_changed(self,*_):
        if self.route.currentData():self.changed.emit(copy.deepcopy(self.group),'device',self.route.currentData())
    def sync(self,group,devices,icon):
        self.group=group;self.name.setText(group['name']);self.name.setToolTip(group['name']);self.icon.setPixmap(icon.pixmap(30,30))
        streams=group['streams'];active='Playing' if group['kind']=='playback' else 'Recording'
        if not group['active']:active='Paused'
        if group['muted']:active='Muted'
        if group['part_muted']:active='Some streams muted'
        self.activity.setText(active+(f' · {len(streams)} streams' if len(streams)>1 else ''))
        self.setToolTip('\n'.join(str(s.get('properties',{}).get('media.name',group['name'])) for s in streams))
        self.volume.sync(group['volume']);self.percent.setText(f'{self.volume.value()}%')
        self.volume.setEnabled(all(s.get('has_volume',True) and s.get('volume_writable',True) and s.get('volume') for s in streams))
        self.mute.setChecked(group['muted']);self.mute.setText('Unmute' if group['muted'] else 'Mute')
        device_kind=backend.KINDS[group['kind']][1];indices={s.get(device_kind) for s in streams}
        current=next((d['name'] for d in devices if d['index'] in indices),None)
        fill_devices(self.route,devices,current,mixed=len(indices)>1)


class AudioPage(QWidget):
    def __init__(self,async_run,listen=True):
        super().__init__();self.async_run=async_run;self.listen=listen
        self.data=None;self.columns={};self.reading=False;self.writing=False;self.again=False
        self.revision=0;self.pending=OrderedDict();self.mode='playback';self.icon_cache={};self.app_icons=None
        self.active=False;self.error=''
        layout=QVBoxLayout(self);layout.setContentsMargins(20,16,20,16);layout.setSpacing(10)
        heading=QHBoxLayout();heading.addWidget(text('Audio mixer','brand'));heading.addStretch()
        self.refresh_button=QPushButton('Refresh');self.refresh_button.clicked.connect(self.refresh);heading.addWidget(self.refresh_button)
        layout.addLayout(heading)
        layout.addWidget(text('Set your devices, then mix each application below. Changes take effect immediately.','muted'))
        masters=QHBoxLayout();masters.setSpacing(14);self.devices={}
        for kind,title in [('sink','OUTPUT'),('source','MICROPHONE')]:
            group=QGroupBox(title);inside=QVBoxLayout(group);inside.setSpacing(7)
            combo=DeviceCombo();combo.setAccessibleName(title.title()+' device');inside.addWidget(combo)
            row=QHBoxLayout();volume=VolumeControl(Qt.Orientation.Horizontal);percent=text('0%');percent.setMinimumWidth(40)
            row.addWidget(volume,1);row.addWidget(percent);inside.addLayout(row)
            mute=QCheckBox('Muted');inside.addWidget(mute);masters.addWidget(group,1)
            self.devices[kind]=(combo,volume,percent,mute)
            volume.valueChanged.connect(lambda value,p=percent:p.setText(f'{value}%'))
            volume.committed.connect(lambda value,k=kind:self.device_action(k,'volume',value))
            mute.clicked.connect(lambda checked,k=kind:self.device_action(k,'mute',checked))
            combo.activated.connect(lambda _,k=kind:self.device_action(k,'default',None))
            combo.setToolTip('Use this device for current and new applications.')
        layout.addLayout(masters)
        toolbar=QHBoxLayout();self.modes=QTabBar();self.modes.setExpanding(False)
        self.modes.addTab('Playback');self.modes.addTab('Recording');self.modes.currentChanged.connect(self.switch_mode)
        toolbar.addWidget(self.modes);toolbar.addSpacing(12);self.count=text('Loading apps…','muted');toolbar.addWidget(self.count);toolbar.addStretch()
        toolbar.addWidget(text('Scroll sideways for more apps','muted'));layout.addLayout(toolbar)
        self.scroll=ColumnsScroll();self.scroll.setObjectName('audioScroll');self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.container=QWidget();self.container.setObjectName('audioColumns');self.row=QHBoxLayout(self.container)
        self.row.setContentsMargins(8,8,8,8);self.row.setSpacing(12);self.row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.empty=text('Loading audio applications…','muted');self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True);self.empty.setMinimumWidth(420);self.row.addWidget(self.empty,1)
        self.scroll.setWidget(self.container);layout.addWidget(self.scroll,1)
        self.status=text('Ready','status');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.refresh_delay=QTimer(self);self.refresh_delay.setSingleShot(True);self.refresh_delay.setInterval(160)
        self.refresh_delay.timeout.connect(self.refresh)
        self.poll=QTimer(self);self.poll.setInterval(4000);self.poll.timeout.connect(self.periodic)
        self.events=QProcess(self);env=QProcessEnvironment.systemEnvironment();env.insert('LC_ALL','C');self.events.setProcessEnvironment(env)
        self.events.readyReadStandardOutput.connect(self.audio_events)
        self.events.readyReadStandardError.connect(lambda:self.events.readAllStandardError())
        QApplication.instance().aboutToQuit.connect(self.stop)

    def showEvent(self,event):
        super().showEvent(event);self.active=True
        if self.listen:self.poll.start();self.start_events();self.refresh()
    def hideEvent(self,event):self.stop();super().hideEvent(event)
    def start_events(self):
        if self.active and self.events.state()==QProcess.ProcessState.NotRunning:self.events.start('pactl',['subscribe'])
    def stop(self):
        self.active=False;self.poll.stop();self.refresh_delay.stop()
        if self.events.state()!=QProcess.ProcessState.NotRunning:
            self.events.terminate()
            if not self.events.waitForFinished(250):self.events.kill();self.events.waitForFinished(250)
    def periodic(self):self.start_events();self.refresh()
    def audio_events(self):
        payload=bytes(self.events.readAllStandardOutput()).decode(errors='replace')
        if self.active and any(' on '+kind+' #' in payload for kind in ('sink','source','sink-input','source-output','server')):
            self.refresh_delay.start()

    def refresh(self):
        if self.reading or self.writing or self.pending:self.again=True;return
        self.reading=True;self.again=False;revision=self.revision
        def done(data):
            if sip.isdeleted(self):return
            self.reading=False
            if revision==self.revision and not self.writing:
                self.data=data;self.render()
                if not self.error:self.status.setText('Each column controls one app. Apps with several audio streams stay together.')
            else:self.again=True
            if self.again and self.active:self.refresh_delay.start()
        def failed(message):
            if sip.isdeleted(self):return
            self.reading=False;self.status.setText('Audio unavailable: '+message)
            if not self.data:self.empty.setText('The audio server is unavailable. Reconnect it, then press Refresh.')
        self.async_run(backend.snapshot,done,failed)

    def submit(self,key,fn):
        self.revision+=1;self.error='';self.pending[key]=fn;self.next_change()
    def next_change(self):
        if self.writing or not self.pending:return
        _,fn=self.pending.popitem(last=False);self.writing=True
        def finished(error=''):
            if sip.isdeleted(self):return
            self.writing=False
            if error:self.error=error;self.status.setText(error)
            if self.pending:self.next_change()
            else:self.refresh()
        self.async_run(fn,lambda _:finished(),finished)
    def app_action(self,group,action,value):
        self.submit((group['kind'],group['key'],action),lambda:backend.apply_app(group,action,value))
    def device_action(self,kind,action,value):
        if not self.data:return
        name=self.devices[kind][0].currentData()
        device=next((d for d in self.data['devices'][kind] if d['name']==name),None)
        if device:
            device=copy.deepcopy(device)
            self.submit((kind,name,action),lambda:backend.apply_device(kind,device,action,value))

    def switch_mode(self,index):
        self.mode='recording' if index else 'playback';self.render()
        self.scroll.horizontalScrollBar().setValue(0)
    def app_icon(self,group):
        cache_key=(group['key'],QIcon.themeName())
        if cache_key in self.icon_cache:return self.icon_cache[cache_key]
        candidates=[group.get('icon',''),group.get('app_id',''),group.get('binary',''),group['name'].lower().replace(' ','-')]
        for name in candidates:
            icon=QIcon.fromTheme(name)
            if name and not icon.isNull():self.icon_cache[cache_key]=icon;return icon
        if self.app_icons is None:
            self.app_icons={}
            try:
                from gi.repository import Gio
                for info in Gio.AppInfo.get_all():
                    value=info.get_icon()
                    if not value:continue
                    icon=QIcon(value.get_file().get_path()) if hasattr(value,'get_file') else next(
                        (QIcon.fromTheme(n) for n in value.get_names() if QIcon.hasThemeIcon(n)),QIcon()) if hasattr(value,'get_names') else QIcon()
                    for name in (info.get_display_name(),(info.get_id() or '').removesuffix('.desktop')):
                        if name and not icon.isNull():self.app_icons[name.casefold()]=icon
            except (ImportError,AttributeError):pass
        icon=next((self.app_icons[n.casefold()] for n in [group.get('app_id',''),group['name']] if n.casefold() in self.app_icons),
                  QIcon.fromTheme('audio-x-generic'))
        self.icon_cache[cache_key]=icon;return icon

    def render(self):
        if not self.data:return
        for kind,(combo,volume,percent,mute) in self.devices.items():
            devices=self.data['devices'][kind];fill_devices(combo,devices,self.data['defaults'][kind])
            current=next((d for d in devices if d['name']==combo.currentData()),None)
            combo.setEnabled(bool(devices))
            for widget in (volume,mute):widget.setEnabled(current is not None)
            if current:
                volume.sync(backend.level([current]));percent.setText(f'{volume.value()}%');mute.setChecked(current.get('mute',False))
        groups=self.data['apps'][self.mode];keys={(self.mode,g['key']) for g in groups}
        for key in list(self.columns):
            if key not in keys:
                column=self.columns.pop(key);column.volume.delay.stop();self.row.removeWidget(column);column.hide();column.deleteLater()
        devices=self.data['devices'][backend.KINDS[self.mode][1]]
        for index,group in enumerate(groups):
            key=(self.mode,group['key']);column=self.columns.get(key)
            if column is None:
                column=AppColumn(group);column.changed.connect(self.app_action);self.columns[key]=column
            self.row.insertWidget(index,column);column.sync(group,devices,self.app_icon(group));column.show()
        self.empty.setVisible(not groups)
        self.empty.setText('No apps are playing audio.\nStart music, a video, or a call to see its mixer column.' if self.mode=='playback'
                           else 'No apps are recording audio.\nApps using a microphone or recording system audio appear here.')
        self.count.setText(f'{len(groups)} '+('app' if len(groups)==1 else 'apps'))
        self.container.setMinimumWidth(16+len(groups)*226 if groups else 440)
