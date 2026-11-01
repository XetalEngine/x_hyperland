"""Real account creation and sudo policy checks in a disposable user namespace."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]/'iso'
spec=importlib.util.spec_from_file_location('account_tools',ROOT/'installer_account.py')
account=importlib.util.module_from_spec(spec);spec.loader.exec_module(account)


@unittest.skipUnless(all(shutil.which(tool) for tool in ('bwrap','chpasswd','sudo','visudo')),'bubblewrap, shadow and sudo tools are required')
class AccountToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        check=subprocess.run(['bwrap','--unshare-all','--ro-bind','/','/','--proc','/proc','--dev','/dev','--uid','0','--gid','0','/usr/bin/true'],capture_output=True)
        if check.returncode:raise unittest.SkipTest('An isolated user namespace is not available in this sandbox')

    def exercise(self,change,include_directory=False,invalid_policy=False,repeat=False,permission_case=None):
        with tempfile.TemporaryDirectory(prefix='iso-account-tools-') as tmp:
            base=Path(tmp);target=base/'target';helpers=base/'helpers';helpers.mkdir()
            for name in ('etc/pam.d','home/alice/.config/hypr','var/log','var/mail','usr','proc','dev','run','tmp'):
                (target/name).mkdir(parents=True)
            (target/'bin').symlink_to('usr/bin');(target/'lib').symlink_to('usr/lib');(target/'lib64').symlink_to('usr/lib')
            (target/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\nalice:x:1000:1000:Alice:/home/alice:/bin/bash\n')
            old_hash=account.password_hash('source password')
            (target/'etc/shadow').write_text('root:!:20000:0:99999:7:::\nalice:'+old_hash+':20000:0:99999:7:::\n')
            (target/'etc/group').write_text('root:x:0:\nalice:x:1000:\nwheel:x:10:alice\n')
            (target/'etc/gshadow').write_text('root:!::\nalice:!::\nwheel:!::alice\n')
            other_account={
                'passwd':'bob:x:1001:1001:Bob:/home/bob:/bin/bash',
                'shadow':'bob:'+account.password_hash('bob keeps this password')+':19000:0:99999:7:::',
                'group':'bob:x:1001:', 'gshadow':'bob:!::',
            }
            for name,record in other_account.items():
                with (target/'etc'/name).open('a') as stream:stream.write(record+'\n')
            (target/'home/bob').mkdir();(target/'home/bob/keep.txt').write_text('Other account files stay here.\n')
            (target/'etc/nsswitch.conf').write_text('passwd: files\ngroup: files\nshadow: files\ngshadow: files\n')
            (target/'etc/login.defs').write_text('USERGROUPS_ENAB yes\nPASS_MAX_DAYS 99999\nPASS_MIN_DAYS 0\n')
            (target/'etc/pam.d/sudo').write_text('auth required pam_unix.so\naccount required pam_unix.so\nsession required pam_unix.so\n')
            # A source with name-only authorization reproduces the reported
            # failure: usermod retains wheel but wheel has no sudo rule here.
            original='Defaults rootpw\nroot ALL=(ALL:ALL) ALL\nalice ALL=(ALL:ALL) ALL\nbob ALL=(root) /usr/bin/true\n'
            if include_directory or permission_case:original+='@includedir /etc/sudoers.d\n'
            if invalid_policy:original+='this is not a valid sudo rule\n'
            (target/'etc/sudoers').write_text(original);(target/'etc/sudoers').chmod(0o440)
            if permission_case:
                directory=target/'etc/sudoers.d';directory.mkdir()
                hooks=directory/'libvirt-hooks'
                hook_contents='alice ALL=(root) /usr/bin/true\n'
                hooks.write_text(hook_contents);hooks.chmod(0o666 if permission_case=='writable' else 0o644)
                (target/'etc/sudoers').chmod(0o644)
                ignored=directory/'unrelated.backup';ignored.write_text('Ignored by includedir\n');ignored.chmod(0o644)
                if permission_case=='hardlink':os.link(hooks,base/'outside-policy')
            (target/'home/alice/.config/hypr/hyprland.conf').write_text('source = /home/alice/.config/hypr/keys.conf\n')
            (target/'etc/sddm.conf').write_text('[Autologin]\nUser=alice\n')
            # Mounts are already supplied by bubblewrap. Only this fixture shim
            # replaces arch-chroot's mount plumbing; the account binaries are real.
            (helpers/'arch-chroot').write_text('#!/bin/sh\nexec /usr/bin/chroot "$@"\n');(helpers/'arch-chroot').chmod(0o755)
            users=[dict(name='alice',uid=1000,gid=1000,home='/home/alice')]
            plan=account.choice(users,0,'Valdemar','phphph','phphph') if change else {'change':False}
            command=['bwrap','--unshare-all','--uid','0','--gid','0',
                     '--cap-add','CAP_SYS_CHROOT','--cap-add','CAP_DAC_OVERRIDE','--cap-add','CAP_CHOWN','--cap-add','CAP_FOWNER',
                     '--cap-add','CAP_SETUID','--cap-add','CAP_SETGID','--ro-bind','/usr','/usr',
                     '--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
                     '--proc','/proc','--dev','/dev','--tmpfs','/run','--tmpfs','/tmp','--dir','/etc',
                     '--bind',str(target),'/target','--ro-bind','/usr','/target/usr','--proc','/target/proc','--dev','/target/dev',
                     '--ro-bind',str(ROOT),'/source','--ro-bind',str(helpers),'/helpers','--setenv','PATH','/helpers:/usr/bin',
                     '--chdir','/','/usr/bin/python3','/source/installer_account.py','/target']
            result=subprocess.run(command,input=json.dumps(plan),capture_output=True,text=True,timeout=20)
            for name,record in other_account.items():
                self.assertIn(record,(target/'etc'/name).read_text().splitlines())
            self.assertEqual((target/'home/bob/keep.txt').read_text(),'Other account files stay here.\n')
            policy=target/'etc/sudoers.d/hyper-fusion-1000.conf'
            if invalid_policy or permission_case in ('writable','hardlink'):
                self.assertNotEqual(result.returncode,0)
                if invalid_policy:self.assertIn('visudo',result.stderr)
                self.assertEqual((target/'etc/sudoers').read_text(),original)
                self.assertFalse(policy.exists())
                self.assertIn('alice:x:1000:',(target/'etc/passwd').read_text())
                self.assertIn(old_hash,(target/'etc/shadow').read_text())
                if permission_case:
                    self.assertEqual((target/'etc/sudoers').stat().st_mode & 0o777,0o644)
                    self.assertEqual(hooks.stat().st_mode & 0o777,0o666 if permission_case=='writable' else 0o644)
                if permission_case=='hardlink':self.assertEqual((base/'outside-policy').stat().st_mode & 0o777,0o644)
                return
            self.assertEqual(result.returncode,0,result.stderr)
            if permission_case:
                self.assertEqual(hooks.read_text(),hook_contents)
                self.assertEqual(hooks.stat().st_mode & 0o777,0o440 if change else 0o644)
                self.assertEqual((target/'etc/sudoers').stat().st_mode & 0o777,0o440 if change else 0o644)
                self.assertEqual(ignored.stat().st_mode & 0o777,0o644)
            if change:
                self.assertIn('valdemar:x:1000:1000:valdemar:/home/valdemar:',(target/'etc/passwd').read_text())
                self.assertIn('wheel:x:10:valdemar',(target/'etc/group').read_text())
                self.assertIn('valdemar:x:1000:',(target/'etc/group').read_text())
                self.assertIn(plan['password_hash'],(target/'etc/shadow').read_text())
                self.assertNotIn(old_hash,(target/'etc/shadow').read_text())
                self.assertNotIn('alice:',(target/'etc/passwd').read_text())
                self.assertNotIn('alice:',(target/'etc/shadow').read_text())
                self.assertIn('/home/valdemar/',(target/'home/valdemar/.config/hypr/hyprland.conf').read_text())
                self.assertIn('User=valdemar',(target/'etc/sddm.conf').read_text())
                self.assertFalse((target/'home/alice').exists())
                self.assertEqual(policy.stat().st_mode & 0o777,0o440)
                self.assertIn('valdemar ALL=(ALL:ALL) PASSWD: ALL',policy.read_text())
                self.assertNotIn('NOPASSWD',policy.read_text())
                self.assertEqual((target/'etc/sudoers').read_text().count('@include /etc/sudoers.d/hyper-fusion-1000.conf'),1)
            else:
                self.assertIn('alice:x:1000:',(target/'etc/passwd').read_text())
                self.assertIn('alice:'+old_hash+':',(target/'etc/shadow').read_text())
                self.assertEqual((target/'etc/sudoers').read_text(),original)
                self.assertFalse(policy.exists())
            username='valdemar' if change else 'alice'
            if repeat:
                second=account.choice([dict(name='valdemar',uid=1000,gid=1000,home='/home/valdemar')],0,'Airton','x','x')
                result=subprocess.run(command,input=json.dumps(second),capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stderr)
                username='airton'
                self.assertIn('airton ALL=(ALL:ALL) PASSWD: ALL',policy.read_text())
                self.assertNotIn('valdemar',policy.read_text())
                self.assertEqual((target/'etc/sudoers').read_text().count('@include /etc/sudoers.d/hyper-fusion-1000.conf'),1)
            # Ask the real sudo policy engine about the restored identity;
            # listing privileges does not run a privileged user command.
            # This namespace maps only root. Sudo normally reads group-readable
            # policies as UID 1, which is intentionally unmapped here. Its
            # supported owner-only mode avoids that switch; rule contents and
            # authorization are unchanged. Default 0440 was validated above.
            (target/'etc/sudo.conf').write_text(''.join('Plugin '+plugin+' sudoers.so sudoers_mode=0400\n' for plugin in ('sudoers_policy','sudoers_io','sudoers_audit')))
            (target/'etc/sudoers').chmod(0o400)
            if policy.exists():policy.chmod(0o400)
            if permission_case:hooks.chmod(0o400)
            sudo_command=command[:-3]+['/usr/bin/chroot','/target','/usr/bin/sudo','-n','-ll','-U',username]
            authorized=subprocess.run(sudo_command,capture_output=True,text=True,timeout=20)
            self.assertEqual(authorized.returncode,0,authorized.stderr)
            self.assertIn('RunAsUsers: ALL',authorized.stdout)
            self.assertIn('RunAsGroups: ALL',authorized.stdout)
            self.assertRegex(authorized.stdout,r'Commands:\s+ALL')
            if change:
                self.assertIn('!rootpw',authorized.stdout)
                self.assertIn('!targetpw',authorized.stdout)
                self.assertIn('!runaspw',authorized.stdout)
            other_privileges=subprocess.run(sudo_command[:-1]+['bob'],capture_output=True,text=True,timeout=20)
            self.assertEqual(other_privileges.returncode,0,other_privileges.stderr)
            self.assertRegex(other_privileges.stdout,r'Commands:\s+/usr/bin/true')
            self.assertNotRegex(other_privileges.stdout,r'Commands:\s+ALL')
            self.assertNotIn('!rootpw',other_privileges.stdout)

    def test_keep_existing_account(self):self.exercise(False)
    def test_rename_home_group_memberships_and_simple_password(self):self.exercise(True)
    def test_renamed_administrator_with_existing_sudoers_include_directory(self):self.exercise(True,include_directory=True)
    def test_invalid_sudo_policy_rolls_back_installer_changes(self):self.exercise(True,invalid_policy=True)
    def test_installing_again_updates_administrator_without_duplicate_rules(self):self.exercise(True,repeat=True)
    def test_restored_sudoers_permissions_are_repaired_before_new_account_creation(self):self.exercise(True,permission_case='ordinary')
    def test_keep_existing_account_preserves_copied_sudoers_permissions(self):self.exercise(False,permission_case='ordinary')
    def test_permission_repair_rolls_back_when_policy_has_a_syntax_error(self):self.exercise(True,permission_case='ordinary',invalid_policy=True)
    def test_writable_policy_is_not_promoted_to_a_trusted_rule(self):self.exercise(True,permission_case='writable')
    def test_permission_repair_never_changes_a_hardlinked_file_outside_target(self):self.exercise(True,permission_case='hardlink')


if __name__=='__main__':unittest.main()
