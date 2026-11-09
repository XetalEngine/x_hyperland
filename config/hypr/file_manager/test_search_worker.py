#!/usr/bin/env python3
"""Real filesystem/content searches; never use the user's documents."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from search_worker import Search, name_matches, options


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fusion-search-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, data=b'fixture\n'):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def search(self, query='*', **kwargs):
        events = []
        job = Search(dict(root=str(self.root), query=query, **kwargs), events.append)
        job.run()
        rows = [row for event in events if event['event'] == 'rows' for row in event['rows']]
        self.assertEqual(events[-1]['event'], 'done')
        self.assertEqual(events[-1]['rows'], len(rows))
        return rows, events[-1]

    def test_familiar_name_patterns(self):
        for name, pattern in [('PHOTO.JPG', '*.jpg'), ('partialname-2.png', 'par*ialname*png'),
                              ('README', '*.'), ('README', '*.*'), ('photo.jpg', '*.png;*.jpg'),
                              ('photo.jpg', '*.png|*.jpg'), ('image5.png', 'image?.png'),
                              ('image3.png', 'image[0-9].png'), ('Überblick.txt', 'über'),
                              ('.profile', '*.'), ('report.', '*.')]:
            with self.subTest(name=name, pattern=pattern):
                self.assertTrue(name_matches(name, pattern))
        self.assertFalse(name_matches('photo.jpg', '*.'))
        self.assertFalse(name_matches('PHOTO.JPG', '*.jpg', sensitive=True))
        self.assertFalse(name_matches('build-release', 'build', partial=False))

    def test_recursive_hidden_and_folder_results(self):
        self.write('root.JPG'); self.write('nested/deep.jpg'); self.write('.hidden/secret.jpg')
        self.write('.private.jpg'); self.write('README')
        rows, _ = self.search('*.jpg')
        self.assertEqual({r['name'] for r in rows}, {'root.JPG', 'deep.jpg'})
        rows, _ = self.search('*.jpg', recursive=False)
        self.assertEqual([r['name'] for r in rows], ['root.JPG'])
        rows, _ = self.search('*.jpg', hidden=True)
        self.assertEqual(len(rows), 4)
        rows, _ = self.search('nested')
        self.assertTrue(rows[0]['directory'])
        rows, _ = self.search('nested', folders=False)
        self.assertEqual(rows, [])

    def test_exclusions_and_type_filters(self):
        for name in ['a.py', 'b.txt', 'build/c.py', 'nested/d.py', 'nested/e.bak']:
            self.write(name, b'needle\n')
        rows, _ = self.search('needle', contents=True, types='*.py;*.txt', exclude='build;*.bak', names='*.py')
        self.assertEqual({r['name'] for r in rows}, {'a.py', 'd.py'})
        rows, _ = self.search('*.py', exclude='nested/*;build')
        self.assertEqual([r['name'] for r in rows], ['a.py'])

    def test_literal_regex_whole_words_and_line_metadata(self):
        path = self.write('space and -dash.txt', 'zero\r\nBLABLABAL twice BLABLABAL\r\nblablabalSuffix\r\n'.encode())
        rows, summary = self.search('BLABLABAL', contents=True)
        self.assertEqual([r['line'] for r in rows], [2, 3])
        self.assertEqual([r['matches'] for r in rows], [2, 1])
        self.assertEqual(rows[0]['path'], str(path))
        self.assertEqual(rows[0]['size'], path.stat().st_size)
        self.assertEqual(rows[0]['column'], 1)
        self.assertEqual(summary['matches'], 3)
        rows, _ = self.search('BLABLABAL', contents=True, case=True, word=True)
        self.assertEqual([r['line'] for r in rows], [2])
        rows, _ = self.search(r'blabla[a-z]+Suffix$', contents=True, regex=True)
        self.assertEqual([r['line'] for r in rows], [3])
        rows, _ = self.search('BLABLA.*', contents=True)
        self.assertEqual(rows, [])

    def test_unicode_encodings_and_columns(self):
        self.write('unicode.txt', 'é🙂 BLABLABAL\n'.encode())
        self.write('windows.txt', 'first\nBLABLABAL\n'.encode('utf-16'))
        rows, _ = self.search('BLABLABAL', contents=True)
        self.assertEqual({r['name']: r['line'] for r in rows}, {'unicode.txt': 1, 'windows.txt': 2})
        self.assertEqual(next(r for r in rows if r['name'] == 'unicode.txt')['column'], 4)
        self.write('legacy.txt', 'café\n'.encode('cp1252'))
        rows, _ = self.search('café', contents=True, encoding='windows-1252', names='legacy.txt')
        self.assertEqual(rows[0]['preview'], 'café')

    def test_size_and_modified_limits(self):
        small = self.write('small.txt', b'a'); large = self.write('large.txt', b'a'*100)
        os.utime(small, (1000, 1000)); os.utime(large, (2000, 2000))
        rows, _ = self.search('*.txt', min_size=50, max_size=200)
        self.assertEqual([r['name'] for r in rows], ['large.txt'])
        rows, _ = self.search('*.txt', after=1000, before=2000)
        self.assertEqual([r['name'] for r in rows], ['small.txt'])

    def test_symlink_loops_and_special_files(self):
        self.write('sub/a.txt', b'needle\n')
        (self.root/'sub/loop').symlink_to(self.root, target_is_directory=True)
        (self.root/'alias.txt').symlink_to(self.root/'sub/a.txt')
        (self.root/'broken').symlink_to(self.root/'missing')
        os.mkfifo(self.root/'pipe.txt')
        rows, _ = self.search('*.txt')
        self.assertEqual([r['name'] for r in rows], ['a.txt'])
        rows, _ = self.search('needle', contents=True, follow=True)
        self.assertEqual({r['name'] for r in rows}, {'a.txt', 'alias.txt'})

    def test_binary_and_multiline(self):
        self.write('data.bin', b'\x00secret\x00\n')
        self.write('late.bin', b'secret\n'+b'padding\n'*5000+b'\x00\n')
        self.write('lines.txt', b'first line\nsecond line\n')
        rows, _ = self.search('secret', contents=True)
        self.assertEqual(rows, [])
        rows, _ = self.search('secret', contents=True, binary=True)
        self.assertEqual({r['name'] for r in rows}, {'data.bin', 'late.bin'})
        rows, _ = self.search('first.*second', contents=True, regex=True, multiline=True)
        self.assertEqual(rows[0]['line'], 1)
        self.assertIn('second', rows[0]['preview'])

    def test_parallel_equivalence_and_result_limit(self):
        for i in range(140): self.write(f'file{i}.txt', b'match\nmatch\n')
        first, _ = self.search('match', contents=True, workers=1)
        parallel, _ = self.search('match', contents=True, workers=4)
        self.assertEqual({(r['path'], r['line']) for r in first}, {(r['path'], r['line']) for r in parallel})
        rows, summary = self.search('match', contents=True, workers=4, limit=7)
        self.assertEqual(len(rows), 7)
        self.assertTrue(summary['limited'])

    def test_long_line_is_bounded_and_next_file_is_searched(self):
        self.write('huge.txt', b'needle'+b'x'*2200000+b'\n')
        self.write('ordinary.txt', b'needle\n')
        rows, summary = self.search('needle', contents=True)
        self.assertEqual([r['name'] for r in rows], ['ordinary.txt'])
        self.assertEqual(summary['long_lines'], 1)

    def test_invalid_requests_and_regex(self):
        for values in [dict(workers=33), dict(limit=0), dict(query=''), dict(min_size=2, max_size=1),
                       dict(after=2000, before=1000), dict(root='/does-not-exist'), dict(encoding='not-real')]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                options(dict(dict(root=str(self.root), query='*'), **values))
        with self.assertRaises(ValueError): self.search('[', contents=True, regex=True)
        with patch('search_worker.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'ripgrep'): self.search('needle', contents=True)
        self.assertEqual(self.search('no files')[0], [])

    def test_worker_protocol_and_no_shell_interpretation(self):
        marker = self.root/'must-not-exist'
        term = f'$(touch {marker})'
        self.write('a.txt', term.encode())
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('search_worker.py'))],
            input=json.dumps(dict(root=str(self.root), query=term, contents=True)),
            text=True, capture_output=True, timeout=10, check=True)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[-1]['rows'], 1)
        self.assertFalse(marker.exists())

    def test_cancel_stops_readers_without_waiting_for_all_files(self):
        for i in range(80): self.write(f'{i}.txt', b'needle\n'*10000)
        events = []; job = Search(dict(root=str(self.root), query='needle', contents=True, limit=100000), events.append)
        thread = threading.Thread(target=job.run)
        thread.start()
        deadline = time.monotonic()+5
        while not job.processes and thread.is_alive() and time.monotonic()<deadline:
            time.sleep(.005)
        job.stop(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(job.processes)


if __name__ == '__main__':
    unittest.main()
