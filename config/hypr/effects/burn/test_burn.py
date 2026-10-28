import copy
import hashlib
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
from effects.burn import model,controller


class OptionsTests(unittest.TestCase):
    def test_exact_upstream_defaults_and_ranges(self):
        for option in ET.parse(ROOT/'compiz-options.xml').getroot():
            name=option.get('name');default=option.find('default')
            if name=='fire_color':
                value=[int(default.findtext(c),16) for c in ('red','green','blue','alpha')]
            elif option.get('type')=='bool':value=default.text=='true'
            else:value=float(default.text)
            self.assertEqual(model.DEFAULTS[name],value,name)
            if name in model.RANGES:
                self.assertEqual(model.RANGES[name],(float(option.findtext('min')),float(option.findtext('max'))))

    def test_rgba16_round_trip(self):
        values=copy.deepcopy(model.DEFAULTS);values['fire_color']=[123,4567,32109,54321]
        self.assertEqual(model.decode(model.encode(values)),values)

    def test_reject_invalid_settings_before_write(self):
        for key,bad in [('fire_life',float('nan')),('fire_particles',99),('duration',0),
                        ('fire_direction',6),('fire_smoke','true'),('fire_color',[1,2,3,-1])]:
            values=copy.deepcopy(model.DEFAULTS);values[key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):model.validate(values)
        with self.assertRaises(ValueError):model.decode(model.encode(model.DEFAULTS)+'fire_size=2\n')

    def test_failed_activation_rolls_back_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.conf';old=model.encode(model.DEFAULTS).encode();path.write_bytes(old)
            values,token=model.load(path);values['duration']=800
            with patch.object(controller,'instance_dir',return_value=Path(directory)),patch.object(controller,'activate',side_effect=RuntimeError('test failure')):
                with self.assertRaisesRegex(RuntimeError,'test failure'):controller.save(values,token,path)
            self.assertEqual(path.read_bytes(),old)

    def test_external_edit_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.conf';path.write_text(model.encode(model.DEFAULTS));values,token=model.load(path)
            changed=dict(values,duration=700);path.write_text(model.encode(changed))
            with patch.object(controller,'instance_dir',return_value=Path(directory)),self.assertRaisesRegex(ValueError,'elsewhere'):
                controller.save(values,token,path)
            self.assertEqual(model.load(path)[0],changed)

    def test_native_particle_math(self):
        with tempfile.TemporaryDirectory() as directory:
            exe=Path(directory)/'engine-test'
            subprocess.run(['g++','-std=c++23','-O2',str(ROOT/'native/test_engine.cpp'),'-o',str(exe)],check=True,capture_output=True)
            result=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=15)
            self.assertIn('passed',result.stdout)


class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def page(self):
        from effects.burn.page import BurnPage
        def run(work,done,failed):
            try:result=work()
            except Exception as error:failed(str(error))
            else:done(result)
        return BurnPage(run)

    def test_controls_cover_every_compiz_option(self):
        page=self.page()
        self.assertEqual(set(page.values()),set(model.DEFAULTS))
        page.fields['fire_size'].setValue(10);page.fields['fire_smoke'].setChecked(True)
        self.assertTrue(page.dirty);self.assertFalse(page.preview.isEnabled())
        enabled=page.enabled.isChecked();page.reset_defaults()
        expected=copy.deepcopy(model.DEFAULTS);expected['enabled']=enabled
        self.assertEqual(page.values(),expected);page.close()

    def test_damaged_burn_file_does_not_break_control_desk(self):
        with patch.object(model,'load',side_effect=ValueError('Invalid setting')):
            page=self.page()
        self.assertIn('Cannot read Burn settings',page.status.text())
        self.assertFalse(page.preview.isEnabled());page.close()

    def test_buttons_fit_small_control_desk(self):
        page=self.page();page.resize(1000,410);page.show();self.app.processEvents()
        for button in (page.apply,page.discard,page.defaults,page.preview,page.reload):
            self.assertTrue(page.rect().contains(button.geometry()),button.text())
        page.close()

    def test_save_failure_keeps_draft_for_retry(self):
        page=self.page();page.fields['duration'].setValue(900)
        with patch.object(controller,'save',side_effect=RuntimeError('Unable to load')):page.save()
        self.assertFalse(page.busy);self.assertTrue(page.dirty);self.assertIn('Unable to load',page.status.text());page.close()


if __name__=='__main__':unittest.main()
