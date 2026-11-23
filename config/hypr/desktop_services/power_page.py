from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QGridLayout,QGroupBox,QComboBox,QPushButton,QCheckBox,QSpinBox,QScrollArea)
from . import power
from .common import install_packages
from .ui import text
import shutil


class PowerPage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=False;self.revision='';self.hardware={}
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content=QWidget();body=QVBoxLayout(content);body.setContentsMargins(20,16,20,16);body.setSpacing(14);scroll.setWidget(content);outer.addWidget(scroll)
        body.addWidget(text('Power & battery','brand'));body.addWidget(text('Your choices stay saved across login, reboot and sleep. Hardware controls require administrator authentication.','muted'))
        hardware=QGroupBox('Processor & charging');grid=QGridLayout(hardware)
        grid.addWidget(text('Saving a hardware choice lets Fusion manage power. Conflicting power daemons are stopped; Restore returns the previous choice and service state.','muted'),0,0,1,4)
        for row,(kind,caption) in enumerate([('cpu_governor','CPU governor'),('cpu_energy','Energy preference'),('cpu_boost','Turbo boost'),('battery_limit','Battery charge limit')],1):
            grid.addWidget(text(caption),row,0);combo=QComboBox();grid.addWidget(combo,row,1)
            save=QPushButton('Apply');save.clicked.connect(lambda _,k=kind:self.apply_hardware(k));grid.addWidget(save,row,2)
            restore=QPushButton('Restore');restore.clicked.connect(lambda _,k=kind:self.apply_hardware(k,True));grid.addWidget(restore,row,3)
            self.hardware[kind]=(combo,save,restore)
        grid.setColumnStretch(1,1);body.addWidget(hardware)
        self.enabled=QCheckBox('Use Fusion idle, lid and low-battery settings');body.addWidget(self.enabled)
        columns=QHBoxLayout();self.minutes={};self.lids={}
        value=power.load()
        for source,caption in [('ac','Plugged in'),('battery','On battery')]:
            group=QGroupBox(caption);form=QFormLayout(group)
            for action,title in [('lock','Lock after'),('screen','Turn screen off after'),('sleep','Suspend after')]:
                spin=QSpinBox();spin.setRange(0,240);spin.setSpecialValueText('Never');spin.setSuffix(' min');spin.setValue(value[source+'_'+action]);self.minutes[source+'_'+action]=spin;form.addRow(title,spin)
            combo=self.lid_combo();combo.setCurrentIndex(combo.findData(value['lid_'+source]));self.lids['lid_'+source]=combo;form.addRow('When lid closes',combo);columns.addWidget(group,1)
        body.addLayout(columns)
        lower=QGroupBox('While docked & low battery');form=QFormLayout(lower)
        combo=self.lid_combo();combo.setCurrentIndex(combo.findData(value['lid_docked']));self.lids['lid_docked']=combo;form.addRow('Lid closes with external display',combo)
        self.critical=QComboBox()
        for name,key in [('Notify me','notify'),('Suspend','suspend'),('Hibernate','hibernate')]:self.critical.addItem(name,key)
        self.critical.setCurrentIndex(self.critical.findData(value['critical_action']));form.addRow('Critical battery',self.critical)
        self.threshold=QSpinBox();self.threshold.setRange(2,20);self.threshold.setSuffix('%');self.threshold.setValue(value['critical_percent']);form.addRow('At or below',self.threshold)
        form.addRow(text('Video playback and other idle inhibitors are respected. Hibernate requires working swap and resume support. Lid controls appear here even on desktops but only act on a physical laptop lid.','muted'))
        body.addWidget(lower);self.enabled.setChecked(value['enabled']);body.addStretch()
        self.status=text('','muted');outer.addWidget(self.status)
        row=QHBoxLayout();self.install=QPushButton('Install idle service');self.install.clicked.connect(lambda:self.job(lambda:install_packages(['hypridle']),lambda _:self.refresh()));row.addWidget(self.install)
        reload=QPushButton('Refresh hardware');reload.clicked.connect(self.refresh);row.addWidget(reload);row.addStretch()
        save=QPushButton('Save power settings');save.setObjectName('primary');save.clicked.connect(self.save);row.addWidget(save);outer.addLayout(row)

    def lid_combo(self):
        combo=QComboBox()
        for name,key in [('System default','system'),('Do nothing','nothing'),('Lock','lock'),('Suspend','suspend'),('Hibernate','hibernate')]:combo.addItem(name,key)
        return combo

    def job(self,work,done=None):
        if self.busy:return
        self.busy=True;self.setEnabled(False);self.status.setText('Working…')
        def finished(result):
            self.busy=False;self.setEnabled(True)
            if done:done(result)
            else:self.status.setText(str(result))
        def failed(error):self.busy=False;self.setEnabled(True);self.status.setText(str(error))
        self.async_run(work,finished,failed)

    def refresh(self):
        self.install.setVisible(not shutil.which('hypridle'));self.job(power.hardware_status,self.populate)

    def populate(self,value):
        self.revision=value['revision']
        for row in value['settings']:
            if row['id'] not in self.hardware:continue
            combo,save,restore=self.hardware[row['id']];combo.clear()
            for choice in row.get('choices',[]):combo.addItem(choice['label']+('%' if row['id']=='battery_limit' else ''),choice['value'])
            selected=row.get('saved') or row.get('current');combo.setCurrentIndex(max(0,combo.findData(selected)))
            combo.setEnabled(row['supported']);save.setEnabled(row['supported']);restore.setEnabled(row.get('has_backup',False))
            if not row['supported']:combo.addItem('Not supported by this hardware')
            combo.setToolTip('Current: '+str(row.get('current') or 'unavailable')+'\nSaved: '+str(row.get('saved') or 'system default'))
        self.status.setText('Hardware refreshed. Unsaved idle and lid choices are retained.')

    def apply_hardware(self,kind,restore=False):
        value=self.hardware[kind][0].currentData()
        def work():
            message=power.apply_hardware(kind,value,self.revision,restore)
            return power.hardware_status(),message
        def done(result):self.populate(result[0]);self.status.setText(result[1])
        self.job(work,done)

    def save(self):
        value=dict(enabled=self.enabled.isChecked(),critical_action=self.critical.currentData(),critical_percent=self.threshold.value())
        value.update({k:s.value() for k,s in self.minutes.items()});value.update({k:s.currentData() for k,s in self.lids.items()})
        self.job(lambda:power.save(value))

    def showEvent(self,event):
        super().showEvent(event)
        if not self.revision:self.refresh()
