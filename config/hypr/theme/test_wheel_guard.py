"""Real Qt wheel events must scroll without emitting setting changes."""
import unittest
from PyQt6.QtCore import Qt, QPoint, QPointF, QDate, QEvent
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest, QSignalSpy
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QScrollArea,
    QSlider, QDial, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QLineEdit, QPlainTextEdit)
import wheel_guard

APP = QApplication.instance() or QApplication([])


def wheel(widget, angle=QPoint(0, -120), pixel=QPoint(), modifiers=Qt.KeyboardModifier.NoModifier):
    pos = QPointF(widget.rect().center())
    event = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), pixel, angle,
        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


class WheelGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = wheel_guard.install(APP)
        self.area = QScrollArea(); self.area.resize(440, 220)
        self.body = QWidget(); self.layout = QVBoxLayout(self.body)
        self.body.setMinimumSize(400, 1100); self.area.setWidget(self.body)
        self.area.show(); APP.processEvents()

    def tearDown(self):
        self.area.close(); self.area.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_hovered_and_focused_controls_are_read_only_for_every_wheel_direction(self):
        controls = [QSlider(Qt.Orientation.Horizontal), QDial(), QSpinBox(), QDoubleSpinBox(),
                    QDateEdit(QDate(2026, 10, 29)), QComboBox(), QComboBox(), QLineEdit('unchanged')]
        controls[5].addItems(['one', 'two', 'three']); controls[5].setCurrentIndex(1)
        controls[6].addItems(['one', 'two', 'three']); controls[6].setEditable(True)
        for control in controls:
            self.layout.addWidget(control)
            if isinstance(control, (QSlider, QDial, QSpinBox, QDoubleSpinBox)):
                control.setValue(50); getter=control.value; signal=control.valueChanged
            elif isinstance(control, QComboBox):getter=control.currentText;signal=control.currentTextChanged
            elif isinstance(control, QDateEdit):getter=control.date;signal=control.dateChanged
            else:getter=control.text;signal=control.textChanged
            before=getter();spy=QSignalSpy(signal)
            for focused in (False, True):
                with self.subTest(control=type(control).__name__, focused=focused):
                    control.setFocus() if focused else control.clearFocus()
                    for angle,pixel in [(QPoint(0,-120),QPoint()),(QPoint(0,120),QPoint()),
                                        (QPoint(-120,0),QPoint()),(QPoint(),QPoint(0,-24))]:
                        wheel(control,angle,pixel)
                    wheel(control,modifiers=Qt.KeyboardModifier.ControlModifier)
                    self.assertEqual(getter(),before);self.assertEqual(len(spy),0)
            control.hide()

    def test_wheel_over_number_editor_moves_its_page_once(self):
        spin=QSpinBox();spin.setValue(42);self.layout.addWidget(spin);APP.processEvents()
        bar=self.area.verticalScrollBar();self.assertGreater(bar.maximum(),0)
        wheel(self.area.viewport());distance=bar.value();self.assertGreater(distance,0)
        bar.setValue(0);wheel(spin.findChild(QLineEdit))
        self.assertEqual(spin.value(),42);self.assertEqual(bar.value(),distance)

    def test_open_dropdown_and_documents_still_scroll(self):
        combo=QComboBox();combo.addItems([str(i) for i in range(100)])
        combo.setStyleSheet('QComboBox {combobox-popup:0;}');combo.setMaxVisibleItems(5)
        self.layout.addWidget(combo);combo.showPopup();APP.processEvents()
        view=combo.view();wheel(view.viewport())
        self.assertGreater(view.verticalScrollBar().value(),0)
        self.assertEqual(combo.currentIndex(),0);combo.hidePopup()
        log=QPlainTextEdit();log.setPlainText('\n'.join(str(i) for i in range(100)))
        log.setFixedHeight(90);self.layout.addWidget(log);APP.processEvents()
        wheel(log.viewport());self.assertGreater(log.verticalScrollBar().value(),0)

    def test_controls_outside_scroll_areas_are_protected_and_keyboard_still_edits(self):
        spin=QSpinBox();spin.setValue(42);spin.show()
        wheel(spin);self.assertEqual(spin.value(),42)
        QTest.keyClick(spin,Qt.Key.Key_Up);self.assertEqual(spin.value(),43)
        edit=spin.findChild(QLineEdit);edit.selectAll();QTest.keyClicks(edit,'27')
        QTest.keyClick(edit,Qt.Key.Key_Return);self.assertEqual(spin.value(),27)
        spin.close();spin.deleteLater()

    def test_nested_scroll_area_bubbles_at_its_limit(self):
        inner=QScrollArea();inner.setFixedHeight(100)
        child=QWidget();child.setMinimumHeight(500);layout=QVBoxLayout(child)
        spin=QSpinBox();spin.setValue(42);layout.addWidget(spin)
        inner.setWidget(child);self.layout.addWidget(inner);APP.processEvents()
        inner.verticalScrollBar().setValue(inner.verticalScrollBar().maximum())
        wheel(spin)
        self.assertGreater(self.area.verticalScrollBar().value(),0)
        self.assertEqual(spin.value(),42)


if __name__ == '__main__':unittest.main()
