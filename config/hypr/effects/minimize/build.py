#!/usr/bin/env python3
"""Build only against the compositor API that this port has been tested with."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SUPPORTED_COMMIT = 'efb50993780079460b0cbed1363e2166a2de1d9f'
# Include code-generation options in the content-addressed build key as well.
COMPILE_FLAGS = ('-std=c++23', '-shared', '-fPIC', '-O2', '-g', '-Wall', '-Wextra',
                 '-Wno-unused-parameter')


def output(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Command failed: '+args[0])
    return result.stdout.strip()


def build(root=ROOT):
    if platform.machine() not in ('x86_64','AMD64'):
        raise RuntimeError('This Minimize adapter supports x86-64 Hyprland; minimized windows are unavailable until the adapter is updated.')
    if not shutil.which('g++') or not shutil.which('pkg-config'):
        raise RuntimeError('Minimize needs a C++ compiler and pkg-config. Install the optional Minimize build dependencies.')
    try:
        flags = shlex.split(output(['pkg-config','--cflags','hyprland','libeis-1.0']))
        headers = next(Path(arg[2:])/'src/version.h' for arg in flags
                       if arg.startswith('-I') and (Path(arg[2:])/'src/version.h').exists())
    except (RuntimeError, StopIteration) as error:
        raise RuntimeError('Install the development headers matching your Hyprland package to enable Minimize.') from error
    match = re.search(r'#define\s+GIT_COMMIT_HASH\s+"([a-f0-9]+)"', headers.read_text())
    if not match or match[1] != SUPPORTED_COMMIT:
        raise RuntimeError('Minimize supports Hyprland 0.56.2. This version needs an updated Minimize adapter; minimized windows are unavailable until the adapter is updated.')
    versions = output(['pkg-config','--modversion','hyprland','aquamarine','hyprutils','hyprgraphics','hyprcursor','hyprlang'])
    signature = hashlib.sha256((versions+str(COMPILE_FLAGS)+str(flags)+output(['g++','-dumpfullversion'])).encode())
    sources = [*(root/'native').glob('*'), root.parent/'burn/native/engine.hpp', root.parent/'burn/native/fire_texture.hpp']
    for source in sorted(sources):
        signature.update(source.name.encode()); signature.update(source.read_bytes())
    build_dir = root/'.build'/signature.hexdigest()[:20]
    build_dir.mkdir(parents=True, exist_ok=True)
    target = build_dir/'xetal-minimize.so'
    with (root/'.build/build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_file():
            return target
        # A unique pathname for each build avoids replacing a mapped .so.
        fd, tmp = tempfile.mkstemp(prefix='compile-',suffix='.so',dir=build_dir); os.close(fd)
        try:
            cmd = ['g++',*COMPILE_FLAGS,*flags,str(root/'native/plugin.cpp'),'-o',tmp,'-lGLESv2']
            process = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
            try:
                stdout,stderr = process.communicate(timeout=180)
            except BaseException:
                # The session loader can be terminated on logout while the
                # compiler is running. Stop only this compiler process group.
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.communicate()
                raise
            (build_dir/'build.log').write_text(stdout+stderr)
            if process.returncode:
                raise RuntimeError(f'Minimize could not be built. The minimize handler remains inactive. Details: {build_dir / "build.log"}')
            os.chmod(tmp,0o755); os.replace(tmp,target)
            (build_dir/'build.json').write_text(json.dumps(dict(commit=match[1],versions=versions),indent=2)+'\n')
        finally:
            Path(tmp).unlink(missing_ok=True)
    return target


if __name__ == '__main__':
    try:
        print(build())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
