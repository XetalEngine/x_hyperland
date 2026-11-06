#!/usr/bin/env python3
"""Use normal su/PAM authentication when a minimal system has no sudo."""
import getpass
import os
from pathlib import Path
import pwd
import re
import secrets
import shlex
import signal
import subprocess
import sys

import debian_su as conversation
import runtime_install as runtime


def desktop(uid):
    account = pwd.getpwuid(int(uid))
    if account.pw_uid <= 0 or account.pw_uid == 65534:
        raise RuntimeError('Open Setup as your regular desktop user.')
    return account


def password():
    if os.environ.get('XETAL_SETUP_GUI') == '1':
        return conversation.root_password()
    # Refuse getpass's echoing stdin fallback if there is no controlling TTY.
    with open('/dev/tty', 'r+') as terminal:
        return bytearray(getpass.getpass('Root password for package setup: ', stream=terminal).encode())


def run(command, prompt=None, output=None):
    if not command:
        raise RuntimeError('A Setup administrator command is required.')
    account = desktop(os.getuid())
    marker = 'XETAL_ROOT_READY_'+secrets.token_hex(16)
    payload = ['/usr/bin/python3', str(Path(__file__).resolve()), '--exec', str(account.pw_uid), marker, *command]
    args = ['/usr/bin/su', '--login', '--shell', '/bin/sh', '--command', shlex.join(payload), 'root']
    if output is None:
        def output(data):
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    return conversation.exchange(args, marker.encode(), prompt or password, output)


def execute(uid, marker, command):
    if os.geteuid() != 0 or not command:
        raise RuntimeError('Administrator authentication is required.')
    account = desktop(uid)
    if not re.fullmatch(r'XETAL_ROOT_READY_[0-9a-f]{32}', marker):
        raise RuntimeError('Invalid administrator authentication exchange.')
    environment = {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'HOME':'/root', 'USER':'root',
                   'LOGNAME':'root', 'LC_ALL':'C', 'DEBIAN_FRONTEND':'noninteractive',
                   'XETAL_SETUP_SU_UID':str(account.pw_uid)}
    print(marker, flush=True)
    os.execvpe(command[0], command, environment)


if __name__ == '__main__':
    try:
        if sys.argv[1:2] == ['--exec'] and len(sys.argv) >= 5:
            execute(sys.argv[2], sys.argv[3], sys.argv[4:])
        else:
            def cancelled(*_):
                raise conversation.AuthenticationCancelled('Administrator operation was cancelled.')
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGQUIT):
                signal.signal(signum, cancelled)
            sys.exit(run(sys.argv[1:]))
    except conversation.AuthenticationCancelled as error:
        print(str(error), file=sys.stderr)
        sys.exit(runtime.DEBIAN_AUTH_CANCELLED)
    except (conversation.AuthenticationError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(runtime.DEBIAN_AUTH_FAILED)
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
