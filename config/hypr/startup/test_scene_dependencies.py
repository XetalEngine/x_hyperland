"""Fresh installs must render every console without developer-only packages."""
from pathlib import Path
import subprocess
import sys
import unittest


class SceneDependencyTests(unittest.TestCase):
    def test_all_console_modes_start_without_numpy(self):
        # A dev machine may have NumPy from other applications. Make it absent
        # in a fresh interpreter so that cannot hide an undeclared dependency.
        bootstrap = '''
import importlib.abc
from pathlib import Path
import runpy
import sys
class NoNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numpy' or fullname.startswith('numpy.'):
            raise ModuleNotFoundError("No module named 'numpy'", name='numpy')
sys.meta_path.insert(0, NoNumpy())
sys.argv = sys.argv[1:]
sys.path.insert(0, str(Path(sys.argv[0]).parent))
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        scene = Path(__file__).with_name('scene.py')
        for mode, heading in (('info', '01 / SYSTEM'), ('matrix', '02 / THE CONSTRUCT'),
                              ('clock', '03 / FUSION CHECK'), ('hero', '04 / XETAL ENGINE')):
            with self.subTest(mode=mode):
                run = subprocess.run([sys.executable, '-c', bootstrap, str(scene), mode, '--frame'],
                                     capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn(heading, run.stdout)


if __name__ == '__main__':
    unittest.main()
