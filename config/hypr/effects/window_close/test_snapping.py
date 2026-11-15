from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from effects.window_close import snap_settings

class SnapTests(unittest.TestCase):
    def test_geometry_monitor_edges_work_areas_constraints_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'snap'
            subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror',str(Path(__file__).parent/'native/test_snapping.cpp'),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)

    def test_setting_preserves_concurrent_change_and_rolls_back_activation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snap.json';enabled,token=snap_settings.load(path);self.assertTrue(enabled)
            with patch.object(snap_settings.controller,'hypr',return_value='ok'):
                self.assertEqual(snap_settings.save(False,token,path)[0],False)
                with self.assertRaises(ValueError):snap_settings.save(True,token,path)
            before=path.read_bytes();_,token=snap_settings.load(path)
            with patch.object(snap_settings.controller,'hypr',side_effect=RuntimeError('test')):
                with self.assertRaises(RuntimeError):snap_settings.save(True,token,path)
            self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
