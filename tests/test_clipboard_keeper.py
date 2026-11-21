"""Production clipboard pipe handling; never connects to a desktop clipboard."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ClipboardKeeper(unittest.TestCase):
    def test_bounded_nonblocking_transfers_and_selection_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            xml = ROOT/'config/hypr/clipboard/native/wlr-data-control-unstable-v1.xml'
            for mode, name in [('client-header', 'wlr-data-control-client-protocol.h'), ('private-code', 'protocol.c')]:
                subprocess.run(['wayland-scanner', mode, str(xml), str(work/name)], check=True, capture_output=True)
            flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'wayland-client'], text=True))
            subprocess.run(['cc', '-c', str(work/'protocol.c'), '-o', str(work/'protocol.o'), *flags], check=True, capture_output=True)
            binary = work/'test'
            subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-I'+str(work),
                str(ROOT/'tests/native/clipboard_keeper.cpp'), str(work/'protocol.o'), '-o', str(binary), *flags], check=True, capture_output=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=10)
            self.assertIn('PASS native clipboard', result.stdout)


if __name__ == '__main__':
    unittest.main()
