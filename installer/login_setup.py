"""Preserve the login choice and migrate an enabled greeter with its runtime."""
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
    if choice is None:
        if not enabled(): return
        # The system greeter has a separate plugin and configuration. An opted-in
        # installation must follow a compositor migration even with no new choice.
        from system_login import runtime_identity
        if json.loads(STATE.read_text()).get('runtime') == runtime_identity(root): return
    elif choice is False and not enabled(): return
    helper = Path(__file__).with_name('system_login.py')
    command = [*runtime_install.administrator(), '/usr/bin/python3', str(helper)]
    if choice is None:
        command += ['--refresh-runtime', '--source', str(root)]
    elif choice:
        command += ['--source', str(root), '--user', pwd.getpwuid(os.getuid()).pw_name]
        if skip_packages: command.append('--skip-packages')
    else: command += ['--restore', 'original']
    subprocess.run(command, check=True)
