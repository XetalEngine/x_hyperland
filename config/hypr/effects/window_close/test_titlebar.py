from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


class NativeTitlebarTests(unittest.TestCase):
    def test_layout_hit_targets_legacy_rules_and_production_artwork(self):
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','pangocairo','json-c'],text=True))
        with tempfile.TemporaryDirectory() as directory:
            executable=Path(directory)/'titlebar'
            subprocess.run(['g++','-std=c++23','-O2',str(Path(__file__).parent/'native/test_titlebar.cpp'),
                            '-o',str(executable),*flags],check=True,capture_output=True)
            subprocess.run([str(executable)],check=True,capture_output=True)


if __name__=='__main__':unittest.main()
