import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recording import backend, page

QT = QApplication.instance() or QApplication([])


def synchronous(fn, done, failed):
    try: result = fn()
    except Exception as error: failed(str(error))
    else: done(result)


class RecordingPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name)/'settings.json'
        load, save = backend.load, backend.save
        self.patches = [patch.object(backend, 'load', side_effect=lambda path=self.path: load(path)),
                        patch.object(backend, 'save', side_effect=lambda v, t: save(v, t, self.path)),
                        patch.object(backend, 'videos_directory', return_value=Path(self.tmp.name))]
        for p in self.patches: p.start()
        self.widget = page.CapturePage(synchronous)

    def tearDown(self):
        self.widget.timer.stop(); self.widget.close()
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_draft_survives_status_refresh_and_saves(self):
        self.widget.fps.setValue(30)
        self.widget.received({'phase': 'idle'}); self.widget.refresh()
        self.assertEqual(self.widget.fps.value(), 30); self.assertTrue(self.widget.dirty)
        self.assertFalse(self.widget.record.isEnabled())
        self.widget.save(); self.assertFalse(self.widget.dirty)
        self.assertEqual(backend.load()[0]['fps'], 30)

    def test_stop_remains_available_with_unsaved_options(self):
        self.widget.received({'phase': 'recording', 'monitor': 'DP-1', 'fps': 64})
        self.widget.audio.setCurrentIndex(2)
        self.assertTrue(self.widget.record.isEnabled())
        with patch.object(page.service, 'request', return_value={'phase': 'stopping'}) as request:
            self.widget.toggle(); request.assert_called_once_with('toggle')
        self.assertFalse(self.widget.record.isEnabled()); self.assertTrue(self.widget.dirty)

    def test_external_edit_is_preserved(self):
        self.widget.fps.setValue(30); self.path.write_text('{"fps": 24}')
        self.widget.save()
        self.assertIn('elsewhere', self.widget.status.text()); self.assertTrue(self.widget.dirty)
        self.assertEqual(backend.load()[0]['fps'], 24)


if __name__ == '__main__': unittest.main()
