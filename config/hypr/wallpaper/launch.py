#!/usr/bin/env python3
"""Toggle an existing browser before importing Qt or starting a second window."""
import os
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    if '--preview' not in sys.argv:
        runtime=os.environ.get('XDG_RUNTIME_DIR'); signature=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
        if runtime and signature:
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
                    peer.settimeout(.2); peer.connect(str(Path(runtime)/'hypr'/signature/'wallpaper.sock'))
                    peer.sendall(b'show\n' if '--show' in sys.argv else b'toggle\n')
                return 0
            except OSError: pass
    os.execv(sys.executable,[sys.executable,str(ROOT/'theme/run.py'),sys.executable,str(ROOT/'wallpaper/browser.py'),*sys.argv[1:]])


if __name__=='__main__': raise SystemExit(main())
