"""Check real background sampling without touching a compositor or GPU."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('g++') and Path('/usr/include/hyprutils/memory/UniquePtr.hpp').exists(),
                     'C++ compiler and Hyprutils headers required')
class BackgroundTests(unittest.TestCase):
    def test_unique_color_ownership_and_gpu_state(self):
        with tempfile.TemporaryDirectory(prefix='fusion-background-test-') as directory:
            root=Path(directory)
            for name in ('render/Renderer.hpp','render/OpenGL.hpp','helpers/cm/ColorManagement.hpp'):
                path=root/'hyprland/src'/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('#include "background_057_fixture.hpp"\n')
            subprocess.run(['g++','-std=c++23','-O2','-Wall','-Wextra',
                            '-I'+str(root),'-I'+str(ROOT/'tests/native'),
                            '-I'+str(ROOT/'config/hypr/effects/window_close/native'),
                            str(ROOT/'tests/native/background_057.cpp'),'-o',str(root/'probe')],check=True)
            subprocess.run([str(root/'probe')],check=True)
