"""State tests without a display; add --native for GTK tests in a Wayland session."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def run(native=False):
    with tempfile.TemporaryDirectory(prefix="xetal-bar-options-build-") as temporary:
        binary = Path(temporary) / "test-options"
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "gtk+-3.0", "gtk-layer-shell-0", "json-glib-1.0"], text=True))
        subprocess.run(["cc", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                        str(ROOT / "test-options.c"), "-o", str(binary), *flags], check=True)
        subprocess.run([str(binary), *([] if native else ["--state-only"])], check=True,
                       env={**os.environ, "G_DEBUG": "fatal-criticals", "GSETTINGS_BACKEND": "memory",
                            "GDK_BACKEND": "wayland", "NO_AT_BRIDGE": "1"})


class BarOptionsTests(unittest.TestCase):
    def test_persistence_and_recovery(self):
        run()


if __name__ == "__main__":
    if "--native" in sys.argv:
        run(native=True)
    else:
        unittest.main()
