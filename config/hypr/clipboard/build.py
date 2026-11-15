#!/usr/bin/env python3
"""Build the small Wayland data-control collector without compositor hooks."""
from pathlib import Path
import fcntl
import hashlib
import os
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent

def build():
    directory=ROOT/'.build'; directory.mkdir(exist_ok=True)
    with (directory/'build.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        inputs=sorted((ROOT/'native').iterdir())
        signature=hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()
        output=directory/'fusion-clipboard-collector'; stamp=directory/'source.sha256'
        if output.is_file() and stamp.exists() and stamp.read_text()==signature:return output
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            work=Path(temporary); xml=ROOT/'native/wlr-data-control-unstable-v1.xml'
            for mode,name in [('client-header','wlr-data-control-client-protocol.h'),('private-code','protocol.c')]:
                subprocess.run(['wayland-scanner',mode,str(xml),str(work/name)],check=True)
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client'],text=True))
            subprocess.run(['cc','-c',str(work/'protocol.c'),'-o',str(work/'protocol.o'),*flags],check=True)
            subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra',str(ROOT/'native/collector.cpp'),str(work/'protocol.o'),'-I'+str(work),'-o',str(work/'collector'),*flags],check=True)
            os.replace(work/'collector',output)
        stamp.write_text(signature)
        return output

if __name__=='__main__':print(build())
