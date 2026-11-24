"""Audio navigation keeps the same sound settings and protects unsaved drafts."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication,QMessageBox
import app
from audio_page import AudioPage
from sounds import model as sounds
from effects.window_close import behavior
from effects.window_close.behavior_page import WindowBehaviorPage

QT=QApplication.instance() or QApplication([])


def immediate(fn,done,failed):
    try:value=fn()
    except Exception as error:failed(str(error))
    else:done(value)


class AudioNavigationTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.tmp=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.path=self.tmp/'sounds.json'
        original_load,original_save=sounds.load,sounds.save
        self.stack.enter_context(patch.object(sounds,'load',side_effect=lambda *args:original_load(self.path)))
        self.stack.enter_context(patch.object(sounds,'save',side_effect=lambda value,token:original_save(value,token,self.path)))
        self.stack.enter_context(patch.object(app,'async_run',lambda *args:None))
        self.stack.enter_context(patch.object(AudioPage,'start_events'))
        self.window=app.Window('audio')
        self.window.pages['audio'].devices.listen=False
        self.addCleanup(self.dispose)

    def dispose(self):
        self.window.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_tabs_route_to_one_editor_and_preserve_audio_draft(self):
        audio=self.window.pages['audio'];theme=self.window.pages['theme']
        self.assertEqual([audio.tabs.tabText(i) for i in range(audio.tabs.count())],['Devices','System Audio'])
        self.assertNotIn('Sounds',[theme.tabs.tabText(i) for i in range(theme.tabs.count())])
        self.assertIs(theme.sounds_page,audio.sounds)
        sound=audio.sounds;sound.pick('amazon');sound.volume.setValue(43)
        theme.mix_page.open_details(sound)
        self.assertIs(self.window.tabs.currentWidget(),audio);self.assertIs(audio.tabs.currentWidget(),sound)
        audio.tabs.setCurrentWidget(audio.devices)
        self.window.request({'tab':'audio','system_audio':True})
        self.assertIs(audio.tabs.currentWidget(),sound)
        audio.tabs.setCurrentWidget(audio.devices);audio.open_system_audio();audio.refresh()
        self.assertTrue(audio.dirty);self.assertFalse(theme.dirty)
        self.assertEqual(sound.draft['pack'],'amazon');self.assertEqual(sound.draft['volume'],43)
        self.assertTrue(theme.pending_components())
        self.assertFalse(self.path.exists())
        sound.save();self.assertFalse(audio.dirty)
        self.assertEqual(sounds.load()[0]['pack'],'amazon');self.assertEqual(sounds.load()[0]['volume'],43)

    def test_cancel_close_keeps_system_audio_edits_and_hiding_stops_preview(self):
        audio=self.window.pages['audio'];audio.sounds.volume.setValue(23)
        event=QCloseEvent()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel) as question:
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted());self.assertIn('Audio',question.call_args.args[2])
        self.assertTrue(audio.dirty)
        audio.open_system_audio();audio.show();QT.processEvents()
        with patch.object(audio.sounds,'stop_preview') as stop:
            audio.tabs.setCurrentWidget(audio.devices);QT.processEvents();stop.assert_called()

    def test_window_behavior_has_default_and_persistent_off_choice(self):
        with patch.object(behavior,'PATH',self.tmp/'behavior.json'),patch.object(behavior.controller,'start'),patch.object(behavior.controller,'hypr',return_value='{"titlebar_protection_supported":true}'):
            page=WindowBehaviorPage(immediate)
            try:
                self.assertTrue(page.protection.isChecked());self.assertFalse(page.dirty)
                page.protection.setChecked(False);page.save()
                self.assertFalse(page.dirty);self.assertFalse(behavior.load()[0]);page.refresh()
                self.assertFalse(page.protection.isChecked())
                page.defaults.click();self.assertTrue(page.dirty)
                page.discard.click();self.assertFalse(page.dirty);self.assertFalse(page.protection.isChecked())
            finally:page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        effects=self.window.pages['theme'].appearance
        self.assertIn('Window Behavior',[effects.tabs.tabText(i) for i in range(effects.tabs.count())])


if __name__=='__main__':unittest.main()
