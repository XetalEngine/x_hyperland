"""Real archive additions, merge decisions and transaction integrity in temporary folders."""
import os
import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PyQt6.QtCore import QCoreApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'archive_manager'))
from tasks import Task
from engine import Runner, format_arguments


class Additions(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fusion-archive-additions-')
        self.addCleanup(self.temp.cleanup); self.base = Path(self.temp.name)
        self.enterContext(patch.dict(os.environ, {'XDG_STATE_HOME':str(self.base/'state')}))
        self.archive = self.base/'sample.zip'
        self.entries = {'Echo/keep.txt':b'keep', 'Echo/update.txt':b'old',
                        'Echo/nested/inside.txt':b'inside', 'root.txt':b'root'}
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, data in self.entries.items(): archive.writestr(name, data)
        self.incoming = self.base/'external'; self.incoming.mkdir()

    def source(self, name, data='new'):
        path = self.incoming/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data); return path

    def contents(self):
        with zipfile.ZipFile(self.archive) as archive:
            self.assertIsNone(archive.testzip())
            return {name:archive.read(name) for name in archive.namelist() if not name.endswith('/')}

    def add(self, sources, folder='', choice='replace', on_issue=None, password=None):
        task = Task(dict(operation='add', sources=[str(self.archive)],
                         add=[str(path) for path in sources], folder=folder, password=password))
        events = []; results = []
        def message(value):
            events.append(value)
            if value['event'] == 'issue' and value['status'] == 'pending':
                if on_issue: on_issue(task, value)
                else: task.command(dict(command='issue_answer', choice=choice, ids=[value['id']],
                                        versions={str(value['id']):value['version']}, all=False))
            elif value['event'] == 'password': task.command(dict(command='password', password=None))
        task.message.connect(message); task.outcome.connect(results.append); task.run()
        self.assertEqual(len(results), 1)
        return results[0], [e for e in events if e['event']=='issue' and e['status']=='pending']

    def test_root_folder_merges_without_duplicating_top_folder(self):
        self.source('Echo/new.txt'); self.source('Echo/nested/more.txt', 'more')
        (self.incoming/'Echo/empty').mkdir()
        result, issues = self.add([self.incoming/'Echo'])
        self.assertTrue(result['ok'], result); self.assertEqual(issues, [])
        self.assertEqual(self.contents(), {**self.entries, 'Echo/new.txt':b'new', 'Echo/nested/more.txt':b'more'})
        with zipfile.ZipFile(self.archive) as archive: self.assertIn('Echo/empty/', archive.namelist())
        self.assertTrue((self.incoming/'Echo/new.txt').is_file())

    def test_individual_member_replace_and_skip(self):
        for choice in ('skip', 'replace'):
            with self.subTest(choice=choice):
                self.source('Echo/update.txt', 'replacement'); self.source('Echo/new.txt')
                result, issues = self.add([self.incoming/'Echo'], choice=choice)
                self.assertTrue(result['ok'], result)
                self.assertTrue(issues)
                self.assertTrue(all(e['destination'].startswith(str(self.archive)+'/Echo/') for e in issues))
                self.assertTrue(all('.fusion-archive-' not in e['source'] for e in issues))
                self.assertEqual(self.contents(), {**self.entries, 'Echo/new.txt':b'new',
                    'Echo/update.txt':b'old' if choice=='skip' else b'replacement'})

    def test_all_collisions_skipped_keeps_original_zip_bytes(self):
        path = self.source('Echo/update.txt', 'replacement'); before = self.archive.read_bytes()
        result, issues = self.add([path], folder='Echo', choice='skip')
        self.assertTrue(result['ok'], result); self.assertEqual(len(issues), 1)
        self.assertEqual(self.archive.read_bytes(), before)

    def test_folder_with_only_skipped_members_keeps_original_zip_bytes(self):
        self.source('Echo/update.txt', 'replacement'); before = self.archive.read_bytes()
        result, issues = self.add([self.incoming/'Echo'], choice='skip')
        self.assertTrue(result['ok'], result); self.assertEqual(len(issues), 1)
        self.assertEqual(self.archive.read_bytes(), before)

    def test_skipped_missing_source_keeps_original_zip_bytes(self):
        before = self.archive.read_bytes()
        result, issues = self.add([self.incoming/'removed.txt'], choice='skip')
        self.assertTrue(result['ok'], result); self.assertEqual(len(issues), 1)
        self.assertEqual(self.archive.read_bytes(), before)

    def test_encrypted_7z_and_zip_additions_keep_existing_members(self):
        for kind in ('7z', 'zip'):
            with self.subTest(kind=kind):
                self.archive = self.base/('protected.'+kind)
                source = self.source('old.txt', 'old secret'); password = 'private addition test'
                runner = Runner()
                arguments = ['a', *format_arguments(dict(format=kind, password=password, threads=2)),
                             '--', str(self.archive), source.name]
                created = runner.run(arguments, cwd=source.parent, password=password)
                self.assertEqual(created.code, 0, created.output)
                path = self.source('new.txt', 'new secret')
                result, issues = self.add([path], password=password)
                self.assertTrue(result['ok'], result); self.assertEqual(issues, [])
                extracted = self.base/('extracted-'+kind); extracted.mkdir()
                result = runner.run(['x', '-o'+str(extracted), '--', str(self.archive)], password=password)
                self.assertEqual(result.code, 0, result.output)
                self.assertEqual((extracted/'old.txt').read_text(), 'old secret')
                self.assertEqual((extracted/'new.txt').read_text(), 'new secret')

    def test_confirmed_replace_works_with_same_size_and_timestamp(self):
        path = self.source('update.txt', 'new')
        with zipfile.ZipFile(self.archive) as archive:
            timestamp = datetime.datetime(*archive.getinfo('Echo/update.txt').date_time).timestamp()
        os.utime(path, (timestamp, timestamp))
        result, issues = self.add([path], folder='Echo')
        self.assertTrue(result['ok'], result); self.assertEqual(len(issues), 1)
        self.assertEqual(self.contents()['Echo/update.txt'], b'new')

    def test_drop_into_implicit_nested_folder_and_mixed_source_parents(self):
        first = self.source('first/new.txt'); second = self.source('second/other.txt', 'other')
        folder = self.incoming/'third/empty'; folder.mkdir(parents=True)
        result, issues = self.add([first, second, folder], folder='Echo/nested')
        self.assertTrue(result['ok'], result); self.assertEqual(issues, [])
        self.assertEqual(self.contents(), {**self.entries, 'Echo/nested/new.txt':b'new',
                                          'Echo/nested/other.txt':b'other'})
        with zipfile.ZipFile(self.archive) as archive: self.assertIn('Echo/nested/empty/', archive.namelist())

    def test_file_folder_conflicts_keep_archived_contents_when_skipped(self):
        self.source('Echo/nested', 'file where archive has folder')
        self.source('Echo/update.txt/child', 'folder where archive has file')
        self.source('Echo/new.txt')
        result, issues = self.add([self.incoming/'Echo'], choice='skip')
        self.assertTrue(result['ok'], result); self.assertEqual(len(issues), 2)
        self.assertTrue(all(not e['replace_allowed'] for e in issues))
        self.assertEqual(self.contents(), {**self.entries, 'Echo/new.txt':b'new'})

    def test_unicode_wildcards_and_newlines_are_literal(self):
        path = self.source('a*?\n雪.txt')
        result, issues = self.add([path], folder='Echo')
        self.assertTrue(result['ok'], result); self.assertEqual(issues, [])
        self.assertEqual(self.contents(), {**self.entries, 'Echo/a*?\n雪.txt':b'new'})

    def test_invalid_missing_or_file_destination_preserves_original(self):
        path = self.source('new.txt'); before = self.archive.read_bytes()
        for folder in ('../escape', '/absolute', 'missing', 'Echo/update.txt'):
            with self.subTest(folder=folder):
                result, _ = self.add([path], folder=folder)
                self.assertFalse(result['ok'], result); self.assertEqual(self.archive.read_bytes(), before)

    def test_archive_itself_or_containing_folder_cannot_be_added(self):
        before = self.archive.read_bytes()
        for source in (self.archive, self.base):
            with self.subTest(source=source):
                result, _ = self.add([source]); self.assertFalse(result['ok'], result)
                self.assertEqual(self.archive.read_bytes(), before)

    def test_cancel_member_overwrite_keeps_original_and_sources(self):
        path = self.source('update.txt', 'replacement'); before = self.archive.read_bytes()
        result, issues = self.add([path], folder='Echo',
                                 on_issue=lambda task,issue:task.command({'command':'cancel'}))
        self.assertTrue(result.get('cancelled'), result); self.assertEqual(len(issues), 1)
        self.assertEqual(self.archive.read_bytes(), before); self.assertEqual(path.read_text(), 'replacement')

    def test_concurrent_archive_edit_while_choosing_overwrite_is_kept(self):
        path = self.source('update.txt', 'replacement'); changed = []
        def answer(task, issue):
            with zipfile.ZipFile(self.archive, 'a') as archive: archive.writestr('another-app.txt', 'keep this')
            changed.append(self.archive.read_bytes())
            task.command(dict(command='issue_answer', choice='replace', ids=[issue['id']],
                              versions={str(issue['id']):issue['version']}, all=False))
        result, _ = self.add([path], folder='Echo', on_issue=answer)
        self.assertFalse(result['ok'], result); self.assertEqual(self.archive.read_bytes(), changed[0])

    def test_separate_staging_and_member_conflicts_keep_distinct_queue_rows(self):
        one = self.source('first/update.txt', 'first'); two = self.source('second/update.txt', 'second')
        result, issues = self.add([one, two], folder='Echo')
        self.assertTrue(result['ok'], result); self.assertEqual(len(issues), 2)
        self.assertEqual(len({e['id'] for e in issues}), 2)
        self.assertEqual(self.contents()['Echo/update.txt'], b'second')
        self.assertEqual(one.read_text(), 'first'); self.assertEqual(two.read_text(), 'second')

    def test_file_arriving_during_source_snapshot_still_requires_member_choice(self):
        self.source('Echo/new.txt'); transfer = Task.transfer
        def copy(task, sources, destination, *args, **kwargs):
            if kwargs.get('phase') == 'Preparing files to add': self.source('Echo/update.txt', 'late arrival')
            return transfer(task, sources, destination, *args, **kwargs)
        with patch.object(Task, 'transfer', copy):
            result, issues = self.add([self.incoming/'Echo'], choice='skip')
        self.assertTrue(result['ok'], result); self.assertEqual(len(issues), 1)
        self.assertEqual(self.contents(), {**self.entries, 'Echo/new.txt':b'new'})


if __name__ == '__main__': unittest.main()
