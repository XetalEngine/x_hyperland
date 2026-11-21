import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt,QByteArray,QBuffer,QIODevice
from PyQt6.QtGui import QImage,QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from clipboard import app as ui
from clipboard.store import Store

class ClipboardFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        directory=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(ui,'STATE',directory))
        self.stack.enter_context(patch.object(ui.History,'start_collector'))
        self.stack.enter_context(patch.object(ui.History,'start_keeper'))
        self.ctl=self.stack.enter_context(patch.object(ui,'ctl',return_value='{}'))
        self.store=Store(directory/'pins.json');self.window=ui.History(self.store,Path('/unused'))
        self.addCleanup(self.window.deleteLater);self.addCleanup(self.window.stop)

class ClipboardUI(ClipboardFixture):
    def test_search_and_keyboard_choose_exactly_once(self):
        self.store.add('text/plain;charset=utf-8',b'First item');self.store.add('text/plain;charset=utf-8','café second'.encode())
        self.window.populate();self.assertEqual(self.window.list.count(),2)
        self.window.search.setText('CAFÉ');self.assertEqual(self.window.list.count(),1)
        self.assertEqual(self.window.selected().text,'café second')
        with patch.object(self.window,'choose') as choose:
            QTest.keyClick(self.window.search,Qt.Key.Key_Return);choose.assert_called_once()
    def test_pin_filter_clear_and_delete(self):
        self.store.add('text/plain;charset=utf-8',b'pin me');self.window.populate();self.window.toggle_pin()
        self.assertTrue(self.window.selected().pinned);self.assertEqual(self.window.pin.text(),'Unpin')
        self.store.add('text/plain;charset=utf-8',b'temporary');self.window.clear()
        self.assertEqual(self.window.list.count(),1);self.window.remove();self.assertEqual(self.window.list.count(),0)
        self.assertFalse(self.window.copy.isEnabled())
    def test_image_preview_and_invalid_image(self):
        image=QImage(320,200,QImage.Format.Format_RGB32);image.fill(QColor('#39a9ff'))
        data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG')
        payload=bytes(data);self.store.add('image/png',payload);self.window.populate()
        self.assertEqual(self.window.list.count(),1);self.assertIn('320 × 200',self.window.list.item(0).text())
        self.assertIsNone(ui.image_preview('image/png',b'not a png'))
        huge=QImage(4100,4000,QImage.Format.Format_Grayscale8);huge.fill(0)
        data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly);huge.save(buffer,'PNG')
        self.assertIsNone(ui.image_preview('image/png',bytes(data)))
    def test_pause_is_persistent_and_late_data_is_ignored(self):
        self.window.pause.setChecked(True);self.assertTrue(self.store.paused)
        self.assertIn('true',(ui.STATE/'preferences.json').read_text())
        self.assertFalse(self.store.add('text/plain;charset=utf-8',b'private'))
        self.window.pause.setChecked(False);self.assertFalse(self.store.paused)
    def test_pausing_history_keeps_the_current_copy_until_logout(self):
        keeper=Mock();self.window.keeper=keeper
        self.window.pause.setChecked(True)
        self.assertTrue(self.store.paused);keeper.kill.assert_not_called()
        self.window.pause.setChecked(False);keeper.kill.assert_not_called()
        self.window.stop();keeper.kill.assert_called_once()
        self.window.keeper=None
    def test_closing_does_not_steal_focus_from_another_app(self):
        self.window.previous='0xab12';self.ctl.return_value='{"class":"other"}'
        self.window.dismiss();self.assertEqual(self.ctl.call_count,1)
        self.ctl.reset_mock();self.ctl.return_value='{"class":"fusion-clipboard"}'
        self.window.dismiss();self.ctl.assert_any_call('dispatch','focuswindow','address:0xab12')
    def test_unreadable_pins_do_not_disable_recent_history(self):
        self.store.pins_unavailable=True;self.store.add('text/plain;charset=utf-8',b'recent');self.window.populate()
        self.assertTrue(self.window.copy.isEnabled());self.assertFalse(self.window.pin.isEnabled())
        self.assertIn('untouched',self.window.status.text())

if __name__=='__main__':unittest.main()
