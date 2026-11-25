#!/usr/bin/env python3
"""Pin successfully installed application launchers, never package dependencies."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def pin_desktop(path):
    from gi.repository import Gio
    path = Path(path).absolute()
    roots = [Path.home()/'.local/share/applications', Path('/usr/local/share/applications'), Path('/usr/share/applications')]
    import os
    roots.insert(0, Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'applications')
    base = next((p for p in roots if path.is_relative_to(p)), None)
    if base is None or not path.is_file(): return False
    app = Gio.DesktopAppInfo.new_from_filename(str(path))
    if not app or not app.should_show() or not app.get_executable(): return False
    sys.path.insert(0, str(ROOT/'launcher'))
    from catalog import pin
    pin(str(path.relative_to(base)).replace('/', '-'), True)
    return True


def pin_package(package):
    package = package.rsplit('/', 1)[-1]
    if not re.fullmatch(r'[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\-]*', package):
        raise ValueError('Invalid package name.')
    result = subprocess.run(['pacman', '-Qq', '--', package], capture_output=True, text=True, timeout=15)
    if result.returncode: return []
    result = subprocess.run(['pacman', '-Qlq', '--', package], capture_output=True, text=True, timeout=15, check=True)
    return [p for p in result.stdout.splitlines() if p.endswith('.desktop') and pin_desktop(p)]


def package_installed(package):
    # Favorites failure must not turn a completed package transaction into a
    # reported install failure. Preserve malformed preferences for recovery.
    try:
        pinned = pin_package(package)
        if pinned: print('Added to Favorites: '+', '.join(Path(p).stem for p in pinned), flush=True)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Installed, but Favorites could not be updated: '+str(error), file=sys.stderr, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    package_installed(parser.parse_args().package)
