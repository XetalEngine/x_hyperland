import tempfile
from pathlib import Path
import unittest
import subprocess
from unittest.mock import patch
import model
import controller


class CloseSettingsTests(unittest.TestCase):
    def test_restore_geometry_stays_inside_each_workarea(self):
        with tempfile.TemporaryDirectory() as directory:
            executable=Path(directory)/'geometry'
            subprocess.run(['g++','-std=c++23','-O2',str(Path(__file__).parent/'native/test_geometry.cpp'),'-o',str(executable)],check=True,capture_output=True)
            subprocess.run([str(executable)],check=True,capture_output=True)
    def test_switch_modifier_and_sizes_round_trip(self):
        for modifier in ('SUPER', 'ALT', 'SUPER+SHIFT'):
            values = dict(model.DEFAULTS, enabled=False, pulse=False, size=50, inset=16, modifier=modifier)
            self.assertEqual(model.decode(model.encode(values)), values)

    def test_rejects_unknown_modifiers_and_out_of_range_controls(self):
        for changes in ({'modifier':'CTRL'}, {'size':12}, {'inset':100}, {'pulse':1}, {'unexpected':True}):
            with self.assertRaises(ValueError): model.validate(dict(model.DEFAULTS, **changes))
        with self.assertRaises(ValueError): model.decode(model.encode(model.DEFAULTS)+'enabled=0\n')

    def test_external_edits_are_preserved_and_failed_apply_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.conf';path.write_text(model.encode(model.DEFAULTS))
            values, token=model.load(path)
            with patch.object(controller,'instance_dir',return_value=Path(directory)), \
                 patch.object(controller.build,'build',return_value=Path('/fixture.so')), \
                 patch.object(controller,'activate') as activate:
                path.write_text(model.encode(dict(values,size=40))); before=path.read_bytes()
                with self.assertRaisesRegex(ValueError,'changed elsewhere'):
                    controller.save(dict(values,enabled=False),token,path)
                self.assertEqual(path.read_bytes(),before);activate.assert_not_called()
                _,token=model.load(path);activate.side_effect=RuntimeError('fixture rejection')
                with self.assertRaisesRegex(RuntimeError,'fixture rejection'):
                    controller.save(dict(values,enabled=False),token,path)
                self.assertEqual(path.read_bytes(),before)

    def test_disabled_unloaded_effect_does_not_build_or_load(self):
        with patch.object(controller,'instance_dir',return_value=Path('/fixture')), \
             patch.object(controller,'hypr',return_value='[]') as ipc, \
             patch.object(controller.build,'build') as build:
            controller.activate(dict(model.DEFAULTS,enabled=False))
            build.assert_not_called();ipc.assert_called_once_with('-j','plugin','list')


if __name__=='__main__': unittest.main()
