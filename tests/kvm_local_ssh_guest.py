#!/usr/bin/env python3
"""Real SSH integration checks, ONLY in an explicitly disposable lab VM.

Copy local_ssh.py and guest_connection.py into /home/tester first. The VM's
cloud-init marker must have purpose=disposable-local-ssh-test. This test changes
only that disposable guest's service, loopback addresses and tester password.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=45, **kwargs)


def main():
    marker = Path('/etc/hyperfusion-deb-lab.json')
    if os.geteuid() != 0 or not marker.exists() or json.loads(marker.read_text()).get('purpose') != 'disposable-local-ssh-test':
        raise SystemExit('Requires the disposable local SSH test VM; never run on a desktop host.')
    sys.path.insert(0, '/home/tester')
    import local_ssh
    before = Path('/etc/ssh/sshd_config').read_bytes()
    run(['systemctl','is-active','--quiet','sshd.service'])
    # Test the same isolated Python/sudo entry point used by the UI, including
    # SUDO_UID validation and importing sibling modules under python -I.
    command = ['runuser','-u','tester','--','sudo','python3','-I','/home/tester/local_ssh.py','--enable',str(__import__('pwd').getpwnam('tester').pw_uid)]
    first = json.loads(run(command).stdout)
    assert first['port'] == 2222
    second = json.loads(run(command).stdout)
    assert second['port'] == 2222
    with tempfile.TemporaryDirectory(prefix='local-ssh-check-') as temporary:
        root = Path(temporary); key = root/'key'
        run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)])
        with Path('/home/tester/.ssh/authorized_keys').open('a') as target:
            target.write(key.with_suffix('.pub').read_text())
        options = ['ssh','-i',str(key),'-p','2222','-o','IdentitiesOnly=yes',
                   '-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(root/'known_hosts'),
                   '-o','ConnectTimeout=3','-o','ConnectionAttempts=1']
        assert run([*options,'-o','BatchMode=yes','tester@127.0.0.1','id -un']).stdout.strip() == 'tester'
        # Password login remains usable even though the cloud image disables it
        # in the administrator's separate, standard SSH configuration.
        password = secrets.token_hex(20)
        run(['chpasswd'], input='tester:'+password+'\n')
        askpass = root/'askpass'; askpass.write_text('#!/bin/sh\nprintf %s '+password+'\n');askpass.chmod(0o700)
        env = {**os.environ,'DISPLAY':':0','SSH_ASKPASS':str(askpass),'SSH_ASKPASS_REQUIRE':'force'}
        result = run([*options,'-o','PubkeyAuthentication=no','-o','NumberOfPasswordPrompts=1',
                      'tester@127.0.0.1','id -un'],env=env,start_new_session=True,stdin=subprocess.DEVNULL)
        assert result.stdout.strip() == 'tester'
        for address, allowed in (('192.168.56.1',True),('203.0.113.1',False)):
            run(['ip','address','add',address+'/32','dev','lo'])
            try:
                result = subprocess.run([*options,'-o','BatchMode=yes','-b',address,'tester@127.0.0.1','true'],
                                        capture_output=True,text=True,timeout=10)
                assert (result.returncode == 0) == allowed,(address,result.stderr)
            finally: run(['ip','address','del',address+'/32','dev','lo'])
        root_login = subprocess.run([*options,'-o','BatchMode=yes','root@127.0.0.1','true'],capture_output=True,timeout=10)
        assert root_login.returncode != 0
    assert Path('/etc/ssh/sshd_config').read_bytes() == before
    run(['systemctl','is-active','--quiet','sshd.service'])
    run(['systemctl','disable','--now',local_ssh.SERVICE])
    print(json.dumps({'setup':True,'repeat_setup':True,'key_login':True,'password_login':True,
                      'private_source_allowed':True,'public_source_denied':True,'root_denied':True,
                      'existing_sshd_preserved':True,'disable':True}))


if __name__ == '__main__': main()
