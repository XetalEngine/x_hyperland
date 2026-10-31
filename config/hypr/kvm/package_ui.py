"""Component inventory embedded in the existing Paths & Tools page."""
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer,QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QGroupBox,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QWidget,
                             QTableWidget,QTableWidgetItem,QHeaderView,QProgressBar,QMessageBox)
import packages
import portable


class Job(QThread):
    done=pyqtSignal(object)
    failed=pyqtSignal(str)
    # A prepared kernel source package can exceed Qt's signed 32-bit int.
    progress=pyqtSignal(object,object)
    def __init__(self,work,parent):
        super().__init__(parent);self.work=work
    def run(self):
        try:self.done.emit(self.work(self.progress.emit))
        except Exception as error:self.failed.emit(str(error))


class PackagesPanel(QGroupBox):
    changed=pyqtSignal()
    inventory_changed=pyqtSignal()
    active=pyqtSignal(bool)
    message=pyqtSignal(str)
    def __init__(self,busy,parent=None):
        super().__init__('KVM components',parent)
        self.busy=busy;self.store=packages.Store();self.release=None;self.job=None
        layout=QVBoxLayout(self);bar=QHBoxLayout()
        self.info=QLabel('Installed components and available downloads');self.info.setWordWrap(True)
        bar.addWidget(self.info,1)
        self.missing=QPushButton('Install / download missing')
        self.missing.clicked.connect(self.download_missing);bar.addWidget(self.missing)
        folders=QPushButton('Open components');folders.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(portable.data_root()/'components'))));bar.addWidget(folders)
        self.check=QPushButton('Check for updates');self.check.clicked.connect(self.check_updates);bar.addWidget(self.check)
        layout.addLayout(bar)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Component','Installed','Available','Status',''])
        self.table.setObjectName('kvmComponents')
        # Theme cell padding must not crop embedded action buttons.
        self.table.setStyleSheet('QTableWidget#kvmComponents::item {padding:0 8px;}')
        self.table.verticalHeader().hide();self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        for n in (1,2): self.table.horizontalHeader().setSectionResizeMode(n,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4,144)
        layout.addWidget(self.table)
        self.progress=QProgressBar();self.progress.hide();layout.addWidget(self.progress)
        note=QLabel('Downloads are compressed and verified before installation. Your disks, NVRAM and TPM state stay in your private workspace.')
        note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note)
        try:
            self.release=self.store.cached()
            if (portable.ROOT/'catalog.json').is_file():
                catalog=packages.decode((portable.ROOT/'catalog.json').read_bytes())
                if self.release is None or packages.version(catalog['version'])>packages.version(self.release['version']):
                    self.release=catalog
        except Exception as error:self.info.setText(str(error))
        self.refresh()

    def refresh(self):
        entries=(self.release or {}).get('components',{})
        self.missing.setEnabled(not self.job and any(not packages.installed(n) and not packages.compatibility(n,e) for n,e in entries.items()))
        self.table.setRowCount(len(entries))
        for row,(name,entry) in enumerate(entries.items()):
            current=packages.installed(name);reason=packages.compatibility(name,entry)
            same=current.get('sha256')==entry['sha256']
            newer=bool(current) and packages.version(current['version'])>packages.version(entry['version'])
            update=packages.update_available(name,entry,current)
            conflict=bool(current) and not same and current['version']==entry['version']
            status=reason or ('Current' if same else 'Newer local version' if newer else
                             'Version conflict' if conflict else 'UPDATE AVAILABLE' if update else 'Ready to download')
            for col,text in enumerate((entry['label'],current.get('version','—'),entry['version'],status)):
                item=QTableWidgetItem(text)
                item.setToolTip(text+(f'\n{entry["size"]/1024**2:.1f} MiB download · {entry["unpacked_size"]/1024**2:.1f} MiB installed' if col==2 else ''))
                self.table.setItem(row,col,item)
            button=QPushButton('Installed' if same or newer else 'Update' if current else 'Download')
            button.setFixedHeight(30)
            button.setStyleSheet('padding: 0 10px; margin: 0; min-height: 0;')
            button.setEnabled(not self.job and (update or not current and not reason))
            if conflict:
                button.setToolTip('This version has different files than the installed component. A newer version is required.')
            button.clicked.connect(lambda _,n=name,e=entry:self.download(n,e))
            cell=QWidget();buttons=QHBoxLayout(cell);buttons.setContentsMargins(6,4,6,4);buttons.addWidget(button)
            self.table.setCellWidget(row,4,cell);self.table.setRowHeight(row,44)
        self.table.setFixedHeight(self.table.horizontalHeader().height()+44*len(entries)+4)
        self.table.setVisible(bool(entries))
        self.inventory_changed.emit()

    def update_messages(self):
        # The release is already signature-verified. Health refreshes read only
        # local metadata, so an external install also clears its notification.
        messages=[]
        for name,entry in (self.release or {}).get('components',{}).items():
            current=packages.installed(name)
            if packages.update_available(name,entry,current):
                messages.append(f'{entry["label"]} update available: {current["version"]} → {entry["version"]}.')
        return messages

    def run(self,work,finished,failed=None):
        if self.job:return
        self.check.setEnabled(False);self.progress.show();self.progress.setRange(0,0)
        self.active.emit(True)
        job=Job(work,self);self.job=job
        job.progress.connect(lambda value,total:self._progress(value,total))
        job.done.connect(finished);job.failed.connect(failed or (lambda error:self.info.setText(error)))
        def release():
            self.job=None;self.check.setEnabled(True);self.progress.hide();self.refresh();job.deleteLater();self.active.emit(False)
        job.finished.connect(release);self.refresh();job.start()

    def _progress(self,value,total):
        self.progress.setRange(0,1000);self.progress.setValue(int(value*1000/max(1,total)))

    def check_updates(self):
        self.info.setText('Checking the signed release feed…')
        def done(release):
            self.release=release;self.info.setText('Release '+release['version']+' · Choose the components to update.');self.refresh()
        self.run(lambda progress:self.store.check(),done)

    def download(self,name,entry):
        if self.busy():
            QMessageBox.information(self,'VM is running','Shut down the VM before replacing its components.');return
        self.info.setText('Downloading '+entry['label']+'…')
        def done(changed):
            portable.prepare_firmware()
            portable.prepare_tpm_workspace()
            self.info.setText(entry['label']+' installed.');self.changed.emit()
        self.run(lambda progress:self.store.download(name,entry,progress),done)

    def download_missing(self):
        if self.job or self.busy():
            self.info.setText('Finish the running VM or component operation first.');return
        entries=[(n,e) for n,e in (self.release or {}).get('components',{}).items()
                 if not packages.installed(n) and not packages.compatibility(n,e)]
        self.info.setText('Installing missing components…')
        def work(progress):
            changed=[]
            for name,entry in entries:
                self.store.download(name,entry,progress)
                changed.append(name)
            return changed
        def done(changed):
            portable.prepare_firmware();portable.prepare_tpm_workspace()
            self.info.setText('Missing components installed. Continue with Next.');self.changed.emit()
        self.run(work,done)

    def bootstrap(self):
        # Opening settings checks metadata only. Downloads are explicit and all
        # runtime programs and supporting binary assets come from the server.
        if not self.busy():
            portable.prepare_firmware();portable.prepare_tpm_workspace()
            self.changed.emit()
        # Reading release metadata is safe while a guest is running, too.
        self.check_updates()
