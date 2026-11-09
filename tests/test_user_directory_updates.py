"""Repair real temporary homes through the automatic-update preparation path."""
from contextlib import ExitStack, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'installer'))
import install
import update

OLD, NEW = '1'*40, '2'*40
FOLDERS = dict(DESKTOP='Desktop', DOCUMENTS='Documents', DOWNLOAD='Downloads',
               MUSIC='Music', PICTURES='Pictures', VIDEOS='Videos',
               TEMPLATES='Templates', PUBLICSHARE='Public')


@unittest.skipUnless(Path('/usr/bin/xdg-user-dirs-update').is_file(), 'Needs xdg-user-dirs')
@unittest.skipIf(os.geteuid() == 0, 'Updates run as a normal desktop user')
class UserDirectoryUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-folder-update-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root/'recipient'; self.home.mkdir()
        self.live = self.home/'.config/hypr'; self.live.mkdir(parents=True)
        (self.live/'code.py').write_text('old code\n')
        update.engine.write_json(self.live/update.engine.META, update.engine.metadata(self.live, OLD))
        self.state = self.home/'.local/state/xetal-hyprland/updates'
        self.system = self.root/'system'; self.system.mkdir()
        (self.system/'user-dirs.defaults').write_text(''.join(f'{k}={v}\n' for k, v in FOLDERS.items()))
        (self.system/'user-dirs.conf').write_text('enabled=True\n')
        self.enterContext(patch.dict(os.environ, {
            'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.home/'.config'),
            'XDG_CONFIG_DIRS': str(self.system), 'LANG': 'C', 'LC_ALL': 'C',
        }))
        self.rendered_folders = []

    def render(self, destination, home, monitors, **kwargs):
        self.assertEqual(home, self.home)
        self.rendered_folders.append({name: (home/name).is_dir() for name in FOLDERS.values()})
        (destination/'theme').mkdir(parents=True)
        (destination/'code.py').write_text('new code\n')
        (destination/'theme/update_widget.py').write_text('# Fixture has no theme build.\n')
        (destination/'scripts').mkdir()
        shutil.copy2(REPO/'config/hypr/scripts/user-directories.py', destination/'scripts/user-directories.py')
        mapping = home/'.config/user-dirs.dirs'
        if mapping.is_file():
            (destination/'dolphin/config').mkdir(parents=True)
            shutil.copy2(mapping, destination/'dolphin/config/user-dirs.dirs')

    def prepare(self, **kwargs):
        with ExitStack() as stack:
            for owner, name, value in (
                (install, 'source_revision', NEW), (install.runtime_install.policy, 'problem', None),
                (update.dependencies, 'check', []), (install, 'connected_monitors', []),
                (install, 'validate_config', None), (install, 'build', None), (install, 'validate', None),
            ):
                stack.enter_context(patch.object(owner, name, return_value=value))
            stack.enter_context(patch.object(install, 'render', side_effect=self.render))
            update.prepare(self.home, NEW, **kwargs)

    def test_old_profile_is_repaired_before_render_without_activating_or_logout(self):
        before = {p.name: p.read_bytes() for p in self.live.iterdir()}
        self.assertFalse((self.live/'scripts/user-directories.py').exists())
        self.prepare()
        self.assertTrue(all(self.rendered_folders[0].values()))
        mapping = self.home/'.config/user-dirs.dirs'
        self.assertEqual(mapping.stat().st_uid, os.geteuid())
        for name in FOLDERS.values():
            self.assertEqual((self.home/name).stat().st_uid, os.geteuid())
        self.assertEqual({p.name: p.read_bytes() for p in self.live.iterdir()}, before)
        pending = update.engine.json_file(self.state/'pending.json')
        self.assertTrue(pending['automatic'])
        self.assertEqual(pending['revision'], NEW)
        self.assertEqual((Path(pending['stage'])/'dolphin/config/user-dirs.dirs').read_bytes(), mapping.read_bytes())
        # A repeated prepare also leaves folder contents and mappings untouched.
        sentinel = self.home/'Documents/keep.txt'; sentinel.write_text('My work.\n')
        original = mapping.read_bytes(), mapping.stat().st_mtime_ns
        self.prepare()
        self.assertEqual((mapping.read_bytes(), mapping.stat().st_mtime_ns), original)
        self.assertEqual(sentinel.read_text(), 'My work.\n')

    def test_existing_locations_and_private_settings_are_not_rewritten(self):
        mapping = self.home/'.config/user-dirs.dirs'
        original = 'XDG_DOCUMENTS_DIR="/not-mounted/personal/Papers"\nXDG_DESKTOP_DIR="$HOME/"\n'
        mapping.write_text(original)
        state = self.live/'file_manager/state'; state.mkdir(parents=True)
        preference = state/'preferences.json'; preference.write_text('{"show_hidden":true}\n')
        self.prepare()
        self.assertEqual(mapping.read_text(), original)
        self.assertFalse(any(self.rendered_folders[0].values()))
        self.assertEqual(preference.read_text(), '{"show_hidden":true}\n')

    def test_disabled_initialization_still_prepares_update(self):
        (self.home/'.config/user-dirs.conf').write_text('enabled=False\n')
        self.prepare()
        self.assertFalse((self.home/'.config/user-dirs.dirs').exists())
        self.assertFalse(any(self.rendered_folders[0].values()))
        self.assertTrue((self.state/'pending.json').is_file())

    def test_helper_failure_is_logged_and_does_not_block_update(self):
        missing_payload = self.root/'missing-helper'
        with patch.object(install, 'PAYLOAD', missing_payload), redirect_stdout(io.StringIO()) as output:
            self.prepare()
        self.assertIn('Standard folder setup will retry at login:', output.getvalue())
        self.assertFalse((self.home/'.config/user-dirs.dirs').exists())
        self.assertTrue((self.state/'pending.json').is_file())

    def test_cancelled_update_does_not_initialize_folders(self):
        def cancelled():
            raise RuntimeError('Cancelled fixture')
        with self.assertRaisesRegex(RuntimeError, 'Cancelled fixture'):
            self.prepare(checkpoint=cancelled)
        self.assertFalse((self.home/'.config/user-dirs.dirs').exists())
        self.assertFalse(self.rendered_folders)
        self.assertFalse((self.state/'pending.json').exists())


if __name__ == '__main__':
    unittest.main()
