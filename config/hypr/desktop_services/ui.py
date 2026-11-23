"""Small shared widgets for Fusion Settings' desktop integrations."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel


def text(value, name=''):
    label = QLabel(value)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
