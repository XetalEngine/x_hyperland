#!/usr/bin/env python3
"""Launch using this profile's theme and native executable."""
import os
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'theme'))
import runtime

def main():
    binary = ROOT / 'file_manager/.build/xetal-files'
    if not binary.is_file():
        subprocess.run([sys.executable, str(ROOT / 'file_manager/build.py')], check=True)
    env = runtime.environment()
    env['XETAL_FILES_ROOT'] = str(ROOT)
    os.execve(str(binary), [str(binary), *sys.argv[1:]], env)

if __name__ == '__main__':
    main()
