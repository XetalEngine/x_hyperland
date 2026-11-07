"""Cursor compilation must not inherit a desktop-only Qt platform."""
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cursors import art


class HeadlessCursorBuildTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('xcursorgen') and shutil.which('hyprcursor-util'),
                         'The cursor compilers are required for this integration test.')
    def test_cli_builds_without_a_display_despite_inherited_desktop_platform(self):
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='cursor-headless-') as directory:
            root = Path(directory)
            for name in ('art.py', 'build.py'):
                shutil.copyfile(source/name, root/name)
            runtime = root/'runtime'; runtime.mkdir(mode=0o700)
            environment = {key:value for key,value in os.environ.items()
                           if not key.startswith('QT_') and key not in ('DISPLAY', 'WAYLAND_DISPLAY')}
            environment.update(XDG_RUNTIME_DIR=str(runtime), XDG_CACHE_HOME=str(root/'cache'))
            def no_core(): resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            for backend in ('xcb', 'wayland'):
                with self.subTest(inherited_backend=backend):
                    result = subprocess.run([sys.executable, str(root/'build.py')],
                        env=dict(environment, QT_QPA_PLATFORM=backend),
                        text=True, capture_output=True, timeout=180, preexec_fn=no_core)
                    self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
                    self.assertEqual(result.stdout.strip(), str(root/'.build/data'))
            # Check generated, usable cursor assets, not just a successful exit.
            for style in art.STYLES:
                theme = root/'.build/data/icons'/('Xetal-Cursor-'+style)
                self.assertTrue((theme/'manifest.hl').is_file())
                self.assertEqual((theme/'cursors/left_ptr').read_bytes()[:4], b'Xcur')


if __name__ == '__main__':
    unittest.main()
