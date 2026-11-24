from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from effects.window_close import behavior
from updates import file_policy


class WindowBehaviorTests(unittest.TestCase):
    def test_native_recovery_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'protection'
            subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror',str(Path(__file__).parent/'native/test_title_protection.cpp'),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)

    def test_default_on_and_saved_off_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'behavior.json';enabled,token=behavior.load(path)
            self.assertTrue(enabled)
            with patch.object(behavior.controller,'start'):
                self.assertFalse(behavior.save(False,token,path)[0])
            self.assertFalse(behavior.load(path)[0])
            self.assertEqual(file_policy.policy('effects/window_close/behavior-settings.json'),'preferences')

    def test_concurrent_edit_and_activation_failure_keep_saved_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'behavior.json';_,token=behavior.load(path)
            with patch.object(behavior.controller,'start'):
                _,new=behavior.save(False,token,path)
                with self.assertRaises(ValueError):behavior.save(True,token,path)
            old=path.read_bytes()
            with patch.object(behavior.controller,'start',side_effect=RuntimeError('test')):
                with self.assertRaises(RuntimeError):behavior.save(True,new,path)
            self.assertEqual(path.read_bytes(),old)

    def test_strict_settings_and_failed_first_save_restore_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'behavior.json';_,token=behavior.load(path)
            with patch.object(behavior.controller,'start',side_effect=RuntimeError('test')):
                with self.assertRaises(RuntimeError):behavior.save(False,token,path)
            self.assertFalse(path.exists());self.assertTrue(behavior.load(path)[0])
            for value in ({'titlebar_protection':1},{'titlebar_protection':False,'extra':True},[],{}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):behavior.load(path)


if __name__=='__main__':unittest.main()
