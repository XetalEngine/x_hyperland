"""A transparent surface shared by live switching and the settings preview."""
from PyQt6.QtCore import Qt


def configure(widget):
    widget.setObjectName('taskSwitcherOverlay')
    widget.setProperty('xetalOverlay', True)
    widget.setWindowFlags(widget.windowFlags() | Qt.WindowType.FramelessWindowHint
                          | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    widget.setAutoFillBackground(False)
    # Widget-local styling wins over every desktop theme, including QDialog fills.
    widget.setStyleSheet('QWidget#taskSwitcherOverlay {background:transparent; border:none;}')
