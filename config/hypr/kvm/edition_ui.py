"""Edition cards, also usable while an existing installation awaits rollout."""
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from edition_info import EDITIONS


class EditionCards(QWidget):
    requested = pyqtSignal(str)

    def __init__(self, parent=None, *, rollout_pending=False):
        super().__init__(parent)
        self.rollout_pending = rollout_pending
        self.buttons = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        cards = QHBoxLayout()
        echo = QIcon(str(Path(__file__).with_name('echo.svg')))
        for key, (title, description) in EDITIONS.items():
            card = QGroupBox(title)
            column = QVBoxLayout(card)
            requirement = QHBoxLayout()
            if key in ('xetallic', 'max'):
                mark = QLabel()
                mark.setPixmap(echo.pixmap(18, 18))
                mark.setAccessibleName('Echo')
                requirement.addWidget(mark)
            label = QLabel(description)
            label.setWordWrap(True)
            requirement.addWidget(label, 1)
            column.addLayout(requirement)
            detail = QLabel('Upstream QEMU + OVMF\nSystem KVM' if key == 'stock' else
                            'Custom QEMU + OVMF\nOptional AMD module' if key == 'xetallic' else
                            'The next Xetallic VM edition')
            detail.setWordWrap(True)
            detail.setObjectName('muted')
            column.addWidget(detail, 1)
            button = QPushButton()
            button.clicked.connect(lambda _, edition=key: self.requested.emit(edition))
            column.addWidget(button)
            self.buttons[key] = button
            cards.addWidget(card, 1)
        layout.addLayout(cards)
        if rollout_pending:
            note = QLabel('Edition switching is waiting for the service update. '
                          'The components below are your current installation.')
            note.setObjectName('muted')
            note.setWordWrap(True)
            layout.addWidget(note)
        self.refresh()

    def refresh(self, selected=None, *, busy=False):
        for key, button in self.buttons.items():
            pending = self.rollout_pending and key != 'max'
            button.setText('Coming soon' if key == 'max' else 'Service update pending' if pending else
                           'Selected' if key == selected else
                           'Switch to Basic' if key == 'stock' else 'Switch to Enhanced')
            button.setEnabled(not self.rollout_pending and key != 'max' and key != selected and not busy)
