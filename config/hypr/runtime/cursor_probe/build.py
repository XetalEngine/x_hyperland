#!/usr/bin/env python3
"""Build the cursor probe against the exact supported compositor headers."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]/'effects'))
from native_toolchain import compiler, environment, adapter, adapter_headers


def output(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Command failed: '+args[0])
    return result.stdout.strip()


def build(root=ROOT):
    if platform.machine() not in ('x86_64', 'AMD64'):
        raise RuntimeError('The cursor probe requires the supported x86-64 Hyprland runtime.')
    flags = shlex.split(output(['pkg-config', '--cflags', 'hyprland', 'libeis-1.0']))
    headers = next((Path(arg[2:])/'src/version.h' for arg in flags
                    if arg.startswith('-I') and (Path(arg[2:])/'src/version.h').is_file()), None)
    match = re.search(r'#define\s+GIT_COMMIT_HASH\s+"([a-f0-9]+)"', headers.read_text()) if headers else None
    plugin_source = adapter(root, match[1] if match else '')
    versions = output(['pkg-config', '--modversion', 'hyprland', 'aquamarine', 'hyprutils', 'hyprgraphics', 'hyprcursor', 'hyprlang'])
    signature = hashlib.sha256((versions+str(flags)+headers.read_text()+output([compiler(), '-dumpfullversion'])).encode())
    for source in (root/'plugin.cpp', root/'drag_actions.hpp', root/'build.py', root.parent/'window_types.hpp', root.parent/'window_types_native.hpp'):
        signature.update(source.read_bytes())
    for source in [*root.glob('*_057.*'), *adapter_headers(root.parents[1]), ROOT.parents[1]/'effects/native_toolchain.py']:
        signature.update(source.name.encode()); signature.update(source.read_bytes())
    directory = root/'.build'/signature.hexdigest()[:20]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/'xetal-cursor-probe.so'
    stamp = directory/'signature'
    with (directory/'build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_file() and stamp.is_file() and stamp.read_text() == signature.hexdigest():
            return target
        fd, temporary = tempfile.mkstemp(prefix='compile-', suffix='.so', dir=directory)
        os.close(fd)
        try:
            cmd = [compiler(), '-std=c++23', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra',
                   '-Wno-unused-parameter', *flags, str(plugin_source), '-o', temporary]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, env=environment())
            try:
                stdout, stderr = process.communicate(timeout=180)
            except BaseException:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.communicate()
                raise
            (directory/'build.log').write_text(stdout+stderr)
            if process.returncode:
                raise RuntimeError('Cursor probe build failed:\n'+stderr[-4000:])
            # Replace the inode, never overwrite a library mapped by Hyprland.
            os.chmod(temporary, 0o755)
            os.replace(temporary, target)
            stamp.write_text(signature.hexdigest())
        finally:
            Path(temporary).unlink(missing_ok=True)
    return target


if __name__ == '__main__':
    try:
        print(build())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
