"""Device controls and horizontally scrolling application mixer columns."""
from __future__ import annotations

from collections import OrderedDict
import copy
import math

from PyQt6 import sip
from PyQt6.QtCore import Qt,QTimer,QProcess,QProcessEnvironment,pyqtSignal,QPointF
from PyQt6.QtGui import QIcon,QPainter,QPen
from PyQt6.QtWidgets import (QApplication,QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,
    QComboBox,QSlider,QPushButton,QCheckBox,QScrollArea,QSizePolicy,QTabBar,QTabWidget,QGroupBox)
import audio_backend as backend
from audio_preview import OutputTest
import audio_layout
import audio_routing

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
        if orientation==Qt.Orientation.Vertical:
            # Keep the track narrow even when a popup supplies its own QSS.
            # Colors continue to come from the active desktop theme.
            self.setStyleSheet('QSlider {background:transparent; border:none;} '
                'QSlider::groove:vertical {width:6px; border-radius:3px;} '
                'QSlider::handle:vertical {height:11px; margin:0 -8px; border-radius:4px;}')
        self.delay=QTimer(self);self.delay.setSingleShot(True);self.delay.setInterval(100)
        self.delay.timeout.connect(lambda:self.committed.emit(self.value()))
        self.valueChanged.connect(lambda _:self.delay.start())
        self.sliderReleased.connect(self.commit)
    def commit(self):self.delay.stop();self.committed.emit(self.value())
    def sync(self,value):
        if self.isSliderDown() or self.delay.isActive():return
        self.blockSignals(True);self.setMaximum(max(100,math.ceil(value/10)*10));self.setValue(value);self.blockSignals(False)


def fill_devices(combo,devices,current,mixed=False,*,mixed_label='Multiple devices'):
    if combo.view().isVisible():return
    combo.blockSignals(True);combo.clear()
    if mixed:combo.addItem(mixed_label,None)
    for device in devices:
        title=device.get('description',device['name'])
        combo.addItem(title,device['name']);combo.setItemData(combo.count()-1,device.get('tooltip',title),Qt.ItemDataRole.ToolTipRole)
    index=0 if mixed else combo.findData(current)
    if index<0 and not mixed:
        combo.insertItem(0,'Device unavailable',None);index=0
    combo.setCurrentIndex(max(0,index));combo.setToolTip(combo.currentData(Qt.ItemDataRole.ToolTipRole) or combo.currentText());combo.blockSignals(False)


class AppColumn(QFrame):
    changed=pyqtSignal(object,str,object)
    def __init__(self,group,compact=False):
        super().__init__();self.group=group;self.setObjectName('audioColumn')
        self.setFixedWidth(audio_layout.COLUMN_WIDTH if compact else 214)
        self.setMinimumHeight(294)
        layout=QVBoxLayout(self);margin=10 if compact else 14;layout.setContentsMargins(margin,12,margin,12);layout.setSpacing(6)
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
    def sync(self,group,devices,icon,default='',routes=None):
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
        device_kind=backend.KINDS[group['kind']][1]
        selections={audio_routing.selection(s,device_kind,devices,default,routes) for s in streams}
        current=next(iter(selections),None)
        title=next((d.get('description',d['name']) for d in devices if d['name']==default),'No default device')
        follow={'name':audio_routing.SYSTEM_DEFAULT,'description':'System Default',
                'tooltip':'Follow the main '+('Output' if device_kind=='sink' else 'Microphone')+' selection: '+title}
        fill_devices(self.route,[follow,*devices],current,mixed=len(selections)>1,mixed_label='Mixed routing')


