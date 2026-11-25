"""Install the pinned default player without requiring network access."""
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def install(profile):
    manifest = REPO/'installer/packages/xmusic/manifest.json'
    print('Installing XMusic and its supported audio-file defaults…', flush=True)
    subprocess.run([sys.executable, str(Path(profile)/'control_panel/software_install.py'),
                    '--vendor', 'xmusic', '--bundle', str(manifest), '--make-default'], check=True)
