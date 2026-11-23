#!/usr/bin/env python3
"""Build pinned desktop components without installing files as root."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent


def build(component):
    if component not in ('mpvpaper','hypr-rdp'):raise ValueError('Unknown component.')
    source=ROOT/'third_party'/component; output=ROOT/'.build'/component
    output.parent.mkdir(parents=True,exist_ok=True)
    with (output.parent/(component+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        jobs=str(min(6,os.cpu_count() or 2))
        if component=='mpvpaper':
            if not (output/'build.ninja').exists():subprocess.run(['meson','setup',str(output),str(source),'--buildtype=release'],check=True)
            subprocess.run(['meson','compile','-C',str(output),'-j',jobs],check=True)
            return output/'mpvpaper'
        subprocess.run(['cargo','build','--release','--locked','--jobs',jobs,'--manifest-path',str(source/'Cargo.toml'),'--target-dir',str(output)],check=True)
        return output/'release/hypr-rdp'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('component',nargs='?',default='all',choices=['all','mpvpaper','hypr-rdp'])
    component=parser.parse_args().component
    for name in (('mpvpaper','hypr-rdp') if component=='all' else (component,)):print(build(name))
