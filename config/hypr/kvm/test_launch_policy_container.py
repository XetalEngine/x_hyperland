"""Exercise real sudo in a disposable root filesystem/user namespace.

The fixture password belongs only to the temporary alice account. Host sudoers,
accounts, modules, services and VM disks are never accessed or changed.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CONTAINER = r'''
import hashlib,json,os,pwd,shutil,subprocess,sys
from pathlib import Path
base=Path(sys.argv[1]); source=Path(sys.argv[2]); root=base/'root'
for directory in ('usr','etc/pam.d','etc/sudoers.d','proc','dev','run','tmp','var/lib','var/log','home/alice','source'):
    (root/directory).mkdir(parents=True,exist_ok=True)
(root/'tmp').chmod(0o1777)
for name,dest in (('bin','usr/bin'),('lib','usr/lib'),('lib64','usr/lib')):
    (root/name).symlink_to(dest)
for path in source.rglob('*'):
    if path.is_file() and path.suffix in ('.py','.json','.sh','.pem') and '__pycache__' not in path.parts:
        target=root/'source'/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
for path in [root/'source',*(root/'source').rglob('*')]:os.chown(path,1000,1000)
password='isolated-fixture-password'
hash_=subprocess.check_output(['/usr/bin/openssl','passwd','-6','-stdin'],input=password+'\n',text=True).strip()
(root/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\nalice:x:1000:1000:Alice:/home/alice:/bin/bash\n')
(root/'etc/shadow').write_text('root:!:20000:0:99999:7:::\nalice:'+hash_+':20000:0:99999:7:::\n');(root/'etc/shadow').chmod(0o600)
(root/'etc/group').write_text('root:x:0:\nalice:x:1000:\n')
(root/'etc/nsswitch.conf').write_text('passwd: files\ngroup: files\nshadow: files\n')
(root/'etc/pam.d/sudo').write_text('auth required pam_unix.so\naccount required pam_unix.so\nsession required pam_permit.so\n')
(root/'etc/sudoers').write_text('Defaults timestamp_timeout=0\nroot ALL=(ALL:ALL) ALL\n@includedir /etc/sudoers.d\nalice ALL=(ALL:ALL) PASSWD: ALL\n');(root/'etc/sudoers').chmod(0o440)
# The host's root UID is intentionally unmapped. A private copy of sudo gets
# the namespace root owner so its setuid transition is real inside the fixture.
(base/'privbin').mkdir()
subprocess.run(['mount','-t','tmpfs','-o','mode=0755,suid,exec','tmpfs',str(base/'privbin')],check=True)
shutil.copy2('/usr/bin/sudo',base/'privbin/sudo');(base/'privbin/sudo').chmod(0o4755)
subprocess.run(['mount','--bind','/usr',str(root/'usr')],check=True)
subprocess.run(['mount','-o','remount,bind,ro',str(root/'usr')],check=True)
subprocess.run(['mount','-t','tmpfs','-o','mode=0755','tmpfs',str(root/'usr/local')],check=True)
subprocess.run(['mount','--bind',str(base/'privbin/sudo'),str(root/'usr/bin/sudo')],check=True)
subprocess.run(['mount','-t','proc','proc',str(root/'proc')],check=True)
for name in ('null','urandom','random','zero'):
    (root/'dev'/name).touch();subprocess.run(['mount','--bind','/dev/'+name,str(root/'dev'/name)],check=True)
os.chroot(root);os.chdir('/')
home=Path('/home/alice');os.chown(home,1000,1000)
component=home/'component';(component/'bin').mkdir(parents=True)
(component/'.component.json').write_text('{}')
(component/'bin/qemu-system-x86_64').write_text('#!/bin/sh\nexit 0\n');(component/'bin/qemu-system-x86_64').chmod(0o755)
files=sorted(p for p in Path('/source').rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts and p.suffix in ('.py','.sh','.json','.pem') and not p.name.startswith('test_') and 'tests' not in p.parts)
digest=hashlib.sha256()
for path in files:digest.update(str(path.relative_to('/source')).encode()+b'\0'+path.read_bytes())
spec=dict(version=1,fingerprint='a'*64,source='/source',data=str(home/'data'),edition='stock',kernel=os.uname().release,
    code=digest.hexdigest(),components={'qemu':{'path':str(component),'manifest':hashlib.sha256(b'{}').hexdigest()}},
    plan={'argv':[str(component/'bin/qemu-system-x86_64')],'options':{},'config':{},'workdir':'/run/hyperfusion-approved-guest'})
request=home/'request.json';request.write_text(json.dumps(spec))
for path in home.rglob('*'):os.chown(path,1000,1000)
def user(args,input='',success=True):
    result=subprocess.run(args,input=input,capture_output=True,text=True,user=1000,group=1000,extra_groups=[],env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C'})
    assert (result.returncode==0)==success,(args,result.returncode,result.stdout,result.stderr)
    return result
helper='/usr/local/libexec/hyperfusion-kvm-1000'
try:
    os.umask(0o077)
    user(['sudo','-S','/usr/bin/python3','-I','/source/launch_policy.py','--install',str(request)],password+'\n')
    user(['sudo','-n',helper],json.dumps({'action':'status'}))
    policy_before=Path('/etc/sudoers').read_text()
    assert policy_before.rstrip().endswith('@include /etc/sudoers.d/hyperfusion-kvm-1000')
    approved=json.loads(Path('/var/lib/hyperfusion-kvm-launch/1000/current.json').read_text())
    user([approved['snapshot']+'/data/editions/stock/components/qemu/current/bin/qemu-system-x86_64'])
    user(['/usr/bin/cat','/var/lib/hyperfusion-kvm-launch/1000/current.json'],success=False)
    user(['sudo','-n','/usr/bin/true'],success=False)
    user(['sudo','-n','/usr/bin/bash','-c','true'],success=False)
    user(['sudo','-n',helper,'--install','/home/alice/request.json'],success=False)
    user(['sudo','-n','PYTHONPATH=/source',helper],success=False)
    user(['sudo','-n',helper],json.dumps({'action':'launch','fingerprint':'b'*64}),success=False)
    user(['sudo','-n',helper],json.dumps({'action':'launch','fingerprint':'a'*64,'command':['/bin/bash']}),success=False)
    user(['/usr/bin/python3','-c',"from pathlib import Path;Path('/source/launch_policy.py').write_text('raise SystemExit(90)')"])
    # The previously authenticated but now edited source is never imported.
    user(['sudo','-n',helper],json.dumps({'action':'status'}))
    user(['/usr/bin/python3','-c',"from pathlib import Path;Path('/usr/local/libexec/hyperfusion-kvm-1000').write_text('bad')"],success=False)
    user(['sudo','-n',helper],json.dumps({'action':'forget'}))
    assert '@include /etc/sudoers.d/hyperfusion-kvm-1000' not in Path('/etc/sudoers').read_text()
    user(['sudo','-n',helper],json.dumps({'action':'status'}),success=False)
    user(['sudo','-n','/usr/bin/true'],success=False)
    print('PASS: real sudo approval, exact command only, source isolation, denied shell/arguments/environment, revoke')
finally:
    # Return private fixture ownership to namespace root (the invoking host
    # user) so TemporaryDirectory can clean up after this namespace disappears.
    for top in (Path('/home'),Path('/source')):
        for path in [top,*top.rglob('*')]:
            if not path.is_symlink():os.chown(path,0,0)
'''


class SudoPolicyContainer(unittest.TestCase):
    def test_private_vm_files_tpm_socket_and_log_under_restrictive_umask(self):
        prefix=['unshare','--map-auto','--map-root-user','--mount','--pid','--fork']
        if not shutil.which('bwrap') or subprocess.run(prefix+['/usr/bin/true'],capture_output=True).returncode:
            self.skipTest('Subordinate user namespaces/bubblewrap unavailable')
        script=r"""
