#!/usr/bin/env python3
"""Launch one saved shortcut, including its current command, icon and terminal preference."""
import argparse
import os
from pathlib import Path
import subprocess
from urllib.parse import unquote
import catalog
import shortcuts


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app',required=True);args=parser.parse_args()
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):return 1
    ident=unquote(args.app)
    try:
        entry=catalog.applications().get(ident)
        if entry is None:raise ValueError('This shortcut was removed or the app is no longer installed.')
        shortcuts.leave_dashboard();entry.launch()
    except Exception as error:
        subprocess.run(['notify-send','-a','Xetal Apps','Could not launch shortcut',str(error)],check=False,timeout=4)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
