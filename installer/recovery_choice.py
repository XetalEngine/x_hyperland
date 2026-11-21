"""Explicit, per-transaction choices when old recovery downloads are missing."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MARKER = 'XETAL_RECOVERY_DOWNLOADS_FAILED '
EXIT_REQUIRED = 75
CONTINUE = 'continue-without-rollback'
CHOICES = {'retry', 'cancel', CONTINUE}
WARNING = ('Continuing disables automatic package rollback for this installation. '
           'If installation later fails, the upgraded system may need manual repair. '
           'Your desktop settings backup is still kept.')


def validate(packages):
    if not isinstance(packages, list) or not packages:
        raise ValueError('Missing recovery package list.')
    seen = set()
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError('Invalid recovery package.')
        name, version = package.get('name'), package.get('version')
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_+@.][A-Za-z0-9_+@.-]*', name)
                or name in seen or not isinstance(version, str)
                or not re.fullmatch(r'[0-9][A-Za-z0-9.+_~:-]*', version)):
            raise ValueError('Invalid recovery package identity.')
        if not isinstance(package.get('error', ''), str):
            raise ValueError('Invalid recovery download error.')
        seen.add(name)
    return packages


def cancelled():
    path = os.environ.get('XETAL_SETUP_CANCEL_FILE')
    return bool(path and Path(path).exists())


def terminal_choice(packages):
    print('Rollback packages could not be downloaded:', flush=True)
    for package in validate(packages):
        print('  '+package['name']+' '+package['version'], flush=True)
    print(WARNING, flush=True)
    if not sys.stdin.isatty() or cancelled():
        return 'cancel'
    try:
        choice = input('Retry downloads [r], cancel installation [Enter], or continue without package rollback [continue]: ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 'cancel'
    return {'r':'retry', 'retry':'retry', 'continue':CONTINUE}.get(choice, 'cancel')


def ask(packages):
    validate(packages)
    if cancelled():
        return 'cancel'
    if os.environ.get('XETAL_SETUP_GUI') != '1':
        return terminal_choice(packages)
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('recovery_prompt.py'))],
                                input=json.dumps(packages), capture_output=True, text=True)
        choice = result.stdout.strip()
        if result.returncode == 0 and choice in CHOICES and not cancelled():
            return choice
    except (OSError, subprocess.SubprocessError):
        pass
    return 'cancel'
