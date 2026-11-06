#!/usr/bin/env python3
"""Explicit, themed compatible-kernel setup shared by KVM and Control Panel."""
import argparse
from pathlib import Path
import platform
import sys
import threading

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout

import kernel_install as kernel


class InstallJob(QThread):
    message = pyqtSignal(str)
    phase_changed = pyqtSignal(str)
    result = pyqtSignal(bool, str)

    def __init__(self, target, aur, parent=None):
        super().__init__(parent)
        self.cancel = threading.Event()
        self.installer = kernel.Installer(target, aur=aur, log=self.record,
                                         phase=self.phase_changed.emit, cancel=self.cancel)

    def record(self, text):
        self.message.emit(text)
        if self.installer.directory:
            try:
                with (self.installer.directory/'setup.log').open('a') as log:log.write(text+'\n')
            except OSError:pass  # Logging failure must not interrupt pacman.

    def run(self):
        try:
            message = self.installer.install();self.record(message);self.result.emit(True, message)
        except Exception as error:
            message = str(error)
            if self.installer.directory:message += '\nLog and any recovery packages: '+str(self.installer.directory)
            try:self.record(message)
            except OSError:pass
            self.result.emit(False, message)


class KernelInstallDialog(QDialog):
    def __init__(self, release=None, parent=None, *, busy=lambda:False):
        super().__init__(parent)
        self.setWindowTitle('Install compatible KVM kernel')
        self.resize(800, 600)
        self.job = None;self.busy = busy;self.target = None
        layout = QVBoxLayout(self);layout.setSpacing(14)
        title = QLabel('Use the kernel built for KVM interception', self)
        title.setStyleSheet('font-size:20px;font-weight:600;');title.setWordWrap(True);layout.addWidget(title)
        self.description = QLabel(self);self.description.setWordWrap(True);layout.addWidget(self.description)
        self.aur = QCheckBox('Try the AUR if needed — set up missing yay and paru automatically', self)
        self.aur.setChecked(True);layout.addWidget(self.aur)
        details = QLabel('Search the package cache, configured repositories and Arch archive for the exact kernel and headers. '
                         'The AUR fallback builds community packages as your user and verifies their kernel release before installation.\n\n'
                         'Installing may downgrade or replace linux and linux-headers. Recovery packages are saved first. '
                         'Missing dependencies may require a system update. Administrator authentication will be requested. '
                         'Reboot into the installed kernel when setup finishes.', self)
        details.setWordWrap(True);layout.addWidget(details)
        self.status = QLabel('Ready to check and install.', self);self.status.setWordWrap(True);layout.addWidget(self.status)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.progress = QProgressBar(self);self.progress.hide();layout.addWidget(self.progress)
        self.log = QPlainTextEdit(self);self.log.setReadOnly(True);self.log.setMaximumBlockCount(2000)
        self.log.setPlaceholderText('Installation details appear here.');layout.addWidget(self.log, 1)
        self.buttons = QDialogButtonBox(self)
        self.proceed = self.buttons.addButton('Proceed', QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = self.buttons.addButton('Cancel', QDialogButtonBox.ButtonRole.RejectRole)
        self.proceed.setObjectName('installCompatibleKernel')
        self.proceed.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel_or_close);layout.addWidget(self.buttons)
        try:
            self.target = kernel.Target.parse(release or kernel.required_kernel())
            self.description.setText('Running: '+platform.release()+'\nRequired: '+self.target.release+
                                     '\nPackages: linux + linux-headers '+self.target.version)
            problem = kernel.platform_problem()
            if problem:raise RuntimeError(problem)
            if kernel.complete(self.target):
                self.status.setText('This kernel and its matching headers are already installed. Boot '+self.target.release+
                                    ', then reopen KVM Settings. No installation is needed.')
                self.proceed.setEnabled(False);self.aur.setEnabled(False);self.cancel_button.setText('Close')
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error));self.proceed.setEnabled(False);self.aur.setEnabled(False)

    def start(self):
        if self.job or not self.target:return
        import module_policy
        reason = module_policy.busy_reason()
        if self.busy() or reason:
            self.status.setText('Shut down running VMs and finish other KVM operations before installing a kernel. '+reason);return
        self.proceed.setEnabled(False);self.aur.setEnabled(False)
        self.progress.setRange(0, 0);self.progress.show()
        self.job = InstallJob(self.target, self.aur.isChecked(), self)
        self.job.message.connect(self.log.appendPlainText)
        self.job.phase_changed.connect(self.phase)
        self.job.result.connect(self.show_result)
        self.job.finished.connect(self.finished_job)
        self.job.start()

    def phase(self, text):
        self.status.setText(text)
        self.cancel_button.setEnabled(not text.startswith('Installing packages'))

    def show_result(self, success, message):
        self.status.setText(('Completed. ' if success else 'Setup stopped. ')+message)
        self.progress.setRange(0, 1);self.progress.setValue(int(success))

    def finished_job(self):
        self.job.deleteLater();self.job = None
        self.cancel_button.setEnabled(True);self.cancel_button.setText('Close')

    def cancel_or_close(self):
        if self.job:
            if self.job.installer.mutating:return
            self.job.cancel.set();self.cancel_button.setEnabled(False)
            self.status.setText('Canceling before the next package operation…')
        else:self.reject()

    def reject(self):
        if self.job:self.cancel_or_close()
        else:super().reject()

    def closeEvent(self, event):
        if self.job:
            self.cancel_or_close();event.ignore()
        else:super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1]);app.setApplicationName('xetal-compatible-kernel')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'theme'))
    import runtime
    runtime.install(app)
    dialog = KernelInstallDialog(args.kernel);dialog.exec()


if __name__ == '__main__':main()
