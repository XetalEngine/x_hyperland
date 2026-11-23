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
