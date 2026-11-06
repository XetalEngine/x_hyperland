"""A persistent, softly flashing warning beside each launch button."""
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QSizePolicy


class ModuleWarning(QLabel):
    def __init__(self, button, install_kernel=None):
        super().__init__(button.parentWidget())
        self.setObjectName('kvmModuleWarning')
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.phase = False
        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self.pulse)
        self.pulse()
        self.install_button = QPushButton('Install kernel…', button.parentWidget())
        self.install_button.setObjectName('installKvmKernel')
        if install_kernel:self.install_button.clicked.connect(install_kernel)
        self.install_button.hide()
        def insert(layout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget() is button:
                    layout.insertWidget(i + 1, self, 1)
                    layout.insertWidget(i + 2, self.install_button)
                    return True
                if item.layout() and insert(item.layout()):
                    return True
            return False
        insert(button.parentWidget().layout())
        self.hide()

    def kernel_action(self, release, *, available=True):
        self.install_button.setVisible(bool(release))
        self.install_button.setEnabled(available)
        self.install_button.setToolTip('Find and install kernel '+release+' with matching headers. Requires confirmation and a reboot.' if release else '')

    def pulse(self):
        self.phase = not self.phase
        self.setStyleSheet('color: ' + ('#edc478' if self.phase else '#bca06d') + '; font-weight: 600;')

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
