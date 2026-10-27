"""Companion selection, terminal input and bounded native image placement."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import companion
import scene


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xetal-companion-test-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state' / 'companion.json'

    def test_choice_survives_relaunch_in_both_directions(self):
        choice = companion.Choice(self.state)
        self.assertEqual(choice.view, 'ascii')
        self.assertFalse(self.state.exists())
        choice.switch()
        reopened = companion.Choice(self.state)
        self.assertEqual(reopened.view, 'mascot')
        reopened.switch()
        self.assertEqual(companion.Choice(self.state).view, 'ascii')
        self.assertEqual(list(self.state.parent.iterdir()), [self.state])

    def test_bad_preferences_fall_back_without_overwriting_them(self):
        self.state.parent.mkdir()
        for text in ('broken', 'null', '[]', '{"version":1,"view":"bad"}',
                     '{"version":2,"view":"mascot"}'):
            self.state.write_text(text)
            self.assertEqual(companion.Choice(self.state).view, 'ascii')
            self.assertEqual(self.state.read_text(), text)

    def test_failed_atomic_save_preserves_previous_preference(self):
        choice = companion.Choice(self.state)
        choice.switch()
        before = self.state.read_bytes()
        with patch.object(companion.os, 'replace', side_effect=OSError('disk full')):
            choice.switch()
        self.assertEqual(choice.view, 'ascii')
        self.assertEqual(self.state.read_bytes(), before)
        self.assertIn('could not be saved', choice.hint())
        self.assertEqual(list(self.state.parent.iterdir()), [self.state])

    def test_split_mouse_reports_create_one_click_on_release(self):
        parser = companion.Input()
        packet = b'\x1b[<0;10;15M\x1b[<0;10;15m'
        events = []
        for index, char in enumerate(packet):
            events += parser.feed(bytes([char]), index * .001)
        self.assertEqual(events, [('click', 9, 14)])
        self.assertEqual(parser.feed(b'', .2), [])

    def test_scroll_right_click_and_drags_do_not_switch(self):
        parser = companion.Input()
        for packet in (b'\x1b[<64;10;15M', b'\x1b[<65;10;15M',
                       b'\x1b[<2;10;15M\x1b[<2;10;15m',
                       b'\x1b[<0;10;15M\x1b[<32;11;15M\x1b[<0;10;15m',
                       b'\x1b[<0;10;15M\x1b[<0;11;15m',
                       b'\x1b[<4;10;15M\x1b[<4;10;15m'):
            self.assertEqual(parser.feed(packet), [])

    def test_escape_waits_for_split_sequences_and_other_reports_are_ignored(self):
        parser = companion.Input()
        self.assertEqual(parser.feed(b'\x1b', 0), [])
        self.assertEqual(parser.feed(b'[A', .02), [])
        self.assertEqual(parser.feed(b'\x1b_Gi=1;quiet error\x1b\\'), [])
        self.assertEqual(parser.feed(b'\x1b', 1), [])
        self.assertEqual(parser.feed(b'', 1.1), [('hide', 0, 0)])
        self.assertEqual(parser.feed(b' qQ'), [('switch', 0, 0), ('hide', 0, 0), ('hide', 0, 0)])

    def test_malformed_incomplete_report_cannot_accumulate_forever(self):
        parser = companion.Input()
        parser.feed(b'\x1b[<000', 0)
        self.assertEqual(parser.feed(b'', 1), [])
        self.assertEqual(parser.feed(b' '), [('switch', 0, 0)])

    def test_click_only_switches_in_the_artwork_area(self):
        with patch.object(scene, 'Choice', lambda: companion.Choice(self.state)):
            view = scene.Scene('hero')
        view.frame(110, 50, 0)
        left, top, width, height = view.art_area
        view.input(('click', 10, top - 1))
        self.assertEqual(view.choice.view, 'ascii')
        view.input(('click', 10, top + height))
        self.assertEqual(view.choice.view, 'ascii')
        view.input(('click', 10, top + 2))
        self.assertEqual(companion.Choice(self.state).view, 'mascot')
        view.input(('switch', 0, 0))
        self.assertEqual(companion.Choice(self.state).view, 'ascii')

    def test_asset_is_original_transparent_png(self):
        from PIL import Image
        self.assertEqual(hashlib.sha256(companion.ART.read_bytes()).hexdigest(),
                         '0dd8e0105f21533de911fb17840df0324dd3569066a094108acaaf71abbe3e75')
        with Image.open(companion.ART) as image:
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_artwork_loaded_once_reused_and_released_on_exit(self):
        art = companion.Artwork()
        first = art.draw((0, 11, 110, 35), (110, 50), (990, 900))
        self.assertIn('a=t', first)
        self.assertIn('a=p', first)
        self.assertIn('p=1', first)
        self.assertEqual('', art.draw((0, 11, 110, 35), (110, 50), (990, 900)))
        self.assertIn('d=i', art.hide())
        second = art.draw((0, 11, 110, 35), (110, 50), (990, 900))
        self.assertNotIn('a=t', second)
        self.assertIn('a=p', second)
        self.assertIn('d=I', art.hide(release=True))
        self.assertFalse(art.loaded)

    def test_resizes_stay_inside_viewport(self):
        art = companion.Artwork()
        art.load()
        for cols, rows, cw, ch in ((110, 50, 9, 18), (180, 70, 14, 29),
                                    (32, 15, 8, 16), (18, 10, 10, 21)):
            area = (1, 2, cols - 2, rows - 5)
            place = art.placement(area, (cols, rows), (cols * cw, rows * ch))
            self.assertIsNotNone(place)
            x, y, dx, dy, height = place
            px, py = x * cw + dx, y * ch + dy
            self.assertGreaterEqual(px, area[0] * cw)
            self.assertGreaterEqual(py, area[1] * ch)
            self.assertLessEqual(px + height * ch * art.ratio, (area[0] + area[2]) * cw)
            self.assertLessEqual(py + height * ch, (area[1] + area[3]) * ch)

    def test_missing_artwork_falls_back_without_forgetting_user_choice(self):
        choice = companion.Choice(self.state)
        choice.switch()
        with patch.object(scene, 'Choice', lambda: companion.Choice(self.state)):
            view = scene.Scene('hero')
        view.artwork = companion.Artwork(Path(self.temp.name) / 'missing.png')
        view.frame(110, 50, 0)
        with patch.object(scene.sys, 'stderr'):
            self.assertEqual(view.graphics(110, 50, -1), '')
        self.assertEqual(view.choice.view, 'ascii')
        self.assertEqual(companion.Choice(self.state).view, 'mascot')
        self.assertIn('unavailable', view.choice.hint())


if __name__ == '__main__':
    unittest.main()
