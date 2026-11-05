import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


content = module('tour_content', 'build_content.py')
launch = module('tour_launch', 'launch.py')


class GuideTests(unittest.TestCase):
    def test_bundle_matches_sources_and_has_no_dangling_lessons(self):
        bundled = json.loads((ROOT / 'data.js').read_text().split(' = ', 1)[1].strip().removesuffix(';'))
        self.assertEqual(bundled, content.content())
        lessons = bundled['lessons']
        ids = {lesson['id'] for lesson in lessons}
        chapters = {chapter['id'] for chapter in bundled['chapters']}
        self.assertEqual(len(ids), len(lessons))
        self.assertGreaterEqual(len(lessons), 50)
        self.assertTrue(set(bundled['route']) <= ids)
        for lesson in lessons:
            with self.subTest(lesson=lesson['id']):
                self.assertIn(lesson['chapter'], chapters)
                self.assertTrue(set(lesson['related']) <= ids)
                self.assertTrue(lesson['steps'] and lesson['sources'])
                for source in lesson['sources']:
                    self.assertTrue((ROOT.parent / source).is_file(), source)
                self.assertTrue((ROOT / 'media' / lesson['image']).is_file())
                if lesson['clip']:
                    for suffix in ('.mp4', '.webm', '.vtt'):
                        path = ROOT / 'media' / (lesson['clip'] + suffix)
                        self.assertTrue(path.is_file(), str(path))
                        self.assertGreater(path.stat().st_size, 100)
                    self.assertTrue((ROOT / 'media' / (lesson['clip'] + '.vtt')).read_text().startswith('WEBVTT'))

    def test_defaults_and_control_panel_inventory_stay_in_sync(self):
        data = content.content()
        tools = json.loads((ROOT.parent / 'control_panel/tools.json').read_text())
        self.assertEqual(data['tools'], tools)
        recorder = next(s for s in data['shortcuts'] if s['keys'] == 'Alt + F9')
        self.assertIn('record', recorder['title'].lower())
        self.assertIn('Super + Escape', [s['keys'] for s in data['shortcuts']])
        self.assertEqual(data['feedback']['username'], 'xetal')

    def test_local_url_encodes_paths_palette_and_explicit_section(self):
        with tempfile.TemporaryDirectory(prefix='guide space ') as directory:
            root = Path(directory)
            (root / 'tour').mkdir()
            (root / 'tour/index.html').write_text('<!doctype html>')
            theme = SimpleNamespace(design=lambda: 'gildedhollow', mode=lambda: 'dark')
            with patch.dict(sys.modules, runtime=theme):
                url = urlsplit(launch.guide_url('feedback', root))
            self.assertEqual(url.scheme, 'file')
            self.assertEqual(unquote(url.path), str(root / 'tour/index.html'))
            self.assertEqual(url.fragment, 'feedback')
            self.assertEqual(parse_qs(url.query), {'theme': ['gildedhollow'], 'mode': ['dark']})
            with self.assertRaises(ValueError):
                launch.guide_url('../../private', root)
            (root / 'tour/index.html').unlink()
            with self.assertRaises(FileNotFoundError):
                launch.guide_url(root=root)

    def test_open_hides_dashboard_before_opening_local_browser_page(self):
        calls = []
        env = {'HYPRLAND_INSTANCE_SIGNATURE': 'test'}
        dashboard = SimpleNamespace(hide_dashboard=lambda: calls.append('hide'))
        url = 'file:///temporary/tour/index.html#feedback'
        with patch.object(launch, 'guide_url', return_value=url), patch.dict(sys.modules, projects_model=dashboard), \
                patch.object(launch.subprocess, 'Popen', side_effect=lambda *args, **kw: calls.append((args, kw))):
            launch.open_guide('feedback', env)
        self.assertEqual(calls[0], 'hide')
        self.assertEqual(calls[1][0][0], ['xdg-open', url])
        self.assertEqual(calls[1][1]['env'], env)
        self.assertNotIn('shell', calls[1][1])


if __name__ == '__main__':
    unittest.main()
