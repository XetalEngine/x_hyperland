#!/usr/bin/env python3
"""Enable Debian's normal sudo group for the authenticated installing user."""
import grp
import os
from pathlib import Path
import pwd
import subprocess
import sys

import runtime_install as runtime


def desktop_account(uid):
    try:
        account = pwd.getpwuid(uid)
    except KeyError:
        raise RuntimeError('The installing desktop account no longer exists.') from None
    # Limit automatic enrollment to a local desktop account, never root,
    # nobody, service accounts, or an account supplied as a command argument.
    local = [line.split(':') for line in Path('/etc/passwd').read_text().splitlines()]
    if uid < 1000 or uid == 65534 or not any(
            len(fields) == 7 and fields[0] == account.pw_name and fields[2] == str(uid)
            for fields in local):
        raise RuntimeError('Automatic Debian administrator setup requires a local desktop account.')
    return account


def sudo_member(account):
    try:
        group = grp.getgrnam('sudo')
    except KeyError:
        return False
    return account.pw_gid == group.gr_gid or account.pw_name in group.gr_mem


def enable():
    """Root helper: derive the target only from sudo/pkexec authentication."""
    if os.geteuid() != 0 or not runtime.policy.debian_host():
        raise RuntimeError('Administrator account setup is only available through Setup on Debian 13.')
    identities = {os.environ[key] for key in ('PKEXEC_UID', 'SUDO_UID') if key in os.environ}
    if len(identities) != 1:
        raise RuntimeError('Cannot identify the authenticated installing user. Open Setup as your desktop user.')
    value = identities.pop()
    if not value.isascii() or not value.isdecimal():
        raise RuntimeError('Cannot identify the authenticated installing user. Open Setup as your desktop user.')
    account = desktop_account(int(value))
    if sudo_member(account):
        return False
    try:
        grp.getgrnam('sudo')
    except KeyError:
        raise RuntimeError('The Debian sudo group is missing. Install the Debian sudo package and retry.') from None
    result = subprocess.run(['/usr/sbin/usermod', '--append', '--groups', 'sudo', '--', account.pw_name],
                            capture_output=True, text=True,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    if result.returncode:
        raise RuntimeError('Could not enable administrator access for '+account.pw_name+': '+
                           (result.stderr or result.stdout).strip())
    if not sudo_member(account):
        raise RuntimeError('Debian administrator group membership could not be verified.')
    print('Debian administrator access enabled for '+account.pw_name+'. Existing groups were preserved.', flush=True)
    return True


def prepare():
    """Foreground Setup only; the desktop process remains unprivileged."""
    if not runtime.policy.debian_host():
        return False
    account = desktop_account(os.getuid())
    if sudo_member(account):
        return False
    print('Setting up Debian administrator access for '+account.pw_name+
          '. Authenticate with the administrator account shown in the password dialog.', flush=True)
    prefix = runtime.administrator()
    result = subprocess.run([*prefix, '/usr/bin/python3', str(Path(__file__).resolve())],
                            capture_output=True, text=True, env={**os.environ, 'LC_ALL': 'C'})
    output = (result.stdout or '')+(result.stderr or '')
    if output:
        print(output, end='' if output.endswith('\n') else '\n', flush=True)
    runtime.check_administrator_result(prefix, result.returncode, output)
    if result.returncode or not sudo_member(account):
        raise RuntimeError('Debian administrator setup did not finish. See the authentication details above.')
    print('Setup can continue now. Other applications will use the new administrator group after your next sign-in.', flush=True)
    return True


if __name__ == '__main__':
    try:
        if len(sys.argv) != 1:
            raise RuntimeError('This helper does not accept an account argument. Open Setup as your desktop user.')
        enable()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
