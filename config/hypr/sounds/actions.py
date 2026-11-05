"""Bounded shutdown music for already-confirmed Fusion power actions."""
from pathlib import Path
import subprocess
import sys

EXIT_ACTIONS = (('systemctl', 'poweroff'), ('systemctl', 'reboot'), ('hyprctl', 'dispatch', 'exit'))
PLAYER = Path(__file__).resolve().with_name('play.py')


def before_power(argv):
    if tuple(argv) not in EXIT_ACTIONS: return
    try:
        subprocess.run([sys.executable, str(PLAYER), 'shutdown'], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5.5)
    except (OSError, subprocess.SubprocessError): pass
