#!/usr/bin/env python3
"""Build the complete copied C++ engine inside this Hyprland profile."""
import fcntl
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent

def build():
    try:
        jobs=len(os.sched_getaffinity(0))
    except (AttributeError,OSError):
        jobs=os.cpu_count() or 1
    output=ROOT/'.build';output.mkdir(exist_ok=True)
    with (output/'build.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        subprocess.run(['cmake','-S',str(ROOT/'backend'),'-B',str(output),'-DCMAKE_BUILD_TYPE=Release',
                        '-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG'],check=True)
        print(f'Building Control Panel with {jobs} parallel jobs.',flush=True)
        subprocess.run(['cmake','--build',str(output),'--parallel',str(jobs)],check=True)
    return output/'xetal-control-panel'
if __name__=='__main__':build()
