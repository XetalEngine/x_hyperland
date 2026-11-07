#!/usr/bin/env python3
"""The full vmstart_2 editor integrated into the isolated Hyprland desktop."""
from pathlib import Path
import argparse
import json
import os
import sys
import subprocess
import fcntl
import shlex
import time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'backend/lib'))
import portable

from PyQt6.QtCore import Qt,QTimer,QSize,QEvent
from PyQt6.QtGui import QCursor,QGuiApplication
from PyQt6.QtNetwork import QLocalServer,QLocalSocket
from PyQt6.QtWidgets import QApplication,QLabel,QPushButton,QMessageBox,QWidget,QHBoxLayout,QSizePolicy
import vmstart2
from vmstart2 import VMStart2
import virtual_gpu
import theme as backend_theme
sys.path.insert(0,str(ROOT.parent/'theme'))
import runtime as desktop_theme
import wheel_guard
from icons import icon
from window_chrome import window_controls,toggle_maximized
from package_ui import PackagesPanel
from account_ui import AccountHeader
from activity import supervisor_active


class KVMSettings(VMStart2):
    def _apply_theme(self,*_):
        self._update_modified()

    def _set_profile_title(self):
        self.setWindowTitle('KVM Settings · '+vmstart2.profiles.NAMES[self.profile_id])

    def _size_and_centre(self):
        screen=QGuiApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        rect=screen.availableGeometry()
        self.resize(min(1820,max(800,rect.width()-80)),min(920,max(560,rect.height()-80)))

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(800,560)
        self.theme_bar.hide()
        brand=self.findChild(QLabel,'appLogo');brand.setPixmap(vmstart2.QPixmap());brand.setText('KVM Settings')
        brand.setAccessibleName('KVM Settings');brand.setToolTip('Windows and Apple virtual machines')
        brand.setStyleSheet('font-size:21px; font-weight:700;');brand.setFixedWidth(196)
        bar=self.centralWidget().layout().itemAt(0).layout()
        self.chip=QLabel();self.chip.setPixmap(icon('chip',desktop_theme.colors()['Accent'],30).pixmap(30,30));bar.insertWidget(0,self.chip)
        self.window_controls=window_controls(self);bar.addWidget(self.window_controls)
        self._decorate_pages()
        self.account_header=AccountHeader(self)
        self.account_actions=QWidget(self)
        actions=QHBoxLayout(self.account_actions);actions.setContentsMargins(0,0,0,0)
        actions.setSpacing(bar.spacing());actions.addWidget(self.account_header)
        # Keep account controls beside Save, moving the whole group below the
        # title bar when a smaller display cannot fit both groups in one row.
        index=bar.indexOf(self.btn_save)
        while index<bar.indexOf(self.window_controls):
            item=bar.takeAt(index)
            if item.widget():actions.addWidget(item.widget())
            else:actions.addItem(item)
        bar.insertWidget(bar.indexOf(self.window_controls),self.account_actions)
        self.account_actions.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
        self.account_row=QHBoxLayout();self.account_row.setContentsMargins(0,0,0,0);self.account_row.addStretch()
        self.centralWidget().layout().insertLayout(1,self.account_row)
        self._account_wrapped=False
        self.account_header.login_requested.connect(self.package_panel.sign_in)
        self.account_header.logout_requested.connect(self.package_panel.disconnect_account)
        self.package_panel.account_changed.connect(self._refresh_account_header)
        self.package_panel.message.connect(self.status.setText)
        self._refresh_account_header()
        self.setWindowIcon(icon('chip',desktop_theme.colors()['Accent']))
        QApplication.instance().hypr_theme.changed.connect(self._theme_changed)
        if not self.cfg.data.get('wizard',{}).get('complete'):
            self._select_tab_by_name('Wizard')
        import health
        health.install(self)

    def _refresh_all(self):
        if hasattr(self,'cfg'):
            import editions
            editions.apply(self.cfg.data)
        super()._refresh_all()
        if hasattr(self,'issue_delegate'):
            import health
            health.refresh(self)

    def _page_changed(self,index):
        super()._page_changed(index)
        if hasattr(self,'issue_delegate'):
            import health
            health.refresh(self)

    def _theme_changed(self):
        self.setWindowIcon(icon('chip',desktop_theme.colors()['Accent']))
        self.chip.setPixmap(icon('chip',desktop_theme.colors()['Accent'],30).pixmap(30,30))
        self._fill_features()
        self._fill_smbios()
        self._layout_account_actions()
        self.update()

    def _refresh_account_header(self):
        self.account_header.refresh(self.package_panel.account,busy=bool(self.package_panel.job))

    def _layout_account_actions(self):
        if not hasattr(self,'_account_wrapped'):return
        root=self.centralWidget().layout();bar=root.itemAt(0).layout()
        margins=root.contentsMargins()
        required=bar.minimumSize().width()+margins.left()+margins.right()
        if self._account_wrapped:required+=self.account_actions.minimumSizeHint().width()+bar.spacing()
        wrapped=self.width()<required
        if wrapped==self._account_wrapped:return
        if wrapped:
            bar.removeWidget(self.account_actions);self.account_row.addWidget(self.account_actions)
        else:
            self.account_row.removeWidget(self.account_actions)
            bar.insertWidget(bar.indexOf(self.window_controls),self.account_actions)
        self._account_wrapped=wrapped

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._layout_account_actions()

    def _toggle_maximized(self):
        toggle_maximized(self)

    def show_for_session(self):
        self.showNormal()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and event.position().y()<62:
            self._toggle_maximized();event.accept();return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and event.position().y()<62 and self.windowHandle():
            self.windowHandle().startSystemMove();event.accept();return
        super().mousePressEvent(event)

    def _decorate_pages(self):
        panel=PackagesPanel(self._busy,self.tab_paths,switch_edition=self._switch_edition)
        panel.changed.connect(self._refresh_all)
        panel.inventory_changed.connect(self._health_changed)
        self.tab_paths.widget().layout().insertWidget(0,panel)
        self.package_panel=panel
        if not getattr(self,'_wizard_connected',False):
            self.tab_wizard.finished.connect(self._wizard_finished)
            self.tab_wizard.component_page.connect(self._mount_components)
            self.tabs.currentChanged.connect(lambda _:self._mount_components(self.tab_wizard.component_host))
            self._wizard_connected=True
        self.tab_wizard.components_ready=self._components_ready
        self._mount_components(self.tab_wizard.component_host)
        self.tab_virtual.before_launch=lambda:self._ready(self.tab_virtual._launch)
        self.tab_dual.before_launch=lambda:self._ready(self.tab_dual._launch)
        from module_warning import ModuleWarning
        self.module_warnings=[ModuleWarning(button,self._install_compatible_kernel) for button in
                              (self.btn_launch,self.tab_virtual.btn_launch,self.tab_dual.btn_launch)]
        self._refresh_module_status()
        self.tab_hw.capture_gpu_rom=self._capture_gpu_rom
        self.tab_wizard.capture_gpu_rom=self._capture_gpu_rom
        self.tab_dual.capture_gpu_rom=self._capture_gpu_rom
        self.tab_machine.create_bridge.connect(self._create_bridge)
        self.tab_wizard.create_bridge.connect(self._create_bridge)
        if hasattr(self.tab_tpm,'btn_repair'):
            self.tab_tpm.btn_repair.clicked.connect(self._repair_tpm)
            self.tab_tpm.checks_changed.connect(self._health_changed)
            self.tab_tpm.action_requested.connect(self._tpm_action)
            panel.message.connect(self.tab_tpm.action_status.setText)
        panel.active.connect(lambda busy:self.tab_tpm.set_actions_busy(busy)
                             if hasattr(self.tab_tpm,'btn_repair') else None)

    def _switch_edition(self,edition):
        import editions,checkpoint,copy
        checkpoint.save(self)
        previous=copy.deepcopy(self.cfg.data);old=editions.selected()
        try:
            editions.switch(self.cfg.data,edition)
            portable.prepare_firmware();portable.prepare_tpm_workspace()
            self._refresh_all();checkpoint.save(self)
        except Exception:
            self.cfg.data.clear();self.cfg.data.update(previous)
            editions.select(old)
            self._refresh_all();checkpoint.save(self)
            raise
        self.status.setText(editions.EDITIONS[edition][0]+' selected. Your guest files and settings are retained.')

    def _health_changed(self):
        if hasattr(self,'issue_delegate') and not getattr(self,'_checking_health',False):
            import health
            health.refresh(self)

    def _refresh_module_status(self):
        if not getattr(self,'package_panel',None):return
        import module_policy,platform,packages
        text,detail=module_policy.warning(self.cfg.data,self.package_panel.release)
        entry=(self.package_panel.release or {}).get('components',{}).get('kvm-amd',{})
        kernel=entry.get('kernel','') if module_policy.requested(self.cfg.data) and packages.cpu_vendor()=='amd' else ''
        if kernel==platform.release():kernel=''
        for label in getattr(self,'module_warnings',[]):
            label.setText(text);label.setToolTip(detail);label.setVisible(bool(text))
            label.kernel_action(kernel,available=not bool(self.package_panel.job))
        # Inventory callbacks can run while the panel is releasing a job.
        # Prepare a matching download on the next event-loop turn, before the
        # user needs to launch a guest. Loading modules remains a launch action.
        if not hasattr(self,'_module_prepare_timer'):
            self._module_prepare_timer=QTimer(self)
            self._module_prepare_timer.setSingleShot(True)
            self._module_prepare_timer.timeout.connect(
                lambda:self._prepare_optional_module() if self.isVisible() else None)
        if not self._module_prepare_timer.isActive():self._module_prepare_timer.start(0)

    def _install_compatible_kernel(self):
        if self.package_panel.job or self._busy():
            self.status.setText('Finish the current operation and shut down the VM before installing a kernel.');return
        from kernel_install_ui import KernelInstallDialog
        entry=(self.package_panel.release or {}).get('components',{}).get('kvm-amd',{})
        dialog=KernelInstallDialog(entry.get('kernel'),self,busy=self._busy)
        dialog.exec();self._refresh_module_status()

    def _prepare_optional_module(self,retry=None):
        """Prepare a compatible published download once per release/session.

        A missing or incompatible optional build never blocks the guest. Failed
        downloads fall back for this session, leaving the saved choice intact.
        """
        import module_policy,packages
        if not module_policy.requested(self.cfg.data):return False
        panel=self.package_panel
        if panel.job:return False
        entry=(panel.release or {}).get('components',{}).get('kvm-amd')
        if (not entry or packages.compatibility('kvm-amd',entry)
                or not module_policy.unavailable(check_busy=False) or self._busy()):return False
        identity=(str(panel.store.root),entry['sha256'])
        attempts=getattr(self,'_module_download_attempts',set())
        if identity in attempts:return False
        attempts.add(identity);self._module_download_attempts=attempts
        session=panel.account.session;config=self.cfg
        self.status.setText('Preparing the custom KVM module for this kernel…')
        def done(_):
            self.status.setText('Compatible custom KVM module ready.'+(' Continuing launch…' if retry else ''))
            self._refresh_all()
        def failed(error):
            panel.info.setText('Optional module download unavailable. Using standard KVM. '+error)
        def resume():
            # Closing/reopening Settings or changing profiles cancels the old
            # launch intent, even if the optional download finishes afterwards.
            if (self.isVisible() and self.package_panel is panel and self.cfg is config
                    and panel.account.session is session):retry()
        panel.run(lambda progress:panel.store.download('kvm-amd',entry,progress),done,failed,session=session)
        if retry:panel.job.finished.connect(lambda:QTimer.singleShot(0,resume))
        return True

    def _capture_gpu_rom(self,slot,finished):
        panel=self.package_panel
        if panel.job or self._busy():
            self.status.setText('Finish the component operation or shut down the VM before reading its GPU ROM.')
            finished(None);return
        import gpu_rom
        self.status.setText('Reading the selected GPU ROM…')
        def done(path):
            finished(path)
            self.status.setText('GPU ROM automatically dumped and assigned: '+path)
            if self.isVisible():
                QMessageBox.information(self,'GPU ROM ready','The GPU ROM was automatically dumped, validated and assigned.\n\n'+path)
            else:
                import checkpoint
                checkpoint.save(self)
        def failed(error):
            finished(None)
            self.status.setText('GPU ROM capture failed. Select a ROM manually or retry.')
            panel.info.setText(error)
            if self.isVisible():QMessageBox.warning(self,'GPU ROM capture failed',error)
        panel.run(lambda progress:gpu_rom.capture(slot),done,failed)

    def _create_bridge(self, name):
        panel = self.package_panel
        if panel.job or self._busy():
            self.status.setText('Finish the current operation and shut down the VM before changing its host network.')
            return
        import network_bridge
        from network_config import configure
        self.status.setText(f'Creating bridge {name}… The wired connection may briefly reconnect.')
        self.tab_machine.net_status.setText(self.status.text())
        def done(result):
            configure(self.cfg, 'tap', result['bridge'])
            self.host['bridges'] = vmstart2.hostinfo.net_bridges()
            self.tab_machine._load_net()
            wizard = self.tab_wizard
            if wizard.step == len(wizard.steps) - 1:
                wizard.go(wizard.step)
            self._refresh_all()
            self.status.setText(result['message'])
            panel.info.setText(result['message'])
            import checkpoint
            checkpoint.save(self)
        def failed(error):
            self.status.setText('Bridge setup stopped. Use NAT or review the network connection.')
            self.tab_machine.net_status.setText(error)
            panel.info.setText(error)
            if self.isVisible():
                QMessageBox.warning(self, 'Bridge setup needs attention', error)
        panel.run(lambda progress:network_bridge.request(name), done, failed)

    def _repair_tpm(self):
        panel=self.package_panel;tab=self.tab_tpm
        if panel.job or self._busy():
            self.status.setText('Finish the component operation or shut down the VM before initializing TPM state.');return
        import packages,tpm_setup
        tools=self.cfg.data.setdefault('tools',{})
        binary=tools.get('swtpm_binary','')
        state=tab.state_dir.text().strip()
        banks=tab.pcr_banks.text().strip();ek=tab.ek_algo.currentData()
        certificates=tab.chk_ekcert.isChecked() or tab.chk_platcert.isChecked()
        lock_nvram=tab.chk_lock.isChecked()
        def work(progress):
            if not binary or not Path(binary).is_file():
                release=panel.release or panel.store.check()
                entry=release['components']['tpm']
                panel.store.download('tpm',entry,progress)
            portable.prepare_tpm_workspace()
            selected=binary if binary and Path(binary).is_file() else str(portable.component_path('tpm')/'bin/swtpm')
            blob=Path(state)/'tpm2-00.permall'
            if blob.is_file():
                try:blob.read_bytes()
                except PermissionError:
                    from uiutil import sudo_command
                    command,env,available=sudo_command([sys.executable,str(ROOT/'private_tpm.py'),
                        '--repair','--state',state,'--root',str(portable.data_root()),
                        '--uid',str(os.getuid()),'--gid',str(os.getgid())],
                        'KVM Settings: restore access to existing private TPM state')
                    if not available:raise RuntimeError('Administrator access is needed to restore TPM state permissions.')
                    subprocess.run(command,env=env,check=True,timeout=90,capture_output=True)
                    blob.read_bytes()
                return selected,'Existing TPM state preserved. Checks refreshed; use the named action for any remaining issue.'
            message=tpm_setup.initialize(state,selected,banks,ek,certificates,lock_nvram)
            return selected,message
        def done(result):
            tools['swtpm_binary']=result[0]
            tab.log.setPlainText(result[1]);tab.check_attestation()
            panel.info.setText(result[1]);self.status.setText(result[1].splitlines()[0])
            self._refresh_all()
            import checkpoint
            checkpoint.save(self)
        def failed(error):
            tab.log.setPlainText(error);panel.info.setText(error)
            tab.check_attestation()
            if self.isVisible():QMessageBox.warning(self,'TPM setup needs attention',error)
        panel.info.setText('Installing / initializing private TPM state…')
        panel.run(work,done,failed)

    def _tpm_action(self, action):
        import copy,checkpoint,tpm_actions,packages
        panel=self.package_panel;tab=self.tab_tpm
        if panel.job or self._busy():
            tab.action_status.setText('Finish the current operation and shut down the VM first.');return
        previous=tpm_actions.snapshot(tab)
        input_values={k:w['edit'].text() for k,w in tab.widgets.items()}
        tools=copy.deepcopy(self.cfg.data.get('tools',{}))
        old_undo=copy.deepcopy(self.cfg.data.get('tpm_previous'))
        if action=='undo' and not old_undo:return
        def ensure_package():
            binary=portable.component_path('tpm')/'bin/swtpm'
            if not binary.is_file() or not binary.with_name('swtpm_setup').is_file():
                release=panel.release or panel.store.check();entry=release['components']['tpm']
                panel.store.download('tpm',entry,lambda a,b:None)
            portable.prepare_tpm_workspace()
        def work(progress):
            if action=='undo':
                return old_undo
            return tpm_actions.prepare(action,tools,input_values,ensure_package,panel.message.emit)
        def done(choice):
            try:
                tpm_actions.activate(tab,choice)
                if action=='undo':self.cfg.data.pop('tpm_previous',None)
                else:self.cfg.data['tpm_previous']=previous
                checkpoint.save(self)
            except Exception as error:
                tpm_actions.activate(tab,previous)
                if old_undo is None:self.cfg.data.pop('tpm_previous',None)
                else:self.cfg.data['tpm_previous']=old_undo
                failed('Could not save the new selection: '+str(error));return
            tab.check_attestation()
            message=choice['label']+' applied and saved. Ready for the next VM start.'
            tab.action_status.setText(message);self.status.setText(message)
            self._refresh_all()
        def failed(error):
            tab.action_status.setText('Not applied. '+error)
            tab.log.setPlainText(error);self.status.setText('TPM action stopped; the previous selection is unchanged.')
        tab.action_status.setText('Preparing your TPM choice…')
        panel.run(work,done,failed)

    def _rebuild_tabs(self):
        if hasattr(self,'package_panel') and self.package_panel.job:
            raise RuntimeError('Wait for the component operation before changing profiles or loading a preset.')
        panel=getattr(self,'package_panel',None)
        for label in getattr(self,'module_warnings',[]):
            label.install_button.hide();label.install_button.deleteLater()
            label.hide();label.deleteLater()
        self.module_warnings=[]
        if panel:
            panel.setParent(self);panel.hide()
            self.package_panel=None
        super()._rebuild_tabs()
        if panel:
            account=panel.account
            panel.deleteLater();self._decorate_pages()
            self.package_panel.account=account;self.package_panel.refresh()

    def _mount_components(self,host):
        panel=getattr(self,'package_panel',None)
        if panel is None:return
        if self.tabs.currentWidget() is not self.tab_wizard:host=None
        panel.setParent(host or self.tab_paths.widget())
        (host.layout() if host is not None else self.tab_paths.widget().layout()).insertWidget(0,panel)
        panel.show()

    def _components_ready(self):
        import packages
        panel=self.package_panel
        if panel.job:
            panel.info.setText('Please wait for component installation to finish.');return False
        required=['baseline','qemu','ovmf','opencore' if self.profile_id=='macos' else 'tpm']
        # The custom module is optional. Its preference survives unsupported
        # kernels and a matching build is prepared automatically at launch.
        missing=[name for name in required if not packages.installed(name)]
        if missing:
            panel.info.setText('Install / download missing components before continuing: '+', '.join(missing));return False
        portable.prepare_firmware();portable.prepare_tpm_workspace()
        return True

    def _can_replace_profile(self):
        if hasattr(self,'package_panel') and self.package_panel.job:
            self.status.setText('Wait for the component operation before changing profiles or loading a preset.')
            return False
        return True

    def switch_profile(self,key):
        if not self._can_replace_profile():
            self.profile_buttons[self.profile_id].setChecked(True)
            return
        super().switch_profile(key)
        if not self.cfg.data.get('wizard',{}).get('complete'):
            self._select_tab_by_name('Wizard')

    def load_preset(self):
        if self._can_replace_profile():super().load_preset()

    def reset_template(self):
        if self._can_replace_profile():super().reset_template()

    def reset_defaults(self):
        if self._can_replace_profile():super().reset_defaults()

    def revert_session(self):
        if self._can_replace_profile():super().revert_session()

    def _busy(self):
        if virtual_gpu.service_active():return True
        for panel in (self.tab_virtual,self.tab_dual):
            if getattr(panel,'_submitting',False) or time.monotonic()<getattr(panel,'_submission_deadline',0):return True
            if supervisor_active(virtual_gpu.status(panel.run)):return True
        return False

    def _ready(self,retry=None):
        import kernel_install
        if kernel_install.active():
            QMessageBox.information(self,'Kernel setup is running','Wait for compatible-kernel installation to finish before launching a VM.');return False
        if not self.cfg.data.get('wizard',{}).get('complete'):
            self._select_tab_by_name('Wizard')
            QMessageBox.information(self,'Complete setup','Finish the setup wizard for this profile before starting a VM.');return False
        if self.package_panel.job:
            QMessageBox.information(self,'Components are busy','Wait for component installation to finish.');return False
        if not self.package_panel.require_account():return False
        if self._prepare_optional_module(retry):return False
        self._refresh_module_status()
        import module_policy
        settings=self.cfg.data.get('tools',{})
        if module_policy.requested(self.cfg.data) and not module_policy.unavailable():
            try:
                from module_tool import check
                args=shlex.split(settings.get('kvm_build_args',''))
                if args==['--build-only']:
                    raise RuntimeError('Published modules are prebuilt. To compile locally, select your own build script in Paths & Tools.')
                else:check(portable.data_root())
            except Exception as error:
                QMessageBox.warning(self,'Custom module unavailable',str(error));return False
        if not super()._before_mac_launch():return False
        # Existing launch routines use sudo -n after this one explicit prompt.
        # The credential timestamp is scoped to this GUI process, not a policy
        # change or a permanent passwordless-sudo rule.
        from uiutil import sudo_command
        command,environment,available=sudo_command(['true'],'KVM Settings: launch a virtual machine')
        if not available:
            QMessageBox.warning(self,'Administrator access','The desktop password prompt is unavailable.');return False
        try:
            reply=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=120)
        except Exception as error:
            QMessageBox.warning(self,'Administrator access',str(error));return False
        if reply.returncode:
            self.status.setText('Launch cancelled: administrator access was not granted.')
            return False
        import editions
        if editions.selected()=='xetallic':
            self.status.setText('Checking your Echo account…');QApplication.processEvents()
            try:
                self.package_panel.account.check()
                reply=subprocess.run(['sudo','-n',sys.executable,str(ROOT/'runtime_access.py'),str(portable.data_root())],
                    input=json.dumps({'token':self.package_panel.account.token}),capture_output=True,text=True,timeout=30)
                if reply.returncode:raise RuntimeError(reply.stderr.strip() or 'Could not prepare the VM launch session.')
            except Exception as error:
                QMessageBox.warning(self,'Echo sign-in',str(error));return False
            finally:self.package_panel.refresh_account()
        return True

    def _launch(self,dry):
        if not dry and not self._ready(lambda:self._launch(False)):return
        return super()._launch(dry)

    def _test_run(self):
        if self._ready(self._test_run):return super()._test_run()

    def _wizard_finished(self):
        if self.save_session(quiet=True):
            self.status.setText('Setup saved. Choose Virtual GPU, Single GPU or Dual GPU to continue.')
            self._select_tab_by_name('Virtual GPU')

    def _open_wizard(self):
        self._select_tab_by_name('Wizard')
        self.tab_wizard.btn_next.setFocus()

    def closeEvent(self,event):
        self.package_panel.end_account_session()
        import checkpoint
        focus=QApplication.focusWidget()
        if focus:focus.clearFocus()
        try:checkpoint.save(self)
        except Exception as error:checkpoint.recover(self,error)
        # Close immediately; let an atomic install finish in the background.
        # A new Apps click can reopen the same window while that job completes.
        if self.package_panel.job:
            application=QApplication.instance()
            application.setQuitOnLastWindowClosed(False)
            def finish():
                if not self.isVisible():application.quit()
                else:application.setQuitOnLastWindowClosed(True)
            self.package_panel.job.finished.connect(finish)
        event.accept()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke-dir',type=Path)
    args=parser.parse_args()
    if not args.smoke_dir and not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        raise SystemExit('KVM Settings belongs to the Xetal Hyprland session.')
    if args.smoke_dir:
        args.smoke_dir.mkdir(parents=True,exist_ok=True)
        os.environ['XETAL_KVM_DATA']=str(args.smoke_dir/'private-data')
        # The backend captured its paths during import; smoke is launched with
        # XETAL_KVM_DATA set by the fixture runner before importing this module.
        if Path(vmstart2.LAST_STATE).parent!=portable.data_root():
            os.execv(sys.executable,[sys.executable,__file__,*sys.argv[1:]])
    portable.prepare()
    app=QApplication(sys.argv[:1]);app.setApplicationName('xetal-kvm-settings');app.setDesktopFileName('xetal-kvm-settings')
    desktop_theme.install(app,backend_theme.build_stylesheet('#65d5cb'))
    wheel_guard.install(app)
    server=None
    if not args.smoke_dir:
        session=Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']
        address=str(session/'kvm-settings.sock')
        start_lock=Path(address+'.startup-lock').open('a');fcntl.flock(start_lock,fcntl.LOCK_EX)
        peer=QLocalSocket();peer.connectToServer(address)
        if peer.waitForConnected(150):
            peer.write(b'{}\n');peer.waitForBytesWritten(300);return 0
        QLocalServer.removeServer(address)
        server=QLocalServer(app);server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(address):raise RuntimeError(server.errorString())
    window=KVMSettings()
    app.aboutToQuit.connect(window.package_panel.end_account_session)
    if server:
        start_lock.close()
        def incoming():
            peer=server.nextPendingConnection()
            def receive():
                if peer.bytesAvailable()>1024:peer.disconnectFromServer();return
                if not peer.canReadLine():return
                peer.readLine();peer.disconnectFromServer()
                if not window.isVisible():window.show_for_session()
                if window.isMinimized():window.showNormal()
                window.raise_();window.activateWindow()
                subprocess.Popen(['hyprctl','dispatch','focuswindow','class:^(xetal-kvm-settings)$'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            peer.readyRead.connect(receive);peer.disconnected.connect(peer.deleteLater)
            if peer.bytesAvailable():receive()
        server.newConnection.connect(incoming)
        lifetime=QLocalSocket(app);lifetime.connectToServer(str(session/'.socket2.sock'))
        lifetime.readyRead.connect(lambda:lifetime.readAll())
        def session_ended():
            window.package_panel.end_account_session()
            window.hide()
            import checkpoint
            try:checkpoint.save(window)
            except Exception as error:checkpoint.recover(window,error)
            if window.package_panel.job:window.package_panel.job.finished.connect(app.quit)
            else:app.quit()
        lifetime.disconnected.connect(session_ended)
    if args.smoke_dir:
        window.resize(1700,980);window.show()
        def capture():
            output={'windows':[],'macos':[]}
            for profile in ('windows','macos'):
                window.switch_profile(profile)
                for index in range(window.tabs.count()):
                    if window.tabs.isTabVisible(index):
                        window.tabs.setCurrentIndex(index);app.processEvents()
                        output[profile].append(window.tabs.tabText(index))
                for name in ('Wizard','Paths & Tools','Virtual GPU'):
                    window._select_tab_by_name(name);app.processEvents()
                    window.grab().save(str(args.smoke_dir/(profile+'-'+name.split()[0]+'.png')))
            (args.smoke_dir/'inventory.json').write_text(json.dumps(output,indent=2))
            app.quit()
        QTimer.singleShot(300,capture)
    else:
        window.show_for_session()
        QTimer.singleShot(100,window.package_panel.bootstrap)
    result=app.exec()
    # Dispose Qt-owned children while the application and Python wrappers are
    # still alive (especially reparented component panels after profile changes).
    window.tabs.blockSignals(True)
    window.tab_wizard.blockSignals(True)
    window.deleteLater()
    app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    return result


if __name__=='__main__':raise SystemExit(main())