class MicrophoneGain(QWidget):
    changed=pyqtSignal(object,object,int)
    def __init__(self):
        super().__init__();self.device=None;self.controls=[];self.control=None;self.token=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,8,0,0);layout.setSpacing(6)
        heading=QHBoxLayout();self.title=text('Mic boost / hardware gain');heading.addWidget(self.title);heading.addStretch()
        self.minimum=QPushButton('Minimum');self.minimum.setToolTip('Set this hardware gain control to its lowest available level.')
        self.minimum.clicked.connect(self.set_minimum);heading.addWidget(self.minimum);layout.addLayout(heading)
        self.combo=DeviceCombo();self.combo.setAccessibleName('Microphone hardware gain control')
        self.combo.activated.connect(self.select_control);layout.addWidget(self.combo)
        self.fader=QWidget();row=QHBoxLayout(self.fader);row.setContentsMargins(0,0,0,0)
        self.slider=VolumeControl(Qt.Orientation.Horizontal);self.slider.setPageStep(1)
        self.slider.setAccessibleName('Microphone hardware gain')
        self.level=text('');self.level.setMinimumWidth(70)
        row.addWidget(self.slider,1);row.addWidget(self.level);layout.addWidget(self.fader)
        self.help=text('Checking microphone hardware gain…','muted');self.help.setWordWrap(True);layout.addWidget(self.help)
        self.slider.valueChanged.connect(self.show_level);self.slider.committed.connect(self.commit)
        self.set_state({},None)

    def cancel_pending(self):
        self.slider.delay.stop();self.slider.blockSignals(True)
        self.slider.setSliderDown(False);self.slider.blockSignals(False)

    def set_state(self,state,device):
        if not device or state.get('source')!=device['name']:
            state={'controls':[],'message':'Connect a microphone, then press Refresh to check hardware gain.'}
        controls=state.get('controls',[])
        token=(backend.identity(device),backend.audio_gain.source_context(device)) if device else None
        token=(token,[(backend.audio_gain.control_key(c),c['minimum'],c['maximum'],c['card_identity']) for c in controls])
        changed=token!=self.token
        if changed:self.cancel_pending()
        self.token=token;self.device=copy.deepcopy(device);self.controls=copy.deepcopy(controls)
        self.help.setText(state.get('message',''))
        available=bool(controls)
        self.combo.setVisible(len(controls)>1);self.fader.setVisible(available);self.minimum.setVisible(available)
        self.setEnabled(available)
        if not available:
            self.control=None;self.title.setText('Mic boost / hardware gain');return
        if not changed and (self.slider.isSliderDown() or self.slider.delay.isActive()):return
        previous=backend.audio_gain.control_key(self.control) if self.control and not changed else None
        self.combo.blockSignals(True);self.combo.clear()
        for control in controls:
            label=control['name']+(f" ({control['index']+1})" if control['index'] else '')
            self.combo.addItem(label,backend.audio_gain.control_key(control))
        selected=next((i for i,c in enumerate(controls) if backend.audio_gain.control_key(c)==previous),0)
        self.combo.setCurrentIndex(selected);self.combo.blockSignals(False);self.select_control(selected)

    def select_control(self,index):
        self.cancel_pending()
        if not 0<=index<len(self.controls):return
        self.control=copy.deepcopy(self.controls[index]);control=self.control
        steps=control['steps']
        selected=min(range(len(steps)),key=lambda i:abs(steps[i][0]-control['value']))
        self.slider.blockSignals(True);self.slider.setRange(0,len(steps)-1);self.slider.setValue(selected);self.slider.blockSignals(False)
        title='Mic boost' if control['kind']=='boost' else 'Hardware capture gain'
        self.title.setText(title);self.title.setToolTip(control['name']);self.slider.setAccessibleName(title+' — '+control['name'])
        low=backend.audio_gain.gain_label(steps[0][1],steps[0][0]);high=backend.audio_gain.gain_label(steps[-1][1],steps[-1][0])
        self.slider.setToolTip(f'{control["name"]}: {low} to {high}. Lower gain to reduce distortion. Channel offsets are kept where the hardware range permits.')
        self.show_level(selected)

    def show_level(self,index):
        if self.control and 0<=index<len(self.control['steps']):
            raw,db=self.control['steps'][index];self.level.setText(backend.audio_gain.gain_label(db,raw))

    def commit(self,index):
        if self.device and self.control and 0<=index<len(self.control['steps']):
            self.changed.emit(copy.deepcopy(self.device),copy.deepcopy(self.control),self.control['steps'][index][0])

    def set_minimum(self):
        if self.control:self.slider.setValue(0);self.slider.commit()


class AudioSettingsPage(QWidget):
    """Devices and system sounds share one Audio destination."""
    def __init__(self,async_run,listen=True):
        super().__init__()
        from sounds.page import SoundsPage
        self.devices=AudioPage(async_run,listen=listen)
        self.sounds=SoundsPage(async_run)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,8,0,0)
        self.tabs=QTabWidget();self.tabs.addTab(self.devices,'Devices');self.tabs.addTab(self.sounds,'System Audio')
        layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(lambda _:self.refresh())

    @property
    def dirty(self):return self.sounds.dirty
    @property
    def busy(self):return self.sounds.busy or self.devices.writing or bool(self.devices.pending)
    def refresh(self):self.tabs.currentWidget().refresh()
    def open_system_audio(self):self.tabs.setCurrentWidget(self.sounds)


