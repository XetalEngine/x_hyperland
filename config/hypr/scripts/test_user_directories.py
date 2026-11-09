"""Exercise first-login initialization with the real XDG utility in temp homes."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('user-directories.py')
spec = importlib.util.spec_from_file_location('user_directories', SOURCE)
directories = importlib.util.module_from_spec(spec)
spec.loader.exec_module(directories)
DEFAULTS = dict(DESKTOP='Desktop', DOWNLOAD='Downloads', TEMPLATES='Templates',
                PUBLICSHARE='Public', DOCUMENTS='Documents', MUSIC='Music',
                PICTURES='Pictures', VIDEOS='Videos', PROJECTS='Projects')


@unittest.skipUnless(Path('/usr/bin/xdg-user-dirs-update').is_file(), 'Needs xdg-user-dirs')
@unittest.skipIf(os.geteuid() == 0, 'Run as an ordinary desktop user')
class UserDirectoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-user-directories-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.config = self.home / '.config'
        self.system = self.root / 'system'
        self.system.mkdir()
        (self.system / 'user-dirs.defaults').write_text(
            ''.join(f'{key}={name}\n' for key, name in DEFAULTS.items()))
        (self.system / 'user-dirs.conf').write_text('enabled=True\nfilename_encoding=UTF-8\n')
        self.env = {**os.environ, 'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.config),
                    'XDG_CONFIG_DIRS': str(self.system), 'LC_ALL': 'C', 'LANG': 'C'}

    def test_fresh_account_gets_real_directories_and_mappings_owned_by_user(self):
        self.assertTrue(directories.initialize(self.env))
        mapping = (self.config / 'user-dirs.dirs').read_text()
        for key, name in DEFAULTS.items():
            self.assertTrue((self.home / name).is_dir(), name)
            self.assertEqual((self.home / name).stat().st_uid, os.geteuid())
            self.assertIn(f'XDG_{key}_DIR="$HOME/{name}"', mapping)

    def test_repeat_login_preserves_contents_and_intentionally_removed_folders(self):
        directories.initialize(self.env)
        sentinel = self.home / 'Documents' / 'keep.txt'
        sentinel.write_text('Keep my work.\n')
        (self.home / 'Desktop').rmdir()
        mapping = self.config / 'user-dirs.dirs'
        before = mapping.read_bytes(), mapping.stat().st_mtime_ns
        self.assertFalse(directories.initialize(self.env))
        self.assertEqual((mapping.read_bytes(), mapping.stat().st_mtime_ns), before)
        self.assertFalse((self.home / 'Desktop').exists())
        self.assertEqual(sentinel.read_text(), 'Keep my work.\n')

    def test_first_initialization_keeps_existing_folders_and_their_contents(self):
        documents = self.home / 'Documents'
        documents.mkdir()
        sentinel = documents / 'keep.txt'
        sentinel.write_text('Existing files belong to the user.\n')
        identity = documents.stat().st_ino, sentinel.stat().st_ino
        self.assertTrue(directories.initialize(self.env))
        self.assertEqual((documents.stat().st_ino, sentinel.stat().st_ino), identity)
        self.assertEqual(sentinel.read_text(), 'Existing files belong to the user.\n')

    def test_custom_unavailable_and_disabled_locations_are_not_reset(self):
        self.config.mkdir()
        mapping = self.config / 'user-dirs.dirs'
        value = 'XDG_DESKTOP_DIR="$HOME/"\nXDG_DOCUMENTS_DIR="/unmounted/example/Documents"\n'
        mapping.write_text(value)
        self.assertFalse(directories.initialize(self.env))
        self.assertEqual(mapping.read_text(), value)
        self.assertEqual(list(self.home.iterdir()), [self.config])

    def test_broken_mapping_symlink_is_preserved(self):
        self.config.mkdir()
        mapping = self.config / 'user-dirs.dirs'
        missing = self.root / 'unavailable' / 'saved.dirs'
        mapping.symlink_to(missing)
        self.assertFalse(directories.initialize(self.env))
        self.assertEqual(mapping.readlink(), missing)
        self.assertFalse(missing.exists())
        self.assertFalse((self.home / 'Desktop').exists())

    def test_user_and_system_opt_out_are_respected(self):
        for target in (self.system, self.config):
            with self.subTest(target=target):
                target.mkdir(exist_ok=True)
                preference = target / 'user-dirs.conf'
                preference.write_text('enabled=False\n')
                self.assertFalse(directories.initialize(self.env))
                self.assertFalse((self.home / 'Desktop').exists())
                self.assertFalse((self.config / 'user-dirs.dirs').exists())
                preference.write_text('enabled=True\n')

    def test_custom_config_home_and_system_names_are_honored(self):
        self.config = self.root / 'custom-config'
        self.config.mkdir()
        self.env['XDG_CONFIG_HOME'] = str(self.config)
        (self.system / 'user-dirs.defaults').write_text('DOCUMENTS=My Papers\n')
        self.assertTrue(directories.initialize(self.env))
        self.assertTrue((self.home / 'My Papers').is_dir())
        self.assertFalse((self.home / '.config').exists())
        self.assertIn('$HOME/My Papers', (self.config / 'user-dirs.dirs').read_text())

    def test_missing_updater_and_timeout_fail_without_a_directory_reset(self):
        for error in (FileNotFoundError('fixture'), subprocess.TimeoutExpired('fixture', 10)):
            with self.subTest(error=error), patch.object(directories.subprocess, 'run', side_effect=error):
                with self.assertRaises(type(error)):
                    directories.initialize(self.env)
                self.assertFalse((self.home / 'Desktop').exists())

    def test_invalid_home_and_root_are_rejected_before_launching_updater(self):
        with patch.object(directories.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                directories.initialize({**self.env, 'HOME': 'relative-home'})
            with patch.object(directories.os, 'geteuid', return_value=0):
                with self.assertRaises(ValueError):
                    directories.initialize(self.env)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
