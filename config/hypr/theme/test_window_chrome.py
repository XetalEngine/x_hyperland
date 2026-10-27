import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QWidget,QDialog,QVBoxLayout,QLabel,QMessageBox,QToolButton
import window_chrome

QT=QApplication.instance() or QApplication([])
window_chrome.install(QT)


class CloseTests(unittest.TestCase):
    def test_close_button_respects_a_windows_close_guard(self):
        class Guarded(QWidget):
            def closeEvent(self,event):event.ignore()
        window=Guarded();layout=QVBoxLayout(window);button=window_chrome.close_button(window);layout.addWidget(button)
        window.show();QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertTrue(window.isVisible());window.hide();window.deleteLater()

    def test_dialog_has_space_for_header_and_x_rejects(self):
        dialog=QDialog();dialog.setWindowTitle('Choose something');layout=QVBoxLayout(dialog);label=QLabel('Body');layout.addWidget(label)
        dialog.resize(400,180);dialog.show();QTest.qWait(20)
        self.assertTrue(dialog.xetal_header.isVisible())
        self.assertGreaterEqual(label.geometry().top(),dialog.xetal_header.geometry().bottom())
        self.assertEqual(len(dialog.findChildren(QToolButton,'windowClose')),1)
        dialog.hide();dialog.show();QTest.qWait(10)
        self.assertEqual(len(dialog.findChildren(QToolButton,'windowClose')),1)
        QTest.mouseClick(dialog.findChild(QToolButton,'windowClose'),Qt.MouseButton.LeftButton)
        self.assertFalse(dialog.isVisible());self.assertEqual(dialog.result(),QDialog.DialogCode.Rejected);dialog.deleteLater()

    def test_confirmation_x_is_cancel_not_destructive_action(self):
        box=QMessageBox(QMessageBox.Icon.Question,'Remove item?','Remove this item?',
                        QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel);box.show();QTest.qWait(20)
        self.assertTrue(box.findChild(QToolButton,'windowClose').isVisible())
        box.grab().save('/tmp/hypr-close-dialog.png')
        QTest.mouseClick(box.findChild(QToolButton,'windowClose'),Qt.MouseButton.LeftButton)
        self.assertEqual(box.standardButton(box.clickedButton()),QMessageBox.StandardButton.Cancel);box.deleteLater()


if __name__=='__main__':unittest.main(verbosity=2)
