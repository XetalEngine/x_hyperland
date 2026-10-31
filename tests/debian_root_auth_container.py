#!/usr/bin/env python3
"""Real su/PAM authentication; run ONLY inside a disposable Debian 13 container."""
from contextlib import nullcontext
import grp
import io
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import debian_su as auth
import runtime_install as runtime


def child():
    data = json.load(sys.stdin)
    account = pwd.getpwnam(data['user'])
    # Restricted user namespaces cannot map a second real UID. In that case
    # the controller removes pam_rootok in this disposable rootfs, so even a
    # root caller must pass the real PAM password conversation.
    identity = patch.object(os, 'getuid', return_value=account.pw_uid) if data['root_pam'] else nullcontext()
    with identity, patch.dict(os.environ, {'XETAL_SETUP_GUI': '1'}), \
         patch.object(runtime.shutil, 'which', side_effect=lambda name: None if name in ('pkexec', 'sudo') else '/usr/bin/'+name):
        prefix = runtime.administrator()
        assert prefix == ['/usr/bin/python3', str(ROOT/'installer/debian_su.py')]
        output = io.BytesIO()
        command = ['/usr/bin/python3', '-c', 'import os;print(os.geteuid(), os.environ["XETAL_SETUP_SU_UID"])']
        def password(): return bytearray(data['password'].encode())
        try:
            auth.run(command, prompt=lambda: bytearray(b'wrong-disposable-password'), output=output.write)
        except auth.AuthenticationError: pass
        else: raise AssertionError('Wrong root password was accepted')
        assert output.getvalue() == b'', 'An unauthenticated command produced output'
        def cancel(): raise auth.AuthenticationCancelled('test cancellation')
        try:
            auth.run(command, prompt=cancel, output=output.write)
        except auth.AuthenticationCancelled: pass
        else: raise AssertionError('Cancellation was ignored')
        assert output.getvalue() == b''
        assert auth.run(command, prompt=password, output=output.write) == 0
        assert output.getvalue().strip() == f'0 {account.pw_uid}'.encode()
        output = io.BytesIO()
        values = ['a space', "single'quote", '$(echo substituted)', '`echo substituted`']
        assert auth.run(['/usr/bin/python3', '-c', 'import json,sys;print(json.dumps(sys.argv[1:]))', *values],
                        prompt=password, output=output.write) == 0
        assert json.loads(output.getvalue()) == values
        output = io.BytesIO()
        assert auth.run(['/usr/bin/python3', str(ROOT/'installer/debian_administrator.py')],
                        prompt=password, output=output.write) == 0
        assert 'administrator access enabled' in output.getvalue().decode()
        assert account.pw_name in grp.getgrnam('sudo').gr_mem
        with patch.object(runtime.shutil, 'which', side_effect=lambda name: '/usr/bin/'+name):
            assert runtime.administrator() == prefix, 'Installation/recovery changed authentication midway'
        assert auth.run(['/usr/bin/python3', '-c', 'raise SystemExit(100)'],
                        prompt=password, output=output.write) == 100
        assert data['password'].encode() not in output.getvalue()
    print('PASS: real PAM rejected wrong password/cancellation, accepted root password, preserved argv, enrolled account and preserved command exit status.')


def main():
    if os.environ.get('XETAL_DISPOSABLE_DEBIAN') != '1' or not runtime.policy.debian_host():
        raise SystemExit('Requires a disposable Debian 13 container and XETAL_DISPOSABLE_DEBIAN=1; never run on a desktop host.')
    if '--child' in sys.argv:
        child()
        return
    if os.geteuid() != 0:
        raise SystemExit('The disposable test controller must run as root.')
    root_pam = '--root-pam' in sys.argv
    name = 'xetal-pam-test'
    for lookup in (pwd.getpwnam, grp.getgrnam):
        try: lookup(name)
        except KeyError: pass
        else: raise RuntimeError('The disposable PAM fixture already exists.')
    shadow = Path('/etc/shadow')
    pam = Path('/etc/pam.d/su')
    original_shadow, original_pam = shadow.read_bytes(), pam.read_bytes()
    original_sudoers = Path('/etc/sudoers').read_bytes()
    created = False
    try:
        subprocess.run(['useradd', '--no-create-home', '--user-group', '--groups', 'audio', name], check=True)
        created = True
        account = pwd.getpwnam(name)
        before = set(os.getgrouplist(name, account.pw_gid))
        assert grp.getgrnam('sudo').gr_gid not in before
        password = secrets.token_hex(24)
        subprocess.run(['chpasswd'], input=('root:'+password+'\n').encode(), check=True)
        if root_pam:
            changed, count = re.subn(rb'(?m)^(auth\s+sufficient\s+pam_rootok\.so.*)$', rb'# test: \1', original_pam)
            assert count == 1, 'Unexpected disposable PAM configuration'
            pam.write_bytes(changed)
        prefix = [] if root_pam else ['runuser', '--user', name, '--']
        result = subprocess.run([*prefix, '/usr/bin/python3', str(Path(__file__).resolve()), '--child'],
                                input=json.dumps(dict(user=name, password=password, root_pam=root_pam)),
                                capture_output=True, text=True, timeout=90)
        assert password not in result.stdout+result.stderr, 'Authentication leaked the test password'
        if result.returncode:
            raise RuntimeError('Debian PAM test failed:\n'+result.stdout+result.stderr)
        assert set(os.getgrouplist(name, account.pw_gid)) == before | {grp.getgrnam('sudo').gr_gid}
        assert Path('/etc/sudoers').read_bytes() == original_sudoers
        print(result.stdout.strip())
    finally:
        pam.write_bytes(original_pam)
        if created:
            subprocess.run(['userdel', name], check=True)
        shadow.write_bytes(original_shadow)
    assert shadow.read_bytes() == original_shadow
    assert pam.read_bytes() == original_pam


if __name__ == '__main__':
    main()
