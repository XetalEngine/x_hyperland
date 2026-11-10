"""Native Fusion archive dialogs and the shared animated job surface."""
from pathlib import Path
import json
import os
import sqlite3
import tempfile
import time

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableView, QTabWidget, QVBoxLayout, QWidget)

from engine import FORMATS, LEVELS, ArchiveError
from tasks import Task
from file_jobs.model import Job, amount
from file_jobs.window import ProgressWindow
from progress import RemoteProgress


def plain(text):
    label = QLabel(text); label.setWordWrap(True); label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class CompressDialog(QDialog):
    def __init__(self, sources, directory, output=None, parent=None):
        super().__init__(parent)
        self.sources = sources
        self.setWindowTitle('7-Zip · Compress files'); self.resize(720, 570)
        layout = QVBoxLayout(self); layout.setContentsMargins(22,22,22,22); layout.setSpacing(12)
        title = plain('Create an archive'); title.setObjectName('settingsHeading'); layout.addWidget(title)
        layout.addWidget(plain(f'{len(sources):,} selected item(s) · Original files are kept'))
        tabs = QTabWidget(); layout.addWidget(tabs,1)
        general = QWidget(); form = QFormLayout(general); form.setSpacing(12); form.setContentsMargins(16,18,16,18)
        tabs.addTab(general,'Archive')
        advanced = QWidget(); compression = QFormLayout(advanced); compression.setSpacing(12); compression.setContentsMargins(16,18,16,18)
        tabs.addTab(advanced,'Compression')
        row = QHBoxLayout(); self.path = QLineEdit(str(output or Path(directory)/(Path(sources[0]).name+'.7z')))
        self.path.setClearButtonEnabled(True); row.addWidget(self.path)
        browse = QPushButton('Browse…'); row.addWidget(browse); form.addRow('Archive',row)
        browse.clicked.connect(self.browse)
        self.format = QComboBox(); self.format.addItems(list(FORMATS)); form.addRow('Format',self.format)
        self.method = QComboBox(); compression.addRow('Compression method', self.method)
        self.level = QComboBox()
        for name, value in LEVELS.items(): self.level.addItem(name, value)
        self.level.setCurrentText('Normal'); compression.addRow('Compression level',self.level)
        self.threads = QSpinBox(); self.threads.setRange(1, max(1, os.cpu_count() or 1)); self.threads.setValue(self.threads.maximum())
        self.threads.setToolTip('Defaults to all logical CPU threads detected on this computer.')
        compression.addRow('CPU threads',self.threads)
        self.dictionary = QLineEdit(); self.dictionary.setPlaceholderText('Automatic · or enter 64m, 256m…')
        compression.addRow('Dictionary size',self.dictionary)
        self.solid = QCheckBox('Solid archive · better compression for related files'); self.solid.setChecked(True)
        compression.addRow('',self.solid)
        self.links = QCheckBox('Preserve symbolic links'); self.links.setChecked(True); compression.addRow('',self.links)
        self.volume = QComboBox(); self.volume.setEditable(True)
        self.volume.addItems(['','100m','700m','4g']); self.volume.lineEdit().setPlaceholderText('One file · or enter a split volume size')
        form.addRow('Split into volumes',self.volume)
        group = QGroupBox('Password protection'); password_form = QFormLayout(group)
        self.encrypt = QCheckBox('Encrypt this archive'); password_form.addRow(self.encrypt)
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm = QLineEdit(); self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        password_form.addRow('Password',self.password); password_form.addRow('Confirm password',self.confirm)
        self.encryption = QComboBox(); self.encryption.addItems(['AES-256','ZipCrypto'])
        password_form.addRow('Encryption',self.encryption)
        self.names = QCheckBox('Encrypt file names'); self.names.setChecked(True); password_form.addRow(self.names)
        self.show_password = QCheckBox('Show password'); password_form.addRow(self.show_password)
        self.show_password.toggled.connect(lambda on: [edit.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password) for edit in (self.password,self.confirm)])
        tabs.addTab(group,'Encryption')
        self.hint = plain(''); layout.addWidget(self.hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Create archive')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.previous_format = '7z'
        self.format.currentTextChanged.connect(self.changed)
        self.method.currentTextChanged.connect(self.controls)
        self.encrypt.toggled.connect(self.controls)
        self.changed('7z')
        if output:
            for kind in sorted(FORMATS,key=len,reverse=True):
                if str(output).lower().endswith('.'+kind):
                    self.format.setCurrentText(kind);break
        self.path.setFocus(); self.path.selectAll()

    def browse(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save archive', self.path.text(), 'Archives (*)',
            options=QFileDialog.Option.DontConfirmOverwrite)
        if path: self.path.setText(path)

    def changed(self, kind):
        path = self.path.text()
        if path.lower().endswith('.'+self.previous_format): self.path.setText(path[:-len(self.previous_format)]+kind)
        self.previous_format = kind
        self.method.blockSignals(True); self.method.clear(); self.method.addItems(FORMATS[kind][1]); self.method.blockSignals(False)
        self.controls()

    def controls(self):
        kind = self.format.currentText(); encrypted = kind in ('7z','zip')
        self.encrypt.setEnabled(encrypted)
        active = encrypted and self.encrypt.isChecked()
        for widget in (self.password,self.confirm,self.show_password): widget.setEnabled(active)
        self.encryption.setEnabled(active and kind == 'zip'); self.names.setEnabled(active and kind == '7z')
        self.solid.setEnabled(kind == '7z')
        self.dictionary.setEnabled(self.method.currentText() in ('LZMA2','LZMA','PPMd'))
        self.level.setEnabled(kind not in ('tar','wim')); self.threads.setEnabled(kind not in ('tar','wim'))
        self.hint.setText('This stream format accepts one file. Use tar.'+kind+' for folders.' if kind in ('gz','xz','bz2') else
                         'The archive is tested before it is saved. Existing destination files require your choice.')

    def request(self):
        options = dict(format=self.format.currentText(), method=self.method.currentText(), level=self.level.currentData(),
            threads=self.threads.value(), dictionary=self.dictionary.text().strip() if self.dictionary.isEnabled() else '',
            solid=self.solid.isChecked(), symlinks=self.links.isChecked(), volume=self.volume.currentText().strip(),
            encrypt_names=self.names.isChecked(), encryption=self.encryption.currentText().replace('-',''))
        request = dict(operation='compress', sources=self.sources, output=os.path.abspath(os.path.expanduser(self.path.text().strip())), options=options)
        if self.encrypt.isEnabled() and self.encrypt.isChecked(): request['password'] = self.password.text()
        return request

    def accept(self):
        if not self.path.text().strip(): QMessageBox.warning(self,'Choose an archive','Enter an archive file name.'); return
        if self.encrypt.isEnabled() and self.encrypt.isChecked():
            if not self.password.text() or self.password.text() != self.confirm.text():
                QMessageBox.warning(self,'Check the password','Enter a nonempty password and matching confirmation.'); return
        from engine import format_arguments
        try:
            request = self.request(); options = dict(request['options'])
            if 'password' in request: options['password'] = request['password']
            format_arguments(options)
        except (ArchiveError, ValueError) as error:
            QMessageBox.warning(self,'Check archive settings',str(error)); return
        super().accept()


class ExtractDialog(QDialog):
    def __init__(self, sources, directory, parent=None):
        super().__init__(parent); self.sources = sources
        self.setWindowTitle('7-Zip · Extract archives'); self.resize(600, 260)
        layout = QVBoxLayout(self); layout.setContentsMargins(22,22,22,22); layout.setSpacing(12)
        label = plain('Extract files'); label.setObjectName('settingsHeading'); layout.addWidget(label)
        row = QHBoxLayout(); self.path = QLineEdit(str(directory)); row.addWidget(self.path)
        browse = QPushButton('Browse…'); row.addWidget(browse); layout.addLayout(row)
        browse.clicked.connect(self.browse)
        self.separate = QCheckBox('Create a separate folder for each archive'); self.separate.setChecked(True); layout.addWidget(self.separate)
        layout.addWidget(plain('Existing files are handled in the transfer window. Passwords are requested when needed.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Extract'); layout.addWidget(buttons)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self,'Extract to',self.path.text())
        if path: self.path.setText(path)

    def request(self): return dict(operation='extract',sources=self.sources,destination=os.path.abspath(os.path.expanduser(self.path.text())),separate=self.separate.isChecked())


class ArchiveJob(Job):
    def __init__(self, request, parent=None):
        self.operation = request['operation']
        titles = dict(compress='Compressing files',extract='Extracting files',test='Testing archives',add='Updating archive',delete='Updating archive',rename='Updating archive',list='Reading archive')
        super().__init__('/archive', '', '7-Zip · Fusion', 3, dict(title=titles[self.operation], immediate=True,
            operation=self.operation,
            descriptionValue1=request['sources'][0],descriptionValue2=request.get('output') or request.get('destination','')), parent)

    def file_summary(self):
        files = self.data.get('processedFiles',0)
        verb = 'tested' if self.operation == 'test' else 'extracted' if self.operation == 'extract' else 'processed'
        total = self.data.get('totalFiles',0)
        return f'{files:,} / {total:,} items {verb}' if total else f'{files:,} items {verb}' if files else ''

    def activity(self):
        if self.result == 'done': return 'Archive operation finished'
        if self.result == 'canceled': return 'Canceled · Original archives kept'
        if self.result == 'failed': return 'Archive operation stopped'
        return super().activity()


class JobController(QObject):
    completed = pyqtSignal(dict)
    closed = pyqtSignal()

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.task = Task(request,self)
        self.job = ArchiveJob(request,self)
        self.window = None
        self.completion_timer=QTimer(self);self.completion_timer.setSingleShot(True)
        self.completion_timer.timeout.connect(self.closed.emit)
        self.remote = RemoteProgress(self.job,self)
        self.remote.ready.connect(self.view_ready)
        self.remote.lost.connect(self.local_window)
        self.job.requested.connect(lambda action: self.task.command({'command':{'suspend':'pause'}.get(action,action)}))
        self.job.queue_decision.connect(lambda decision: self.task.command(dict(decision,command='issue_answer')))
        self.task.message.connect(self.receive); self.task.outcome.connect(self.finish)
        self.started = time.monotonic(); self.last_bytes = 0; self.last_time = self.started
        self.journal = ''
        self.task.finished.connect(self.worker_finished)
        self.task.start()

    def local_window(self):
        if self.window is None:
            self.window=ProgressWindow(self.job);self.window.setWindowTitle('7-Zip · Fusion archive operation')
            self.window.dismissed.connect(self.closed.emit);self.window.show()
            if self.job.result is not None:self.window.completed()

    def view_ready(self,available):
        if not available:self.local_window()
        elif not self.task.isRunning() and self.job.result is not None:self.completion_timer.start(100)

    def worker_finished(self):
        if self.remote.validated:self.completion_timer.start(100)

    def receive(self, value):
        kind = value['event']
        if kind == 'progress':
            total = value.get('total', 0); done = value.get('completed', 0)
            known = total < 2**64-1
            now = time.monotonic(); elapsed = now-self.last_time
            speed = max(0,int((done-self.last_bytes)/elapsed)) if elapsed else 0
            self.last_bytes = done; self.last_time = now
            data = dict(phase=value.get('phase',''), currentFile=value.get('path',''), totalBytes=total if known else 0,
                        processedBytes=done, processedFiles=value.get('files',0), totalsKnown=known, speed=speed)
            if known: data['percent'] = min(99, done*100//total) if total else 0
            self.job.update(data)
        elif kind == 'transfer_progress':
            self.job.update(value)
            access = value.get('administratorAccess','')
            text = ('Waiting for administrator authorization…' if access == 'authorizing' else
                    'Administrator access is active for this archive job. No further password is needed for this session.' if access == 'authorized' else
                    'Administrator access was not granted. '+value.get('administratorError','') if access == 'failed' else '')
            self.job.update_queue({'state':dict(access=access,accessText=text,
                hintText='Completed files are kept. Retry or skip only affects the selected items.')})
        elif kind == 'phase':
            self.job.update(dict(phase=value['text'],currentFile='',totalsKnown=False))
        elif kind == 'paused': self.job.update(dict(suspended=value['value']))
        elif kind == 'transfer':
            self.journal=value['journal']
            self.job.update_queue({'state':dict(journal=self.journal,reportFile=str(self.task.report))})
        elif kind == 'password':
            caption = 'The password was not accepted. Try again:' if value.get('wrong') else 'Enter the archive password:'
            password, accepted = QInputDialog.getText(self.window,'7-Zip · Password',caption,QLineEdit.EchoMode.Password)
            self.task.command(dict(command='password',password=password if accepted else None))
        elif kind == 'issue':
            status = value['status']
            labels = dict(pending='Needs a choice',retry='Retry queued',working='Retrying…',authorizing='Authorizing…',skipped='Skipped · Original kept',resolved=value.get('resolution') or 'Completed successfully')
            row = dict(value, name=Path(value.get('source','')).name, statusText=labels.get(status,status),
                resultText='Completed after retry' if status == 'resolved' else value.get('detail',''))
            row['details'] = '\n'.join((row['statusText'],row['resultText'],'From: '+value.get('source',''),'To: '+value.get('destination',''),'Stage: '+value.get('stage','')))
            self.job.update_queue({'rows':[row], 'state':dict(heading='Items needing attention',journal=self.journal,
                reportFile=str(self.task.report),
                hintText=('Completed files are kept. Retry or skip only affects the selected items.' if self.journal else
                          'Archive retries rebuild the archive. Skipped inputs remain outside the archive.'),
                summary='Other files continue. Skipped items are included in the final report.')})
            pending = sum(r.get('status') in ('pending','retry','working','authorizing') for r in self.job.queue_rows.values())
            self.job.update(dict(issueCount=len(self.job.queue_rows),pendingIssues=pending))

    def finish(self, result):
        if not result.get('ok'):
            for row in list(self.job.queue_rows.values()):
                if row['status'] in ('pending','retry','working','authorizing'):
                    self.receive(dict(row,event='issue',status='canceled' if result.get('cancelled') else 'failed',
                        retry_allowed=False,replace_allowed=False))
        if not result.get('ok') and not result.get('cancelled'):
            self.receive(dict(event='issue',id=-2147483647,version=1,source=self.task.request['sources'][0],
                destination=self.task.request.get('output') or self.task.request.get('destination',''),
                stage=self.task.phase,category='archive:failed',status='failed',detail=result.get('error','Archive operation failed'),
                retry_allowed=False,replace_allowed=False))
        self.job.update_queue({'state':dict(done=True,summary='Archive operation finished. Review the results below.')})
        if result.get('notes'): self.job.update(dict(warningMessage='\n'.join(result['notes'])))
        if result.get('ok'): self.job.terminate()
        else: self.job.terminate(1 if result.get('cancelled') else 2,result.get('error',''))
        self.completed.emit(result)


class MemberModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent); self.db = None; self.query = ''; self.count = 0; self.cache = {}
        self.sort_column = 'id'; self.direction = 'ASC'

    def open(self, path):
        if self.db: self.db.close()
        self.db = sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
        self.filter('')

    def filter(self, text):
        self.beginResetModel(); self.query=text; self.cache.clear()
        self.count = self.db.execute('SELECT COUNT(*) FROM members WHERE instr(lower(path),lower(?))>0',(text,)).fetchone()[0] if self.db else 0
        self.endResetModel()

    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else self.count
    def columnCount(self,parent=QModelIndex()): return 0 if parent.isValid() else 5
    def entry(self,row):
        page = row//256
        if page not in self.cache:
            values = self.db.execute(f'SELECT data FROM members WHERE instr(lower(path),lower(?))>0 ORDER BY {self.sort_column} {self.direction} LIMIT 256 OFFSET ?',
                                     (self.query,page*256)).fetchall()
            if len(self.cache)>16: self.cache.clear()
            self.cache[page] = [json.loads(value[0]) for value in values]
        return self.cache[page][row%256]
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        item = self.entry(index.row())
        if role == Qt.ItemDataRole.ToolTipRole: return item['path']
        if role == Qt.ItemDataRole.DisplayRole:
            return (item['path'], 'Folder' if item['directory'] else amount(item['size']),
                    amount(item['packed']),item.get('method') or '', 'Yes' if item.get('encrypted') else '')[index.column()]
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ('Name / path','Size','Packed size','Method','Encrypted')[section]
    def sort(self,column,order=Qt.SortOrder.AscendingOrder):
        if column < 0: return
        self.sort_column = ('path','size','packed',"json_extract(data,'$.method')","json_extract(data,'$.encrypted')")[column]
        self.direction = 'DESC' if order == Qt.SortOrder.DescendingOrder else 'ASC'; self.filter(self.query)


class ArchiveBrowser(QWidget):
    launch = pyqtSignal(dict)
    def __init__(self, archive, parent=None):
        super().__init__(parent); self.archive = Path(archive); self.password=None; self.reader=None
        self.storage = tempfile.TemporaryDirectory(prefix='fusion-archive-browser-')
        self.setWindowTitle(self.archive.name+' · 7-Zip · Fusion'); self.resize(1000,680)
        layout = QVBoxLayout(self); layout.setContentsMargins(18,18,18,18); layout.setSpacing(10)
        heading = plain(self.archive.name); heading.setObjectName('settingsHeading'); layout.addWidget(heading)
        path = plain(str(self.archive)); path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); layout.addWidget(path)
        toolbar = QHBoxLayout(); layout.addLayout(toolbar)
        for text, callback in (('Extract…',self.extract),('Test archive',lambda:self.submit('test')),
                ('Add files…',self.add),('Add folder…',self.add_folder),('Delete selected',self.remove),('Rename…',self.rename),('Reload',self.reload)):
            button=QPushButton(text); button.clicked.connect(callback); toolbar.addWidget(button)
        self.search=QLineEdit(); self.search.setPlaceholderText('Search files and paths inside this archive…'); self.search.setClearButtonEnabled(True); layout.addWidget(self.search)
        self.model=MemberModel(self); self.table=QTableView(); self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True); self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide(); layout.addWidget(self.table,1)
        self.status=plain('Reading archive…'); layout.addWidget(self.status)
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(180)
        self.search.textChanged.connect(lambda:self.timer.start()); self.timer.timeout.connect(lambda:self.model.filter(self.search.text()))
        QShortcut(QKeySequence.StandardKey.Find,self,activated=self.search.setFocus)
        self.table.doubleClicked.connect(lambda:self.extract())
        QTimer.singleShot(0,self.reload)

    def selected(self): return [self.model.entry(i.row())['path'] for i in self.table.selectionModel().selectedRows()]
    def submit(self,operation,**extra): self.launch.emit(dict(operation=operation,sources=[str(self.archive)],password=self.password,**extra))
    def reload(self):
        if self.reader and self.reader.isRunning(): return
        database=Path(self.storage.name)/(str(time.time_ns())+'.sqlite')
        self.reader=Task(dict(operation='list',sources=[str(self.archive)],index=str(database),password=self.password),self)
        self.reader.message.connect(self.read_event)
        def finished(result):
            if result.get('ok'):
                self.model.open(database); self.status.setText(f'{self.model.count:,} entries · 7-Zip 26.06 · Select entries to extract only those files')
            else: self.status.setText(result.get('error','Canceled'))
        self.reader.outcome.connect(finished); self.reader.start()
    def read_event(self,event):
        if event['event']=='password':
            value, ok=QInputDialog.getText(self,'Archive password','Enter the archive password:',QLineEdit.EchoMode.Password)
            if ok: self.password=value
            self.reader.command(dict(command='password',password=value if ok else None))
    def extract(self):
        dialog=ExtractDialog([str(self.archive)],str(self.archive.parent),self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            request=dialog.request(); request['members']=self.selected(); request['password']=self.password; self.launch.emit(request)
    def add(self):
        files,_=QFileDialog.getOpenFileNames(self,'Add files to archive')
        if files:self.submit('add',add=files)
    def add_folder(self):
        directory=QFileDialog.getExistingDirectory(self,'Add folder to archive')
        if directory:self.submit('add',add=[directory])
    def remove(self):
        members=self.selected()
        if members and QMessageBox.question(self,'Delete archive entries?',f'Delete {len(members)} selected entries from this archive?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            self.submit('delete',members=members)
    def rename(self):
        members=self.selected()
        if len(members)!=1: QMessageBox.information(self,'Rename archive entry','Select one file or folder.'); return
        name,ok=QInputDialog.getText(self,'Rename archive entry','New name / path:',text=members[0])
        if ok and name and name!=members[0]:self.submit('rename',members=members,new_name=name)
    def closeEvent(self,event):
        if self.reader and self.reader.isRunning():
            self.reader.command({'command':'cancel'}); event.ignore(); self.reader.finished.connect(self.close); return
        if self.model.db:self.model.db.close();self.model.db=None
        self.password=None;self.storage.cleanup();super().closeEvent(event)
