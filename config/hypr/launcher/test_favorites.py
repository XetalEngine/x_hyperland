"""Portable defaults and read-only inheritance of the recipient's KDE pins."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import catalog


class FavoritesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.config = self.home/'.config'; self.config.mkdir()
        self.local = self.home/'favorites.json'
        self.local.write_bytes(catalog.LOCAL.read_bytes())
        for mocked in (patch.object(catalog, 'LOCAL', self.local),
                       patch.object(catalog.Path, 'home', return_value=self.home)):
            mocked.start(); self.addCleanup(mocked.stop)

    def test_empty_recipient_has_my_computer_and_bundled_favorites(self):
        self.assertEqual(catalog.favorites(), ['xetal-files-computer.desktop', 'kitty.desktop', 'xetal-calculator.desktop'])

    def test_kde_favorites_are_inherited_without_writing_kde_and_can_be_unpinned(self):
        source = self.config/'kactivitymanagerd-statsrc'
        source.write_text('[Favorites-instance-1-global]\nordering=applications:recipient-browser.desktop\n')
        before = source.read_bytes()
        self.assertEqual(catalog.favorites(),
                         ['recipient-browser.desktop', 'xetal-files-computer.desktop', 'kitty.desktop', 'xetal-calculator.desktop'])
        catalog.pin('recipient-browser.desktop', False)
        catalog.pin('kitty.desktop', False)
        self.assertEqual(catalog.favorites(), ['xetal-files-computer.desktop', 'xetal-calculator.desktop'])
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(json.loads(self.local.read_text())['hide'],
                         ['recipient-browser.desktop', 'kitty.desktop'])


if __name__ == '__main__': unittest.main()
