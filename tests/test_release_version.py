"""Real commit hooks and offline archives in disposable repositories."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
VERSION = 'config/hypr/VERSION'


class ReleaseCommitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-version-')
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)/'repo'; self.repo.mkdir()
        for name in (VERSION, 'tools/version.py', 'config/hypr/updates/release_version.py',
                     '.githooks/pre-commit'):
            target = self.repo/name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO/name, target)
        (self.repo/VERSION).write_text('0.0.0.199-alpha\n')
        self.git('init','-q','-b','main')
        self.git('add','.')
        self.git('commit','-qm','Baseline 199')
        self.tool('--install-hooks')

    def git(self, *args, ok=True):
        result = subprocess.run(['git','-C',str(self.repo),'-c','user.name=Fixture',
            '-c','user.email=fixture@example.invalid','-c','commit.gpgSign=false',*args],
            capture_output=True,text=True)
        if ok:self.assertEqual(result.returncode,0,result.stderr)
        return result

    def tool(self, *args, ok=True):
        result = subprocess.run([sys.executable,str(self.repo/'tools/version.py'),*args],capture_output=True,text=True)
        if ok:self.assertEqual(result.returncode,0,result.stderr)
        return result

    def commit(self, name):
        (self.repo/name).write_text(name)
        self.git('add','--',name)
        self.git('commit','-qm',name)

    def test_new_commits_stamp_and_stage_only_the_version(self):
        (self.repo/'unstaged').write_text('keep outside commit')
        self.commit('first')
        self.assertEqual(self.git('show','HEAD:'+VERSION).stdout.strip(),'0.0.0.200-alpha')
        self.assertNotEqual(self.git('cat-file','-e','HEAD:unstaged',ok=False).returncode,0)
        self.commit('second')
        self.assertEqual(self.tool('--check','HEAD').stdout.strip(),'0.0.0.201-alpha')

    def test_retry_does_not_skip_builds_and_amend_advances(self):
        self.tool('--bump'); self.tool('--bump')
        self.assertEqual((self.repo/VERSION).read_text().strip(),'0.0.0.200-alpha')
        self.git('commit','-qm','Retry')
        self.assertEqual(self.tool().stdout.strip(),'0.0.0.200-alpha')
        self.git('commit','--amend','--no-edit','-q')
        self.assertEqual(self.tool().stdout.strip(),'0.0.0.201-alpha')

    def test_zip_and_shallow_clone_keep_the_stamped_version(self):
        self.commit('first')
        archive = self.repo.parent/'source.zip'
        self.git('archive','--format=zip','--output='+str(archive),'HEAD')
        with zipfile.ZipFile(archive) as source:
            self.assertEqual(source.read(VERSION),b'0.0.0.200-alpha\n')
        clone = self.repo.parent/'shallow'
        self.git('clone','-q','--depth=1',self.repo.as_uri(),str(clone))
        self.repo = clone
        self.tool('--install-hooks'); self.commit('second')
        self.assertEqual(self.tool().stdout.strip(),'0.0.0.201-alpha')

    def test_merge_commit_bumps_above_both_parents(self):
        self.git('checkout','-qb','feature'); self.commit('feature')
        self.git('checkout','-q','main'); self.commit('main')
        self.git('merge','--no-ff','--no-commit','feature')
        self.git('commit','-qm','Merge feature')
        self.assertEqual(self.tool('--check','HEAD').stdout.strip(),'0.0.0.201-alpha')

    def test_unstaged_version_edits_and_existing_hooks_are_not_overwritten(self):
        (self.repo/VERSION).write_text('0.1.0.199-beta\n')
        result = self.tool('--bump',ok=False)
        self.assertNotEqual(result.returncode,0); self.assertIn('unstaged',result.stderr)
        self.git('config','core.hooksPath','/tmp/another-hook-directory')
        self.assertNotEqual(self.tool('--install-hooks',ok=False).returncode,0)
        self.assertEqual(self.git('config','--get','core.hooksPath').stdout.strip(),'/tmp/another-hook-directory')


if __name__ == '__main__':unittest.main()
