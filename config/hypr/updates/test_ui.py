"""Palette, badge CSS and update controls in an isolated offscreen window."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import service
import update_engine as engine
from app import Window, theme_runtime, STYLE


class UpdateUiTests(unittest.TestCase):
    def test_three_themes_and_settings_use_private_state(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix='xetal-updates-ui-') as directory:
            state = Path(directory)/'updates'
            with patch.object(service, 'STATE', state):
                service.publish(phase='available', current='1'*40, latest='2'*40,
                                title='A tested new desktop version', message='A new Xetal desktop update is available.',
                                github={'relation':'ahead'})
                for design in ('raw', 'modern', 'breakpoint'):
                    with patch.object(theme_runtime, 'design', return_value=design):
                        app.setPalette(theme_runtime.palette('dark',design)); app.setStyleSheet(STYLE)
                        window = Window(); window.show(); app.processEvents()
                        self.assertTrue(window.prepare.isEnabled()); self.assertFalse(window.progress.isVisible())
                        self.assertLess(window.prepare.geometry().bottom(), window.height())
                        self.assertFalse(window.grab().isNull())
                        window.automatic.setChecked(False)
                        self.assertFalse(service.preferences()['automatic'])
                        service.publish(phase='preparing'); window.refresh(); app.processEvents()
                        self.assertFalse(window.prepare.isEnabled()); self.assertTrue(window.progress.isVisible())
                        service.publish(phase='runtime-required',current='2'*40,latest='2'*40)
                        window.refresh(); app.processEvents()
                        self.assertTrue(window.prepare.isEnabled())
                        self.assertEqual(window.prepare.text(),'Open compositor setup')
                        with patch('app.subprocess.Popen'):
                            window.prepare.click()
                        self.assertEqual(service.take_request(),'setup')
                        window.close(); window.deleteLater(); service.publish(phase='available')

    def test_gtk_badge_animation_parses_in_all_palettes(self):
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk
        import update_widget
        for design in ('raw','modern','breakpoint'):
            for mode in ('dark','light','contrast'):
                provider = Gtk.CssProvider()
                provider.load_from_data(update_widget.style(theme_runtime.colors(mode,design)).encode())


if __name__ == '__main__': unittest.main()
