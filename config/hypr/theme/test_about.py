"""About is read-only even when opened over staged application settings."""
import os
from pathlib import Path
import tempfile
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QEvent, QPoint, QRect
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QScrollArea, QScrollBar
from fusion_about import AboutDialog, show_about
from interface_settings import InterfaceSettingsDialog, write_preferences
QT = QApplication.instance() or QApplication([])

class AboutTests(unittest.TestCase):
    def tearDown(self):
        for widget in QT.topLevelWidgets(): widget.close(); widget.deleteLater()
        QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_logo_credits_and_clipboard(self):
        parent = QWidget()
        dialog = show_about(parent, 'Example', 'Example description', 'Upstream credit')
        self.assertFalse(dialog.findChild(QLabel, 'aboutEngineLogo').pixmap().isNull())
        self.assertEqual(dialog.findChild(QLabel, 'aboutAuthor').text(), 'Xetal — Thiago Costa')
        self.assertEqual(dialog.findChild(QLabel, 'aboutCredits').text(), 'Upstream credit')
        self.assertIs(show_about(parent, 'Example', ''), dialog)
        for service in ('Discord', 'Echo'):
            button = dialog.findChild(QPushButton, f'copy{service}Username')
            button.click()
            self.assertEqual(QT.clipboard().text(), 'xetal')
            self.assertEqual(button.text(), 'Copied')
        dialog.close(); QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertIsNone(parent.findChild(AboutDialog, 'fusionAboutDialog'))

    def test_settings_about_keeps_preferences_and_parent_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'interface.json'
            write_preferences(path, dict(show_window_controls=False, hidden_pages=['example'], future='keep'))
            before = path.read_bytes(); writes = []
            settings = InterfaceSettingsDialog('Example', path, [], writes.append,
                about_description='Description', about_credits='Credit')
            settings.show()
            settings.findChild(QPushButton, 'aboutApplicationButton').click()
            dialog = settings.findChild(AboutDialog, 'fusionAboutDialog')
            self.assertIsNotNone(dialog)
            self.assertEqual(dialog.findChild(QLabel, 'aboutAppName').text(), 'Example')
            self.assertEqual(dialog.findChild(QLabel, 'aboutCredits').text(), 'Credit')
            dialog.close(); QT.processEvents()
            self.assertTrue(settings.isVisible()); self.assertEqual(path.read_bytes(), before)
            self.assertEqual(writes, [])

    def test_all_information_fits_without_scrollbars_even_after_small_resize(self):
        parent = QWidget()
        for point_size in (10, 15):
            parent.setFont(QFont('Sans Serif', point_size))
            dialog = show_about(parent, 'Control Panel',
                'System tools and desktop management for Hyper Fusion.',
                "Powered by the CachyOsTools C++ engine. All system tools and the ISO builder are included in this desktop's source. GPLv3.")
            QT.processEvents()
            dialog.resize(480, 400)
            QT.processEvents()
            self.assertEqual(dialog.findChildren(QScrollArea), [])
            self.assertEqual(dialog.findChildren(QScrollBar), [])
            for widget in dialog.findChildren(QLabel) + dialog.findChildren(QPushButton):
                if widget.isVisible():
                    bounds = QRect(widget.mapTo(dialog, QPoint()), widget.size())
                    self.assertTrue(dialog.rect().contains(bounds), widget.objectName())
                    if isinstance(widget, QLabel) and widget.wordWrap():
                        self.assertGreaterEqual(widget.height(), widget.heightForWidth(widget.width()), widget.text())
            dialog.close(); QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)

if __name__ == '__main__': unittest.main()
