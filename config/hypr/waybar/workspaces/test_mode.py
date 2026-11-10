"""Run in a disposable display: xvfb-run -a env GDK_BACKEND=x11 python3 test_mode.py."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def run():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='workspace-mode-') as temporary:
        binary = Path(temporary)/'test'
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'gtk+-3.0', 'json-glib-1.0'], text=True))
        subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        str(root/'test-mode.c'), '-o', str(binary), *flags], check=True)
        subprocess.run([str(binary), temporary], check=True,
                       env={**os.environ, 'G_DEBUG':'fatal-criticals', 'GSETTINGS_BACKEND':'memory', 'NO_AT_BRIDGE':'1'})


if __name__ == '__main__':
    run()
