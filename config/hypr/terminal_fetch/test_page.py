"""Exercise import, save, discard and preview against an isolated profile."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terminal_fetch import artwork, model
from terminal_fetch.page import TerminalPage


class TerminalPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for mocked in (patch.object(model, 'ROOT', self.root),
                       patch.dict(os.environ, {'XDG_CACHE_HOME': str(self.root / 'cache')})):
            mocked.start(); self.addCleanup(mocked.stop)
        self.source = self.root / 'original.png'
        original = QImage(240, 120, QImage.Format.Format_ARGB32)
        original.fill(QColor('#8cb6ce')); original.save(str(self.source))
        self.page = TerminalPage(lambda fn, done, failed: done({'os': 'Test OS', 'cpu': 'Example CPU'}))
        self.page.resize(1280, 850); self.page.show(); self.app.processEvents()
        self.addCleanup(self.page.close)

    def test_import_copy_survives_source_removal_and_saves_actual_selection(self):
        self.assertFalse(self.page.dirty)
        self.assertTrue(self.page.use_image(self.source))
        settings = self.page.value(); path = model.logo_path(settings)
        copy = QImage(str(path))
        self.assertEqual((copy.width(), copy.height()), (480, 480))
        self.assertEqual(copy.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(copy.pixelColor(240, 240).name(), '#8cb6ce')
        self.source.unlink(); self.page.save()
        self.assertEqual(model.load(), settings); self.assertFalse(self.page.dirty)
        self.assertFalse(self.page.emblem.isHidden())
        self.assertLess(self.page.canvas.height(), 420)
        self.assertLess(self.page.preview_group.height(), self.page.height() - 100)
        self.page.logo.setCurrentIndex(self.page.logo.findData('fusion'))
        self.page.discard()
        self.assertEqual(self.page.value(), settings)

    def test_image_errors_do_not_replace_the_current_choice(self):
        self.page.use_image(self.source); previous = self.page.value()
        invalid = self.root / 'invalid.png'; invalid.write_text('not an image')
        self.assertFalse(self.page.use_image(invalid)); self.assertEqual(self.page.value(), previous)
        huge = self.root / 'huge.svg'
        huge.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="20000"/>')
        self.assertFalse(self.page.use_image(huge)); self.assertEqual(self.page.value(), previous)
        self.page.save(); model.logo_path(previous).unlink(); self.page.preview()
        self.assertTrue(self.page.emblem.isHidden()); self.assertFalse(self.page.apply.isEnabled())
        self.assertIn('unavailable', self.page.image_status.text())

    def test_custom_choice_requires_image_and_discard_preserves_saved_choices(self):
        self.page.logo.setCurrentIndex(self.page.logo.findData('custom'))
        self.assertFalse(self.page.apply.isEnabled())
        self.assertIn('Choose an image', self.page.image_status.text())
        self.page.discard(); self.assertFalse(self.page.dirty)
        self.page.enabled.setChecked(False)
        self.assertTrue(self.page.display.isHidden()); self.assertTrue(self.page.emblem.isHidden())
        self.assertIn('Welcome is off', self.page.preview_note.text())
        self.page.save(); self.assertFalse(model.load()['enabled'])

    def test_external_edits_are_not_overwritten(self):
        self.page.logo.setCurrentIndex(self.page.logo.findData('fusion'))
        external = {**model.DEFAULTS, 'show_user': False}; model.save(external)
        self.page.save()
        self.assertEqual(model.load(), external); self.assertTrue(self.page.dirty)
        self.assertIn('changed elsewhere', self.page.status.text())

    def test_svg_import_preserves_transparency_and_aspect_ratio(self):
        source = self.root / 'logo.svg'
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="160">'
                          '<rect width="80" height="160" fill="#bb4d76"/></svg>')
        imported = artwork.import_logo(source, self.root / 'logos')
        image = QImage(str(imported))
        self.assertEqual(image.pixelColor(0, 240).alpha(), 0)
        self.assertEqual(image.pixelColor(240, 240).name(), '#bb4d76')
        self.assertEqual(artwork.import_logo(source, self.root / 'logos'), imported)


if __name__ == '__main__': unittest.main()
