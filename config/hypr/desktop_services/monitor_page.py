import json
import os
import subprocess
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGroupBox,QVBoxLayout,QHBoxLayout,QGridLayout,QSpinBox,QPushButton,QMessageBox
from . import monitor_hardware as hardware
from .common import ROOT
from .ui import text


class MonitorPicture(QGroupBox):
    def __init__(self,async_run):
        super().__init__('Monitor picture');self.async_run=async_run;self.name='';self.busy=False;self.device=None;self.guard=None
        box=QVBoxLayout(self);self.caption=text('Select a display to adjust its brightness and colors.','muted');box.addWidget(self.caption)
        grid=QGridLayout();self.fields={}
        for i,(key,title) in enumerate([('brightness','Brightness'),('contrast','Contrast'),('red','Red'),('green','Green'),('blue','Blue')]):
            control=QSpinBox();control.setRange(0,100);control.setSpecialValueText('—');control.setSuffix('%');control.setEnabled(False);self.fields[key]=control
            grid.addWidget(text(title),i//3*2,i%3);grid.addWidget(control,i//3*2+1,i%3)
        box.addLayout(grid);row=QHBoxLayout();self.read_button=QPushButton('Read monitor controls');self.read_button.clicked.connect(self.refresh);row.addWidget(self.read_button);row.addStretch()
        self.apply_button=QPushButton('Preview picture…');self.apply_button.clicked.connect(self.preview);self.apply_button.setEnabled(False);row.addWidget(self.apply_button);box.addLayout(row)

    def select(self,name):
        if name==self.name:return
        self.name=name;self.device=None;self.apply_button.setEnabled(False)
        for field in self.fields.values():field.setEnabled(False);field.setValue(0)
        self.caption.setText(name+' · Read controls to detect hardware brightness, contrast and RGB adjustment.')

    def job(self,work,done):
        if self.busy:return
        self.busy=True;self.setEnabled(False)
        def finished(value):self.busy=False;self.setEnabled(True);done(value)
        def failed(error):self.busy=False;self.setEnabled(True);self.caption.setText(str(error))
        self.async_run(work,finished,failed)

    def refresh(self):
        name=self.name
        def work():
            device=hardware.probe(name);return device,hardware.levels(device)
        def done(result):
            if name!=self.name:return
            self.device,values=result
            for key,field in self.fields.items():
                field.setEnabled(key in values)
                if key in values:field.setRange(1,100);field.setValue(round(100*values[key]['value']/values[key]['maximum']))
            self.apply_button.setEnabled(True);self.caption.setText(name+' · Only controls supported by this monitor are enabled. Keep a preview to save it for future logins.')
        self.job(work,done)

    def preview(self):
        name=self.name;values={k:v.value() for k,v in self.fields.items() if v.isEnabled()}
        def work():
            env=dict(os.environ,PYTHONPATH=str(ROOT))
            child=subprocess.Popen([sys.executable,'-m','desktop_services.monitor_hardware','--preview',name,json.dumps(values)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            line=child.stdout.readline()
            try:result=json.loads(line)
            except ValueError:
                child.terminate();raise RuntimeError('Monitor preview could not start.')
            if not result.get('ready'):
                child.wait(timeout=5);raise RuntimeError(result.get('error','Monitor preview failed.'))
            return child
        def ready(child):
            self.guard=child
            dialog=QMessageBox(QMessageBox.Icon.Question,'Keep this picture?','Restore automatically in 20 seconds.',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Cancel,self)
            dialog.button(QMessageBox.StandardButton.Save).setText('Keep picture');dialog.button(QMessageBox.StandardButton.Cancel).setText('Revert')
            dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
            timer=QTimer(dialog);timer.setSingleShot(True);timer.timeout.connect(dialog.reject);timer.start(19000)
            keep=dialog.exec()==QMessageBox.StandardButton.Save
            def finish():
                try:out,error=child.communicate('keep\n' if keep else 'revert\n',timeout=45)
                except subprocess.TimeoutExpired:raise RuntimeError('The monitor is taking too long to restore its settings.')
                result=json.loads(out.splitlines()[-1]) if out.strip() else {}
                if child.returncode:raise RuntimeError(result.get('error') or error or 'Could not restore monitor settings.')
                return 'Picture saved for '+name+'.' if result.get('kept') else 'Previous picture restored.'
            def complete(message):self.guard=None;self.caption.setText(message)
            self.job(finish,complete)
        self.job(work,ready)
