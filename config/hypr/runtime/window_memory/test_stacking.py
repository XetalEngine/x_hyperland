from pathlib import Path
import subprocess
import tempfile
import unittest


class StackingTests(unittest.TestCase):
    def test_native_render_and_input_planes_follow_forced_floating_order(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'stacking'
            result=subprocess.run(['g++','-std=c++23','-Wall','-Wextra','-Werror',
                                   str(Path(__file__).with_suffix('.cpp')),'-o',str(binary)],
                                  capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(binary)],check=True,timeout=5)


if __name__=='__main__':unittest.main()