class AudioPage(QWidget):
    appCountChanged=pyqtSignal(int)
    def __init__(self,async_run,listen=True,*,compact=False,open_settings=None):
        super().__init__();self.async_run=async_run;self.listen=listen;self.compact=compact
        self.data=None;self.columns={};self.reading=False;self.writing=False;self.again=False
        self.revision=0;self.pending=OrderedDict();self.mode='playback';self.icon_cache={};self.app_icons=None
        self.active=False;self.error='';self.app_count=None;self.column_width=audio_layout.COLUMN_WIDTH
        layout=QVBoxLayout(self);layout.setContentsMargins(*(0,0,0,0) if compact else (20,16,20,16));layout.setSpacing(10)
        heading=QHBoxLayout()
        if compact:
            self.count=text('Loading…','muted');heading.addWidget(self.count);heading.addStretch()
            if open_settings:
                settings=QPushButton('Settings');settings.setToolTip('Open Audio settings');settings.setAccessibleName('Open Audio settings')
                settings.clicked.connect(open_settings);heading.addWidget(settings)
        else:heading.addWidget(text('Audio mixer','brand'));heading.addStretch()
        self.refresh_button=QPushButton('↻' if compact else 'Refresh')
        self.refresh_button.setToolTip('Refresh audio devices and apps');self.refresh_button.setAccessibleName('Refresh audio devices and apps')
        if compact:self.refresh_button.setFixedWidth(30)
        self.refresh_button.clicked.connect(self.refresh);heading.addWidget(self.refresh_button)
        layout.addLayout(heading)
        if not compact:layout.addWidget(text('Set your devices, then mix each application below. Changes take effect immediately.','muted'))
        self.test_output=OutputTest(self.preview_error)
        masters=QHBoxLayout();masters.setSpacing(audio_layout.MASTER_GAP if compact else 14);self.devices={}
        for kind,title in ([('sink','OUTPUT')] if compact else [('sink','OUTPUT'),('source','MICROPHONE')]):
            group=QFrame() if compact else QGroupBox(title)
            inside=QVBoxLayout(group);inside.setSpacing(7);inside.setAlignment(Qt.AlignmentFlag.AlignTop)
            combo=DeviceCombo();combo.setAccessibleName(title.title()+' device')
            if compact:
                self.master=group;group.setObjectName('audioMaster');group.setFixedWidth(audio_layout.MASTER_WIDTH)
                inside.setContentsMargins(12,12,12,12)
                inside.addWidget(text('Main volume','audioApp'))
                subtitle=text('All playback','muted');subtitle.setMinimumHeight(24);inside.addWidget(subtitle)
            else:
                inside.addWidget(combo)
                inside.addWidget(text('Microphone volume' if kind=='source' else 'Output volume','muted'))
            row=QHBoxLayout();volume=VolumeControl(Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal)
            percent=text('0%','audioLevel' if compact else '');percent.setMinimumWidth(40)
            volume.setAccessibleName('Microphone volume' if kind=='source' else 'Output volume')
            if compact:
                percent.setAlignment(Qt.AlignmentFlag.AlignCenter);inside.addWidget(percent)
                volume.setFixedWidth(35);volume.setMinimumHeight(75)
                row.addStretch();row.addWidget(volume);row.addStretch();inside.addLayout(row,1)
                mute=QPushButton('Mute');mute.setCheckable(True);mute.setObjectName('audioMute')
            else:
                row.addWidget(volume,1);row.addWidget(percent);inside.addLayout(row)
                mute=QCheckBox('Muted')
            actions=QHBoxLayout();actions.addWidget(mute);actions.addStretch()
            if kind=='sink':actions.addWidget(self.test_output)
            inside.addLayout(actions);masters.addWidget(group,1)
            if compact:
                inside.addWidget(text('Output device','muted'));inside.addWidget(combo)
            self.devices[kind]=(combo,volume,percent,mute)
            volume.valueChanged.connect(lambda value,p=percent:p.setText(f'{value}%'))
            volume.committed.connect(lambda value,k=kind:self.device_action(k,'volume',value))
            mute.clicked.connect(lambda checked,k=kind:self.device_action(k,'mute',checked))
            combo.activated.connect(lambda _,k=kind:self.device_action(k,'default',None))
            combo.setToolTip('System Default for apps without an individual device choice.')
            if kind=='source':
                self.mic_gain=MicrophoneGain();self.mic_gain.changed.connect(self.gain_action);inside.addWidget(self.mic_gain)
        if not compact:
            layout.addLayout(masters)
            toolbar=QHBoxLayout();self.modes=QTabBar();self.modes.setExpanding(False)
            self.modes.addTab('Playback');self.modes.addTab('Recording');self.modes.currentChanged.connect(self.switch_mode)
            toolbar.addWidget(self.modes);toolbar.addSpacing(12);self.count=text('Loading apps…','muted');toolbar.addWidget(self.count);toolbar.addStretch()
            toolbar.addWidget(text('Scroll sideways for more apps','muted'));layout.addLayout(toolbar)
        self.scroll=ColumnsScroll();self.scroll.setObjectName('audioScroll');self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.container=QWidget();self.container.setObjectName('audioColumns');self.row=QHBoxLayout(self.container)
        margin=0 if compact else 8
        self.row.setContentsMargins(margin,margin,margin,margin);self.row.setSpacing(audio_layout.COLUMN_GAP if compact else 12);self.row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.empty=text('Loading audio applications…','muted');self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True);self.empty.setMinimumWidth(180 if compact else 420);self.row.addWidget(self.empty,1)
        self.scroll.setWidget(self.container);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        if compact:
            self.scroll.setMinimumWidth(audio_layout.MIN_COLUMN_WIDTH);masters.addWidget(self.scroll,1);layout.addLayout(masters,1)
        else:layout.addWidget(self.scroll,1)
        self.status=text('Ready','status');self.status.setWordWrap(True);layout.addWidget(self.status)
        if compact:self.status.hide()
        self.refresh_delay=QTimer(self);self.refresh_delay.setSingleShot(True);self.refresh_delay.setInterval(160)
        self.refresh_delay.timeout.connect(self.refresh)
        self.poll=QTimer(self);self.poll.setInterval(4000);self.poll.timeout.connect(self.periodic)
        self.events=QProcess(self);env=QProcessEnvironment.systemEnvironment();env.insert('LC_ALL','C');self.events.setProcessEnvironment(env)
        self.events.readyReadStandardOutput.connect(self.audio_events)
        self.events.readyReadStandardError.connect(lambda:self.events.readAllStandardError())
        QApplication.instance().aboutToQuit.connect(self.stop)

    def fit_compact(self,width,count=None):
        if not self.compact:return
        if count is None:count=self.app_count if self.app_count is not None else 1
        _,self.column_width=audio_layout.fit(count,width)
        for column in self.columns.values():column.setFixedWidth(self.column_width)
        self.container.setMinimumWidth(max(0,len(self.columns)*(self.column_width+audio_layout.COLUMN_GAP)-audio_layout.COLUMN_GAP))
        self.scroll.setVisible(count>0)

    def set_status(self,message):
        self.status.setText(message)
        if self.compact:self.status.setVisible(bool(message))

    def showEvent(self,event):
        super().showEvent(event);self.active=True
        if self.listen:self.poll.start();self.start_events();self.refresh()
    def hideEvent(self,event):self.stop();super().hideEvent(event)
    def start_events(self):
        if self.active and self.events.state()==QProcess.ProcessState.NotRunning:self.events.start('pactl',['subscribe'])
    def stop(self):
        self.active=False;self.poll.stop();self.refresh_delay.stop()
        self.test_output.stop()
        if not self.compact:self.mic_gain.cancel_pending()
        if self.events.state()!=QProcess.ProcessState.NotRunning:
            self.events.terminate()
            if not self.events.waitForFinished(250):self.events.kill();self.events.waitForFinished(250)
    def periodic(self):self.start_events();self.refresh()
    def audio_events(self):
        payload=bytes(self.events.readAllStandardOutput()).decode(errors='replace')
        if self.active and any(' on '+kind+' #' in payload for kind in ('card','sink','source','sink-input','source-output','server')):
            self.refresh_delay.start()

    def refresh(self):
        if self.reading or self.writing or self.pending:self.again=True;return
        self.reading=True;self.again=False;revision=self.revision
        def done(data):
            if sip.isdeleted(self):return
            self.reading=False
            if revision==self.revision and not self.writing:
                self.data=data;self.render()
                if not self.error:self.set_status(('No apps playing audio.' if not self.columns else '') if self.compact
                    else 'Each column controls one app. Apps with several audio streams stay together.')
            else:self.again=True
            if self.again and self.active:self.refresh_delay.start()
        def failed(message):
            if sip.isdeleted(self):return
            self.reading=False;self.set_status('Audio unavailable: '+message)
            self.test_output.set_device(None)
            if not self.data:self.empty.setText('The audio server is unavailable. Reconnect it, then press Refresh.')
        self.async_run((lambda:backend.snapshot(playback_only=True)) if self.compact else backend.snapshot,done,failed)

    def preview_error(self,message):
        self.error=message;self.set_status(message)

    def submit(self,key,fn):
        self.revision+=1;self.error='';self.pending[key]=fn;self.next_change()
    def next_change(self):
        if self.writing or not self.pending:return
        _,fn=self.pending.popitem(last=False);self.writing=True
        def finished(error=''):
            if sip.isdeleted(self):return
            self.writing=False
            if error:self.error=error;self.set_status(error)
            if self.pending:self.next_change()
            else:self.refresh()
        self.async_run(fn,lambda _:finished(),finished)
    def app_action(self,group,action,value):
        if action=='device' and group['kind']=='playback' and self.data:
            choice=next((d for d in self.data.get('outputs',self.data['devices']['sink']) if d['name']==value),None)
            if choice and 'monitor_route' in choice:
                choice=copy.deepcopy(choice)
                self.set_status('Switching '+group['name']+' to '+choice['description']+'…')
                self.submit((group['kind'],group['key'],action),lambda:backend.apply_app_output(group,choice))
                return
        self.submit((group['kind'],group['key'],action),lambda:backend.apply_app(group,action,value))
    def device_action(self,kind,action,value):
        if not self.data:return
        name=self.devices[kind][0].currentData()
        if kind=='sink' and action=='default':
            choice=next((d for d in self.data.get('outputs',self.data['devices']['sink']) if d['name']==name),None)
            if choice:
                self.test_output.set_device(None)
                self.devices[kind][1].delay.stop()
                for widget in (self.devices[kind][1],self.devices[kind][3]):widget.setEnabled(False)
                self.set_status('Switching audio output…')
                choice=copy.deepcopy(choice)
                self.submit((kind,'default'),lambda:backend.apply_output(choice))
            return
        device=next((d for d in self.data['devices'][kind] if d['name']==name),None)
        if device:
            if kind=='source' and action=='default':self.mic_gain.cancel_pending()
            device=copy.deepcopy(device)
            self.submit((kind,name,action),lambda:backend.apply_device(kind,device,action,value))

    def gain_action(self,device,control,value):
        key=('source',device['name'],'hardware-gain',backend.audio_gain.control_key(control))
        self.submit(key,lambda:backend.apply_gain(device,control,value))

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
            devices=self.data['devices'][kind]
            choices=self.data.get('outputs',devices) if kind=='sink' else devices
            fill_devices(combo,choices,self.data['defaults'][kind])
            current=next((d for d in devices if d['name']==combo.currentData()),None)
            combo.setEnabled(bool(choices))
            for widget in (volume,mute):widget.setEnabled(current is not None)
            if current:
                volume.sync(backend.level([current]));percent.setText(f'{volume.value()}%');mute.setChecked(current.get('mute',False))
            if kind=='sink':
                self.test_output.set_device(current)
                if self.compact:mute.setText('Unmute' if current and current.get('mute',False) else 'Mute')
            if kind=='source':self.mic_gain.set_state(self.data.get('microphone_gain',{}),current)
        groups=self.data['apps'][self.mode];keys={(self.mode,g['key']) for g in groups}
        for key in list(self.columns):
            if key not in keys:
                column=self.columns.pop(key);column.volume.delay.stop();self.row.removeWidget(column);column.hide();column.deleteLater()
        devices=self.data.get('outputs',self.data['devices']['sink']) if self.mode=='playback' else self.data['devices']['source']
        for index,group in enumerate(groups):
            key=(self.mode,group['key']);column=self.columns.get(key)
            if column is None:
                column=AppColumn(group,compact=self.compact);column.changed.connect(self.app_action);self.columns[key]=column
                if self.compact:column.setFixedWidth(self.column_width)
            self.row.insertWidget(index,column)
            column.sync(group,devices,self.app_icon(group),self.data['defaults'][backend.KINDS[self.mode][1]],self.data.get('routes',{}));column.show()
        self.empty.setVisible(not groups)
        self.empty.setText('No apps are playing audio.\nStart music, a video, or a call to see its mixer column.' if self.mode=='playback'
                           else 'No apps are recording audio.\nApps using a microphone or recording system audio appear here.')
        self.count.setText(f'{len(groups)} '+('app' if len(groups)==1 else 'apps'))
        if self.compact:
            self.container.setMinimumWidth(max(0,len(groups)*(self.column_width+audio_layout.COLUMN_GAP)-audio_layout.COLUMN_GAP))
            if len(groups)!=self.app_count:
                self.app_count=len(groups);self.appCountChanged.emit(self.app_count)
        else:self.container.setMinimumWidth(16+len(groups)*226 if groups else 440)
