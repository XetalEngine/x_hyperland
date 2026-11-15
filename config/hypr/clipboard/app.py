#!/usr/bin/env python3
"""Session-owned, themed clipboard history. Selection copies; it never types."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'theme'))
import runtime as theme_runtime
from clipboard.store import Store, Frames, write_private
from clipboard.build import build
from clipboard import appearance
from clipboard.placement import prepare_popup
from launcher.activation import BarActivation
from launcher.outside_click import CLICK_EVENT, check_pointer
from PyQt6.QtCore import Qt, QTimer, QProcess, QEvent, QSize, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QIcon, QImageReader, QPixmap, QShortcut, QKeySequence
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QCheckBox, QAbstractItemView)

APP_ID='fusion-clipboard'
STATE=ROOT/'clipboard/state'

def ctl(*args):
    return subprocess.check_output(['hyprctl',*args],text=True,stderr=subprocess.DEVNULL,timeout=1).strip()

def image_preview(mime,data):
    buffer=QBuffer(); buffer.setData(QByteArray(data)); buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer,mime.split('/')[-1].encode()); reader.setAllocationLimit(64)
    size=reader.size()
    if not size.isValid() or size.width()*size.height()>16_000_000:return None
    reader.setScaledSize(size.scaled(96,64,Qt.AspectRatioMode.KeepAspectRatio))
    image=reader.read()
    if image.isNull():return None
    return QIcon(QPixmap.fromImage(image)),f'Image · {size.width()} × {size.height()}'

class History(QWidget):
    def __init__(self,store,collector):
        super().__init__(); self.store=store; self.collector_path=collector; self.collector=None; self.owners=set()
        self.frames=Frames(); self.previous=''; self.cache={}; self.stopping=False; self.failure_count=0
        self.generation=0; self.opened_at=0.; self.dismissed_at=-1.; self.activation=None
        # A normal frameless toplevel unmaps through the compositor's Burn
        # effect, just like Power. Qt.Popup would use a different Wayland role.
        self.setWindowTitle('Clipboard history'); self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(440,540)
        layout=QVBoxLayout(self); layout.setContentsMargins(14,12,14,12); layout.setSpacing(10)
        heading=QHBoxLayout(); heading.setSpacing(10)
        self.mark=QLabel(); self.mark.setFixedSize(30,36); self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter); heading.addWidget(self.mark)
        titles=QVBoxLayout(); titles.setSpacing(2)
        title=QLabel('Clipboard'); title.setObjectName('clipboardTitle'); titles.addWidget(title)
        subtitle=QLabel('Your recent copies, ready to use'); subtitle.setObjectName('muted'); titles.addWidget(subtitle)
        heading.addLayout(titles,1)
        self.close_button=QPushButton(); self.close_button.setFixedSize(28,28)
        self.close_button.setToolTip('Close · Esc'); self.close_button.setAccessibleName('Close clipboard history')
        self.close_button.clicked.connect(lambda:self.dismiss()); heading.addWidget(self.close_button); layout.addLayout(heading)
        layout.addSpacing(4)
        self.search=QLineEdit(); self.search.setPlaceholderText('Search clipboard…'); self.search.setClearButtonEnabled(True); layout.addWidget(self.search)
        self.list=QListWidget(); self.list.setSpacing(2); self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setItemDelegate(appearance.EntryDelegate(self)); layout.addWidget(self.list,1)
        self.empty=QLabel(self.list.viewport()); self.empty.setObjectName('empty'); self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        empty_layout=QVBoxLayout(self.list.viewport()); empty_layout.addWidget(self.empty)
        self.list.setAccessibleName('Clipboard history'); self.search.setAccessibleName('Search clipboard history')
        self.status=QLabel(); self.status.setObjectName('muted'); self.status.setWordWrap(True); layout.addWidget(self.status)
        actions=QHBoxLayout(); actions.setSpacing(4)
        self.copy=QPushButton('Copy'); self.copy.setObjectName('copy'); self.copy.setToolTip('Copy selected item · Enter')
        self.pin=QPushButton('Pin'); self.pin.setToolTip('Keep this item across logins')
        self.delete=QPushButton('Remove'); self.delete.setToolTip('Remove selected item · Delete')
        actions.addWidget(self.pin); actions.addWidget(self.delete); actions.addStretch(); actions.addWidget(self.copy)
        layout.addLayout(actions)
        bottom=QHBoxLayout(); self.pause=QCheckBox('Pause history'); clear=QPushButton('Clear recent'); clear.setObjectName('quiet'); clear.setToolTip('Remove recent items; keep pinned items.')
        bottom.addWidget(self.pause); bottom.addStretch(); bottom.addWidget(clear); layout.addLayout(bottom)
        hint=QLabel('Enter to copy · Ctrl+V to paste'); hint.setObjectName('muted')
        hint.setToolTip('Recent copies stay in memory for this login. Only pinned items are saved on this device.'); layout.addWidget(hint)
        self.search.textChanged.connect(self.populate); self.search.installEventFilter(self); self.list.installEventFilter(self)
        self.list.itemActivated.connect(self.choose); self.list.currentItemChanged.connect(self.selection)
        self.copy.clicked.connect(self.choose); self.pin.clicked.connect(self.toggle_pin); self.delete.clicked.connect(self.remove)
        clear.clicked.connect(self.clear); self.pause.toggled.connect(self.set_paused)
        QShortcut(QKeySequence('Escape'),self,activated=self.dismiss)
        QShortcut(QKeySequence('Ctrl+F'),self,activated=self.search.setFocus)
        appearance.refresh(self)
        if hasattr(QApplication.instance(),'hypr_theme'):
            QApplication.instance().hypr_theme.changed.connect(lambda:appearance.refresh(self))
        try:paused=json.loads((STATE/'preferences.json').read_text()).get('paused') is True
        except (OSError,ValueError,AttributeError):paused=False
        self.store.paused=paused; self.pause.blockSignals(True); self.pause.setChecked(paused); self.pause.blockSignals(False); self.populate()
        if not paused:self.start_collector()

    def start_collector(self):
        if self.stopping or self.store.paused or self.collector:return
        self.frames=Frames(); process=QProcess(self); self.collector=process
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(lambda:self.receive(process))
        process.readyReadStandardError.connect(lambda:process.readAllStandardError())
        process.finished.connect(lambda *_:self.collector_finished(process))
        process.errorOccurred.connect(lambda *_:self.collector_finished(process) if process.state()==QProcess.ProcessState.NotRunning else None)
        process.start(str(self.collector_path),[])

    def collector_finished(self,process):
        if self.collector is not process:return
        self.collector=None; process.deleteLater()
        if self.stopping or self.store.paused:return
        self.failure_count+=1; self.status.setText('Clipboard capture is unavailable. Retrying…')
        QTimer.singleShot(min(30000,1000*2**min(self.failure_count,5)),self.start_collector)

    def receive(self,process):
        data=bytes(process.readAllStandardOutput())
        if process is not self.collector or self.store.paused:return
        try:frames=self.frames.feed(data)
        except (ValueError,UnicodeError):process.kill();return
        changed=False
        for mime,payload in frames:
            if mime.startswith('image/') and image_preview(mime,payload) is None:continue
            try:changed=self.store.add(mime,payload) or changed
            except (ValueError,UnicodeError):continue
        if changed:
            self.failure_count=0; self.populate()

    def populate(self):
        current=self.selected(); query=self.search.text().casefold(); self.list.clear()
        retained={i.key for i in self.store.items}; self.cache={k:v for k,v in self.cache.items() if k in retained}
        for item in sorted(self.store.items,key=lambda i:not i.pinned):
            if item.mime.startswith('image/'):
                if item.key not in self.cache:self.cache[item.key]=image_preview(item.mime,item.data)
                preview=self.cache[item.key]
                if preview is None:continue
                icon,label=preview; searchable=label+' '+item.mime
            else:
                icon=QIcon(); searchable=item.text; label=' '.join(searchable.split())[:200] or 'Blank text'
            if query and query not in searchable.casefold():continue
            row=QListWidgetItem(label)
            is_image=item.mime.startswith('image/')
            detail=item.mime.split('/')[-1].upper()+' image' if is_image else f'Text · {len(item.text):,} characters'
            if item.pinned:detail='Pinned · '+detail
            row.setIcon(icon); row.setData(Qt.ItemDataRole.UserRole,item.key)
            row.setData(appearance.DETAIL,detail); row.setData(appearance.PINNED,item.pinned); row.setData(appearance.IMAGE,is_image)
            row.setData(Qt.ItemDataRole.AccessibleTextRole,label+', '+detail)
            row.setSizeHint(QSize(0,80 if is_image else 66))
            self.list.addItem(row)
            if current and current.key==item.key:self.list.setCurrentItem(row)
        if not self.list.currentItem() and self.list.count():self.list.setCurrentRow(0)
        self.selection(); self.status.setText(('Paused · ' if self.store.paused else '')+f'{self.list.count()} shown · {sum(i.pinned for i in self.store.items)} pinned')
        if not self.list.count():self.status.setText('No matches.' if query else 'Copy some text or an image to get started.' if not self.store.paused else 'History is paused.')
        self.empty.setText('No matching copies\nTry another search.' if query else 'History is paused\nResume to collect new copies.' if self.store.paused else 'Nothing copied yet\nCopy text or an image and it will appear here.')
        self.empty.setVisible(not self.list.count())
        if self.store.pins_unavailable:self.status.setText('Saved pins could not be read and are untouched. Recent history is still available.')

    def selected(self):
        row=self.list.currentItem()
        return next((i for i in self.store.items if row and row.data(Qt.ItemDataRole.UserRole)==i.key),None)

    def selection(self,*_):
        item=self.selected()
        for button in (self.copy,self.pin,self.delete):button.setEnabled(item is not None)
        self.pin.setEnabled(item is not None and not self.store.pins_unavailable)
        self.pin.setText('Unpin' if item and item.pinned else 'Pin')

    def choose(self,*_):
        item=self.selected()
        if item is None:return
        # Keep the Wayland source alive until another app replaces selection.
        # Never synthesize keystrokes into whichever window happens to be active.
        process=QProcess(self); self.owners.add(process)
        # The previous source exits when this one actually owns the clipboard.
        # A failed new process must not destroy the previous clipboard content.
        process.finished.connect(lambda *_:(self.owners.discard(process),process.deleteLater()))
        process.start('wl-copy',['--foreground','--type',item.mime])
        if not process.waitForStarted(1000):
            self.owners.discard(process);process.deleteLater();self.status.setText('Could not copy this item: wl-copy is unavailable.');return
        process.write(item.data); process.closeWriteChannel()
        if process.waitForFinished(80) and process.exitCode()!=0:
            self.status.setText('Could not take ownership of the clipboard. Try again.');return
        self.dismiss()

    def toggle_pin(self):
        item=self.selected()
        if item:
            try:self.store.pin(item.key); self.populate()
            except (OSError,ValueError):self.status.setText('Could not save the pin. Check free space or unpin an item (25 pins / 16 MiB maximum).')

    def remove(self):
        item=self.selected()
        if item:
            try:self.store.delete(item.key); self.populate()
            except OSError:self.status.setText('Could not remove the saved pin. Check filesystem access.')

    def clear(self):self.store.clear(); self.populate()

    def set_paused(self,paused):
        try:write_private(STATE/'preferences.json',{'paused':paused})
        except OSError:
            self.pause.blockSignals(True); self.pause.setChecked(self.store.paused); self.pause.blockSignals(False)
            self.status.setText('Could not save the history preference.'); return
        self.store.paused=paused
        if paused and self.collector:
            process=self.collector; self.collector=None; process.kill(); process.waitForFinished(500); process.deleteLater(); self.frames=Frames()
        if not paused:self.start_collector()
        self.populate()

    def reveal(self,*,from_bar=False):
        if self.isVisible():self.dismiss();return
        # The same bar click can arrive after its outside-click notification.
        if from_bar and time.monotonic()-self.dismissed_at<.35:return
        try:size=prepare_popup(from_bar=from_bar)
        except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.SubprocessError):
            # Never flash a centered window when compositor placement failed.
            print('Could not place the clipboard popup on the current display.',file=sys.stderr);return
        try:self.previous=json.loads(ctl('-j','activewindow')).get('address','')
        except (OSError,ValueError,subprocess.SubprocessError):self.previous=''
        self.search.clear(); self.populate()
        self.generation+=1; self.opened_at=time.monotonic(); self.resize(*size)
        self.show(); self.raise_(); self.activateWindow(); self.search.setFocus()
        if self.activation:self.activation.cancel();self.activation.deleteLater()
        self.activation=BarActivation(self); self.activation.start()

    def dismiss(self,*,restore_focus=True):
        owns_focus=False
        if restore_focus:
            try:owns_focus=json.loads(ctl('-j','activewindow')).get('class')==APP_ID
            except (OSError,ValueError,subprocess.SubprocessError):pass
        self.hide()
        if owns_focus and self.previous.startswith('0x') and all(c in '0123456789abcdefABCDEF' for c in self.previous[2:]):
            try:ctl('dispatch','focuswindow','address:'+self.previous)
            except (OSError,subprocess.SubprocessError):pass

    def dismissal_protected(self):
        return QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None

    def compositor_events(self,connection):
        while connection.canReadLine():
            event=bytes(connection.readLine()).strip()
            if not self.isVisible() or self.dismissal_protected():continue
            if event.startswith((b'workspace>>',b'workspacev2>>')):
                self.dismiss(restore_focus=False)
            elif event==CLICK_EVENT and time.monotonic()-self.opened_at>=.2:
                generation=self.generation
                check_pointer(self,lambda outside,generation=generation:self.outside_checked(outside,generation),'Clipboard history')

    def outside_checked(self,outside,generation):
        if outside is True and generation==self.generation and self.isVisible() and not self.dismissal_protected():
            self.dismiss(restore_focus=False)

    def hideEvent(self,event):
        self.generation+=1; self.dismissed_at=time.monotonic()
        if self.activation:self.activation.cancel()
        super().hideEvent(event)

    def paintEvent(self,event):appearance.paint_panel(self)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.KeyPress:
            if obj is self.search and event.key() in (Qt.Key.Key_Down,Qt.Key.Key_Up):self.list.setFocus();return True
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.choose();return True
            if obj is self.list and event.key()==Qt.Key.Key_Delete:self.remove();return True
        return super().eventFilter(obj,event)

    def closeEvent(self,event):event.ignore();self.dismiss()

    def stop(self):
        self.stopping=True
        if self.activation:self.activation.cancel()
        for process in (self.collector,*self.owners.copy()):
            if process:process.kill();process.waitForFinished(500)

def session_directory():
    runtime=os.environ.get('XDG_RUNTIME_DIR',''); signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')
    if not runtime or not signature or '/' in signature:raise RuntimeError('Clipboard history needs a Hyprland session.')
    path=Path(runtime)/'hypr'/signature
    if not (path/'.socket.sock').is_socket():raise RuntimeError('The Hyprland session has ended.')
    return path

def request(path,*,from_bar=False):
    connection=QLocalSocket(); connection.connectToServer(str(path))
    if not connection.waitForConnected(300):return False
    connection.write(b'bar\n' if from_bar else b'show\n');connection.waitForBytesWritten(300);connection.disconnectFromServer();return True

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');parser.add_argument('--show',action='store_true');parser.add_argument('--from-bar',action='store_true');args=parser.parse_args()
    directory=session_directory(); address=directory/'.clip.sock'
    app=QApplication([sys.argv[0]]);app.setApplicationName(APP_ID);app.setDesktopFileName(APP_ID);app.setQuitOnLastWindowClosed(False)
    if not args.serve:
        if not request(address,from_bar=args.from_bar):
            subprocess.Popen([sys.executable,__file__,'--serve','--show',*(['--from-bar'] if args.from_bar else [])],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,close_fds=True)
        return 0
    with (directory/'fusion-clipboard.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            if args.show:request(address,from_bar=args.from_bar)
            return 0
        collector=build()
        # Corrupt pins are not silently overwritten or deleted.
        try:store=Store(STATE/'pins.json')
        except (OSError,ValueError,KeyError,TypeError):
            store=Store(STATE/'pins.json',load=False);store.pins_unavailable=True
        theme_runtime.install(app)
        window=History(store,collector); server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(str(address))
        if not server.listen(str(address)):raise RuntimeError('Cannot start clipboard history.')
        connections=set()
        def connected():
            while server.hasPendingConnections():
                peer=server.nextPendingConnection();connections.add(peer)
                def read(peer=peer):
                    if peer.canReadLine():
                        command=bytes(peer.readLine(32)).strip()
                        if command in (b'show',b'bar'):window.reveal(from_bar=command==b'bar')
                        peer.disconnectFromServer()
                peer.readyRead.connect(read);peer.disconnected.connect(lambda peer=peer:(connections.discard(peer),peer.deleteLater()));read()
        server.newConnection.connect(connected)
        # Socket EOF, including a compositor crash, ends capture and its owners.
        session=QLocalSocket();session.connectToServer(str(directory/'.socket2.sock'))
        session.disconnected.connect(app.quit);session.errorOccurred.connect(lambda *_:app.quit());session.readyRead.connect(lambda:window.compositor_events(session))
        timer=QTimer();timer.timeout.connect(lambda:None);timer.start(500)
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,lambda *_:app.quit())
        app.aboutToQuit.connect(window.stop)
        if args.show:QTimer.singleShot(0,lambda:window.reveal(from_bar=args.from_bar))
        return app.exec()

if __name__=='__main__':sys.exit(main())
