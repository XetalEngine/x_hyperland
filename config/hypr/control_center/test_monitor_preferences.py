import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'theme'))
import monitor_preferences as prefs
import desktop_settings as settings
from test_desktop import monitors
from switcher import placement

class MonitorTests(unittest.TestCase):
    def test_primary_is_saved_with_display_layout_and_does_not_follow_focus(self):
        data=monitors();data[1]['focused']=True
        with patch.object(prefs,'primary_name',return_value='DP-1'):
            models=settings.display_models(data)
        self.assertEqual([m['name'] for m in models if m['primary']],['DP-1'])
        before=copy.deepcopy(models)
        for m in models:m['primary']=m['name']=='DP-2'
        self.assertNotEqual(settings.layout_state(before),settings.layout_state(models))
        config=settings.display_config(models,'# note\n# xetal-primary-monitor: DP-1\nmonitor = OLD,disable\n')
        self.assertEqual(config.count(prefs.MARKER),1);self.assertIn('DP-2',config)
        self.assertIn('monitor = OLD,disable',config)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'displays.conf';path.write_text(config);self.assertEqual(prefs.primary_name(path),'DP-2')
        # Primary changes are metadata, never a display-driver rollback failure.
        self.assertTrue(settings.matches_layout(models,before))
    def test_pointer_selection_handles_negative_origin_rotation_and_scale(self):
        a=dict(name='A',id=0,width=1920,height=1080,scale=1,x=0,y=0,focused=True)
        b=dict(name='B',id=1,width=1080,height=1920,scale=2,transform=1,x=-960,y=0)
        self.assertEqual(prefs.select([a,b],'pointer',pointer={'x':-900,'y':200})['name'],'B')
        self.assertEqual(prefs.select([a,b],'active')['name'],'A')
        self.assertEqual(prefs.select([a,b],'primary',primary='B')['name'],'B')
        self.assertEqual(prefs.select([a,b],'primary',primary='disconnected')['name'],'A')
        b['disabled']=True;self.assertEqual(prefs.select([a,b],'primary',primary='B')['name'],'A')
    def test_checkbox_sets_exactly_one_primary_and_emits_change(self):
        from PyQt6.QtWidgets import QApplication
        from display_page import Arrangement
        app=QApplication.instance() or QApplication([]);view=Arrangement();view.models=settings.display_models(monitors());view.resize(900,400);view.show();app.processEvents()
        changes=[];view.edited.connect(lambda:changes.append(True))
        view.primary_boxes['DP-2'].click();app.processEvents()
        self.assertEqual([m['name'] for m in view.models if m['primary']],['DP-2']);self.assertTrue(changes)
        view.close()
    def test_first_frame_rule_is_relative_to_selected_scaled_monitor(self):
        calls=[]
        m=dict(id=2,width=1080,height=1920,scale=1.5,transform=1,reserved=[0,30,0,0])
        self.assertEqual(placement.prepare(m,1000,500,lambda *args:calls.append(args) or 'ok\nok\nok'),(140,125))
        self.assertIn(':monitor 2',calls[0][1]);self.assertIn(':move 140 125',calls[0][1])

if __name__=='__main__':unittest.main()
