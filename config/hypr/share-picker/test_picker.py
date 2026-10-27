import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt,QPoint
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from model import portal_windows, match_windows, selection, logical_size
from app import Picker

QT=QApplication.instance() or QApplication([])
MONITOR={'id':0,'name':'DP-1','width':2560,'height':1440,'scale':1.25,'transform':0,'x':0,'y':0}
CLIENT={'address':'0x12345678','class':'example','title':'A window','mapped':True,'workspace':{'name':'4'},'monitor':0,'pid':12}
SOURCE='71[HC>]example[HT>]A window[HE>]305419896[HA>]'


class ContractTests(unittest.TestCase):
    def test_portal_handle_is_not_compositor_address(self):
        window=match_windows(portal_windows(SOURCE),[CLIENT])[0]
        self.assertEqual(window['address'],'0x12345678')
        self.assertEqual(selection(window),'[SELECTION]/window:71\n')
        self.assertEqual(selection(window,True),'[SELECTION]r/window:71\n')

    def test_duplicate_and_invalid_portal_handles_are_ignored(self):
        windows=portal_windows(SOURCE+SOURCE+'999999999999[HC>]bad[HT>]Bad[HE>]1[HA>]garbage')
        self.assertEqual(len(windows),1)

    def test_identical_titles_do_not_retarget_closed_window(self):
        other={**CLIENT,'address':'0x98765432'}
        window=match_windows(portal_windows(SOURCE),[other])[0]
        self.assertFalse(window['available'])

    def test_region_output_and_rejection(self):
        self.assertEqual(selection({'kind':'region','name':'DP-1','rect':(10,20,600,400)}),
                         '[SELECTION]/region:DP-1@10,20,600,400\n')
        for source in [{'kind':'screen','name':'DP-1\nwindow:7'},
                       {'kind':'region','name':'DP-1','rect':(-1,20,600,400)},
                       {'kind':'region','name':'DP-1','rect':(0,0,0,400)}]:
            with self.assertRaises(ValueError):selection(source)

    def test_rotation_and_scale(self):
        self.assertEqual(logical_size(MONITOR),(2048,1152))
        self.assertEqual(logical_size({**MONITOR,'transform':1}),(1152,2048))


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.calls=patch('app.ctl',side_effect=lambda cmd:[CLIENT] if cmd=='clients' else [MONITOR]);self.calls.start()
        self.env=patch.dict(os.environ,{'HYPRLAND_INSTANCE_SIGNATURE':''});self.env.start()
        self.window=Picker(monitors=[MONITOR],clients=[CLIENT],source_text=SOURCE)

    def tearDown(self):
        self.window.close();self.window.deleteLater();QT.processEvents();self.env.stop();self.calls.stop()

    def test_cancel_emits_no_selection(self):
        self.window.choose(self.window.screen_cards[0]);self.window.close()
        self.assertEqual(self.window.output,'')

    def test_explicit_confirmation_required(self):
        self.window.choose(self.window.screen_cards[0])
        self.assertEqual(self.window.output,'')
        self.assertFalse(self.window.remember.isChecked())
        self.window.confirm();self.assertEqual(self.window.output,'[SELECTION]/screen:DP-1\n')

    def test_tab_change_clears_choice(self):
        self.window.choose(self.window.screen_cards[0]);self.window.tabs.setCurrentIndex(1)
        self.assertIsNone(self.window.chosen);self.assertFalse(self.window.share.isEnabled())

    def test_closed_window_blocks_confirmation(self):
        self.window.choose(self.window.window_cards[0])
        with patch('app.ctl',side_effect=lambda cmd:[] if cmd=='clients' else [MONITOR]):self.window.confirm()
        self.assertEqual(self.window.output,'');self.assertFalse(self.window.share.isEnabled())

    def test_region_mouse_selection_uses_logical_coordinates(self):
        self.window.queue.stop();self.window.tabs.setCurrentIndex(2);self.window.show();QT.processEvents()
        canvas=self.window.region;area=canvas.image_rect()
        start=QPoint(round(area.x()+area.width()*.25),round(area.y()+area.height()*.25))
        end=QPoint(round(area.x()+area.width()*.75),round(area.y()+area.height()*.75))
        QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(canvas,end);QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=end)
        self.assertIsNotNone(self.window.chosen)
        for actual,expected in zip(self.window.chosen['rect'],(512,288,1024,576)):
            # Two rounded pointer positions can span one thumbnail pixel extra.
            self.assertLessEqual(abs(actual-expected),6)


if __name__=='__main__':unittest.main()
