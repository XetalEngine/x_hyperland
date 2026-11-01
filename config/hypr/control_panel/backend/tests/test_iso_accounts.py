"""Account choices and target confinement; no host user or block-device changes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'iso/installer_account.py'
spec=importlib.util.spec_from_file_location('account_setup',SOURCE)
account=importlib.util.module_from_spec(spec);spec.loader.exec_module(account)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.target=Path(self.temp.name)/'target';(self.target/'etc').mkdir(parents=True)
        (self.target/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\nalice:x:1000:1000:Alice:/home/alice:/bin/bash\nbob:x:1001:1001:Bob:/home/bob:/bin/bash\n')
        (self.target/'etc/group').write_text('root:x:0:\nalice:x:1000:\nbob:x:1001:\nwheel:x:10:alice\n')
        self.users=[dict(name='alice',uid=1000,gid=1000,home='/home/alice')]
        self.plan=dict(change=True,original='alice',uid=1000,username='charlie',password_hash='$6$salt$'+'a'*86)

    def test_password_is_hashed_privately_and_not_returned(self):
        with patch.object(account.subprocess,'run',wraps=subprocess.run) as run:
            plan=account.choice(self.users,0,'charlie','Keep this private!','Keep this private!')
        self.assertTrue(account.HASH.fullmatch(plan['password_hash']))
        self.assertNotIn('Keep this private!',json.dumps(plan))
        run.assert_not_called()
        for name,password in [('alice','x'),('charlie','')]:
            with self.assertRaises(ValueError):account.choice(self.users,0,name,password,password)

    def test_invalid_names_passwords_and_reserved_names_are_rejected(self):
        for name in ('root','wheel','-root','x:y','a/b','a'*33):
            with self.subTest(name=name),self.assertRaises(ValueError):
                account.choice(self.users,0,name,'x','x',{'root','wheel'})
        for a,b in [('one','two'),('nul\x00character','nul\x00character')]:
            with self.assertRaises(ValueError):account.choice(self.users,0,'charlie',a,b)

    def test_fresh_account_cannot_keep_source_login_or_password(self):
        for changes in ({'change':False},{'username':'alice'},{'password_hash':''}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):account.require_fresh(self.plan|changes)

    def test_uppercase_username_and_user_chosen_passwords(self):
        for password in ('phphph','x',' ','111111','é🙂', 'a'*300):
            with self.subTest(length=len(password)):
                plan=account.choice(self.users,0,'Valdemar',password,password)
                self.assertEqual(plan['username'],'valdemar')
                self.assertTrue(account.HASH.fullmatch(plan['password_hash']))
                library=account.ctypes.CDLL('libcrypt.so.2')
                library.crypt_rn.argtypes=[account.ctypes.c_char_p,account.ctypes.c_char_p,account.ctypes.c_void_p,account.ctypes.c_int]
                library.crypt_rn.restype=account.ctypes.c_char_p
                buffer=account.ctypes.create_string_buffer(32768)
                self.assertEqual(library.crypt_rn(password.encode(),plan['password_hash'].encode(),buffer,len(buffer)).decode(),plan['password_hash'])
                if len(password)>256:
                    self.assertNotEqual(library.crypt_rn(password[:256].encode(),plan['password_hash'].encode(),buffer,len(buffer)).decode(),plan['password_hash'])

    def test_source_metadata_filters_system_and_invalid_accounts(self):
        p=self.target/'accounts.tsv';p.write_text('root\t0\t0\t/root\nalice\t1000\t1000\t/home/alice\nnobody\t65534\t65534\t/\nbad!\t1001\t1001\t/home/bad\n')
        self.assertEqual(account.accounts(p),self.users)

    def test_identity_and_destination_collisions_are_rechecked(self):
        for change in ({'uid':1001},{'username':'root'},{'username':'bob'},{'password_hash':'raw password'},{'username':'-admin'}):
            with self.subTest(change=change),self.assertRaises(ValueError):account.validate(self.plan|change,self.target)
        (self.target/'home/charlie').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'home folder'):account.validate(self.plan,self.target)

    def test_account_commands_only_use_mounted_target_and_encrypted_stdin(self):
        with self.assertRaises(ValueError):account.apply(self.plan,self.target)
        with self.assertRaises(ValueError):account.apply(self.plan,Path('/'))
        encoded='$6$salt$'+'a'*86
        with patch.object(Path,'is_mount',return_value=True),patch.object(account.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run,patch.object(account,'ensure_administrator') as administrator:
            account.apply(self.plan|{'password_hash':encoded},self.target)
        self.assertEqual(administrator.call_args.args[:3],(self.target,'charlie',1000))
        calls=run.call_args_list
        self.assertEqual(calls[0].args[0],['arch-chroot',str(self.target),'visudo','--check'])
        self.assertEqual(calls[1].args[0],['arch-chroot',str(self.target),'groupmod','--new-name','charlie','alice'])
        self.assertEqual(calls[2].args[0],['arch-chroot',str(self.target),'userdel','alice'])
        self.assertEqual(calls[3].args[0],['arch-chroot',str(self.target),'useradd','--uid','1000','--gid','1000',
            '--home-dir','/home/charlie','--shell','/bin/bash','--comment','charlie','--no-user-group','--create-home','--groups','wheel','charlie'])
        self.assertEqual(calls[4].args[0],['arch-chroot',str(self.target),'chpasswd','--encrypted'])
        self.assertEqual(calls[4].kwargs['input'],'charlie:'+encoded+'\n')
        with patch.object(Path,'is_mount',return_value=True),patch.object(account.subprocess,'run') as run:
            account.apply({'change':False},self.target);run.assert_not_called()

    def test_moved_profile_paths_inventory_and_autologin_are_updated(self):
        p=self.target/'home/charlie/.config/hypr';p.mkdir(parents=True)
        old='exec = /home/alice/.config/hypr/start\n# /home/alice-other\n'
        (p/'hyprland.conf').write_text(old)
        (p/'.xetal-update.json').write_text(json.dumps({'files':{'hyprland.conf':{'text':old,'sha256':hashlib.sha256(old.encode()).hexdigest()}}}))
        outside=Path(self.temp.name)/'untouched';outside.write_text(old);(p/'link').symlink_to(outside)
        (self.target/'etc/sddm.conf').write_text('[Autologin]\nUser=alice\n')
        account.migrate_profile(self.target,'/home/alice','/home/charlie');account.migrate_autologin(self.target,'alice','charlie')
        expected=old.replace('/home/alice/','/home/charlie/')
        self.assertEqual((p/'hyprland.conf').read_text(),expected)
        entry=json.loads((p/'.xetal-update.json').read_text())['files']['hyprland.conf']
        self.assertEqual(entry['sha256'],hashlib.sha256(entry['text'].encode()).hexdigest())
        self.assertEqual(outside.read_text(),old)
        self.assertIn('User=charlie',(self.target/'etc/sddm.conf').read_text())

    def test_external_home_or_account_database_is_rejected(self):
        outside=Path(self.temp.name)/'outside';outside.mkdir();(self.target/'home').symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'outside'):account.validate(self.plan,self.target)
        with self.assertRaisesRegex(ValueError,'outside'):account.migrate_profile(self.target,'/home/alice','/home/charlie')

if __name__=='__main__':unittest.main()
