import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]))
from effects.cube import model,controller


class CubeTests(unittest.TestCase):
    def test_native_workspace_isolation_and_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'geometry'
            subprocess.run(['g++','-std=c++23','-Wall','-Wextra',str(ROOT/'native/test_math.cpp'),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)

    def test_roundtrip_and_strict_validation(self):
        values=model.validate(model.DEFAULTS)
        self.assertEqual(model.validate(json.loads(model.encode(values))),values)
        for key,value in [('enabled',1),('zoom',4),('wall_opacity',float('nan')),('window_space',2.5),
                          ('sky_mode','invalid'),('top_image','../../private.png'),('sky_top',[0,0,2,1])]:
            bad=values.copy();bad[key]=value
            with self.assertRaises(ValueError,msg=key):model.validate(bad)
        with self.assertRaises(ValueError):model.validate(dict(values,unknown=True))

    def test_import_is_portable_and_preserves_original(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.png';Image.new('RGBA',(120,80),(100,50,20,140)).save(source)
            before=source.read_bytes();relative=model.import_image(source,root)
            self.assertRegex(relative,r'^images/[0-9a-f]{64}\.png$')
            self.assertEqual(source.read_bytes(),before)
            values=model.validate(model.DEFAULTS);values['top_image']=relative
            model.prepare_images(values,root)
            raw=(root/'cache'/(Path(relative).stem+'.rgba')).read_bytes()
            self.assertEqual(struct.unpack('<8sII',raw[:16]),(b'XTCUBE1\0',120,80))
            self.assertEqual(len(raw),16+120*80*4)
            (root/relative).write_bytes(b'changed outside')
            with self.assertRaises(ValueError):model.prepare_images(values,root)

    def test_failed_activation_restores_previous_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json';old=model.encode(model.DEFAULTS).encode();path.write_bytes(old)
            values,token=model.load(path);values['zoom']=.5
            with patch.object(controller,'instance_dir',return_value=Path(d)),patch.object(controller.build,'build',return_value='plugin.so'),patch.object(controller,'activate',side_effect=RuntimeError('ABI mismatch')):
                with self.assertRaisesRegex(RuntimeError,'ABI mismatch'):controller.save(values,token,path)
            self.assertEqual(path.read_bytes(),old)

    def test_external_edits_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json';path.write_text(model.encode(model.DEFAULTS));values,token=model.load(path)
            changed=values.copy();changed['zoom']=.4;path.write_text(model.encode(changed))
            values['zoom']=.5
            with patch.object(controller,'instance_dir',return_value=Path(d)),patch.object(controller.build,'build',return_value='plugin.so'),patch.object(controller,'activate') as activate:
                with self.assertRaisesRegex(ValueError,'changed elsewhere'):controller.save(values,token,path)
                activate.assert_not_called()
            self.assertEqual(model.load(path)[0]['zoom'],.4)

    def test_controls_keep_dirty_edits_and_buttons_outside_scroll(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication,QScrollArea
        from effects.cube.page import CubePage
        app=QApplication.instance() or QApplication([])
        page=CubePage(lambda *a:None);page.resize(1100,480);page.show();app.processEvents()
        page.fields['zoom'].setValue(50)
        page.refresh();self.assertTrue(page.dirty);self.assertEqual(page.values()['zoom'],.5)
        self.assertTrue(page.apply.isEnabled());self.assertLess(page.apply.geometry().bottom(),page.height())
        self.assertIsNone(page.apply.findChild(QScrollArea))
        page.reset();self.assertFalse(page.dirty);page.close()

    def test_invalid_config_never_enables_apply(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication
        from effects.cube.page import CubePage
        app=QApplication.instance() or QApplication([])
        with patch.object(model,'load',side_effect=ValueError('Bad JSON')):
            page=CubePage(lambda *a:None)
        page.fields['zoom'].setValue(50)
        self.assertFalse(page.apply.isEnabled());self.assertFalse(page.preview.isEnabled());page.close()


if __name__=='__main__':unittest.main()
