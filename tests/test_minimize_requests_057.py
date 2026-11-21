"""Minimize protocol handling without a compositor or desktop changes."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ClientRequestTests(unittest.TestCase):
    def test_real_signal_delivery_lifecycle_and_plugin_reload(self):
        with tempfile.TemporaryDirectory() as name:
            binary = Path(name)/'requests'
            flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','hyprutils'],text=True))
            subprocess.run(['g++','-std=c++23','-Wall','-Wextra',
                '-I'+str(ROOT/'config/hypr/effects/minimize/native'),
                str(ROOT/'tests/native/minimize_requests_057.cpp'),'-o',str(binary),*flags],check=True)
            subprocess.run([str(binary)],check=True)

if __name__ == '__main__': unittest.main()
