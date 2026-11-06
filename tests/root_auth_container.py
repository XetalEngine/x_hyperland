#!/usr/bin/env python3
"""Real root-password fallback test, ONLY in a disposable Arch container."""
from contextlib import nullcontext
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
import dependencies
import root_auth as auth
import runtime_install as runtime


def child():
    data = json.load(sys.stdin)
    identity = patch.object(os, 'getuid', return_value=data['uid']) if data['root_pam'] else nullcontext()
    with identity, patch.dict(os.environ, {'XETAL_SETUP_GUI':'1'}), \
         patch.object(runtime.shutil, 'which', side_effect=lambda name:None if name in ('sudo', 'pkexec') else '/usr/bin/'+name):
        prefix = runtime.administrator()
        assert prefix == ['/usr/bin/python3', str(ROOT/'installer/root_auth.py')]
        output = io.BytesIO()
        command = ['/usr/bin/python3', '-c', 'import os;print(os.geteuid(), os.environ["XETAL_SETUP_SU_UID"])']
        try:
            auth.run(command, prompt=lambda:bytearray(b'wrong-test-password'), output=output.write)
        except auth.conversation.AuthenticationError:
            pass
        else:
            raise AssertionError('Wrong password accepted')
        assert not output.getvalue()
        def cancel():
            raise auth.conversation.AuthenticationCancelled('test')
        try:
            auth.run(command, prompt=cancel, output=output.write)
        except auth.conversation.AuthenticationCancelled:
            pass
        else:
            raise AssertionError('Cancellation ignored')
        assert not output.getvalue()
        password = lambda:bytearray(data['password'].encode())
        assert auth.run(command, prompt=password, output=output.write) == 0
        assert output.getvalue().strip() == f'0 {os.getuid()}'.encode()
        output = io.BytesIO()
        values = ['a space', "single'quote", '$(echo substituted)', '`echo substituted`']
        assert auth.run(['/usr/bin/python3', '-c', 'import json,sys;print(json.dumps(sys.argv[1:]))', *values],
                        prompt=password, output=output.write) == 0
        assert json.loads(output.getvalue()) == values
        assert auth.run(['/usr/bin/python3', '-c', 'raise SystemExit(100)'], prompt=password, output=output.write) == 100
        assert data['password'].encode() not in output.getvalue()
        with patch.object(runtime.shutil, 'which', side_effect=lambda name:'/usr/bin/'+name):
            assert runtime.administrator() == prefix
    print('PASS: real PAM authentication, wrong password, cancellation, literal arguments, identity and exit status.')


def main():
    if (os.environ.get('XETAL_DISPOSABLE_ARCH') != '1' or dependencies.distribution().get('ID') != 'arch'
            or not (Path('/run/.containerenv').exists() or Path('/.dockerenv').exists())):
        raise SystemExit('Requires an explicitly disposable Arch container; never run on a desktop host.')
    if '--child' in sys.argv:
        return child()
    if os.geteuid() != 0:
        raise SystemExit('Test controller must be container root.')
    name = 'fusion-root-auth-test'
    try:
        pwd.getpwnam(name)
    except KeyError:
        pass
    else:
        raise RuntimeError('Disposable test account already exists.')
    shadow = Path('/etc/shadow');original = shadow.read_bytes()
    pam = {path:path.read_bytes() for path in (Path('/etc/pam.d/su'), Path('/etc/pam.d/su-l'))}
    root_pam = '--root-pam' in sys.argv
    subprocess.run(['useradd', '--no-create-home', name], check=True)
    try:
        account = pwd.getpwnam(name)
        password = secrets.token_hex(24)
        subprocess.run(['chpasswd'], input=('root:'+password+'\n').encode(), check=True)
        if root_pam:
            # Restricted test namespaces may disable setuid executables. Require
            # real PAM authentication even for root in this disposable rootfs.
            for path, content in pam.items():
                changed, count = re.subn(rb'(?m)^(auth\s+sufficient\s+pam_rootok\.so.*)$', rb'# test: \1', content)
                assert count == 1
                path.write_bytes(changed)
        prefix = [] if root_pam else ['runuser', '-u', name, '--']
        result = subprocess.run([*prefix, '/usr/bin/python3', str(Path(__file__).resolve()), '--child'],
                                input=json.dumps({'password':password, 'uid':account.pw_uid, 'root_pam':root_pam}),
                                capture_output=True, text=True, timeout=90)
        assert password not in result.stdout+result.stderr
        if result.returncode:
            raise RuntimeError('Root authentication test failed:\n'+result.stdout+result.stderr)
        print(result.stdout.strip())
    finally:
        for path, content in pam.items():
            path.write_bytes(content)
        subprocess.run(['userdel', name], check=True)
        shadow.write_bytes(original)


if __name__ == '__main__':
    main()
