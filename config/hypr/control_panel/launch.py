#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):raise SystemExit('Control Panel requires a Hyprland session.')
binary=ROOT/'control_panel/.build/xetal-control-panel'
if not binary.is_file():
    subprocess.run(['python3',str(ROOT/'control_panel/build.py')],check=True)
os.environ['XETAL_HYPR_ROOT']=str(ROOT)
# C++ helpers use only their own settings path; theme/run.py supplies the shared visual palette.
os.execv(sys.executable,[sys.executable,str(ROOT/'theme/run.py'),str(binary),*sys.argv[1:]])
