"""Real offline Git downloads and killed workers in disposable private caches."""
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

import github


class GitCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-git-recovery-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root/'cache'
        self.origin = self.root/'origin'
        self.origin.mkdir()
        self.git('init', '-q', '-b', 'main')
        (self.origin/'code').write_text('first release\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'First')
        self.first = self.git('rev-parse', 'HEAD')
        (self.origin/'code').write_text('second release\n')
        (self.origin/'config/hypr').mkdir(parents=True)
        (self.origin/'config/hypr/VERSION').write_text('0.0.0.237-alpha\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Second')
        self.commit = self.git('rev-parse', 'HEAD')
        repository = patch.object(github, 'REPOSITORY', self.origin.as_uri())
        repository.start()
        self.addCleanup(repository.stop)

    def git(self, *args):
        return subprocess.check_output([
            'git', '-C', str(self.origin), '-c', 'user.name=Fixture',
            '-c', 'user.email=fixture@example.invalid', *args,
        ], text=True, stderr=subprocess.PIPE).strip()

    def initialize(self):
        with github.git_cache(self.cache) as (bare, _, _): return bare

    def test_stale_locks_recover_and_download_the_exact_commit(self):
        bare = self.initialize()
        locks = ['shallow.lock', 'FETCH_HEAD.lock', 'packed-refs.lock', 'refs/heads/main.lock']
        for name in locks:
            path = bare/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('interrupted work')
        # A developer's unrelated working files must never be used or changed.
        (self.origin/'code').write_text('uncommitted work\n')
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            destination = github.source(self.commit, self.cache, self.root/'source')
        self.assertIn('Recovered an interrupted', output.getvalue())
        self.assertEqual((destination/'code').read_text(), 'second release\n')
        self.assertEqual((self.origin/'code').read_text(), 'uncommitted work\n')
        for name in locks: self.assertFalse((bare/name).exists())
        downloaded = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual(downloaded, self.commit)
        self.assertEqual((bare/'shallow').read_text().strip(), self.commit)

    def test_history_check_also_recovers_and_preserves_ancestry_checks(self):
        bare = self.initialize()
        (bare/'shallow.lock').write_text('interrupted check')
        value = github.git_latest(self.first, cache=self.cache)
        self.assertEqual(value['sha'], self.commit)
        self.assertEqual(value['relation'], 'ahead')
        self.assertEqual(value['release_version'], '0.0.0.237-alpha')
        self.assertFalse((bare/'shallow.lock').exists())

    def test_legacy_cache_is_never_modified_even_if_its_worker_is_still_running(self):
        legacy = self.cache/'repository.git'
        legacy.mkdir(parents=True)
        marker = legacy/'shallow.lock'
        marker.write_text('legacy worker owns this')
        github.source(self.commit, self.cache, self.root/'source')
        self.assertEqual(marker.read_text(), 'legacy worker owns this')

    def test_active_operation_keeps_its_git_locks(self):
        with github.git_cache(self.cache) as (bare, _, _):
            marker = bare/'shallow.lock'
            marker.write_text('live fetch')
            with self.assertRaisesRegex(RuntimeError, 'still running'):
                github.source(self.commit, self.cache, self.root/'blocked')
            self.assertEqual(marker.read_text(), 'live fetch')
        github.source(self.commit, self.cache, self.root/'source')
        self.assertFalse(marker.exists())

    def test_interrupted_initialization_is_completed(self):
        bare = self.cache/'git-v2/repository.git'
        (bare/'objects').mkdir(parents=True)
        (bare/'config.lock').write_text('incomplete initialization')
        github.source(self.commit, self.cache, self.root/'source')
        self.assertTrue((bare/'HEAD').is_file())
        self.assertFalse((bare/'config.lock').exists())

    def test_symlinked_cache_or_lock_is_rejected_without_touching_target(self):
        outside = self.root/'outside'
        outside.mkdir()
        marker = outside/'valuable'
        marker.write_text('keep')
        self.cache.mkdir()
        (self.cache/'git-v2').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'): self.initialize()
        (self.cache/'git-v2').unlink()
        bare = self.initialize()
        (bare/'shallow.lock').symlink_to(marker)
        with self.assertRaisesRegex(ValueError, 'unsupported lock'): self.initialize()
        self.assertEqual(marker.read_text(), 'keep')
        (bare/'shallow.lock').unlink()
        lease = self.cache/'git-v2/operation.lock'
        lease.unlink()
        lease.symlink_to(marker)
        with self.assertRaises(OSError): self.initialize()
        self.assertEqual(marker.read_text(), 'keep')

    def test_killed_parent_cannot_release_a_running_git_childs_lease(self):
        helper = self.root/'upload-pack'
        helper.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nimport time\n'
                          'Path('+repr(str(self.root/'ready'))+').touch()\ntime.sleep(30)\n')
        helper.chmod(0o700)
        wrapper = self.root/'worker.py'
        wrapper.write_text(
            'import json,subprocess,sys\nfrom pathlib import Path\n'
            'sys.path.insert(0, '+repr(str(Path(github.__file__).parent))+')\nimport github\n'
            'with github.git_cache(Path('+repr(str(self.cache))+')) as (bare, command, options):\n'
            ' child = subprocess.Popen([*command, "fetch", "--depth=1", '
            +repr('--upload-pack='+str(helper))+', '+repr(self.origin.as_uri())+', '
            +repr(self.commit)+'], **options)\n'
            ' Path('+repr(str(self.root/'child.json'))+').write_text(json.dumps(child.pid))\n'
            ' child.wait()\n')
        worker = subprocess.Popen([sys.executable, str(wrapper)], start_new_session=True,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def stop():
            try: os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            worker.wait(timeout=5)
        self.addCleanup(stop)
        deadline = time.monotonic()+8
        while not (self.root/'ready').exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue((self.root/'ready').exists(), 'Real Git child did not start')
        marker = self.cache/'git-v2/repository.git/shallow.lock'
        marker.write_text('interrupted fetch')
        worker.kill()
        worker.wait(timeout=5)
        child = json.loads((self.root/'child.json').read_text())
        self.assertTrue(Path('/proc', str(child)).exists())
        with self.assertRaisesRegex(RuntimeError, 'still running'): self.initialize()
        self.assertEqual(marker.read_text(), 'interrupted fetch')
        stop()
        # The descendants may take a moment to exit after SIGKILL.
        deadline = time.monotonic()+5
        while True:
            try:
                self.initialize()
                break
            except RuntimeError:
                if time.monotonic() >= deadline: raise
                time.sleep(.02)
        self.assertFalse(marker.exists())
        github.source(self.commit, self.cache, self.root/'source')

    def test_commit_mismatch_is_rejected_before_creating_the_checkout(self):
        check_output = subprocess.check_output
        def mismatch(command, **options):
            if command[-2:] == ['rev-parse', 'FETCH_HEAD']: return '0'*40+'\n'
            return check_output(command, **options)
        with patch.object(github.subprocess, 'check_output', side_effect=mismatch):
            with self.assertRaisesRegex(ValueError, 'does not match'):
                github.source(self.commit, self.cache, self.root/'source')
        self.assertFalse((self.root/'source').exists())

    def test_archive_paths_and_link_entries_are_still_rejected(self):
        real_run = subprocess.run
        for name, kind in [('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE),
                           ('link', tarfile.SYMTYPE)]:
            with self.subTest(name=name):
                def archive(command, **options):
                    if 'archive' not in command: return real_run(command, **options)
                    with tarfile.open(fileobj=options['stdout'], mode='w') as stream:
                        member = tarfile.TarInfo(name)
                        member.type = kind
                        member.linkname = '/escape' if kind == tarfile.SYMTYPE else ''
                        stream.addfile(member)
                    return subprocess.CompletedProcess(command, 0)
                destination = self.root/('source-'+str(kind)+name.replace('/', '-'))
                with patch.object(github.subprocess, 'run', side_effect=archive):
                    with self.assertRaisesRegex(ValueError, 'unsupported archive entry'):
                        github.source(self.commit, self.cache, destination)
        self.assertFalse((self.root/'escape').exists())


if __name__ == '__main__': unittest.main()
