#!/usr/bin/env python3
import os
import sys
from runtime import environment,icon_library
if __name__ == '__main__':
    if len(sys.argv)<2: raise SystemExit('Provide a program to run.')
    if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        try:icon_library.ensure()
        except (OSError,ValueError):pass
    os.execvpe(sys.argv[1],sys.argv[1:],environment())
