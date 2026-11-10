"""Real desktop entries and shared Favorites, isolated from the desktop user."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import tool_favorites as favorites
import shortcuts


class ToolFavoritesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='panel-favorites-')
        self.addCleanup(temporary.cleanup)
        self.fixture = Path(temporary.name)
        # Shell metacharacters must remain literal in generated Exec arguments.
        self.root = self.fixture/'profile 100% "quoted" $test `literal`'
        (self.root/'control_panel').mkdir(parents=True)
        (self.root/'session_ui').mkdir()
        shutil.copy2(favorites.ROOT/'control_panel/tools.json', self.root/'control_panel/tools.json')
        shutil.copy2(favorites.ROOT/'session_ui/client.py', self.root/'session_ui/client.py')
        self.local = self.fixture/'favorites.json'
        self.local.write_text(json.dumps({'add': ['first.desktop', 'last.desktop'],
                                         'hide': ['hidden.desktop'], 'future': {'keep': True}}))
        for mocked in (patch.object(favorites, 'ROOT', self.root),
                       patch.object(favorites.catalog, 'LOCAL', self.local),
                       patch.object(favorites.catalog, 'kde_favorites', return_value=[]),
                       patch.dict(os.environ, {'XDG_DATA_HOME': str(self.fixture/'data')})):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_every_tool_opens_its_exact_page_through_existing_session_client(self):
        instance = self.fixture/'hypr/fixture'
        instance.mkdir(parents=True)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(instance/'.xpanel.sock'))
            server.listen()
            server.settimeout(3)
            env = {**os.environ, 'HYPRLAND_INSTANCE_SIGNATURE': 'fixture',
                   'XDG_RUNTIME_DIR': str(self.fixture)}
            for ident, tool in favorites.tools().items():
                with self.subTest(tool=ident):
                    self.assertIn(ident, favorites.set_favorite({'id': ident, 'enabled': True})['favorites'])
                    path = favorites.applications_dir()/favorites.desktop_id(ident)
                    info = favorites.owned_entry(path, ident)
                    self.assertEqual(info.get_display_name(), tool['title'])
                    self.assertTrue(info.get_nodisplay())
                    argv = shortcuts.Entry(favorites.desktop_id(ident), info).argv()
                    self.assertEqual(argv[1:], [str(self.root/'session_ui/client.py'), 'panel', '--section', ident])
                    subprocess.run(argv, env=env, check=True, timeout=4)
                    peer, _ = server.accept()
                    with peer:
                        peer.settimeout(2)
                        request = json.loads(peer.recv(4096))
                        self.assertEqual(request, {'section': ident, 'preload': False})

    def test_pin_is_idempotent_and_unpin_keeps_other_favorites_and_shortcuts(self):
        ident = favorites.desktop_id('network')
        favorites.set_favorite({'id': 'network', 'enabled': True})
        first = self.local.read_bytes()
        favorites.set_favorite({'id': 'network', 'enabled': True})
        self.assertEqual(self.local.read_bytes(), first)
        self.assertEqual(json.loads(first)['add'], ['first.desktop', 'last.desktop', ident])
        favorites.set_favorite({'id': 'network', 'enabled': False})
        data = json.loads(self.local.read_text())
        self.assertEqual(data['add'], ['first.desktop', 'last.desktop'])
        self.assertEqual(data['hide'], ['hidden.desktop', ident])
        self.assertEqual(data['future'], {'keep': True})
        self.assertEqual(favorites.snapshot()['favorites'], [])
        self.assertTrue((favorites.applications_dir()/ident).exists())

    def test_apps_unpin_and_deleted_shortcut_are_reflected_and_recoverable(self):
        favorites.set_favorite({'id': 'iso', 'enabled': True})
        favorites.catalog.pin(favorites.desktop_id('iso'), False)
        self.assertEqual(favorites.snapshot()['favorites'], [])
        favorites.set_favorite({'id': 'iso', 'enabled': True})
        (favorites.applications_dir()/favorites.desktop_id('iso')).unlink()
        self.assertEqual(favorites.snapshot()['favorites'], [])
        self.assertEqual(favorites.set_favorite({'id': 'iso', 'enabled': True})['favorites'], ['iso'])
        self.assertEqual(json.loads(self.local.read_text())['add'].count(favorites.desktop_id('iso')), 1)

    def test_failed_save_preserves_existing_data_and_removes_only_new_shortcut(self):
        self.local.write_text('{broken favorites')
        with self.assertRaises(ValueError):
            favorites.set_favorite({'id': 'iso', 'enabled': True})
        self.assertEqual(self.local.read_text(), '{broken favorites')
        self.assertFalse((favorites.applications_dir()/favorites.desktop_id('iso')).exists())

    def test_unrelated_file_and_symlink_are_never_overwritten(self):
        directory = favorites.applications_dir()
        directory.mkdir(parents=True)
        path = directory/favorites.desktop_id('iso')
        original = self.local.read_bytes()
        path.write_text('someone else owns this')
        with self.assertRaises(ValueError):
            favorites.set_favorite({'id': 'iso', 'enabled': True})
        self.assertEqual(path.read_text(), 'someone else owns this')
        path.unlink()
        path.symlink_to(self.local)
        with self.assertRaises(ValueError):
            favorites.set_favorite({'id': 'iso', 'enabled': True})
        self.assertEqual(self.local.read_bytes(), original)

    def test_concurrent_apps_and_panel_saves_keep_every_pin(self):
        script = ('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                  'import catalog;catalog.LOCAL=Path(sys.argv[2]);catalog.pin(sys.argv[3],True)')
        launcher = Path(favorites.catalog.__file__).parent
        children = [subprocess.Popen([sys.executable, '-c', script, str(launcher), str(self.local),
                                      f'concurrent-{i}.desktop']) for i in range(8)]
        for child in children:
            self.assertEqual(child.wait(timeout=10), 0)
        data = json.loads(self.local.read_text())
        self.assertEqual(data['add'][:2], ['first.desktop', 'last.desktop'])
        self.assertEqual(set(data['add'][2:]), {f'concurrent-{i}.desktop' for i in range(8)})
        self.assertEqual(data['hide'], ['hidden.desktop'])


if __name__ == '__main__':
    unittest.main()
