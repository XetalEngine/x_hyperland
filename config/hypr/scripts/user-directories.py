#!/usr/bin/env python3
"""Initialize standard folders for accounts without an XDG directory map."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def initialize(environment=None):
    """Leave existing locations (including unavailable mounts) entirely alone.

    The upstream utility also resets missing destinations on subsequent runs.
    Only use its first-run behavior here; it handles locale, system defaults
    and the user's enabled=False preference without sourcing any shell files.
    """
    environment = dict(os.environ if environment is None else environment)
    home = Path(environment.get('HOME', ''))
    if not home.is_absolute() or not home.is_dir():
        raise ValueError('A valid absolute HOME directory is required.')
    if os.geteuid() == 0:
        raise ValueError('Initialize user folders as the desktop user, not root.')
    config = Path(environment.get('XDG_CONFIG_HOME', ''))
    if not config.is_absolute():
        config = home / '.config'
    mapping = config / 'user-dirs.dirs'
    try:
        mapping.lstat()  # A broken symlink or unreadable map is not a new account.
    except FileNotFoundError:
        pass
    else:
        return False
    environment['XDG_CONFIG_HOME'] = str(config)
    subprocess.run(['/usr/bin/xdg-user-dirs-update'], env=environment,
                   check=True, timeout=10)
    return mapping.is_file()


def main():
    try:
        initialize()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Could not initialize standard user folders: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
