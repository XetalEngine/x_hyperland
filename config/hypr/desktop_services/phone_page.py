from pathlib import Path
import os
import shutil
import subprocess
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QGroupBox,QComboBox,
    QPushButton,QLineEdit,QPlainTextEdit,QFileDialog,QMessageBox)
from . import phone
from .common import STATE,read,write,install_packages
from .ui import text


class PhonePage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=False;self.settings=STATE/'phone.json'
        body=QVBoxLayout(self);body.setContentsMargins(22,18,22,18);body.setSpacing(14)
        body.addWidget(text('Your phone, connected','brand'))
        body.addWidget(text('Install KDE Connect on your phone, join the same network, and approve pairing on both devices. SMS requires Android messaging permission.','muted'))
        row=QHBoxLayout();self.device=QComboBox();self.device.setMinimumWidth(280);row.addWidget(self.device,1)
        for caption,callback in [('Refresh',self.refresh),('Pair',lambda:self.perform('pair')),('Unpair',self.unpair),('Find phone',lambda:self.perform('ring'))]:
            button=QPushButton(caption);button.clicked.connect(callback);row.addWidget(button)
        body.addLayout(row)
        columns=QHBoxLayout();columns.setSpacing(16)
        share=QGroupBox('Files & clipboard');left=QVBoxLayout(share)
        left.addWidget(text('Send pictures, videos, audio clips or other files directly to your paired phone.'))
        files=QPushButton('Send files to phone…');files.setObjectName('primary');files.clicked.connect(self.share_files);left.addWidget(files)
        self.note=QPlainTextEdit();self.note.setPlaceholderText('Text to send to your phone');self.note.setMaximumHeight(180);left.addWidget(self.note)
        note=QPushButton('Send text to phone');note.clicked.connect(lambda:self.perform('share-text',self.note.toPlainText()));left.addWidget(note);left.addStretch();columns.addWidget(share,1)
        sms=QGroupBox('Text messages · SMS');right=QVBoxLayout(sms)
        self.number=QLineEdit();self.number.setPlaceholderText('Recipient phone number');right.addWidget(self.number)
        self.message=QPlainTextEdit();self.message.setPlaceholderText('Write a text message');self.message.setMaximumHeight(180);right.addWidget(self.message)
        send=QPushButton('Send SMS');send.setObjectName('primary');send.clicked.connect(self.send_sms);right.addWidget(send)
        inbox=QPushButton('Open conversations');inbox.clicked.connect(lambda:self.launch('kdeconnect-sms'));right.addWidget(inbox)
        right.addWidget(text('Messages are sent through your phone and may use your mobile plan.','muted'));right.addStretch();columns.addWidget(sms,1);body.addLayout(columns)
        whatsapp=QGroupBox('WhatsApp');box=QVBoxLayout(whatsapp)
        box.addWidget(text('Link your WhatsApp account to send text, record voice messages, and attach videos or audio files in WhatsApp Web. Your conversations stay in WhatsApp.'))
        actions=QHBoxLayout();open_button=QPushButton('Open WhatsApp');open_button.setObjectName('primary');open_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(phone.whatsapp_url())));actions.addWidget(open_button)
        handler=QPushButton('Use Fusion for WhatsApp links');handler.clicked.connect(self.set_handler);actions.addWidget(handler);actions.addStretch();box.addLayout(actions);body.addWidget(whatsapp)
        self.status=text('','muted');body.addWidget(self.status);body.addStretch()
        footer=QHBoxLayout();self.install=QPushButton('Install phone integration');self.install.clicked.connect(lambda:self.job(lambda:install_packages(['kdeconnect']),lambda _:self.refresh()));footer.addWidget(self.install)
        footer.addStretch();manage=QPushButton('Device permissions & plugins…');manage.clicked.connect(lambda:self.launch('kdeconnect-app'));footer.addWidget(manage);body.addLayout(footer)
        self.device.currentIndexChanged.connect(self.remember)

    def job(self,work,done=None):
        if self.busy:return
        self.busy=True;self.setEnabled(False)
        def finished(result):
            self.busy=False;self.setEnabled(True)
            if done:done(result)
            else:self.status.setText(result or 'Request sent to your phone.')
        def failed(error):self.busy=False;self.setEnabled(True);self.status.setText(str(error))
        self.async_run(work,finished,failed)

    def refresh(self):
        self.install.setVisible(not shutil.which('kdeconnect-cli'))
        if not self.busy:self.job(phone.devices,self.populate)

    def populate(self,devices):
        selected=self.device.currentData() or read(self.settings,{}).get('device','')
        self.device.blockSignals(True);self.device.clear()
        for item in devices:self.device.addItem(item['name']+(' · connected' if item['available'] else ' · pairing or offline'),item['id'])
        self.device.setCurrentIndex(max(0,self.device.findData(selected)));self.device.blockSignals(False)
        self.status.setText('Choose a phone and approve pairing on it.' if devices else 'No phone found. Open KDE Connect on your phone, then refresh.')

    def remember(self):
        if self.device.currentData():write(self.settings,dict(device=self.device.currentData()))

    def perform(self,operation,value='',destination=''):
        device=self.device.currentData()
        self.job(lambda:phone.action(device,operation,value,destination))

    def unpair(self):
        if QMessageBox.question(self,'Unpair phone','Remove this phone’s pairing?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Yes:self.perform('unpair')

    def share_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Send files to phone',str(Path.home()))
        if paths:
            device=self.device.currentData()
            def send():
                for path in paths:phone.action(device,'share',path)
                return f'Sent {len(paths)} file request(s) to your phone.'
            self.job(send)

    def send_sms(self):
        self.perform('send-sms',self.message.toPlainText(),self.number.text())

    def launch(self,command):
        try:subprocess.Popen([command],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as error:self.status.setText(str(error))

    def set_handler(self):
        from .common import run
        def setup():
            from .common import ROOT
            destination=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications/fusion-whatsapp.desktop'
            write(destination,(ROOT/'desktop/data/applications/fusion-whatsapp.desktop').read_text())
            return run(['xdg-mime','default','fusion-whatsapp.desktop','x-scheme-handler/whatsapp'])
        self.job(setup,lambda _:self.status.setText('WhatsApp links now open through Fusion in WhatsApp Web.'))
