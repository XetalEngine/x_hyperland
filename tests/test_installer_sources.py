"""Real Git exports and disposable profiles; no network or live installation."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'installer'))
import install
import update as updater


class InstallerSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-source-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root/'repo'
        (self.repo/'installer').mkdir(parents=True)
        for name in ('.gitattributes', 'installer/source-revision.txt'):
            shutil.copy2(REPO/name, self.repo/name)
        self.git('init', '-q')
        self.git('add', '.')
        self.git('commit', '-qm', 'Archive fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(
            ['git', '-C', str(self.repo), '-c', 'user.name=Fixture',
             '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgSign=false',
             *args], text=True, stderr=subprocess.PIPE)

    def export(self, format):
        archive = self.root/('source.'+format)
        self.git('archive', '--format='+format, '--output='+str(archive), self.commit)
        # A parent repository is deliberate: it must not supply the ZIP's version.
        destination = self.repo/('download-'+format)
        destination.mkdir()
        if format == 'zip':
            with zipfile.ZipFile(archive) as stream:stream.extractall(destination)
        else:
            with tarfile.open(archive) as stream:stream.extractall(destination, filter='data')
        return destination

    def test_clone_and_linked_worktree_use_their_own_commits(self):
        self.assertEqual(install.source_revision(self.repo), self.commit)
        worktree = self.root/'worktree'
        self.git('worktree', 'add', '--quiet', '--detach', str(worktree), self.commit)
        self.assertTrue((worktree/'.git').is_file())
        self.assertEqual(install.source_revision(worktree), self.commit)
        (self.repo/'installer/source-revision.txt').write_text('f'*40+'\n')
        self.assertEqual(install.source_revision(self.repo), self.commit)

    def test_zip_and_tar_register_the_exported_commit_without_git_or_network(self):
        self.git('commit', '--allow-empty', '-qm', 'Later checkout version')
        self.assertNotEqual(self.git('rev-parse', 'HEAD').strip(), self.commit)
        for format in ('zip', 'tar.gz'):
            with self.subTest(format=format):
                extracted = self.export(format)
                self.assertFalse((extracted/'.git').exists())
                self.assertEqual((extracted/'installer/source-revision.txt').read_text().strip(), self.commit)
                stage = self.root/('profile-'+format)
                stage.mkdir()
                (stage/'hyprland.conf').write_text('# delivered defaults\n')
                with patch.object(install, 'REPO', extracted), \
                     patch.object(install.subprocess, 'check_output', side_effect=AssertionError('Archive registration must not invoke Git')), \
                     patch('urllib.request.urlopen', side_effect=AssertionError('Archive registration must work offline')):
                    install.register_updates(stage)
                metadata = json.loads((stage/'.xetal-update.json').read_text())
                self.assertEqual(metadata['revision'], self.commit)
                self.assertEqual(metadata['files']['hyprland.conf']['text'], '# delivered defaults\n')
                self.assertFalse((extracted/'.git').exists())

    def test_incomplete_archive_cannot_inherit_parent_git_version(self):
        extracted = self.repo/'incomplete'
        (extracted/'installer').mkdir(parents=True)
        marker = extracted/'installer/source-revision.txt'
        for value in (None, '$Format:%H$\n', 'bad revision', 'a'*7):
            with self.subTest(value=value):
                if value is not None:marker.write_text(value)
                with self.assertRaisesRegex(RuntimeError, 'Download a fresh ZIP'):
                    install.source_revision(extracted)

    def test_check_reports_missing_archive_version_before_installation(self):
        extracted = self.root/'incomplete'
        extracted.mkdir()
        with patch.object(install, 'REPO', extracted), \
             patch.object(install.dependencies, 'check', return_value=[]), \
             patch.object(sys, 'argv', ['x_hyperinstall.sh', '--check']), \
             patch('builtins.print') as output:
            self.assertEqual(install.main(), 1)
        self.assertTrue(any('Download a fresh ZIP' in str(call) for call in output.call_args_list))

    def test_update_rejects_archive_for_a_different_announced_commit(self):
        extracted = self.export('zip')
        with patch.object(install, 'REPO', extracted), \
             patch.object(updater.dependencies, 'check', side_effect=AssertionError('Wrong source must stop before preparing')):
            with self.assertRaisesRegex(RuntimeError, 'does not match the announced commit'):
                updater.prepare(self.root/'recipient', 'f'*40)


if __name__ == '__main__':unittest.main()
