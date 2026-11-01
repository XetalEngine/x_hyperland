#!/usr/bin/env python3
"""Software-rendered restore wizard. The existing shell owns every disk write."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QProcess, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap, QPen
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QScrollArea, QCheckBox, QComboBox, QLineEdit,
    QFormLayout, QProgressBar, QPlainTextEdit, QSizePolicy)

import installer_account
from installer_protocol import LIMIT

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('restore_console', ROOT/'installer-ui.py')
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)
STEPS = ('Welcome', 'Your drive', 'Your account', 'Review', 'Install', 'Done')
PHASES = ('Prepare drive', 'Create filesystems', 'Restore snapshot',
          'Set up account', 'Prepare boot files', 'Finish installation')
STYLE = '''
QWidget { color: #e4eef5; font-family: "DejaVu Sans"; font-size: 14px; }
QWidget#installer { background: #0a141e; }
QFrame#sidebar { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #163244,stop:1 #101e2c); border-radius: 22px; }
QLabel#eyebrow { color: #66c7f5; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#brand { font-size: 24px; font-weight: 800; letter-spacing: 2px; }
QLabel#headline { font-size: 30px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #94aabd; }
QLabel#badge { color: #95d8f9; background: #183247; border: 1px solid #2b536d; border-radius: 12px; padding: 7px 13px; font-size: 11px; }
QLabel#step { color: #8ba3b6; padding: 12px 14px; border-radius: 10px; }
QLabel#step[active="true"] { color: #dff3ff; background: #224a65; font-weight: 700; }
QLabel#step[complete="true"] { color: #73c8df; }
QPushButton { background: #182a39; border: 1px solid #2e4659; border-radius: 10px; padding: 11px 22px; font-weight: 600; }
QPushButton:hover { background: #213d50; border-color: #65b6df; }
QPushButton:focus { border: 2px solid #85d2fb; }
QPushButton:disabled { color: #5f7689; background: #111f2c; border-color: #20313f; }
QPushButton#primary { background: #46b9f1; color: #071925; border-color: #46b9f1; }
QPushButton#primary:hover { background: #80d4ff; }
QPushButton#primary:disabled { background: #25465b; color: #7494a8; border-color: #25465b; }
QPushButton#danger { background: #edab77; color: #26180e; border-color: #edab77; }
QPushButton#card { text-align: left; background: #122331; border: 1px solid #294454; border-radius: 14px; padding: 0; }
QPushButton#card:hover { background: #182e40; border-color: #589ac0; }
QPushButton#card:checked { background: #183b52; border: 2px solid #59c4fa; }
QPushButton#card QLabel { background: transparent; border: none; }
QLabel#cardTitle { font-weight: 700; font-size: 16px; }
QLabel#cardDetail { color: #a4bacb; font-size: 12px; }
QLabel#cardGlyph { color: #69cef7; font-size: 24px; }
QPushButton#link { color: #9db8cc; background: transparent; border: none; font-size: 11px; padding: 6px; }
QScrollArea, QWidget#page { background: transparent; border: none; }
QScrollBar:vertical { background: #101f2c; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #35586f; min-height: 32px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLineEdit, QComboBox { background: #0b1823; border: 1px solid #35536a; border-radius: 8px; padding: 10px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus { border-color: #62c7fb; }
QLineEdit:disabled, QComboBox:disabled { color: #718797; border-color: #233848; }
QComboBox QAbstractItemView { background: #142939; selection-background-color: #245473; }
QCheckBox { spacing: 10px; padding: 10px 0; }
QCheckBox::indicator { width: 20px; height: 20px; }
QLabel#warning { background: #302820; color: #efc69e; border: 1px solid #665039; border-radius: 12px; padding: 18px; }
QLabel#error { color: #ffc291; padding: 8px 0; }
QPlainTextEdit { background: #08121c; color: #a7bdce; border: 1px solid #294152; border-radius: 10px; padding: 12px; font-family: monospace; font-size: 12px; }
QProgressBar { border: none; border-radius: 6px; background: #1a3040; min-height: 12px; max-height: 12px; }
QProgressBar::chunk { background: #52c4f4; border-radius: 6px; }
QLabel#percentage { color: #6ed2ff; font-size: 56px; font-weight: 700; }
'''


def label(text='', name='', wrap=False):
    item = QLabel(str(text))
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name: item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


class Card(QPushButton):
    def __init__(self, title, detail, glyph):
        super().__init__()
        self.setObjectName('card')
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self.setAccessibleDescription(detail)
        row = QHBoxLayout(self); row.setContentsMargins(20, 14, 20, 14); row.setSpacing(18)
        icon = label(glyph, 'cardGlyph'); icon.setFixedWidth(34)
        row.addWidget(icon)
        words = QVBoxLayout(); words.setSpacing(5)
        words.addWidget(label(title, 'cardTitle', True))
        words.addWidget(label(detail, 'cardDetail', True))
        row.addLayout(words, 1)
        self.mark = label('○', 'cardGlyph'); row.addWidget(self.mark)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.toggled.connect(lambda checked: self.mark.setText('●' if checked else '○'))
        self.setMinimumHeight(85)


class DiskMap(QWidget):
    """A visual explanation of the whole-disk layout, never a device selector."""
    def __init__(self):
        super().__init__(); self.setMinimumHeight(100)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#245470')); painter.drawRoundedRect(0, 8, 90, 42, 8, 8)
        painter.setBrush(QColor('#3997c8')); painter.drawRoundedRect(98, 8, max(1, width-98), 42, 8, 8)
        painter.setPen(QColor('#e9f7ff')); painter.drawText(18, 34, 'EFI')
        painter.drawText(116, 34, 'Your system · ext4')
        painter.setPen(QColor('#91a9bb')); painter.drawText(0, 78, 'New boot partition + restored system')


class Wizard(QWidget):
    def __init__(self, preview=False, clone_dir=ROOT):
        super().__init__()
        self.setObjectName('installer'); self.setWindowTitle('Hyper Fusion · Install ISO')
        self.resize(1180, 790); self.setMinimumSize(800, 560)
        self.preview, self.clone_dir = preview, Path(clone_dir)
        self.current = {}; self.peer = None; self.cards = []; self.selected = ''
        self.result = ''; self.busy = False; self.account_inputs = []
        self.preview_index = 0; self.preview_mode = 'wipe'; self.preview_drive = 'Fusion NVMe · 1 TB'
        self.preview_account = 'Keep existing accounts and passwords.'
        self.progress_started = 0; self.progress_state = ''; self.verifier = None
        self.acknowledged_completion = False
        outer = QHBoxLayout(self); outer.setContentsMargins(26, 26, 26, 26); outer.setSpacing(32)
        self.sidebar = QFrame(); self.sidebar.setObjectName('sidebar'); self.sidebar.setFixedWidth(230)
        side = QVBoxLayout(self.sidebar); side.setContentsMargins(24, 30, 24, 22); side.setSpacing(7)
        side.addWidget(label('YOUR WORKSPACE', 'eyebrow'))
        side.addWidget(label('HYPER\nFUSION', 'brand'))
        self.logo = label(); self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image = ROOT/'logo.png'
        if not image.exists(): image = ROOT/'installer-logo.png'
        self.logo.setPixmap(QPixmap(str(image)).scaled(190, 190, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        side.addWidget(self.logo); side.addSpacing(8)
        self.steps = []
        for i, text in enumerate(STEPS):
            step = label(f'{i+1:02}   {text}', 'step'); side.addWidget(step); self.steps.append(step)
        side.addStretch()
        side.addWidget(label('A familiar system.\nA fresh beginning.', 'muted', True))
        outer.addWidget(self.sidebar)
        content = QVBoxLayout(); content.setSpacing(16); outer.addLayout(content, 1)
        top = QHBoxLayout(); top.addWidget(label('SYSTEM RESTORE', 'eyebrow')); top.addStretch()
        self.badge = label('PREVIEW · SAMPLE DRIVES' if preview else 'INSTALL ISO', 'badge'); top.addWidget(self.badge)
        content.addLayout(top)
        self.title = label('Getting ready…', 'headline', True); content.addWidget(self.title)
        self.subtitle = label('', 'subtitle', True); content.addWidget(self.subtitle)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.addWidget(self.scroll, 1)
        self.error = label('', 'error', True); self.error.hide(); content.addWidget(self.error)
        self.status = label('', 'muted', True); content.addWidget(self.status)
        bottom = QHBoxLayout(); bottom.setSpacing(14)
        self.back = QPushButton('Back'); self.back.setObjectName('back'); self.back.clicked.connect(self.go_back)
        self.text_button = QPushButton('Use console installer'); self.text_button.setObjectName('link')
        self.text_button.clicked.connect(self.use_console)
        self.next = QPushButton('Next  →'); self.next.setObjectName('primary'); self.next.setMinimumWidth(160)
        self.next.clicked.connect(self.advance)
        bottom.addWidget(self.back); bottom.addWidget(self.text_button); bottom.addStretch(); bottom.addWidget(self.next)
        content.addLayout(bottom)
        self.timer = QTimer(self); self.timer.setInterval(150); self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.setStyleSheet(STYLE)
        if preview: self.show_preview()

    def resizeEvent(self, event):
        self.logo.setVisible(self.height() >= 700)
        self.sidebar.setFixedWidth(230 if self.width() >= 1050 else 190)
        super().resizeEvent(event)

    def show_page(self, page, peer=None):
        self.current = dict(page); self.peer = peer; self.result = ''; self.busy = False
        generation=self.current
        self.cards = []; self.selected = ''; self.account_inputs = []
        self.error.clear(); self.error.hide(); self.status.clear()
        self.title.setText(console.clean(page.get('title', '')))
        self.subtitle.setText('')
        self.back.setVisible(True); self.back.setEnabled(True); self.back.setText('Back')
        self.next.setVisible(True); self.next.setEnabled(True); self.next.setText('Next  →')
        self.next.setObjectName('primary'); self.next.setStyleSheet('')
        self.text_button.setVisible(page['kind'] == 'home' and not self.preview)
        old = self.scroll.takeWidget()
        if old: old.deleteLater()
        self.page = QWidget(); self.page.setObjectName('page')
        self.body = QVBoxLayout(self.page); self.body.setContentsMargins(0, 5, 10, 5); self.body.setSpacing(13)
        self.scroll.setWidget(self.page)
        kind = page['kind']
        step = {'home':0, 'verify':0, 'menu':1, 'account':2, 'confirm':3, 'progress':4, 'message':5}[kind]
        self.set_step(step)
        self.badge.setText('PREVIEW · SAMPLE DRIVES' if self.preview or page.get('dummy') else ('UEFI' if page.get('uefi') else 'BIOS'))
        if kind == 'home':
            self.title.setText('Your system. A fresh start.')
            self.subtitle.setText('Choose how you’d like to install your snapshot.')
            self.back.setText('Exit')
            glyphs = {'wipe':'◫', 'verify':'✓', 'free':'+', 'parts':'▤'}
            for tag, description in zip(page['items'][::2], page['items'][1::2]):
                if tag in console.ACTIONS:
                    action = console.ACTIONS[tag]
                    self.add_card(tag, action[0], action[2], glyphs[tag])
            self.select(page.get('mode', 'wipe'))
            self.status.setText('Snapshot integrity: '+console.clean(page.get('snapshot', 'not checked')))
        elif kind == 'menu':
            self.title.setText('Choose your drive' if 'drive' in page.get('title','').lower() or page.get('mode')=='wipe' else console.clean(page.get('title','Choose a destination')))
            self.subtitle.setText(console.clean(page.get('text','')))
            for tag, description in zip(page['items'][::2], page['items'][1::2]):
                self.add_card(tag, console.clean(tag), console.clean(description), '◫')
            self.next.setEnabled(False)  # Selecting a mode never selects a disk.
        elif kind == 'account': self.account_page()
        elif kind == 'confirm':
            final = page.get('accept','').startswith('Confirm')
            self.title.setText('Ready to install?' if final else 'Review your choices')
            self.subtitle.setText('Check the destination carefully before continuing.')
            if page.get('mode') == 'wipe': self.body.addWidget(DiskMap())
            self.body.addWidget(label(console.clean(page.get('text','')), 'warning', True))
            self.next.setText(page.get('accept','Confirm install'))
            if final:
                self.next.setObjectName('danger'); self.next.style().unpolish(self.next); self.next.style().polish(self.next)
                # A double-click on the preceding Next button must not also
                # approve the newly displayed destructive confirmation.
                self.next.setEnabled(False)
                QTimer.singleShot(500,lambda:self.next.setEnabled(True) if self.current is generation else None)
            self.back.setFocus()  # Enter never approves a newly displayed warning.
        elif kind == 'progress':
            self.title.setText('Making room for your next chapter.')
            self.subtitle.setText('Your files, applications and preferences are on their way.')
            self.percentage = label('0%', 'percentage'); self.body.addWidget(self.percentage)
            self.progress = QProgressBar(); self.progress.setTextVisible(False); self.body.addWidget(self.progress)
            self.progress_message = label('Preparing your installation…', 'subtitle', True); self.body.addWidget(self.progress_message)
            self.phase_labels=[]
            for text in PHASES:
                item=label('○  '+text, 'muted'); self.body.addWidget(item); self.phase_labels.append(item)
            self.body.addWidget(label('Installation details', 'muted'))
            self.details=QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMinimumHeight(150)
            self.body.addWidget(self.details)
            self.progress_started=time.monotonic(); self.progress_state=''; self.last_stage=0; self.busy=True
            self.back.hide(); self.next.setEnabled(False); self.next.setText('Installing…')
            self.status.setText('Keep this computer connected to power.')
        elif kind == 'verify': self.start_verify()
        else:
            self.body.addWidget(label(console.clean(page.get('text','')), '', True))
            if page.get('details'):
                details=QPlainTextEdit(console.clean(page['details'])); details.setReadOnly(True)
                self.body.addWidget(details)
            self.back.hide(); self.next.setText('Done')
        self.body.addStretch()
        if kind not in ('confirm','account'): self.back.setFocus()

    def set_step(self, index):
        for i, step in enumerate(self.steps):
            step.setProperty('active', i == index); step.setProperty('complete', i < index)
            step.style().unpolish(step); step.style().polish(step)

    def add_card(self, tag, title, detail, glyph):
        card=Card(title, detail, glyph); card.clicked.connect(lambda: self.select(tag))
        self.body.addWidget(card); self.cards.append((tag, card))

    def select(self, tag):
        if tag not in [key for key, _ in self.cards]: return
        self.selected=tag
        for key, card in self.cards: card.setChecked(tag == key)
        self.next.setEnabled(True)

    def account_page(self):
        self.title.setText('Make it yours.')
        self.subtitle.setText('Create your administrator account. Use your new password for login and sudo.')
        clone=Path(self.current.get('clone_dir', self.clone_dir))
        source=clone/'accounts.tsv'
        self.users=installer_account.accounts(source) if source.is_file() else []
        if not self.users and (self.preview or self.current.get('dummy')):
            self.users=[dict(name='fusion',uid=1000,gid=1000,home='/home/fusion')]
        names=clone/'account-names.txt'
        self.reserved=set(names.read_text().splitlines()) if names.is_file() else set()
        self.body.addWidget(label('A new username and password are required for this ISO.', 'muted', True))
        form=QFormLayout(); form.setSpacing(15); form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.user=QComboBox(); self.user.addItems([u['name'] for u in self.users])
        self.username=QLineEdit(); self.username.setMaxLength(32)
        self.username.textEdited.connect(self.normalize_username)
        self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm=QLineEdit(); self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.username.setObjectName('username'); self.password.setObjectName('password'); self.confirm.setObjectName('passwordConfirm')
        self.username.setPlaceholderText('Choose a new username')
        self.password.setPlaceholderText('Choose your password — any strength')
        for text, field in [('Desktop to inherit',self.user),('New username',self.username),('New password',self.password),('Confirm password',self.confirm)]:
            form.addRow(label(text),field); self.account_inputs.append(field)
        self.body.addLayout(form)
        self.body.addWidget(label('Login names use lowercase letters. Password strength is your choice; both entries must match.', 'muted', True))
        self.body.addWidget(label('Your desktop and files transfer to your new account. The selected source login and password are replaced.', 'muted', True))
        self.user.currentIndexChanged.connect(lambda _: [field.clear() for field in (self.username,self.password,self.confirm)])
        self.user.setEnabled(len(self.users)>1)
        if not self.users:
            self.next.setEnabled(False)
            self.body.addWidget(label('This snapshot has no regular account whose desktop can be transferred.', 'muted', True))
        self.username.setFocus()

    def normalize_username(self,text):
        cursor=self.username.cursorPosition()
        if text != text.lower():self.username.setText(text.lower()); self.username.setCursorPosition(cursor)

    def advance(self):
        if self.busy or not self.next.isEnabled(): return
        kind=self.current.get('kind')
        if kind in ('home','menu'):
            if not self.selected:return
            result=self.selected
        elif kind == 'account':
            try:
                plan=installer_account.choice(self.users,self.user.currentIndex(),self.username.text(),self.password.text(),self.confirm.text(),self.reserved)
            except (ValueError,IndexError,OSError) as error:
                self.error.setText(str(error)); self.error.show(); return
            self.password.clear(); self.confirm.clear(); result=json.dumps(plan)
        else: result=self.result
        if kind == 'progress': self.acknowledged_completion=True
        self.respond(0,result)

    def go_back(self):
        if self.busy:return
        self.respond(1 if self.current.get('kind')=='home' else 10)

    def use_console(self):
        if self.current.get('kind') != 'home' or self.preview:return
        self.respond(20); QApplication.instance().exit(20)

    def respond(self, status, result=''):
        if self.preview:
            self.preview_answer(status,result); return
        peer,self.peer=self.peer,None
        if peer:
            peer.write((json.dumps({'status':status,'result':result})+'\n').encode())
            peer.flush(); peer.waitForBytesWritten(1000); peer.disconnectFromServer()
        self.back.setEnabled(False); self.next.setEnabled(False); self.text_button.hide()
        self.status.setText('Checking your selection…' if status == 0 else 'Returning…')

    def closeEvent(self,event):
        if self.busy:
            event.ignore(); return
        if self.peer:self.respond(1)
        event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:
            self.go_back(); event.accept()
        else: super().keyPressEvent(event)

    def tick(self):
        if self.current.get('kind') != 'progress':return
        if self.details.isVisible() and not self.preview:
            try:
                with Path('/var/log/xetal-installer.log').open('rb') as stream:
                    stream.seek(0,2); stream.seek(max(0,stream.tell()-16000))
                    log=stream.read().decode(errors='replace')
                if log!=self.details.toPlainText():
                    self.details.setPlainText(log); self.details.verticalScrollBar().setValue(self.details.verticalScrollBar().maximum())
            except OSError:pass
        state,text='0','Preparing your installation…'
        if self.preview or (self.current.get('dummy') and not self.current.get('progress_file')):
            stage=int((time.monotonic()-self.progress_started)/.65)
            state='done' if stage>=6 else str(stage)
            text='Preview complete. Your disks and files are unchanged.' if stage>=6 else PHASES[stage]+'…'
        else:
            try: state,text=Path(self.current['progress_file']).read_text().split('\n',1)
            except (KeyError,OSError,ValueError):return
        if (state,text)==self.progress_state:return
        self.progress_state=(state,text)
        done=state in ('done','failed')
        step=6 if state=='done' else max(0,min(5,int(state))) if state.isdigit() else self.last_stage
        self.last_stage=step
        self.progress.setValue(step*100//6); self.percentage.setText('100%' if state=='done' else str(step*100//6)+'%')
        self.progress_message.setText(console.clean(text)); self.busy=not done
        for i,item in enumerate(self.phase_labels):item.setText(('✓  ' if i<step else '●  ' if i==step else '○  ')+PHASES[i])
        if done:
            self.set_step(5); self.next.setEnabled(True); self.next.setText('Done')
            self.title.setText('Your system is ready.' if state=='done' and not self.preview and not self.current.get('dummy') else 'Preview complete.' if state=='done' else 'Installation stopped.')
            if state=='failed':self.percentage.setText('Stopped')
            self.subtitle.setText('You can close the installer now.'); self.status.clear()

    def start_verify(self):
        self.title.setText('Checking your snapshot.')
        self.subtitle.setText('Reading the archive and comparing its SHA-256 checksum.')
        self.body.addWidget(label('This can take several minutes. The check does not change any disks.', 'muted', True))
        self.busy=True; self.back.setEnabled(False); self.next.setEnabled(False)
        clone=Path(self.current.get('clone_dir',self.clone_dir))
        self.verifier=QProcess(self); self.verifier.setWorkingDirectory(str(clone))
        self.verifier.setStandardOutputFile(os.devnull); self.verifier.setStandardErrorFile(os.devnull)
        self.verifier.finished.connect(lambda code,*_:self.verified(code==0))
        self.verifier.errorOccurred.connect(lambda _:self.verified(False))
        if self.preview:QTimer.singleShot(800,lambda:self.verified(True))
        elif (clone/'snapshot.sha256').is_file() and (clone/'rootfs-snapshot.tar.zst').is_file():
            self.verifier.start('sha256sum',['--check','--strict','snapshot.sha256'])
        else:QTimer.singleShot(0,lambda:self.verified(False))

    def verified(self,passed):
        if self.current.get('kind')!='verify':return
        page=dict(self.current,kind='message',title='Snapshot check '+('passed' if passed else 'failed'),
                  text='The snapshot matches its checksum.' if passed else 'Installation is blocked until a check passes. Recreate the ISO or installation media if the problem persists.')
        self.show_page(page,self.peer); self.result='passed' if passed else 'failed'

    def show_preview(self):
        kinds=('home','menu','account','confirm','confirm','progress')
        index=self.preview_index; kind=kinds[index]
        page=dict(kind=kind,dummy=True,uefi=True,mode=self.preview_mode,snapshot='not checked',clone_dir=str(ROOT),items=[])
        if kind=='home':page['items']=[value for key in ('wipe','verify','free','parts') for value in (key,console.ACTIONS[key][0])]
        if kind=='menu':page.update(title='Choose your drive',text='Sample drives for this preview.',items=['Fusion NVMe · 1 TB','Internal SSD · sample drive','Portable SSD · 256 GB','USB storage · sample drive'])
        if kind=='confirm':page.update(title='Review your choices',accept='Confirm preview' if index==4 else 'Next  →',text='Destination: '+self.preview_drive+'\n\n'+console.ACTIONS[self.preview_mode][0]+'\n\n'+self.preview_account+'\n\nThis preview will not change any disks or accounts.')
        self.show_page(page)

    def preview_answer(self,status,result):
        if status:
            if self.preview_index==0:self.close(); return
            self.preview_index-=1
        else:
            kind=self.current['kind']
            if self.preview_index==0 and kind=='message':self.show_preview(); return
            if kind=='home':
                if result=='verify':self.show_page(dict(kind='verify',dummy=True,clone_dir=str(ROOT))); return
                self.preview_mode=result
            elif kind=='menu':self.preview_drive=result
            elif kind=='account':
                plan=json.loads(result)
                self.preview_account='New administrator: '+plan['username']+'. New login and sudo password. Desktop inherited from '+plan['original']+'.'
            elif kind=='progress':self.close(); return
            self.preview_index+=1
        self.show_preview()


class Server:
    def __init__(self,window,path):
        self.window=window; self.clients={}; self.server=QLocalServer(window)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(str(path)):raise RuntimeError(self.server.errorString())
        os.chmod(path,0o600)
        self.server.newConnection.connect(self.accept)

    def accept(self):
        while self.server.hasPendingConnections():
            peer=self.server.nextPendingConnection(); self.clients[peer]=bytearray()
            peer.readyRead.connect(lambda p=peer:self.read(p))
            peer.disconnected.connect(lambda p=peer:self.disconnected(p))

    def disconnected(self,peer):
        self.clients.pop(peer,None)
        if self.window.peer is peer:self.window.peer=None
        peer.deleteLater()

    def read(self,peer):
        data=self.clients.get(peer)
        if data is None:return
        data.extend(bytes(peer.readAll()))
        if len(data)>LIMIT:peer.abort(); return
        if b'\n' not in data:return
        try:
            value=json.loads(data)
            if not isinstance(value,dict) or value.get('kind') not in ('home','menu','account','confirm','progress','verify','message','finish'):
                raise ValueError('Unknown page')
            if self.window.peer is not None:raise ValueError('Another page is active')
            if value['kind']=='finish':
                if self.window.acknowledged_completion:
                    peer.write(b'{"status":0,"result":""}\n');peer.flush();peer.disconnectFromServer();return
                value['kind']='message'
            items=value.get('items',[])
            if not isinstance(items,list) or len(items)%2 or not all(isinstance(x,str) for x in items):raise ValueError('Invalid menu')
            self.window.show_page(value,peer); self.clients[peer]=bytearray()
        except (ValueError,KeyError,TypeError,OSError):peer.abort()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('preview','serve'))
    parser.add_argument('--socket'); parser.add_argument('--ready'); parser.add_argument('--fullscreen',action='store_true')
    args=parser.parse_args()
    if args.mode=='serve' and (not args.socket or not args.ready):parser.error('serve requires private socket and readiness paths')
    app=QApplication([sys.argv[0]])
    app.setStyle('Fusion'); app.setApplicationName('Hyper Fusion Installer')
    app.setFont(QFont('DejaVu Sans',10))
    window=Wizard(args.mode=='preview')
    server=Server(window,args.socket) if args.mode=='serve' else None
    if args.fullscreen:
        # LinuxFB and bare X11 may have no window manager to resize for us.
        if app.primaryScreen():window.setGeometry(app.primaryScreen().geometry())
        window.showFullScreen()
    else:window.show()
    if args.ready:
        def ready():
            if not app.primaryScreen() or app.primaryScreen().size().width()<800 or app.primaryScreen().size().height()<560:
                app.exit(2);return
            Path(args.ready).write_text('ready\n')
        QTimer.singleShot(200,ready)
    return app.exec()


if __name__=='__main__':raise SystemExit(main())
