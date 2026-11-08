"""Arch recipes must not run Debian setup scripts or remove browser payloads."""
from pathlib import Path
import tempfile
import unittest

import deb_recipes as recipes


class RecipeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, content='fixture'):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def chrome(self):
        self.write('opt/google/chrome/chrome')
        self.write('usr/share/applications/google-chrome.desktop')
        for size in (16, 24, 32, 48, 64, 128, 256):
            self.write(f'opt/google/chrome/product_logo_{size}.png', f'icon-{size}')
        for path in recipes.CHROME_CRON:
            self.write(path)

    def test_chrome_icons_are_packaged_and_only_known_debian_updaters_removed(self):
        self.chrome()
        untouched = self.write('etc/cron.daily/unrelated')
        self.write('.INSTALL', 'broken() {\nif true; then\n')
        recipes.finalize(self.root, recipes.CHROME)
        for size in (16, 24, 32, 48, 64, 128, 256):
            self.assertEqual((self.root/f'usr/share/icons/hicolor/{size}x{size}/apps/google-chrome.png').read_text(),
                             f'icon-{size}')
            self.assertTrue((self.root/f'opt/google/chrome/product_logo_{size}.png').exists())
        for path in recipes.CHROME_CRON:
            self.assertFalse((self.root/path).exists())
        self.assertTrue(untouched.exists())
        self.assertEqual((self.root/'opt/google/chrome/chrome').read_text(), 'fixture')
        self.assertNotIn('broken()', (self.root/'.INSTALL').read_text())

    def test_changed_vendor_layout_stops_before_installation(self):
        self.chrome()
        (self.root/'opt/google/chrome/product_logo_256.png').unlink()
        with self.assertRaisesRegex(RuntimeError, 'layout changed'):
            recipes.finalize(self.root, recipes.CHROME)

    def test_dpkg_prerequisite_is_replaced_only_for_the_explicit_chrome_recipe(self):
        control = {'package': recipes.CHROME, 'pre-depends': 'dpkg (>= 1.14.0)', 'depends': 'libnss3'}
        adapted = recipes.dependency_fields(control)
        self.assertNotIn('pre-depends', adapted)
        self.assertIn('libnss3', adapted['depends'])
        self.assertIn('desktop-file-utils', adapted['depends'])
        self.assertEqual(control['pre-depends'], 'dpkg (>= 1.14.0)')
        generic = dict(control, package='different-application')
        self.assertEqual(recipes.dependency_fields(generic), generic)

    def test_new_chrome_predependency_is_not_dropped(self):
        control = {'package': recipes.CHROME, 'pre-depends': 'dpkg, another-component', 'depends': ''}
        self.assertEqual(recipes.dependency_fields(control)['pre-depends'], control['pre-depends'])

    def test_generic_broken_scripts_stop_and_valid_scripts_are_never_executed(self):
        self.write('.INSTALL', 'post_install() {\nif true; then\n}\n')
        with self.assertRaisesRegex(RuntimeError, 'invalid installation script'):
            recipes.finalize(self.root, 'example')
        script = self.write('.INSTALL', f'touch "{self.root}/should-not-exist"\npost_install() {{ :; }}\n')
        before = script.read_bytes()
        recipes.finalize(self.root, 'example')
        self.assertEqual(script.read_bytes(), before)
        self.assertFalse((self.root/'should-not-exist').exists())


if __name__ == '__main__':
    unittest.main()
