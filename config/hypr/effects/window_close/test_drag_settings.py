import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from effects.window_close import drag_settings


class DragSettingsTests(unittest.TestCase):
    def test_default_validation_and_external_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'drag-settings.json'
            values, token = drag_settings.load(path)
            self.assertEqual(values, dict(distance=2, hold_ms=120))
            custom, saved = drag_settings.save(dict(distance=4, hold_ms=200), token, path)
            self.assertEqual(drag_settings.load(path), (custom, saved))
            with self.assertRaisesRegex(ValueError, 'changed elsewhere'):
                drag_settings.save(values, token, path)
            self.assertEqual(drag_settings.load(path)[0], custom)
        for changes in ({'distance': 0}, {'distance': 25}, {'hold_ms': -1}, {'hold_ms': 501}, {'distance': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                drag_settings.validate(dict(drag_settings.DEFAULTS, **changes))

    def test_sliders_load_and_apply_the_same_settings_used_by_the_grip(self):
        from PyQt6.QtWidgets import QApplication, QSlider
        from effects.window_close.drag_page import DragSettings
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory, patch.object(drag_settings, 'PATH', Path(directory) / 'drag-settings.json'):
            page = DragSettings()
            sliders = page.findChildren(QSlider)
            sliders[0].setValue(5); sliders[1].setValue(180)
            self.assertEqual(page.controls['distance'].value(), 5)
            self.assertFalse(drag_settings.PATH.exists())
            page.apply()
            self.assertEqual(drag_settings.load()[0], dict(distance=5, hold_ms=180))
            other = DragSettings()
            self.assertEqual(other.controls['hold_ms'].value(), 180)
            page.defaults(); page.apply()
            self.assertEqual(drag_settings.load()[0], drag_settings.DEFAULTS)
            other.apply()
            self.assertIn('changed elsewhere', other.status.text())
            self.assertEqual(drag_settings.load()[0], drag_settings.DEFAULTS)
            page.close(); other.close()


if __name__ == '__main__': unittest.main()
