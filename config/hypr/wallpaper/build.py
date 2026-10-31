#!/usr/bin/env python3
"""Build the optional GTK/GL transition helper against each distribution's SDK."""
import hashlib
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def build(root=ROOT):
    source = root/'transition.c'
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gtk+-3.0', 'gtk-layer-shell-0', 'epoxy'], text=True))
    fingerprint = hashlib.sha256(source.read_bytes()+repr(flags).encode()+subprocess.check_output(['cc', '-dumpmachine'])).hexdigest()[:20]
    target = root/'.build'/fingerprint/'wallpaper-transition'
    if target.is_file() and os.access(target, os.X_OK): return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.compile-', dir=target.parent) as tmp:
        output = Path(tmp)/'transition'
        subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(output), *flags], check=True)
        os.replace(output, target)
    return target


if __name__ == '__main__': print(build())
