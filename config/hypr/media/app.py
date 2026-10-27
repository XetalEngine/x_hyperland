#!/usr/bin/env python3
"""Small, session-owned MP3/MP4 downloader with a bounded live log."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QProcess, QSocketNotifier
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut, QTextCursor
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QPlainTextEdit, QProgressBar, QMessageBox, QSizeGrip)
import backend

sys.path.insert(0, str(backend.ROOT/'theme'))
import runtime
from window_chrome import close_button

STYLE = '''
QWidget {background:#171c24; color:#e3ecf8; font-family:"Noto Sans"; font-size:13px;}
QLabel {background:transparent;}
QLabel#eyebrow {color:#69d8ce; font-size:10px; letter-spacing:3px;}
QLabel#title {font-size:24px; font-weight:700;}
QLabel#muted {color:#91a6bf; font-size:12px;}
QLabel#status {color:#88e0d5;}
QLineEdit {background:#0e1722; border:1px solid #384f66; border-radius:8px; padding:11px; selection-background-color:#32616b;}
QLineEdit:focus {border-color:#73d8cf;}
QPushButton {background:#253342; border:1px solid #3b5063; border-radius:7px; padding:8px 14px;}
QPushButton:hover {background:#324a59; border-color:#6ccfc5;}
QPushButton:disabled {color:#708398; background:#202a35; border-color:#303e4c;}
QPushButton#format {text-align:left; padding:15px; background:#1c2938; font-size:15px;}
QPushButton#format:checked {background:#234a53; border:1px solid #72d8c9; color:#d9fff4;}
QPushButton#primary {background:#28696d; border:1px solid #6dc6bb; font-weight:700;}
QPushButton#primary:hover {background:#347f80;}
QPushButton#primary:disabled {background:#243f45; border-color:#36555e; color:#789299;}
QPlainTextEdit {background:#0c141f; border:1px solid #304457; border-radius:8px; padding:8px; font-family:"DejaVu Sans Mono"; font-size:11px; selection-background-color:#32616b;}
QProgressBar {background:#283744; border:none; border-radius:3px; min-height:6px; max-height:6px;}
QProgressBar::chunk {background:#6cd8c8; border-radius:3px;}
QScrollBar:vertical {background:#101923; width:9px;}
QScrollBar::handle:vertical {background:#456072; border-radius:4px; min-height:22px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QToolTip {background:#1c2a37; color:#eef7ff; border:1px solid #537185;}
'''


def button(text, callback, name=None):
    item = QPushButton(text); item.clicked.connect(callback)
    if name: item.setObjectName(name)
    return item


def stop_process(process, force=False):
    if process.state() == QProcess.ProcessState.NotRunning:
        return
    pid = int(process.processId())
    if force:
        try:
            if pid > 1 and os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
    else:
        # worker.py forwards termination to its own yt-dlp/ffmpeg process group.
        process.terminate()


class Window(QWidget):
    def __init__(self, initial='', preview=False, state=backend.STATE, worker=None):
        super().__init__(); self.preview_mode=preview; self.state_dir=Path(state)
        self.worker=worker or backend.ROOT/'media/worker.py'
        self.kind='mp3'; self.busy=False; self.cancelled=False; self.succeeded=False
        self.close_pending=False; self.shutting_down=False; self.last_file=None; self.pending_url=''
        self.buffer=b''; self.info_buffer=b''; self.action=''
        self.setWindowTitle('Xetal Media'); self.setMinimumSize(530,490); self.resize(640,620)
        try:
            preferences=json.loads((self.state_dir/'window.json').read_text())
            self.kind=preferences['format'] if preferences['format'] in backend.FORMATS else 'mp3'
            self.resize(max(530,min(1000,int(preferences['width']))),max(490,min(850,int(preferences['height']))))
        except (OSError,ValueError,KeyError,TypeError): pass
        layout=QVBoxLayout(self); layout.setContentsMargins(22,18,22,14); layout.setSpacing(8)
        header=QHBoxLayout(); titles=QVBoxLayout(); titles.setSpacing(3)
        eyebrow=QLabel('XETAL  /  MEDIA'); eyebrow.setObjectName('eyebrow'); titles.addWidget(eyebrow)
        title=QLabel('Media downloader'); title.setObjectName('title'); titles.addWidget(title)
        header.addLayout(titles,1); header.addWidget(close_button(self),0,Qt.AlignmentFlag.AlignTop); layout.addLayout(header)
        hint=QLabel('A YouTube link. Your music or video. Best available quality.'); hint.setObjectName('muted'); layout.addWidget(hint)
        url_row=QHBoxLayout(); self.url=QLineEdit(initial); self.url.setMaxLength(8192)
        self.url.setPlaceholderText('Paste or type a YouTube address…'); self.url.setAccessibleName('YouTube address')
        self.url.returnPressed.connect(self.download); self.url.textChanged.connect(self.update_buttons)
        url_row.addWidget(self.url,1); self.paste=button('Paste',self.paste_url); url_row.addWidget(self.paste); layout.addLayout(url_row)
        formats=QHBoxLayout(); self.formats={}
        for kind,caption,icon_name in [('mp3','MP3  ·  Music','audio-x-generic'),('mp4','MP4  ·  Video','video-x-generic')]:
            control=button(caption,lambda checked=False,k=kind:self.choose(k),'format'); control.setCheckable(True)
            control.setIcon(QIcon.fromTheme(icon_name)); formats.addWidget(control,1); self.formats[kind]=control
        layout.addLayout(formats)
        self.quality=QLabel(); self.quality.setObjectName('muted'); layout.addWidget(self.quality)
        destination_row=QHBoxLayout(); self.destination_label=QLabel(); self.destination_label.setObjectName('muted')
        self.destination_label.setWordWrap(True); destination_row.addWidget(self.destination_label,1)
        self.folder_button=button('Open folder',self.open_folder); destination_row.addWidget(self.folder_button); layout.addLayout(destination_row)
        self.status=QLabel('Selected text captured.' if initial else 'Ready when you are.'); self.status.setObjectName('status')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.progress=QProgressBar(); self.progress.setTextVisible(False); self.progress.setRange(0,100); self.progress.setValue(0); layout.addWidget(self.progress)
        log_row=QHBoxLayout(); label=QLabel('DOWNLOAD LOG'); label.setObjectName('eyebrow'); log_row.addWidget(label); log_row.addStretch()
        copy_button=button('Copy log',self.copy_log); copy_button.setStyleSheet('padding:4px 12px;'); log_row.addWidget(copy_button); layout.addLayout(log_row)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(400)
        self.log.setMinimumHeight(86); self.log.setPlaceholderText('Download progress and messages appear here.'); layout.addWidget(self.log,1)
        engine_row=QHBoxLayout(); self.engine=QLabel('yt-dlp'); self.engine.setObjectName('muted'); engine_row.addWidget(self.engine,1)
        self.update_button=button('Update yt-dlp',self.update_engine)
        self.update_button.setToolTip('Install the latest official yt-dlp for this popup. The system package is managed separately.')
        engine_row.addWidget(self.update_button); layout.addLayout(engine_row)
        bottom=QHBoxLayout(); self.open_button=button('Open file',self.open_file); self.open_button.setEnabled(False); bottom.addWidget(self.open_button)
        bottom.addStretch(); self.cancel_button=button('Cancel',self.cancel); self.cancel_button.setEnabled(False); bottom.addWidget(self.cancel_button)
        self.download_button=button('Download MP3',self.download,'primary'); bottom.addWidget(self.download_button); bottom.addWidget(QSizeGrip(self)); layout.addLayout(bottom)
        self.process=QProcess(self); self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output); self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.info=QProcess(self); self.info.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.info.readyReadStandardOutput.connect(self.read_info)
        self.info.finished.connect(self.read_info)
        self.cancel_timer=QTimer(self); self.cancel_timer.setSingleShot(True); self.cancel_timer.setInterval(1800)
        self.cancel_timer.timeout.connect(lambda:stop_process(self.process,True))
        self.choose(self.kind); QShortcut(QKeySequence('Escape'),self,activated=self.close)
        self.setMinimumHeight(layout.minimumSize().height())
        self.resize(self.width(),max(self.height(),self.minimumHeight()))
        self.url.setFocus()
        if not preview: QTimer.singleShot(0,self.refresh_version)

    def append(self,text):
        if text: self.log.appendPlainText(str(text)[:16384])

    def choose(self,kind):
        if self.busy:return
        self.kind=kind; self.folder=backend.destination(kind)
        for name,widget in self.formats.items(): widget.setChecked(name==kind)
        self.quality.setText('Best source audio · highest-quality MP3 encoding' if kind=='mp3' else 'Best video + audio · no resolution cap · MP4 without video re-encoding')
        self.destination_label.setText('Save to '+str(self.folder)); self.download_button.setText('Download '+kind.upper()); self.update_buttons()

    def update_buttons(self,*_):
        if not hasattr(self,'download_button'):return
        self.download_button.setEnabled(not self.busy and bool(self.url.text().strip()))
        self.update_button.setEnabled(not self.busy); self.paste.setEnabled(not self.busy); self.url.setEnabled(not self.busy)
        for control in self.formats.values():control.setEnabled(not self.busy)
        self.cancel_button.setEnabled(self.busy and not self.cancelled)

    def paste_url(self):
        text=QApplication.clipboard().text()
        self.url.setText(backend.selected_url(text) or text.strip()[:8192]); self.url.setFocus()
        self.status.setText('Link pasted. Choose MP3 or MP4, then Download.')

    def present(self,url=''):
        if url:
            if self.busy:self.pending_url=url; self.append('Selected link saved for your next download.')
            else:self.url.setText(url); self.status.setText('Selected text captured.')
        self.show(); self.raise_(); self.activateWindow()

    def refresh_version(self):
        if self.preview_mode or self.info.state()!=QProcess.ProcessState.NotRunning:return
        self.info_buffer=b''; self.info.start(sys.executable,[str(self.worker),'info'])

    def read_info(self,*_):
        self.info_buffer+=bytes(self.info.readAllStandardOutput())
        while b'\n' in self.info_buffer:
            line,self.info_buffer=self.info_buffer.split(b'\n',1)
            try:
                event=json.loads(line)
                if event.get('type')=='version':self.engine.setText('yt-dlp '+event['text']+' · '+event['source'])
                elif event.get('type')=='error':self.engine.setText('yt-dlp unavailable · use Update')
            except ValueError:pass

    def start_job(self,action,args=()):
        if self.busy:return
        self.busy=True; self.action=action; self.cancelled=False; self.succeeded=False; self.buffer=b''
        self.log.clear(); self.progress.setRange(0,0); self.update_buttons()
        self.process.start(sys.executable,[str(self.worker),action,*args])

    def download(self):
        if self.busy:return
        try:url=backend.youtube_url(self.url.text())
        except ValueError as error:self.status.setText(str(error)); self.url.setFocus(); return
        self.url.setText(url); self.last_file=None; self.open_button.setEnabled(False)
        self.status.setText('Finding the best available '+self.kind.upper()+' source…')
        self.start_job('download',['--format',self.kind,'--url',url])

    def update_engine(self):
        if self.busy:return
        self.status.setText('Updating this popup’s yt-dlp…'); self.start_job('update')

    def read_output(self):
        self.buffer+=bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:self.handle_event(json.loads(line))
            except (ValueError,KeyError,TypeError):self.append(line.decode('utf-8','replace'))
        if len(self.buffer)>65536:self.append(self.buffer[:65536].decode('utf-8','replace'));self.buffer=b''

    def handle_event(self,event):
        kind=event['type']; text=str(event.get('text',''))
        if kind=='progress':
            percent=event.get('percent')
            self.progress.setRange(0,100 if percent is not None else 0)
            if percent is not None:self.progress.setValue(int(percent))
            self.status.setText(text)
        elif kind=='title':self.append('Downloading: '+text)
        elif kind=='file':self.append('File: '+text)
        elif kind=='success':
            self.succeeded=True; self.status.setText(text); self.append(text)
            self.progress.setRange(0,100); self.progress.setValue(100)
            if event.get('file'):self.last_file=Path(event['file']);self.open_button.setEnabled(self.last_file.is_file())
        else:
            self.append(text)
            if kind=='error':self.status.setText(text)
            elif text.startswith(('[Merger]','[ExtractAudio]','[VideoRemuxer]','[Metadata]')):
                self.status.setText('Finishing '+self.kind.upper()+'…');self.progress.setRange(0,0)

    def process_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:
            self.append(self.process.errorString());self.finished(-1)

    def finished(self,code,*_):
        self.read_output();self.cancel_timer.stop();self.busy=False;self.progress.setRange(0,100)
        if self.cancelled:
            self.status.setText('Cancelled. You can retry the download to resume partial files.');self.append('Cancelled by you.')
        elif not self.succeeded:
            self.status.setText('Could not finish. Check the log below.');self.append('Worker exited with status '+str(code)+'.')
        if self.action=='update':self.refresh_version()
        if self.pending_url:self.url.setText(self.pending_url);self.pending_url='';self.append('Your next selected link is ready.')
        self.update_buttons()
        if self.close_pending:self.close()

    def cancel(self):
        if not self.busy:return
        self.cancelled=True;self.status.setText('Stopping…');self.update_buttons();stop_process(self.process);self.cancel_timer.start()

    def copy_log(self):QApplication.clipboard().setText(self.log.toPlainText())

    def open_folder(self):
        folder=self.folder
        folder.mkdir(parents=True,exist_ok=True)
        subprocess.Popen([str(backend.ROOT/'scripts/dolphin.sh'),str(folder)],start_new_session=True)

    def open_file(self):
        if self.last_file and self.last_file.is_file():subprocess.Popen(['xdg-open',str(self.last_file)],start_new_session=True)

    def shutdown(self):
        self.shutting_down=True
        for process in (self.process,self.info):
            stop_process(process)
            if not process.waitForFinished(1200):stop_process(process,True);process.waitForFinished(500)

    def closeEvent(self,event):
        if self.busy and not self.shutting_down:
            if self.close_pending or QMessageBox.question(self,'Stop and close?', 'Stop the current job and close this window?',
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Yes:
                self.close_pending=True;self.cancel()
            event.ignore();return
        if not self.preview_mode:
            self.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
            temporary=self.state_dir/'window.json.tmp'
            temporary.write_text(json.dumps({'format':self.kind,'width':self.width(),'height':self.height()}))
            temporary.chmod(0o600);temporary.replace(self.state_dir/'window.json')
        self.shutdown();event.accept()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and event.position().y()<78 and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(event)


def send(address,request):
    connection=QLocalSocket();connection.connectToServer(address)
    if not connection.waitForConnected(300):return False
    connection.write(json.dumps(request).encode()+b'\n');connection.waitForBytesWritten(500);connection.disconnectFromServer();return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='');parser.add_argument('--no-selection',action='store_true');parser.add_argument('--preview')
    args=parser.parse_args()
    # Read PRIMARY before creating a window, so the previously focused app still owns it.
    initial=backend.prefill(args.url) if args.url else ('' if args.no_selection or args.preview else backend.primary_selection())
    app=QApplication(sys.argv[:1]);app.setApplicationName('xetal-media');app.setDesktopFileName('xetal-media');runtime.install(app,STYLE)
    if args.preview:
        window=Window(initial,preview=True);window.show()
        QTimer.singleShot(150,lambda:(window.grab().save(args.preview),app.quit()));return app.exec()
    signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE');runtime_dir=os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not runtime_dir:return 1
    instance=Path(runtime_dir)/'hypr'/signature;address=str(instance/'media-popup.sock')
    with (instance/'media-popup.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            for _ in range(10):
                if send(address,{'url':initial}):return 0
                time.sleep(.05)
            return 1
        QLocalServer.removeServer(address);server=QLocalServer()
        if not server.listen(address):raise RuntimeError(server.errorString())
        window=Window(initial)
        def incoming():
            connection=server.nextPendingConnection();connection.pending=b''
            def receive():
                connection.pending+=bytes(connection.readAll())
                if len(connection.pending)>16384:connection.disconnectFromServer();return
                if b'\n' not in connection.pending:return
                try:window.present(backend.prefill(str(json.loads(connection.pending)['url'])))
                except (ValueError,KeyError,TypeError):connection.disconnectFromServer();return
                subprocess.Popen(['hyprctl','dispatch','focuswindow','class:^(xetal-media)$'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                connection.disconnectFromServer()
            connection.readyRead.connect(receive);connection.disconnected.connect(connection.deleteLater)
            if connection.bytesAvailable():receive()
        server.newConnection.connect(incoming)
        session=socket.socket(socket.AF_UNIX);session.connect(str(instance/'.socket2.sock'));session.setblocking(False)
        notifier=QSocketNotifier(session.fileno(),QSocketNotifier.Type.Read)
        def alive(*_):
            try:
                if session.recv(65536):return
            except BlockingIOError:return
            except OSError:pass
            notifier.setEnabled(False);window.shutdown();app.quit()
        notifier.activated.connect(alive);app.aboutToQuit.connect(window.shutdown)
        window.present(initial)
        try:return app.exec()
        finally:notifier.setEnabled(False);session.close();server.close()


if __name__=='__main__':raise SystemExit(main())
