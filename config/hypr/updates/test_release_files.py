"""Offline history fixtures for unregistered files in development/ISO profiles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import github
from release_files import ReleaseFiles
import update_engine as engine


class ReleaseFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-release-files-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root/'repo'; self.repo.mkdir()
        self.git('init', '-q', '--initial-branch=main')
        payload = self.repo/'config/hypr/scripts'; payload.mkdir(parents=True)
        (payload/'original.py').write_text('original\n')
        self.old = self.commit('original release')
        self.earlier = b'print("earlier log guard")\n'
        self.incoming = b'print("current log guard")\n'
        (payload/'guard.py').write_bytes(self.earlier)
        (payload/'template.conf').write_text('home = @HOME@\nprofile = @HYPR@\n')
        self.commit('add guard')
        (payload/'guard.py').write_bytes(self.incoming)
        (payload/'template.conf').write_text('updated default\n')
        self.new = self.commit('update guard')
        self.live = self.root/'user/.config/hypr'; self.live.mkdir(parents=True)
        self.home = self.root/'user'
        engine.write_json(self.live/engine.META, engine.metadata(self.live, self.old))
        (self.live/'scripts').mkdir()
        (self.live/'scripts/guard.py').write_bytes(self.earlier)
        self.upstream = self.root/'incoming'; (self.upstream/'scripts').mkdir(parents=True)
        (self.upstream/'scripts/guard.py').write_bytes(self.incoming)
        self.stage = self.root/'stage'; self.state = self.root/'state'

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), '-c', 'user.name=Fixture',
                                        '-c', 'user.email=fixture@example.invalid', *args], stderr=subprocess.PIPE)

    def commit(self, message):
        self.git('add', '.'); self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD').decode().strip()

    def prepare(self, resolver=None):
        expected = engine.merge_profile(self.live, self.upstream, self.stage, self.new,
                                        known_release_file=resolver or ReleaseFiles(self.repo, self.new, self.home))
        return engine.prepare_plan(self.live, self.stage, expected, self.new)

    def test_previous_release_is_adopted_with_backup_and_rollback(self):
        plan = self.prepare()
        self.assertEqual((self.live/'scripts/guard.py').read_bytes(), self.earlier)
        self.assertEqual(engine.installed(self.live)['revision'], self.old)
        backup = engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual((self.live/'scripts/guard.py').read_bytes(), self.incoming)
        self.assertEqual((backup/'files/scripts/guard.py').read_bytes(), self.earlier)
        rollback = engine.rollback_plan(self.live, backup)
        engine.apply_plan(self.live, backup/'files', rollback, self.state)
        self.assertEqual((self.live/'scripts/guard.py').read_bytes(), self.earlier)
        self.assertEqual(engine.installed(self.live)['revision'], self.old)

    def test_modified_local_file_still_blocks_and_preserves_inventory(self):
        modified = self.earlier+b'# personal modification\n'
        (self.live/'scripts/guard.py').write_bytes(modified)
        before = (self.live/engine.META).read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'already exists locally'): self.prepare()
        self.assertEqual((self.live/'scripts/guard.py').read_bytes(), modified)
        self.assertEqual((self.live/engine.META).read_bytes(), before)

    def test_matching_incoming_file_needs_no_history_and_later_edits_block_activation(self):
        (self.live/'scripts/guard.py').write_bytes(self.incoming)
        with patch.object(ReleaseFiles, '__call__', side_effect=AssertionError('Unnecessary lookup')):
            plan = self.prepare()
        (self.live/'scripts/guard.py').write_bytes(self.earlier+b'# edited after preparation\n')
        with self.assertRaisesRegex(RuntimeError, 'changed after'): engine.apply_plan(self.live, self.stage, plan, self.state)

    def test_matches_rendered_home_paths_but_not_another_filename_or_future_release(self):
        resolver = ReleaseFiles(self.repo, self.new, self.home)
        text = f'home = {self.home}\nprofile = {self.live}\n'.encode()
        self.assertTrue(resolver('scripts/template.conf', text))
        self.assertFalse(resolver('scripts/not-the-guard.py', self.earlier))
        future = b'future unreleased guard\n'
        (self.repo/'config/hypr/scripts/guard.py').write_bytes(future)
        self.commit('future release')
        self.assertFalse(resolver('scripts/guard.py', future))

    def test_history_failure_does_not_overwrite_local_file(self):
        with patch.object(ReleaseFiles, 'history', side_effect=RuntimeError('History unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'History unavailable'): self.prepare()
        self.assertEqual((self.live/'scripts/guard.py').read_bytes(), self.earlier)

    def test_shallow_checkout_uses_private_cache_and_leaves_source_untouched(self):
        shallow = self.root/'shallow'
        subprocess.run(['git', 'clone', '-q', '--depth=1', self.repo.as_uri(), str(shallow)], check=True)
        (shallow/'developer-note').write_text('keep me')
        cache = self.root/'cache'
        with patch.object(github, 'REPOSITORY', self.repo.as_uri()):
            resolver = ReleaseFiles(shallow, self.new, self.home, cache)
            self.assertTrue(resolver('scripts/guard.py', self.earlier))
        self.assertEqual((shallow/'developer-note').read_text(), 'keep me')
        self.assertEqual(subprocess.check_output(['git', '-C', str(shallow), 'rev-parse', '--is-shallow-repository']).strip(), b'true')
        self.assertTrue((cache/'repository.git').is_dir())

    def test_metadata_entries_with_local_edits_still_block(self):
        engine.write_json(self.live/engine.META, engine.metadata(self.live, self.old))
        (self.live/'scripts/guard.py').write_bytes(b'personal guard\n')
        with self.assertRaisesRegex(RuntimeError, 'overlap'): self.prepare()

    def test_outdated_inventory_also_recognizes_existing_released_file(self):
        (self.live/'scripts/guard.py').write_bytes(b'original guard\n')
        engine.write_json(self.live/engine.META, engine.metadata(self.live, self.old))
        (self.live/'scripts/guard.py').write_bytes(self.earlier)
        plan = self.prepare()
        self.assertEqual((self.stage/'scripts/guard.py').read_bytes(), self.incoming)
        self.assertEqual(plan['expected']['scripts/guard.py'], engine.sha(self.earlier))


if __name__ == '__main__': unittest.main()
