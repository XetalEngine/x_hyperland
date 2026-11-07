"""Private TPM ownership checks use disposable files, never a real guest."""
import os
from pathlib import Path
import pwd
import tempfile
import unittest
from unittest.mock import patch,Mock

import private_tpm


class PrivateTPMTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.state=self.root/'tpm-identities/fixture/state'
        self.state.mkdir(parents=True)
        self.blob=self.state/'tpm2-00.permall';self.blob.write_bytes(b'original guest keys')
        self.uid=os.getuid();self.gid=pwd.getpwuid(self.uid).pw_gid

    def test_repair_preserves_bytes_and_selected_identity(self):
        extra=self.state/'keep-me';extra.write_bytes(b'not a TPM file');extra.chmod(0o640)
        lock=self.state/'.lock';lock.touch()
        private_tpm.repair(self.state,self.root,self.uid,self.gid)
        self.assertEqual(self.blob.read_bytes(),b'original guest keys')
        self.assertEqual(self.blob.stat().st_mode&0o777,0o600)
        self.assertEqual(lock.stat().st_mode&0o777,0o600)
        self.assertEqual(self.state.stat().st_mode&0o777,0o700)
        self.assertEqual(extra.read_bytes(),b'not a TPM file')
        self.assertEqual(extra.stat().st_mode&0o777,0o640)

    def test_symlink_and_hardlink_state_are_rejected_without_touching_target(self):
        target=self.root/'other';target.write_bytes(b'leave alone');target.chmod(0o644)
        self.blob.unlink()
        for link in ('symlink','hardlink'):
            with self.subTest(link=link):
                if link=='symlink':self.blob.symlink_to(target)
                else:os.link(target,self.blob)
                with self.assertRaises((ValueError,OSError)):
                    private_tpm.repair(self.state,self.root,self.uid,self.gid)
                self.assertEqual(target.read_bytes(),b'leave alone')
                self.assertEqual(target.stat().st_mode&0o777,0o644)
                self.blob.unlink()

    def test_symlink_directory_and_parent_escape_are_rejected(self):
        alias=self.root/'alias';alias.symlink_to(self.state,target_is_directory=True)
        for path in (alias,self.root,self.root/'../outside'):
            with self.subTest(path=path),self.assertRaises((OSError,ValueError)):
                private_tpm.repair(path,self.root,self.uid,self.gid)
        self.assertEqual(self.blob.read_bytes(),b'original guest keys')

    def test_missing_state_never_creates_keys(self):
        self.blob.unlink()
        with self.assertRaisesRegex(ValueError,'No keys were created'):
            private_tpm.repair(self.state,self.root,self.uid,self.gid)
        self.assertEqual(list(self.state.iterdir()),[])

    def test_private_process_drops_root_but_external_state_is_not_adopted(self):
        with patch.object(private_tpm,'repair') as repair,patch.object(os,'geteuid',return_value=0):
            self.assertEqual(private_tpm.process_options(self.state,self.uid,self.gid,self.root),
                             dict(user=self.uid,group=self.gid,extra_groups=[]))
            repair.assert_called_once_with(self.state,self.root,self.uid,self.gid)
            repair.reset_mock()
            self.assertEqual(private_tpm.process_options('/var/lib/libvirt/fixture',self.uid,self.gid,self.root),{})
            repair.assert_not_called()

    def test_generated_single_gpu_hook_uses_same_private_state_owner(self):
        import sys,subprocess,portable
        sys.path.insert(0,str(portable.ROOT/'backend/lib'));self.addCleanup(sys.path.pop,0)
        import launcher
        from model import VMConfig
        with patch.dict(os.environ,{'XETAL_KVM_DATA':str(self.root)}):
            cfg=VMConfig(portable.configuration('windows'))
            script=launcher.build_start(cfg,{})
        self.assertIn('private_tpm.py --state',script)
        self.assertIn(f'--uid {self.uid} --gid {os.getgid()}',script)
        self.assertIn('"$SWTPM" socket --daemon',script)
        subprocess.run(['bash','-n'],input=script,text=True,check=True)


if __name__=='__main__':unittest.main()
