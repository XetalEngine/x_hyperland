"""The actual settings window keeps navigation and pages usable after hiding them."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QEvent, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton
import app
import keys
from interface_settings import read_preferences, write_preferences

QT = QApplication.instance() or QApplication([])


class InterfaceTests(unittest.TestCase):
    def test_all_layouts_hide_restore_and_keep_direct_page_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'hyprland.conf').write_text('$mainMod = SUPER\n' + keys.SOURCE + '\n')
            (root/'keybindings.conf').write_text('bind = SUPER, Q, exec, kitty\n')
            store = keys.Store(root, root/'key-history')
            path = root/'control_center/state/interface.json'
            write_preferences(path, dict(show_window_controls=False, hidden_pages=['audio', 'network']))
            with patch.object(keys, 'ROOT', root), patch.object(keys, 'Store', return_value=store), patch.object(app, 'async_run', lambda *args: None):
                window = app.Window(visible=False)
                try:
                    self.assertTrue(window.window_controls.isHidden())
                    self.assertFalse(window.app_settings_button.isHidden())
                    for style in ('classic', 'sidebar', 'ribbon', 'modern'):
                        with patch.object(app.theme_runtime, 'layout', return_value=style):
                            window.apply_design()
                            self.assertTrue(window.rail_buttons['audio'].isHidden())
                            self.assertFalse(window.tabs.isTabVisible(window.tabs.indexOf(window.pages['audio'])))
                            window.switch('audio')
                            self.assertIs(window.tabs.currentWidget(), window.pages['audio'])
                    values = dict(show_window_controls=True, hidden_pages=list(window.pages))
                    window.apply_interface_preferences(values)
                    self.assertFalse(window.window_controls.isHidden())
                    self.assertIs(window.tabs.currentWidget(), window.empty_page)
                    self.assertFalse(window.app_settings_button.isHidden())
                    window.apply_interface_preferences(dict(show_window_controls=False, hidden_pages=[]))
                    self.assertIsNot(window.tabs.currentWidget(), window.empty_page)
                    self.assertTrue(all(not button.isHidden() for button in window.rail_buttons.values()))
                    self.assertEqual(read_preferences(path)['hidden_pages'], ['audio', 'network'])
                    observed = {}
                    before = path.read_bytes()
                    def inspect_about():
                        settings = window.findChild(QDialog, 'interfaceSettingsDialog')
                        if settings is None: return
                        try:
                            settings.findChild(QPushButton, 'aboutApplicationButton').click()
                            about = settings.findChild(QDialog, 'fusionAboutDialog')
                            observed['name'] = about.findChild(QLabel, 'aboutAppName').text()
                            observed['logo'] = not about.findChild(QLabel, 'aboutEngineLogo').pixmap().isNull()
                            about.close()
                        finally:
                            settings.reject()
                    QTimer.singleShot(0, inspect_about)
                    window.open_interface_settings()
                    self.assertEqual(observed, dict(name='Fusion Settings', logo=True))
                    self.assertEqual(path.read_bytes(), before)
                finally:
                    window.refresh_timer.stop(); window.deleteLater()
                    QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == '__main__': unittest.main()
