#!/usr/bin/env python3
"""Portable default for Fusion's editable system-monitor shortcut."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def command(which=shutil.which):
    for name in ('plasma-systemmonitor', 'gnome-system-monitor', 'missioncenter', 'xfce4-taskmanager', 'lxtask'):
        if path := which(name):
            return [path]
    if which('kitty') and which('htop'):
        return [which('kitty'), '--config', str(ROOT/'kitty.conf'), '-e', which('htop')]
    raise RuntimeError('Install a system monitor, or choose its command in Fusion Settings → Hotkeys → Open system monitor.')


def main():
    try:
        argv = command()
        os.execv(argv[0], argv)
    except (OSError, RuntimeError) as error:
        subprocess.run(['notify-send', '-i', 'utilities-system-monitor', 'System monitor', str(error)], check=False)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
