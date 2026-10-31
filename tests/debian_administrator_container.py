#!/usr/bin/env python3
"""Exercise real account enrollment ONLY inside a disposable Debian container."""
import grp
import os
from pathlib import Path
import pwd
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import runtime_install as runtime


def main():
    if os.environ.get('XETAL_DISPOSABLE_DEBIAN') != '1' or os.geteuid() != 0 or not runtime.policy.debian_host():
        raise SystemExit('Requires root inside disposable Debian 13 and XETAL_DISPOSABLE_DEBIAN=1; never run on a desktop host.')
    name = 'xetal-auth-test'
    # Refuse to reuse or delete any pre-existing account/group.
    for lookup in (pwd.getpwnam, grp.getgrnam):
        try: lookup(name)
        except KeyError: pass
        else: raise RuntimeError('The disposable authentication fixture already exists.')
    subprocess.run(['groupadd', name], check=True)
    created = False
    try:
        subprocess.run(['useradd', '--no-create-home', '--gid', name, '--groups', 'audio', name], check=True)
        created = True
        account = pwd.getpwnam(name)
        before = set(os.getgrouplist(name, account.pw_gid))
        sudo_gid = grp.getgrnam('sudo').gr_gid
        assert sudo_gid not in before
        protected = {path: path.read_bytes() for path in
                     (Path('/etc/passwd'), Path('/etc/shadow'), Path('/etc/sudoers'))}
        command = [sys.executable, str(ROOT/'installer/debian_administrator.py')]
        env = {**os.environ, 'PKEXEC_UID': str(account.pw_uid)}
        env.pop('SUDO_UID', None)
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
        assert 'administrator access enabled' in result.stdout, result.stdout
        assert set(os.getgrouplist(name, account.pw_gid)) == before | {sudo_gid}
        groups = {path: path.read_bytes() for path in (Path('/etc/group'), Path('/etc/gshadow'))}
        subprocess.run(command, env=env, capture_output=True, text=True, check=True)
        assert all(path.read_bytes() == contents for path, contents in groups.items()), 'Repeat changed groups'
        denied = subprocess.run(command, env={**env, 'PKEXEC_UID': '0'}, capture_output=True, text=True)
        assert denied.returncode != 0 and 'local desktop account' in denied.stderr, denied
        assert all(path.read_bytes() == contents for path, contents in groups.items()), 'Root target changed groups'
        assert all(path.read_bytes() == contents for path, contents in protected.items()), 'Unrelated account configuration changed'
    finally:
        if created:
            subprocess.run(['userdel', name], check=True)
        # Debian's userdel can also remove the matching private group.
        try: grp.getgrnam(name)
        except KeyError: pass
        else: subprocess.run(['groupdel', name], check=True)
    print('PASS: Debian account enrolled; existing groups/password/sudoers preserved; repeat unchanged; root target rejected.')


if __name__ == '__main__':
    main()
