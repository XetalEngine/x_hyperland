"""Wheel gestures scroll settings pages; deliberate input changes their values."""
from PyQt6.QtCore import QObject, QEvent, QPointF
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (QApplication, QAbstractScrollArea, QAbstractSlider,
                            QAbstractSpinBox, QComboBox, QLineEdit, QScrollBar, QWidget)


def protected_control(widget):
    while isinstance(widget, QWidget):
        # Popup lists, text documents and actual scrollbars keep native scrolling.
        if isinstance(widget, (QAbstractScrollArea, QScrollBar)):
            return None
        if isinstance(widget, (QAbstractSlider, QAbstractSpinBox, QComboBox, QLineEdit)):
            return widget
        if widget.isWindow():
            break
        widget = widget.parentWidget()
    return None


class WheelGuard(QObject):
    forwarding = False

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or self.forwarding:
            return False
        control = protected_control(watched)
        if control is None:
            return False
        parent = control.parentWidget()
        self.forwarding = True
        try:
            while parent is not None:
                if isinstance(parent, QAbstractScrollArea):
                    viewport = parent.viewport()
                    local = viewport.mapFromGlobal(event.globalPosition().toPoint())
                    forwarded = QWheelEvent(QPointF(local), event.globalPosition(),
                        event.pixelDelta(), event.angleDelta(), event.buttons(),
                        event.modifiers(), event.phase(), event.inverted())
                    forwarded.setAccepted(False)
                    QApplication.sendEvent(viewport, forwarded)
                    if forwarded.isAccepted():
                        break
                if parent.isWindow():
                    break
                parent = parent.parentWidget()
        finally:
            self.forwarding = False
        event.accept()
        return True


def install(app):
    if not hasattr(app, 'settings_wheel_guard'):
        app.settings_wheel_guard = WheelGuard(app)
        app.installEventFilter(app.settings_wheel_guard)
    return app.settings_wheel_guard
