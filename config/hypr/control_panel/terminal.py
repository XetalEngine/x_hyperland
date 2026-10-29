#!/usr/bin/env python3
"""Keep backend terminal operations in the Hyprland Kitty profile."""
import os
from pathlib import Path
import shlex
import sys
root=Path(__file__).resolve().parents[1]
args=sys.argv[1:]
if args[:1]==['-e']:args=args[1:]
if len(args)==1 and any(c.isspace() for c in args[0]):args=[os.environ.get('SHELL','/bin/bash'),'-ic',args[0]]
os.execvp('kitty',['kitty','--config',str(root/'kitty.conf'),*args])
