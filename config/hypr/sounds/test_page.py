"""Sound previews and UI drafts never overwrite newer choices."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEvent
from sounds import model
from sounds.page import SoundsPage

QT=QApplication.instance() or QApplication([])


class SoundPageTests(unittest.TestCase):
    def setUp(self):
        self.load=patch.object(model,'load',return_value=(copy.deepcopy(model.DEFAULTS),'baseline'));self.load.start()
        self.window=SoundsPage();self.window.resize(1080,680);self.window.show();QT.processEvents()
    def tearDown(self):
        self.window.close();self.window.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.load.stop()
    def test_pack_choice_is_a_draft_and_mute_does_not_disable_previews(self):
        self.window.cards['gildedhollow'].click()
        self.assertEqual(self.window.draft['pack'],'gildedhollow');self.assertFalse(self.window.follow.isChecked())
        self.window.enabled.setChecked(False);self.assertTrue(self.window.dirty)
        self.assertTrue(all(button.isEnabled() for button in self.window.preview_buttons.values()))
        self.window.refresh();self.assertFalse(self.window.draft['enabled'])
        self.window.discard.click();self.assertEqual(self.window.draft,model.DEFAULTS);self.assertFalse(self.window.dirty)
    def test_failed_save_keeps_the_draft_and_baseline(self):
        self.window.volume.setValue(19)
        with patch.object(model,'save',side_effect=ValueError('changed in another window')):
            self.window.save()
        self.assertTrue(self.window.dirty);self.assertEqual(self.window.draft['volume'],19)
        self.assertIn('another window',self.window.status.text())
    def test_preview_uses_selected_pack_and_unsaved_volume(self):
        self.window.cards['porcelainink'].click();self.window.volume.setValue(24)
        with patch('sounds.page.QProcess.start') as start:
            self.window.preview('question')
            self.assertEqual(start.call_args.args[1][1:],['question','--preview','--pack','porcelainink','--volume','24'])
            self.assertTrue(self.window.timer.isActive())
            self.window.hide();self.assertFalse(self.window.timer.isActive());self.assertIsNone(self.window.player)


if __name__=='__main__':unittest.main()
