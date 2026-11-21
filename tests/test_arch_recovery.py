"""Real libalpm file ownership and dependency recovery in an isolated root."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'installer'))
import arch_runtime


@unittest.skipUnless(Path('/usr/include/alpm.h').exists() and shutil.which('cc'), 'Arch libalpm and compiler required')
class ArchRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='fusion-alpm-test-')
        cls.workspace=Path(cls.temporary.name)
        cls.binary=cls.workspace/'arch-recovery'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                        str(ROOT/'installer/arch_recovery.c'),'-o',str(cls.binary),'-lalpm','-ljson-c'],check=True)
        cls.keyring=cls.workspace/'gnupg';cls.keyring.mkdir(mode=0o700)
        for name in ('pubring.gpg','trustdb.gpg'):
            source=Path('/etc/pacman.d/gnupg')/name
            if not source.exists():raise unittest.SkipTest('Arch signing keyring required')
            shutil.copyfile(source,cls.keyring/name)
        # Public trust data only. No agent, secret keys or network key retrieval.
        (cls.keyring/'gpg.conf').write_text('no-auto-check-trustdb\nno-auto-key-retrieve\nno-autostart\n')
        cls.package=next(p for item,p,s in arch_runtime.packages(cache=cls.workspace/'archives') if item['name']=='hyprlang')
        cls.version=next(item['version'] for item in arch_runtime.target()['packages'] if item['name']=='hyprlang')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.directory=Path(tempfile.mkdtemp(dir=self.workspace,prefix='case-'))
        self.root=self.directory/'root';self.root.mkdir()
        self.db=self.directory/'db';(self.db/'local').mkdir(parents=True)
        (self.db/'local/ALPM_DB_VERSION').write_text('9\n')
        self.inventory={}

    def entry(self,name,version,*,depends=(),provides=(),files=()):
        directory=self.db/'local'/(name+'-'+version);directory.mkdir()
        fields={'NAME':[name],'VERSION':[version],'BASE':[name],'ARCH':['x86_64'],'REASON':['0'],
                'VALIDATION':['none'],'DEPENDS':depends,'PROVIDES':provides}
        (directory/'desc').write_text(''.join('%'+key+'%\n'+'\n'.join(values)+'\n\n' for key,values in fields.items() if values))
        (directory/'files').write_text('%FILES%\n'+'\n'.join(files)+'\n\n')
        self.inventory[name]=version

    def plan(self,*,add=True,remove=True):
        return dict(root=str(self.root),database=str(self.db),gpgdir=str(self.keyring),logfile=str(self.directory/'alpm.log'),
                    architectures=['x86_64'],hookdirs=[],noupgrade=[],noextract=[],database_only=False,
                    inventory=self.inventory,add=[dict(path=str(self.package),name='hyprlang',version=self.version)] if add else [],
                    remove=[dict(name='compat-test',version='1-1')] if remove else [],
                    reasons={'fixture-dependencies':0,'hyprlang':1})

    def run_plan(self,plan):
        path=self.directory/'plan.json';path.write_text(json.dumps(plan))
        return subprocess.run([str(self.binary),str(path)],text=True,capture_output=True,timeout=30)

    def collision_fixture(self):
        # Synthetic installed metadata models a library split: the new main
        # package depends on a compatibility package; the old signed package
        # owns the compatibility file itself. Never alter the signed archive.
        self.entry('fixture-dependencies','1-1',provides=['libgcc','libstdc++','glibc','hyprutils','libhyprutils.so=13-64'])
        self.entry('hyprlang','999-1',depends=['compat-test'])
        self.entry('compat-test','1-1',files=['usr/','usr/lib/','usr/lib/libhyprlang.so.2'])
        self.file=self.root/'usr/lib/libhyprlang.so.2';self.file.parent.mkdir(parents=True)
        self.file.write_text('compatibility package placeholder')

    def test_removal_alone_is_rejected_and_does_not_change_files(self):
        self.collision_fixture()
        result=self.run_plan(self.plan(add=False))
        self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertIn('requires compat-test',result.stderr)
        self.assertEqual(self.file.read_text(),'compatibility package placeholder')
        self.assertFalse((self.db/'db.lck').exists())

    def test_restore_alone_is_rejected_for_real_file_conflict(self):
        self.collision_fixture()
        result=self.run_plan(self.plan(remove=False))
        self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertIn('File conflict:',result.stderr)
        self.assertEqual(self.file.read_text(),'compatibility package placeholder')
        self.assertFalse((self.db/'db.lck').exists())

    def test_atomic_restore_and_removal_preserve_dependencies_and_file_ownership(self):
        self.collision_fixture()
        result=self.run_plan(self.plan())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(self.file.is_symlink())
        self.assertEqual(self.file.resolve().read_bytes()[:4],b'\x7fELF')
        self.assertFalse((self.db/'local/compat-test-1-1').exists())
        self.assertFalse((self.db/'local/hyprlang-999-1').exists())
        desc=(self.db/'local'/('hyprlang-'+self.version)/'desc').read_text()
        self.assertIn('%REASON%\n1\n',desc)
        self.assertIn('%VALIDATION%\npgp\n',desc)
        self.assertFalse((self.db/'db.lck').exists())

    def test_invalid_plan_is_rejected_without_leaving_a_package_lock(self):
        self.collision_fixture()
        plan=self.plan();plan['reasons']['hyprlang']='bad'
        result=self.run_plan(plan)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.db/'db.lck').exists())
        self.assertEqual(self.file.read_text(),'compatibility package placeholder')

    def test_unsigned_archive_cannot_be_restored(self):
        self.collision_fixture()
        package=self.directory/self.package.name;shutil.copyfile(self.package,package)
        plan=self.plan();plan['add'][0]['path']=str(package)
        result=self.run_plan(plan)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('signature',result.stderr.lower())
        self.assertEqual(self.file.read_text(),'compatibility package placeholder')
        self.assertFalse((self.db/'db.lck').exists())
