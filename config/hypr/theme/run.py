#!/usr/bin/env python3
import os
import sys
from runtime import environment
if __name__ == '__main__':
    if len(sys.argv)<2: raise SystemExit('Provide a program to run.')
    os.execvpe(sys.argv[1],sys.argv[1:],environment())