import json,os,socket,struct,subprocess,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import launch_sandbox as sandbox
import launch_policy as policy
base=Path(sys.argv[2]);base.chmod(0o755)
snapshot=base/'snapshot';snapshot.mkdir()
work=base/'run';work.mkdir()
private=base/'private';private.mkdir(mode=0o700);os.chown(private,1000,1000)
disk=private/'disk.img';disk.write_bytes(b'old disk');disk.chmod(0o600);os.chown(disk,1000,1000)
asset=private/'table.aml';asset.write_bytes(b'private ACPI');asset.chmod(0o600);os.chown(asset,1000,1000)
secret=private/'secret';secret.write_text('keep private');secret.chmod(0o600);os.chown(secret,1000,1000)
guest=snapshot/'guest'
guest.write_text('''#!/usr/bin/python3
import fcntl,json,os,socket,sys
from pathlib import Path
fds=[int(sys.argv[i+1].split(',')[0].split('=')[1]) for i,arg in enumerate(sys.argv[:-1]) if arg=='-add-fd']
node=json.loads(sys.argv[sys.argv.index('-blockdev')+1]);assert node['filename'].startswith('/dev/fdset/')
fd=next(fd for fd in fds if fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDWR)
os.ftruncate(fd,0);os.write(fd,b'approved write')
path=Path(sys.argv[sys.argv.index('-acpitable')+1][5:]);assert path.read_bytes()==b'private ACPI'
assert not (path.parent/'secret').exists()
try:path.write_text('must fail');raise AssertionError('asset was writable')
except OSError:pass
fields=dict(part.split('=',1) for part in sys.argv[sys.argv.index('-chardev')+1].split(',')[1:])
assert 'path' not in fields
with socket.socket(fileno=int(fields['fd'])) as client:
 client.sendall(b'TPM fixture');assert client.recv(32)==b'fixture reply'
caps=next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:'))
assert int(caps.split()[1],16)==0
assert not Path('/etc/shadow').exists()
print('private inputs, socket and capability boundary passed')
''');guest.chmod(0o755)
endpoint=str(private/'tpm.sock')
plan=dict(uid=1000,gid=1000,workdir=str(work),approved_snapshot=str(snapshot),tpm={'sock':endpoint},
 argv=[str(guest),'-blockdev',json.dumps({'driver':'file','filename':str(disk)}),
       '-acpitable','file='+str(asset),'-chardev','socket,id=chrtpm,path='+endpoint])
