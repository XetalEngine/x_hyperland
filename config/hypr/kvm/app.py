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
        self.resize(min(1560,max(800,rect.width()-80)),min(850,max(560,rect.height()-80)))

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

    def _theme_changed(self):
        self.setWindowIcon(icon('chip',desktop_theme.colors()['Accent']))
        self.chip.setPixmap(icon('chip',desktop_theme.colors()['Accent'],30).pixmap(30,30))
        self.maximize.setIcon(icon('maximize',desktop_theme.colors()['Text'],18))
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
        required=['qemu','ovmf','opencore' if self.profile_id=='macos' else 'tpm']
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
