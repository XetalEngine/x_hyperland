"""The boot/login configuration is touched only by an explicit Setup choice."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import runtime_install

STATE = Path('/var/lib/xetal-fusion-login/installation.json')


def enabled():
    try: return json.loads(STATE.read_text()).get('enabled') is True
    except (OSError, ValueError): return False


def apply(choice, root, skip_packages=False):
    if choice is None or (choice is False and not enabled()): return
    helper = Path(__file__).with_name('system_login.py')
    command = [*runtime_install.administrator(), '/usr/bin/python3', str(helper)]
    if choice:
        command += ['--source', str(root), '--user', pwd.getpwuid(os.getuid()).pw_name]
        if skip_packages: command.append('--skip-packages')
    else: command += ['--restore', 'original']
    subprocess.run(command, check=True)