original=sandbox.sandbox_command
def no_host_kvm(*args):
 command=original(*args);index=command.index('--dev-bind');assert command[index+1:index+3]==['/dev/kvm','/dev/kvm']
 del command[index:index+3];return command
try:
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
  listener.bind(endpoint);os.chmod(endpoint,0o600);os.chown(endpoint,1000,1000);listener.listen();listener.settimeout(10)
  with patch.object(sandbox,'sandbox_command',side_effect=no_host_kvm):child=sandbox.ApprovedRuntime(plan).spawn_guest()
  try:
   connection,_=listener.accept()
   with connection:
    assert struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1:]==(1000,1000)
    connection.settimeout(10);assert connection.recv(32)==b'TPM fixture';connection.sendall(b'fixture reply')
   assert child.wait(timeout=10)==0
  finally:
   if child.poll() is None:child.kill();child.wait()
 assert disk.read_bytes()==b'approved write' and asset.read_bytes()==b'private ACPI'
 assert secret.read_text()=='keep private' and disk.stat().st_uid==1000 and disk.stat().st_mode&0o777==0o600
 runs=base/'logs';runs.mkdir()
 approved=dict(uid=1000,gid=1000,snapshot=str(snapshot),data=str(base),edition='stock',
  plan=dict(workdir='/run/hyperfusion-approved-guest',options={},config={},qmp='',agent_chardev=''))
 os.umask(0o077)
 with patch.object(policy,'protected_directory',return_value=runs),patch.object(policy.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')):
  run=policy.submit(approved)
 log=Path(run['workdir'])/'output.log';log.write_text('readable launch failure')
 result=subprocess.run(['/usr/bin/cat',str(log)],user=1000,group=1000,extra_groups=[],capture_output=True,text=True)
 assert result.returncode==0 and result.stdout=='readable launch failure'
 assert log.stat().st_mode&0o777==0o640
 print('PASS: private VM files and TPM, no guest capabilities, readable owner-group log with umask 0077')
finally:
 for path in [private,*private.rglob('*')]:os.chown(path,0,0)
"""
        with tempfile.TemporaryDirectory(prefix='fusion-private-vm-fixture-') as temporary:
            result=subprocess.run(prefix+['/usr/bin/python3','-c',script,str(Path(__file__).parent),temporary],
                                  capture_output=True,text=True,timeout=40)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS: private VM files and TPM',result.stdout)

    def test_real_scoped_sudo_and_revocation(self):
        if not all(shutil.which(command) for command in ('unshare','newuidmap','mount','sudo','visudo','openssl')):
            self.skipTest('User-namespace account tools unavailable')
        prefix=['unshare','--map-auto','--map-root-user','--mount','--pid','--fork']
        probe=subprocess.run(prefix+['/usr/bin/true'],capture_output=True)
        if probe.returncode:self.skipTest('Subordinate user namespaces unavailable')
        with tempfile.TemporaryDirectory(prefix='hyperfusion-sudo-fixture-') as temporary:
            result=subprocess.run(prefix+['/usr/bin/python3','-c',CONTAINER,temporary,str(Path(__file__).parent)],
                                  capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS: real sudo approval',result.stdout)


if __name__=='__main__':unittest.main()
