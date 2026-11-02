import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent.parent))
from effects.wobbly import model,controller


class OptionsTests(unittest.TestCase):
    def test_all_original_options_defaults_and_ranges(self):
        options=list(ET.parse(ROOT/'compiz-options.xml').iter('option'))
        self.assertEqual({o.get('name') for o in options},set(model.DEFAULTS)-{'enabled'})
        for o in options:
            key=o.get('name');kind=o.get('type');value=o.findtext('default') or ''
            if kind in ('bool','bell'):value=value=='true'
            elif kind in ('float','int'):value=float(value)
            self.assertEqual(model.DEFAULTS[key],value,key)
            if key in model.RANGES:self.assertEqual(model.RANGES[key],(float(o.findtext('min')),float(o.findtext('max'))))
    def test_round_trip_and_invalid_settings(self):
        self.assertEqual(model.decode(model.encode(model.DEFAULTS)),model.DEFAULTS)
        for key,value in [('friction',float('nan')),('spring_k',11),('grid_resolution',1.5),('min_grid_size',3),
                          ('shiver','yes'),('snap_key','<Shift><Shift>'),('snap_key','Q'),('move_window_match','Normal &'),('map_window_match','(Normal')]:
            with self.subTest(key=key),self.assertRaises(ValueError):model.validate(dict(model.DEFAULTS,**{key:value}))
        with self.assertRaises(ValueError):model.decode(model.encode(model.DEFAULTS).replace('"enabled": false','"enabled": false, "enabled": true'))
    def test_original_and_extended_window_matches(self):
        for value in ('','Any','Normal | Dialog','Normal & !class=kitty','(Normal | Dialog) & title=*Settings*','xid=0x1234','state=maximized'):
            self.assertEqual(model.validate_match(value),value)
        for value in ('UnknownThing','Normal || Dialog','Normal)','()','class=','floating=2','state=hidden'):
            with self.subTest(value=value),self.assertRaises(ValueError):model.validate_match(value)
    def test_failed_load_restores_saved_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json';path.write_text(model.encode(model.DEFAULTS));before=path.read_bytes();values,token=model.load(path)
            values['friction']=6
            with patch.object(controller,'instance_dir',return_value=Path(directory)),patch.object(controller,'activate',side_effect=RuntimeError('load failed')):
                with self.assertRaisesRegex(RuntimeError,'load failed'):controller.save(values,token,path)
            self.assertEqual(path.read_bytes(),before)
    def test_external_change_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json';path.write_text(model.encode(model.DEFAULTS));values,token=model.load(path)
            path.write_text(model.encode(dict(values,friction=6)))
            with patch.object(controller,'instance_dir',return_value=Path(directory)),self.assertRaisesRegex(ValueError,'elsewhere'):controller.save(values,token,path)
            self.assertEqual(model.load(path)[0]['friction'],6)
    def test_original_physics_and_native_matcher(self):
        with tempfile.TemporaryDirectory() as directory:
            exe=Path(directory)/'engine'
            subprocess.run(['g++','-std=c++23','-O2',str(ROOT/'native/test_engine.cpp'),'-o',str(exe),'-ljson-c'],check=True,capture_output=True)
            result=subprocess.run([str(exe),str(ROOT/'settings.json')],check=True,capture_output=True,text=True,timeout=15)
            self.assertIn('passed',result.stdout)


class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def page(self):
        from effects.wobbly.page import WobblyPage
        def run(work,done,failed):
            try:result=work()
            except Exception as exc:failed(str(exc))
            else:done(result)
        return WobblyPage(run)
    def test_controls_cover_all_options_and_reset(self):
        page=self.page();self.assertEqual(set(page.fields),set(model.DEFAULTS))
        page.fields['friction'].setValue(6);page.fields['snap_key'].setEditText('<Control><Shift>')
        self.assertTrue(page.dirty);self.assertEqual(page.values()['snap_key'],'<Control><Shift>')
        page.reset_defaults();self.assertEqual(page.values(),model.DEFAULTS);page.close()
    def test_invalid_match_blocks_save_without_breaking_editor(self):
        page=self.page();page.fields['move_window_match'].setText('Normal &')
        self.assertTrue(page.dirty);self.assertFalse(page.apply.isEnabled());self.assertFalse(page.preview.isEnabled())
        page.fields['move_window_match'].setText('Normal & !class=kitty');self.assertTrue(page.apply.isEnabled());page.close()
    def test_invalid_file_and_failed_apply_keep_draft(self):
        with patch.object(model,'load',side_effect=ValueError('bad file')):page=self.page()
        self.assertIn('Cannot read Wobbly',page.status.text());page.fields['friction'].setValue(6)
        with patch.object(controller,'save',side_effect=RuntimeError('Rejected')):page.save()
        self.assertFalse(page.busy);self.assertTrue(page.dirty);self.assertEqual(page.values()['friction'],6);page.close()
    def test_effect_tab_participates_in_pending_edits(self):
        sys.path[:0]=[str(ROOT.parent.parent/'control_center'),str(ROOT.parent.parent/'theme')]
        from effects.burn.page import WindowEffectsPage
        page=WindowEffectsPage(lambda *a:None)
        self.assertIn('Wobbly Windows',[page.tabs.tabText(i) for i in range(page.tabs.count())])
        page.wobbly.fields['friction'].setValue(6);self.assertTrue(page.dirty)
        page.wobbly.busy=True;self.assertTrue(page.busy);page.close()


if __name__=='__main__':unittest.main()
