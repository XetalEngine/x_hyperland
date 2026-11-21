"""Exercise per-output HDR editing without changing real display modes."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]/'config/hypr'
sys.path[:0] = [str(ROOT/'control_center'), str(ROOT/'theme')]
from PyQt6.QtWidgets import QApplication
from display_page import DisplaysPage
import desktop_settings as settings
from test_desktop import monitors

QT = QApplication.instance() or QApplication([])


class HDRTests(unittest.TestCase):
    def setUp(self):
        raw = monitors()
        raw[0]['hardwareDetails'] = {'hdr': True}
        raw[1]['hardwareDetails'] = {'hdr': False}
        self.models = settings.display_models(raw)
        self.page = DisplaysPage(lambda *_: None)
        self.page.loaded((copy.deepcopy(self.models), 'fixture'))
        self.page.resize(1100, 850); self.page.show(); QT.processEvents()
        self.addCleanup(self.page.close)
        self.page.select('DP-1')

    def test_color_edit_enables_apply_only_for_selected_display_and_discard_restores(self):
        self.assertFalse(self.page.apply.isEnabled())
        self.assertEqual(self.page.hdr.currentData(), 'srgb')
        with patch.object(settings, 'ctl') as ipc:
            self.page.hdr.setCurrentIndex(self.page.hdr.findData('hdr'))
            self.assertTrue(self.page.apply.isEnabled())
            self.assertTrue(self.page.sdr_brightness.isVisible())
            self.page.sdr_brightness.setValue(125)
            self.page.sdr_saturation.setValue(90)
            self.page.select('DP-2')
            self.assertEqual(self.page.hdr.currentData(), 'srgb')
            self.assertFalse(self.page.sdr_brightness.isVisible())
            self.page.select('DP-1')
            self.assertEqual(self.page.sdr_brightness.value(), 125)
            self.assertEqual(self.page.models[0]['bitdepth'], 10)
            self.assertEqual(self.page.models[0]['sdrsaturation'], .9)
            self.page.discard_changes()
            self.assertEqual(settings.layout_state(self.page.models), settings.layout_state(self.models))
            self.assertFalse(self.page.apply.isEnabled())
            ipc.assert_not_called()  # editing is a draft until Apply & preview

    def test_non_hdr_output_cannot_select_hdr_but_unknown_support_can_preview(self):
        self.page.select('DP-2')
        for mode in settings.HDR_MODES:
            self.assertFalse(self.page.hdr.model().item(self.page.hdr.findData(mode)).isEnabled())
        self.page.models[1]['hdr_capable'] = None
        self.page.sync_form()
        self.assertTrue(self.page.hdr.model().item(self.page.hdr.findData('hdr')).isEnabled())

    def test_hdr_brightness_and_saturation_fit_the_display_panel(self):
        self.page.hdr.setCurrentIndex(self.page.hdr.findData('hdr'))
        QT.processEvents()
        from PyQt6.QtWidgets import QScrollArea
        scroll = self.page.findChild(QScrollArea)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)


if __name__ == '__main__': unittest.main()
