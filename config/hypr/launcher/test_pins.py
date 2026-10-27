"""Ordered pins stay persistent, race-safe, and separate from menu Favorites."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pins
import test_shortcuts
import app
import catalog


class PinStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)/'bar-pins.json'
        self.patch = patch.object(pins, 'STATE', self.state); self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()

    def test_pin_unpin_retains_order_without_duplicates(self):
        for ident in ['a', 'b', 'c', 'a']: pins.pin(ident)
        self.assertEqual(pins.pinned(), ['a', 'b', 'c'])
        pins.pin('b', False); pins.pin('b')
        self.assertEqual(pins.pinned(), ['a', 'c', 'b'])
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)

    def test_drag_in_both_directions_and_self_drop(self):
        for ident in ['a', 'b', 'c', 'd']: pins.pin(ident)
        pins.move('a', 'c', after=True)
        self.assertEqual(pins.pinned(), ['b', 'c', 'a', 'd'])
        pins.move('d', 'b')
        self.assertEqual(pins.pinned(), ['d', 'b', 'c', 'a'])
        pins.move('b', 'b')
        self.assertEqual(pins.pinned(), ['d', 'b', 'c', 'a'])

    def test_stale_drag_does_not_restore_an_unpinned_app(self):
        pins.pin('a'); pins.pin('b'); pins.pin('a', False)
        before = self.state.read_bytes()
        with self.assertRaises(ValueError): pins.move('a', 'b')
        self.assertEqual(self.state.read_bytes(), before)

    def test_corrupt_state_is_never_silently_overwritten(self):
        self.state.write_text('{broken')
        with self.assertRaises(ValueError): pins.pin('a')
        self.assertEqual(self.state.read_text(), '{broken')

    def test_parallel_changes_keep_all_pins(self):
        code = 'import pins; from pathlib import Path; pins.STATE=Path(__import__("sys").argv[1]); pins.pin(__import__("sys").argv[2])'
        children = [subprocess.Popen([sys.executable, '-c', code, str(self.state), str(i)]) for i in range(12)]
        for child in children: self.assertEqual(child.wait(timeout=8), 0)
        self.assertEqual(set(pins.pinned()), set(map(str, range(12))))

    def test_menu_move_stops_at_edges_and_missing_apps_remain_removable(self):
        pins.pin('a'); pins.pin('b'); pins.step('a', -1); pins.step('b', 1)
        self.assertEqual(pins.pinned(), ['a', 'b'])
        pins.step('b', -1)
        self.assertEqual(pins.pinned(), ['b', 'a'])
        self.assertFalse(pins.entries({})[0]['available'])
        pins.pin('b', False)
        self.assertEqual(pins.pinned(), ['a'])


class PinMenuTests(unittest.TestCase):
    setUp = test_shortcuts.ShortcutTests.setUp
    tearDown = test_shortcuts.ShortcutTests.tearDown

    def test_bar_pin_action_is_distinct_from_favorites(self):
        menu = app.Menu(True)
        before = catalog.favorites()
        def caption():
            return next(a.text() for a in menu.build_context_menu('example.desktop').actions() if a.data() == 'bar-pin')
        self.assertIn('Pin to bar', caption())
        menu.perform('bar-pin', 'example.desktop')
        self.assertEqual(pins.pinned(), ['example.desktop'])
        self.assertEqual(catalog.favorites(), before)
        self.assertEqual(caption(), 'Unpin from bar')
        menu.perform('bar-pin', 'example.desktop')
        self.assertEqual(pins.pinned(), [])


if __name__ == '__main__': unittest.main(verbosity=2)
