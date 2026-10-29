import importlib.util
import json
import os
import shlex
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
    def test_native_settings_preserve_values_and_reject_invalid_input(self):
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'settings';path=Path(d)/'settings.json'
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','json-c'],text=True))
            subprocess.run(['g++','-std=c++23','-Wall','-Wextra',str(ROOT/'native/test_settings.cpp'),'-o',str(binary),*flags],check=True,capture_output=True)
            values=model.validate(model.DEFAULTS)
            for mode,number in [('gradient',1),('image',2),('sky',3)]:
                for motion in (False,True):
                    values.update(sky_mode=mode,sky_motion=motion,sky_speed=-20)
                    path.write_text(model.encode(values))
                    result=subprocess.run([str(binary),str(path)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(result.stdout.strip(),f'{number} {int(motion)} -20')
            for key,value in [('enabled',1),('zoom',True),('wall_opacity',float('nan')),('window_space',2.5),
                              ('sky_motion',None),('sky_mode','invalid'),('sky_image','../../private.png'),
                              ('sky_image','images/'+'a'*64+'.png\0'),('cap_color',[0,0,2,1]),('sky_top',[0,0,False,1])]:
                with self.subTest(key=key,value=value):
                    path.write_text(json.dumps(dict(values,**{key:value})))
                    self.assertEqual(subprocess.run([str(binary),str(path)],capture_output=True).returncode,1)
            good=model.encode(values).encode()
            for bad in [good+b'{}',good+b'\0',good[:-8],b'{}',b'[]',b'x'*16385,good.replace(b'image',b'\xff',1)]:
                path.write_bytes(bad)
                self.assertEqual(subprocess.run([str(binary),str(path)],capture_output=True).returncode,1)

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

    def test_background_motion_controls_cover_pictures_and_panoramas(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication
        from effects.cube.page import CubePage
        app=QApplication.instance() or QApplication([])
        with patch.object(model,'load',return_value=(model.validate(model.DEFAULTS),'token')):
            page=CubePage(lambda *a:None)
        for mode in ('image','sky','gradient','image'):
            page.fields['sky_mode'].setCurrentIndex(page.fields['sky_mode'].findData(mode))
            for key in ('sky_motion','sky_speed'):
                self.assertEqual(page.fields[key].isEnabled(),mode!='gradient')
            self.assertTrue(page.values()['sky_motion'])
        page.fields['sky_motion'].setChecked(False);page.fields['sky_speed'].setValue(4)
        self.assertFalse(page.values()['sky_motion']);self.assertEqual(page.values()['sky_speed'],4)
        self.assertTrue(page.dirty);self.assertTrue(page.apply.isEnabled());page.close()


if __name__=='__main__':unittest.main()
