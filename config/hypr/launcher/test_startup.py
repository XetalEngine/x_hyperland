"""Exercise the Apps entrypoint without an existing Python import cache."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def environment():
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
               QT_STYLE_OVERRIDE='Fusion')
    # Preview uses the real startup path without talking to the current desktop.
    env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
    return env


class StartupTests(unittest.TestCase):
    def test_apps_entrypoint_initializes_theme_and_renders_menu(self):
        with tempfile.TemporaryDirectory() as directory:
            preview = Path(directory)/'apps.png'
            result = subprocess.run([sys.executable, str(ROOT/'launcher/placement.py'),
                                     '--preview', str(preview)], cwd=directory, env=environment(),
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(preview.is_file(), result.stdout + result.stderr)
            data = preview.read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('>II', data[16:24])
            self.assertGreater(width, 100)
            self.assertGreater(height, 100)

    def test_geometry_and_theme_imports_work_in_either_order(self):
        source = '''
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root/'launcher'))
if sys.argv[2] == 'theme-first':
    sys.path.insert(0, str(root/'theme'))
    import runtime
import floating
sys.path.insert(0, str(root/'theme'))
import runtime
assert callable(runtime.install)
assert callable(runtime.launcher_design)
assert floating.workarea({'x':0,'y':0,'width':800,'height':600}) == (0,0,800,600)
assert floating.geometry_managed({'stableId':'1'}, {'stableId':'1','geometry_managed':True})
'''
        for order in ('geometry-first', 'theme-first'):
            with self.subTest(order=order):
                result = subprocess.run([sys.executable, '-c', source, str(ROOT), order],
                                        env=environment(), capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
