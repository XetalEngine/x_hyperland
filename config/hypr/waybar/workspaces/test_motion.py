"""Run in Xvfb: native layout/paint, identity and animation lifetime checks."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def run():
    source=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='workspace-motion-') as directory:
        binary=Path(directory)/'test'
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',
            'gtk+-3.0','gtk-layer-shell-0','json-glib-1.0'],text=True))
        subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
            str(source/'test-motion.c'),'-o',str(binary),*flags],check=True)
        subprocess.run([str(binary),directory],check=True,env=dict(os.environ,
            G_DEBUG='fatal-criticals',GSETTINGS_BACKEND='memory',NO_AT_BRIDGE='1'))


if __name__=='__main__':run()
