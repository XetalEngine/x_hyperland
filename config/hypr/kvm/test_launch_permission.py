"""Permission regression checks; never touch host sudoers or launch a real VM."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget
import launch_permission as client
import launch_policy as policy
import launch_wait
import launch_sandbox as sandbox


class ResponsiveAuthentication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_slow_authentication_keeps_event_loop_alive_and_restores_window(self):
        window = QWidget(); beats = []
        timer = QTimer(); timer.timeout.connect(lambda: beats.append(True)); timer.start(5)
        def wait():
            time.sleep(.12)
            return 42
        self.assertEqual(launch_wait.run(wait, window), 42)
        timer.stop()
        self.assertGreater(len(beats), 5)
        self.assertTrue(window.isEnabled())
        self.assertFalse(window._launch_waiting)

    def test_cancel_or_error_restores_controls_and_refuses_nested_launch(self):
        window = QWidget(); nested = []
        def repeat():
            try: launch_wait.run(lambda: None, window)
            except RuntimeError: nested.append(True)
        QTimer.singleShot(5, repeat)
        def cancelled():
            time.sleep(.05)
            raise InterruptedError('cancelled')
        with self.assertRaises(InterruptedError): launch_wait.run(cancelled, window)
        self.assertTrue(nested)
        self.assertTrue(window.isEnabled())


class BrokerContract(unittest.TestCase):
    def test_rule_allows_one_no_argument_helper_not_python_or_shell(self):
        rule = policy.rule(1000)
        self.assertIn('#1000 ALL=(root) NOPASSWD: NOSETENV:', rule)
        self.assertTrue(rule.rstrip().endswith('/hyperfusion-kvm-1000 ""'))
        self.assertNotIn('NOPASSWD: ALL', rule)
        self.assertNotIn('/bin/bash', rule)
        self.assertNotIn('systemd-run', rule)
        with tempfile.NamedTemporaryFile(mode='w') as file:
            file.write(rule); file.flush()
            result = subprocess.run(['/usr/bin/visudo', '-cf', file.name], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_config_and_unexpected_fields_never_execute(self):
        approved = dict(uid=1000, fingerprint='a'*64, kernel=os.uname().release)
        with patch.object(policy, 'submit') as submit:
            with self.assertRaises(ValueError):
                policy.dispatch(approved, dict(action='launch', fingerprint='b'*64))
            with self.assertRaises(ValueError):
                policy.dispatch(approved, dict(action='launch', fingerprint='a'*64, command=['bash']))
            with self.assertRaises(ValueError):
                policy.dispatch(approved, dict(action='launch', fingerprint='a'*64, plan={'argv':['bash']}))
            submit.assert_not_called()

    def test_kernel_change_requires_approval(self):
        approved = dict(uid=1000, fingerprint='a'*64, kernel='different-kernel')
        with self.assertRaisesRegex(ValueError, 'kernel changed'):
            policy.dispatch(approved, dict(action='launch', fingerprint='a'*64))

    def test_replaced_physical_disk_is_rejected_before_open(self):
        record=dict(path='/dev/fixture',canonical='/dev/fixture',rdev=1,sysfs='/sys/fixture',identity={'serial':'old'})
        with patch.object(policy,'device_identity',return_value=dict(record,identity={'serial':'new'})), patch.object(policy.os,'open') as opened:
            with self.assertRaisesRegex(RuntimeError,'disk changed'):policy.device_file(record)
            opened.assert_not_called()

    def test_forget_only_removes_own_rule_and_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root/'1000').mkdir()
            (root/'1000/current.json').write_text('{}')
            (root/'hyperfusion-kvm-1000').write_text('own rule')
            other = root/'hyperfusion-kvm-1001'; other.write_text('other rule')
            with patch.object(policy, 'BASE', root), patch.object(policy, 'SUDOERS', root), patch.object(policy, 'LIBEXEC', root), patch.object(policy,'policy_include') as include:
                self.assertEqual(policy.dispatch(dict(uid=1000), {'action':'forget'}), {'forgotten':True})
                include.assert_called_once_with(1000,False)
            self.assertFalse((root/'1000/current.json').exists())
            self.assertFalse((root/'hyperfusion-kvm-1000').exists())
            self.assertEqual(other.read_text(), 'other rule')

    def test_client_sends_no_shell_arguments_or_token_on_command_line(self):
        response = subprocess.CompletedProcess([], 0, '{"ready":true}', '')
        with patch.object(Path, 'is_file', return_value=True), patch.object(client.subprocess, 'run', return_value=response) as run:
            client.call('arm', 'a'*64, token='fixture-only-secret')
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['sudo', '-n', str(client.helper())])
        self.assertNotIn('fixture-only-secret', str(args))
        self.assertEqual(json.loads(kwargs['input'])['token'], 'fixture-only-secret')

    def test_file_paths_preserve_spaces_and_qemu_escaped_commas(self):
        files = sandbox.file_paths(['/usr/bin/qemu', '-blockdev', json.dumps({'filename':'/home/a/disk one.qcow2'}),
                                    '-smbios', 'file=/home/a/a,,b.bin', '-qmp', 'unix:/run/guest/qmp.sock,server=on'])
        self.assertEqual(files, {'/usr/bin/qemu', '/home/a/disk one.qcow2', '/home/a/a,b.bin'})


@unittest.skipUnless(shutil.which('bwrap'), 'bubblewrap required')
class SandboxBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe=subprocess.run(['bwrap','--unshare-all','--ro-bind','/','/','/usr/bin/true'],capture_output=True)
        if probe.returncode:raise unittest.SkipTest('User namespaces unavailable')

    def test_guest_can_write_only_bound_vm_files_even_after_source_link_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); snapshot=root/'snapshot'; snapshot.mkdir()
            work=root/'run'; work.mkdir()
            image=root/'disk image.raw'; image.write_text('guest data')
            secret=root/'host-secret'; secret.write_text('must remain unchanged')
            link=root/'disk-link'; link.symlink_to(image.name)
            # Exercise real mount/PID isolation under a disposable outer user
            # namespace. There is no real /dev/kvm, guest or privileged host job.
            script='''
import json, os, sys
from pathlib import Path
sys.path.insert(0, '/source')
import launch_sandbox as sandbox
base=Path('/fixture');fds=[]
plan=dict(uid=0,workdir=str(base/'run'),approved_snapshot=str(base/'snapshot'))
command=sandbox.sandbox_command(plan,['/usr/bin/python3','/fixture/disk-link'],fds)
# Replace the guest executable test with a fixture that opens the mounted input.
guest="from pathlib import Path; p=Path('/fixture/disk-link'); p.write_text('VM write'); assert not Path('/fixture/host-secret').exists(); assert not Path('/etc/shadow').exists(); assert not Path('/proc/1/root/fixture/host-secret').exists(); print('isolated')"
command=command[:-1]+['-c',guest]
# /dev/kvm is irrelevant to this filesystem test; remove only its exact bind.
i=command.index('--dev-bind');del command[i:i+3]
# Change the source after its descriptor was opened: the bind must retain the
# original file, not follow this replacement to a different host file.
(base/'disk-link').unlink();(base/'disk-link').symlink_to(base/'host-secret')
import subprocess
r=subprocess.run(command,pass_fds=tuple(fds),capture_output=True,text=True)
for fd in fds:os.close(fd)
print(r.stdout,r.stderr);sys.exit(r.returncode)
'''
            result=subprocess.run(['bwrap','--unshare-all','--uid','0','--gid','0','--cap-add','ALL','--ro-bind','/usr','/usr',
                '--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
                '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/run','--dir','/etc','--ro-bind','/etc/passwd','/etc/passwd',
                '--ro-bind','/etc/group','/etc/group','--bind',str(root),'/fixture',
                '--ro-bind',str(Path(__file__).parent),'/source',
                '/usr/bin/python3','-c',script],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('isolated',result.stdout)
            self.assertEqual(image.read_text(),'VM write')
            self.assertEqual(secret.read_text(),'must remain unchanged')

    def test_supervisor_tracks_and_pins_only_its_namespaced_guest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'snapshot').mkdir();(root/'run').mkdir()
            guest='''import json,os,socket,sys
s=socket.socket(socket.AF_UNIX);s.bind(sys.argv[1]);s.listen()
running=False;done=False
while not done:
 c,_=s.accept()
 with c:
  f=c.makefile('rwb');f.write(b'{"QMP":{}}\\n');f.flush()
  for raw in f:
   q=json.loads(raw);cmd=q['execute'];value={}
   if cmd=='query-cpus-fast':value=[{'cpu-index':0,'thread-id':os.getpid()}]
   elif cmd=='query-iothreads':value=[]
   elif cmd=='cont':
    assert len(os.sched_getaffinity(0))==1
    running=True
   elif cmd=='query-status':value={'running':running}
   elif cmd=='quit':done=True
   f.write(json.dumps({'return':value,'id':q['id']}).encode()+b'\\n');f.flush()
   if done:break
'''
            (root/'snapshot/guest.py').write_text(guest)
            script='''import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/source');sys.path.insert(0,'/source/backend/lib')
from virtual_gpu import QMP
base=Path('/fixture');work=base/'run';cpu=min(os.sched_getaffinity(0))
plan=dict(uid=0,gid=0,workdir=str(work),qmp=str(work/'qmp.sock'),approved_snapshot=str(base/'snapshot'),
 config={'devices':[]},options={'realtime':False},iothreads=[],
 pinning={'vcpupin':[{'vcpu':0,'cpuset':str(cpu)}]},
 argv=['/usr/bin/python3',str(base/'snapshot/guest.py'),str(work/'qmp.sock')])
(work/'plan.json').write_text(json.dumps(plan))
worker="import json,sys;sys.path.insert(0,'/source');from launch_sandbox import ApprovedRuntime;sys.exit(ApprovedRuntime(json.load(open('/fixture/run/plan.json'))).run())"
with (work/'log').open('w+') as log:
 child=subprocess.Popen(['/usr/bin/python3','-c',worker],stdout=log,stderr=log)
 try:
  deadline=time.monotonic()+10
  while child.poll() is None and time.monotonic()<deadline:
   try:state=json.loads((work/'status.json').read_text())
   except (OSError,ValueError):state={}
   if state.get('state')=='running':break
   time.sleep(.05)
  assert state.get('state')=='running',(work/'log').read_text()
  with QMP(str(work/'qmp.sock')) as qmp:
   assert qmp.execute('query-status')['running'];qmp.execute('quit')
  assert child.wait(timeout=5)==0,(work/'log').read_text()
  assert json.loads((work/'status.json').read_text())['state']=='stopped'
  print('guest lifecycle and CPU pinning passed')
 finally:
  if child.poll() is None:child.kill();child.wait()
'''
            result=subprocess.run(['bwrap','--unshare-all','--uid','0','--gid','0','--cap-add','ALL',
                '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
                '--proc','/proc','--dev','/dev','--dev-bind','/dev/zero','/dev/kvm','--tmpfs','/tmp','--tmpfs','/run',
                '--bind',str(root),'/fixture','--ro-bind',str(Path(__file__).parent),'/source',
                '/usr/bin/python3','-c',script],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('guest lifecycle and CPU pinning passed',result.stdout)


if __name__ == '__main__':unittest.main()
