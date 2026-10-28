"""A bar click dismissed on press must not reopen the menu on release."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bar_toggle


class BarToggleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'dismissed.json'
        self.point=[45,16];self.now=100.0
        for item in (patch.object(bar_toggle,'marker_path',return_value=self.path),
                     patch.object(bar_toggle,'pointer',side_effect=lambda:self.point),
                     patch.object(bar_toggle.time,'monotonic',side_effect=lambda:self.now)):
            item.start();self.addCleanup(item.stop)

    def test_press_dismissal_consumes_only_the_matching_release(self):
        bar_toggle.remember();self.now+=.4
        self.assertTrue(bar_toggle.consume())
        self.assertFalse(bar_toggle.consume(),'The next click must open Apps normally')

    def test_desktop_click_does_not_block_a_later_apps_click(self):
        self.point=[1200,600];bar_toggle.remember();self.point=[45,16]
        self.assertFalse(bar_toggle.consume())
        self.assertFalse(self.path.exists())

    def test_small_mouse_motion_between_press_and_release_is_allowed(self):
        bar_toggle.remember();self.point=[49,19]
        self.assertTrue(bar_toggle.consume())

    def test_old_marker_does_not_swallow_another_click(self):
        bar_toggle.remember();self.now+=bar_toggle.MAX_AGE+1
        self.assertFalse(bar_toggle.consume())

    def test_corrupt_or_future_marker_is_discarded(self):
        for contents in ('not json',json.dumps({'time':102,'position':[45,16]}),
                         json.dumps({'time':100,'position':[None,16]})):
            self.path.write_text(contents)
            self.assertFalse(bar_toggle.consume())
            self.assertFalse(self.path.exists())

    def test_unavailable_pointer_leaves_normal_launching_available(self):
        self.point=None;bar_toggle.remember()
        self.assertFalse(bar_toggle.consume())


if __name__=='__main__':unittest.main()
