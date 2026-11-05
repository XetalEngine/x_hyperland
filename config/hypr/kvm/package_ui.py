"""Component inventory embedded in the existing Paths & Tools page."""
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer,QUrl
from PyQt6.QtGui import QDesktopServices,QIcon
from PyQt6.QtWidgets import (QGroupBox,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QWidget,
                             QTableWidget,QTableWidgetItem,QHeaderView,QProgressBar,QMessageBox,
                             QDialog)
import packages
import portable
import editions
from echo_account import Account
from account_ui import LoginDialog
from edition_ui import EditionCards


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
        finally:self.work=None


class PackagesPanel(QGroupBox):
    changed=pyqtSignal()
    inventory_changed=pyqtSignal()
    active=pyqtSignal(bool)
    message=pyqtSignal(str)
    edition_changed=pyqtSignal(str)
    account_changed=pyqtSignal()
    def __init__(self,busy,parent=None,*,switch_edition=None):
        super().__init__('KVM components',parent)
        self.busy=busy;self.store=packages.Store();self.release=None;self.job=None;self.account=Account()
        self.switch_edition=switch_edition
        layout=QVBoxLayout(self)
        self.edition_cards=EditionCards(self)
        self.edition_buttons=self.edition_cards.buttons
        self.edition_cards.requested.connect(self.choose_edition)
        layout.addWidget(self.edition_cards)
        account_row=QHBoxLayout()
        self.account_info=QLabel('Sign in to Echo to use Enhanced free.');account_row.addWidget(self.account_info,1)
        self.account_button=QPushButton('Login to Echo');self.account_button.setIcon(QIcon(str(portable.ROOT/'echo.svg')))
        self.account_button.clicked.connect(lambda:self.sign_in());account_row.addWidget(self.account_button)
        self.sign_out=QPushButton('Logout');self.sign_out.clicked.connect(self.disconnect_account);account_row.addWidget(self.sign_out)
        self.account_info.setTextFormat(Qt.TextFormat.PlainText)
        layout.addLayout(account_row)
        bar=QHBoxLayout()
        self.info=QLabel('Installed components and available downloads');self.info.setWordWrap(True)
        bar.addWidget(self.info,1)
        self.missing=QPushButton('Install / download missing')
        self.missing.clicked.connect(self.download_missing);bar.addWidget(self.missing)
        folders=QPushButton('Open components');folders.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root/'components'))));bar.addWidget(folders)
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
        self.load_catalog()
        self.refresh()

    def load_catalog(self):
        self.release=None
        try:
            self.release=self.store.cached()
            catalog_path=portable.ROOT/('catalog-stock.json' if self.store.edition=='stock' else 'catalog.json')
            if catalog_path.is_file():
                catalog=packages.decode(catalog_path.read_bytes())
                if catalog.get('edition')==self.store.edition and (self.release is None or packages.version(catalog['version'])>packages.version(self.release['version'])):
                    self.release=catalog
        except Exception as error:self.info.setText(str(error))

    def choose_edition(self,edition):
        if self.job or self.busy():
            self.info.setText('Finish the component operation and shut down the VM before switching editions.');return
        if edition not in ('stock','xetallic') or edition==self.store.edition:return
        target=packages.Store(edition=edition)
        try:
            bundled=portable.ROOT/('catalog-stock.json' if edition=='stock' else 'catalog.json')
            candidates=[release for release in (target.cached(),packages.decode(bundled.read_bytes())) if release]
            release=max(candidates,key=lambda release:packages.version(release['version']))
            if release.get('edition')!=edition:raise ValueError('The release does not match the selected edition.')
        except Exception as error:self.info.setText(str(error));return
        def missing(release):
            return [(name,entry) for name,entry in release['components'].items()
                    if not packages.installed(name,target.root) and not packages.compatibility(name,entry)]
        if not missing(release):
            self._commit_edition(target,release);return
        if edition=='xetallic' and not self.account.token:
            self.sign_in(after=lambda:self.choose_edition(edition));return
        self.info.setText('Preparing '+editions.EDITIONS[edition][0]+'…')
        def work(progress):
            current=target.check()
            for name,entry in missing(current):target.download(name,entry,progress)
            return current
        # Keep the current edition active until every missing component is ready.
        self.run(work,lambda current:self._commit_edition(target,current))

    def _commit_edition(self,target,release):
        if self.busy():
            self.info.setText('Shut down the VM before switching editions.');return
        try:
            if self.switch_edition:self.switch_edition(target.edition)
            else:editions.select(target.edition)
        except Exception as error:
            self.info.setText('Could not switch editions: '+str(error));return
        self.store=target;self.release=release
        self.info.setText(editions.EDITIONS[target.edition][0]+' selected. Ready to use.')
        self.refresh();self.edition_changed.emit(target.edition)

    def sign_in(self,after=None):
        if self.job:return
        session=self.account.session
        if not self.account.can_remember:
            self._login_prompt({},session,after);return
        # Wallet access may ask the user to unlock it. Keep the window responsive
        # and only read it after an explicit Login click, never during startup.
        credentials={}
        self._account_message('Opening Echo login…')
        self.run(lambda progress:self.account.saved_credentials(),credentials.update,
                 after=lambda:self._login_prompt(credentials,session,after),session=session)

    def _login_prompt(self,credentials,session,after):
        if session is not self.account.session:
            credentials.clear();return
        dialog=LoginDialog(credentials,self.account.can_remember,self.window())
        credentials.clear();self._account_dialog=dialog
        try:
            if dialog.exec()!=QDialog.DialogCode.Accepted or session is not self.account.session:return
            values=dialog.values()
        finally:
            dialog.clear_secrets();dialog.deleteLater();self._account_dialog=None
        self._account_message('Signing in to Echo…')
        self.run(lambda progress:self.account.login(*values,session=session),
                 lambda user:self._account_message(('Signed in to Echo. '+self.account.wallet_warning).strip()),
                 failed=self._account_message,after=after,session=session)

    def _account_message(self,text):
        self.info.setText(text);self.message.emit(text)

    def end_account_session(self):
        self.account.end_session()
        dialog=getattr(self,'_account_dialog',None)
        if dialog:dialog.reject()
        self.refresh_account()

    def disconnect_account(self):
        if self.job:return
        self.end_account_session()
        self.run(lambda progress:self.account.forget(),lambda _:self._account_message('Logged out of Echo.'),
                 failed=self._account_message)

    def require_account(self):
        if self.store.edition=='stock':return True
        if self.account.token:return True
        self.sign_in();return False

    def refresh_account(self):
        enhanced=self.store.edition=='xetallic'
        self.account_info.setVisible(enhanced)
        self.account_button.setVisible(enhanced and not self.account.token)
        self.sign_out.setVisible(enhanced and bool(self.account.token))
        self.account_info.setText('Logged in as '+self.account.user.get('username','Echo user') if self.account.token else 'Log in to Echo to use Enhanced free.')
        self.account_button.setEnabled(not self.job);self.sign_out.setEnabled(bool(self.account.token) and not self.job)
        self.account_changed.emit()

    def refresh(self):
        self.edition_cards.refresh(self.store.edition,busy=bool(self.job))
        self.refresh_account()
        entries=(self.release or {}).get('components',{})
        self.missing.setEnabled(not self.job and any(not packages.installed(n,self.store.root) and not packages.compatibility(n,e) for n,e in entries.items()))
        self.table.setRowCount(len(entries))
        for row,(name,entry) in enumerate(sorted(entries.items(),key=lambda item:item[0]=='kvm-amd')):
            current=packages.installed(name,self.store.root);reason=packages.compatibility(name,entry)
            same=current.get('sha256')==entry['sha256']
            newer=bool(current) and packages.version(current['version'])>packages.version(entry['version'])
            update=packages.update_available(name,entry,current)
            conflict=bool(current) and not same and current['version']==entry['version']
            status=reason or ('Current' if same else 'Newer local version' if newer else
                             'Version conflict' if conflict else 'UPDATE AVAILABLE' if update else 'Ready to download')
            label=('QEMU · Enhanced free · Build 1963' if name=='qemu' and self.store.edition=='xetallic' else
                   'Custom KVM module · Ultra AMD Stealth Interceptor (optional) · '+entry['kernel']
                   if name=='kvm-amd' else entry['label'])
            for col,text in enumerate((label,current.get('version','—'),entry['version'],status)):
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
            self.table.setCellWidget(row,4,cell);self.table.setRowHeight(row,64 if name=='kvm-amd' else 44)
        self.table.setFixedHeight(self.table.horizontalHeader().height()+sum(self.table.rowHeight(r) for r in range(len(entries)))+4)
        self.table.setVisible(bool(entries))
        self.inventory_changed.emit()

    def update_messages(self):
        # The release is already signature-verified. Health refreshes read only
        # local metadata, so an external install also clears its notification.
        messages=[]
        for name,entry in (self.release or {}).get('components',{}).items():
            current=packages.installed(name,self.store.root)
            if packages.update_available(name,entry,current):
                messages.append(f'{entry["label"]} update available: {current["version"]} → {entry["version"]}.')
        return messages

    def run(self,work,finished,failed=None,after=None,*,session=None):
        if self.job:return
        self.check.setEnabled(False);self.progress.show();self.progress.setRange(0,0)
        self.active.emit(True)
        job=Job(work,self);self.job=job
        job.progress.connect(lambda value,total:self._progress(value,total))
        succeeded=[]
        def current():return session is None or session is self.account.session
        def fail(error):
            if current():(failed or self.info.setText)(error)
        def done(result):
            if not current():return
            try:finished(result);succeeded.append(True)
            except Exception as error:fail(str(error))
        job.done.connect(done);job.failed.connect(fail)
        def release():
            self.job=None;self.check.setEnabled(True);self.progress.hide();self.refresh();job.deleteLater();self.active.emit(False)
            if succeeded and after and current():QTimer.singleShot(0,lambda:after() if current() else None)
        job.finished.connect(release);self.refresh();job.start()

    def _progress(self,value,total):
        self.progress.setRange(0,1000);self.progress.setValue(int(value*1000/max(1,total)))

    def check_updates(self):
        self.info.setText('Checking the signed release feed…')
        def done(release):
            self.release=release;self.info.setText('Release '+release['version']+' · Choose the components to update.');self.refresh()
        self.run(lambda progress:self.store.check(),done)

    def download(self,name,entry):
        if not self.require_account():return
        if self.busy():
            QMessageBox.information(self,'VM is running','Shut down the VM before replacing its components.');return
        self.info.setText('Downloading '+entry['label']+'…')
        def done(changed):
            portable.prepare_firmware()
            portable.prepare_tpm_workspace()
            self.info.setText(entry['label']+' installed.');self.changed.emit()
        self.run(lambda progress:self.store.download(name,entry,progress),done)

    def download_missing(self):
        if not self.require_account():return
        if self.job or self.busy():
            self.info.setText('Finish the running VM or component operation first.');return
        entries=[(n,e) for n,e in (self.release or {}).get('components',{}).items()
                 if not packages.installed(n,self.store.root) and not packages.compatibility(n,e)]
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
