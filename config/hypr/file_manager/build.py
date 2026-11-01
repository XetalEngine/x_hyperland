#!/usr/bin/env python3
"""Build Fusion Files in this profile; generated files never enter a release."""
import fcntl
import os
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parent

def build():
    output = ROOT / '.build'
    output.mkdir(exist_ok=True)
    with (output / 'build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cache = output/'CMakeCache.txt'
        if cache.exists():
            values = dict(line.split('=', 1) for line in cache.read_text().splitlines()
                          if line.startswith(('CMAKE_HOME_DIRECTORY:INTERNAL=', 'CMAKE_CACHEFILE_DIR:INTERNAL=')))
            if (values.get('CMAKE_HOME_DIRECTORY:INTERNAL') != str(ROOT)
                    or values.get('CMAKE_CACHEFILE_DIR:INTERNAL') != str(output)):
                # Activation moves the staged profile. Drop only generated
                # CMake state when rebuilding it at its installed location.
                cache.unlink()
                shutil.rmtree(output/'CMakeFiles', ignore_errors=True)
        subprocess.run(['cmake', '-S', str(ROOT), '-B', str(output),
                        '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=OFF'], check=True)
        jobs = min(4, len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1)
        subprocess.run(['cmake', '--build', str(output), '--parallel', str(jobs)], check=True)
    return output / 'xetal-files'

if __name__ == '__main__':
    build()
