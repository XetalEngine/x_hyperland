"""A persistent, softly flashing warning beside each launch button."""
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy


class ModuleWarning(QLabel):
    def __init__(self, button):
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
        def insert(layout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget() is button:
                    layout.insertWidget(i + 1, self, 1)
                    return True
                if item.layout() and insert(item.layout()):
                    return True
            return False
        insert(button.parentWidget().layout())
        self.hide()

    def pulse(self):
        self.phase = not self.phase
        self.setStyleSheet('color: ' + ('#edc478' if self.phase else '#bca06d') + '; font-weight: 600;')

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
