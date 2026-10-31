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
from PyQt6.QtWidgets import QApplication,QLabel,QPushButton,QMessageBox
import vmstart2
from vmstart2 import VMStart2
import virtual_gpu
import theme as backend_theme
sys.path.insert(0,str(ROOT.parent/'theme'))
import runtime as desktop_theme
import wheel_guard
from icons import icon
from window_chrome import close_button
from package_ui import PackagesPanel
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
        self.maximize=QPushButton();self.maximize.setFixedSize(34,34);self.maximize.setToolTip('Maximize / restore')
        self.maximize.setAccessibleName('Maximize / restore');self.maximize.setStyleSheet('padding:0; min-width:0; min-height:0;')
        self.maximize.setIcon(icon('maximize',desktop_theme.colors()['Text'],18))
        self.maximize.clicked.connect(self._toggle_maximized);bar.addWidget(self.maximize)
        bar.addWidget(close_button(self))
        self._decorate_pages()
        self.setWindowIcon(icon('chip',desktop_theme.colors()['Accent']))
        QApplication.instance().hypr_theme.changed.connect(self._theme_changed)
        if not self.cfg.data.get('wizard',{}).get('complete'):
            self._select_tab_by_name('Wizard')
        import health
        health.install(self)

    def _refresh_all(self):
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
        self.maximize.setIcon(icon('maximize',desktop_theme.colors()['Text'],18))
        self._fill_features()
        self._fill_smbios()
        self.update()

    def _toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

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
        panel=PackagesPanel(self._busy,self.tab_paths)
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
        self.tab_virtual.before_launch=self._ready
        self.tab_dual.before_launch=self._ready
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
        self.use_system_kvm=QPushButton('Use system KVM')
        self.use_system_kvm.setToolTip('Skip the custom module and use the running kernel’s standard KVM module.')
        self.use_system_kvm.clicked.connect(self._use_system_kvm)
        panel.layout().insertWidget(1,self.use_system_kvm)
        self.use_system_kvm.setVisible(bool(self.cfg.data.get('tools',{}).get('kvm_build_enabled')))

    def _health_changed(self):
        if hasattr(self,'issue_delegate') and not getattr(self,'_checking_health',False):
            import health
            health.refresh(self)

    def _use_system_kvm(self):
        self.cfg.data.setdefault('tools',{})['kvm_build_enabled']=False
        self.tab_paths.chk_kvm.setChecked(False)
        self.use_system_kvm.hide()
        self.status.setText('Using this kernel’s standard KVM module. The custom module will not be loaded.')
        self._refresh_all()

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
                    command,env,available=sudo_command(['test','-r',str(blob)],'KVM Settings: check existing TPM state')
                    if not available:raise RuntimeError('Administrator access is needed to read the existing TPM state.')
                    subprocess.run(command,env=env,check=True,timeout=90,capture_output=True)
                return selected,'Existing TPM state preserved. Checks refreshed; use the named action for any remaining issue.'
            message=tpm_setup.initialize(state,selected,banks,ek,certificates,lock_nvram)
            return selected,message
        def done(result):
            tools['swtpm_binary']=result[0]
            tab.log.setPlainText(result[1]);tab.check_attestation()
            panel.info.setText(result[1]);self.status.setText(result[1].splitlines()[0])
            self._refresh_all()
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
        if panel:
            panel.setParent(self);panel.hide()
            self.package_panel=None
        super()._rebuild_tabs()
        if panel:
            panel.deleteLater();self._decorate_pages()

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
        tools=self.cfg.data.get('tools',{})
        if tools.get('kvm_build_enabled'):
            entry=(panel.release or {}).get('components',{}).get('kvm-amd')
            if entry and not packages.compatibility('kvm-amd',entry):required.append('kvm-amd')
            else:
                tools['kvm_build_enabled']=False
                self.status.setText('This CPU/kernel uses the standard KVM module. Your other baseline settings are retained.')
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

    def _ready(self):
        if not self.cfg.data.get('wizard',{}).get('complete'):
            self._select_tab_by_name('Wizard')
            QMessageBox.information(self,'Complete setup','Finish the setup wizard for this profile before starting a VM.');return False
        if self.package_panel.job:
            QMessageBox.information(self,'Components are busy','Wait for component installation to finish.');return False
        settings=self.cfg.data.get('tools',{})
        if settings.get('kvm_build_enabled') and Path(settings.get('kvm_build',''))==ROOT/'module-tool.sh':
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
        return True

    def _launch(self,dry):
        if not dry and not self._ready():return
        return super()._launch(dry)

    def _test_run(self):
        if self._ready():return super()._test_run()

    def _wizard_finished(self):
        if self.save_session(quiet=True):
            self.status.setText('Setup saved. Choose Virtual GPU, Single GPU or Dual GPU to continue.')
            self._select_tab_by_name('Virtual GPU')

    def _open_wizard(self):
        self._select_tab_by_name('Wizard')
        self.tab_wizard.btn_next.setFocus()

    def closeEvent(self,event):
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
