"""Release ownership regressions using disposable, offline profiles."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import file_policy
import update_engine as engine

OLD, NEW = '1'*40, '2'*40


class FilePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-update-policy-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.live = self.root/'live'; self.live.mkdir()
        self.upstream = self.root/'incoming'; self.upstream.mkdir()
        self.stage = self.root/'stage'; self.state = self.root/'state'
        self.register()

    def write(self, root, name, data, mode=0o644):
        path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        path.chmod(mode)
        return path

    def register(self):
        # Older installations have no file-policy field in their inventory.
        inventory = engine.metadata(self.live, OLD)
        for entry in inventory['files'].values(): entry.pop('policy', None)
        engine.write_json(self.live/engine.META, inventory)

    def prepare(self):
        expected = engine.merge_profile(self.live, self.upstream, self.stage, NEW)
        return engine.prepare_plan(self.live, self.stage, expected, NEW)

    def test_multiple_unknown_copies_update_without_history_or_fingerprints_and_roll_back(self):
        names = ('scripts/runtime-log-guard.py', 'scripts/session.sh', 'startup/launch.py',
                 'control_panel/native.cpp', 'control_panel/tools.json',
                 'runtime/manifest.json', 'compat/entry.lua', 'assets/logo.png')
        for name in names:
            self.write(self.live, name, b'unknown local copy\n')
            self.write(self.upstream, name, '{}' if name.endswith('.json') else b'new release\n')
        inventory = (self.live/engine.META).read_bytes()
        with patch.object(engine.subprocess, 'run', side_effect=AssertionError('No Git lookup or code merge')):
            plan = self.prepare()
        self.assertEqual((self.live/engine.META).read_bytes(), inventory)
        for name in names:
            self.assertEqual((self.live/name).read_bytes(), b'unknown local copy\n')
            self.assertEqual((self.stage/name).read_bytes(), (self.upstream/name).read_bytes())
        backup = engine.apply_plan(self.live, self.stage, plan, self.state)
        for name in names:
            self.assertEqual((self.live/name).read_bytes(), (self.upstream/name).read_bytes())
            self.assertEqual((backup/'files'/name).read_bytes(), b'unknown local copy\n')
        engine.apply_plan(self.live, backup/'files', engine.rollback_plan(self.live, backup), self.state)
        self.assertEqual((self.live/engine.META).read_bytes(), inventory)
        for name in names: self.assertEqual((self.live/name).read_bytes(), b'unknown local copy\n')

    def test_unchanged_upstream_code_still_repairs_local_edits_missing_files_and_modes(self):
        names = ('scripts/edited.py', 'scripts/missing.py', 'scripts/launch.sh')
        for name in names:
            self.write(self.live, name, 'released\n', 0o755)
            self.write(self.upstream, name, 'released\n', 0o755)
        self.register()
        (self.live/names[0]).write_text('modified locally\n')
        (self.live/names[1]).unlink()
        (self.live/names[2]).chmod(0o600)
        plan = self.prepare(); engine.apply_plan(self.live, self.stage, plan, self.state)
        for name in names:
            self.assertEqual((self.live/name).read_text(), 'released\n')
            self.assertEqual((self.live/name).stat().st_mode & 0o777, 0o755)

    def test_unregistered_preferences_retain_choices_and_receive_new_defaults(self):
        self.write(self.live, 'theme/state.json', '{"mode":"light","custom":true}')
        self.write(self.upstream, 'theme/state.json', '{"mode":"dark","design":"modern"}')
        plan = self.prepare(); engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual(engine.json_file(self.live/'theme/state.json'),
                         {'mode':'light', 'custom':True, 'design':'modern'})

    def test_fresh_launcher_defaults_never_replace_existing_favorites_or_copies(self):
        favorites = 'launcher/favorites.json'
        original = '{"add":["old-default.desktop","kitty.desktop"],"hide":[]}'
        self.write(self.live, favorites, original)
        self.register()
        personal = '{"add":["my-app.desktop"],"hide":["kitty.desktop","xetal-calculator.desktop"]}'
        self.write(self.live, favorites, personal)
        self.write(self.upstream, favorites,
                   '{"add":["xetal-files-computer.desktop","kitty.desktop","xetal-calculator.desktop"],"hide":[]}')
        saved = {'launcher/bar-pins.json': '{"version":1,"pins":["my-app.desktop"]}',
                 'launcher/shortcuts.json': '{"version":1,"overrides":{},"copies":{"mine":{"name":"My tool"}}}',
                 'launcher/favorite-layout.json': '{"version":1,"groups":[]}',
                 'launcher/icons/mine.png': 'my icon'}
        for name, data in saved.items(): self.write(self.live, name, data)
        for name in ('launcher/bar-pins.json', 'launcher/shortcuts.json'):
            self.write(self.upstream, name, '{}')
        plan = self.prepare(); engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual((self.live/favorites).read_text(), personal)
        for name, data in saved.items(): self.assertEqual((self.live/name).read_text(), data)

    def test_file_manager_update_delivers_executable_and_keeps_private_preferences(self):
        self.write(self.live, 'file_manager/state/settings.ini', 'private bookmarks and columns\n')
        self.write(self.upstream, 'file_manager/main.cpp', 'new application\n')
        self.write(self.upstream, 'desktop/data/applications/xetal-files-computer.desktop', 'My Computer launcher\n')
        expected = engine.merge_profile(self.live, self.upstream, self.stage, NEW)
        self.write(self.stage, 'file_manager/.build/xetal-files', 'built executable', 0o755)
        self.write(self.stage, 'file_manager/.build/CMakeCache.txt', '/private/build/path')
        self.write(self.stage, 'file_manager/.build/files-tests', 'test executable')
        self.write(self.stage, 'file_manager/state/settings.ini', 'temporary settings')
        plan = engine.prepare_plan(self.live, self.stage, expected, NEW)
        self.assertIn('file_manager/.build/xetal-files', plan['changes'])
        self.assertNotIn('file_manager/.build/CMakeCache.txt', plan['changes'])
        self.assertNotIn('file_manager/.build/files-tests', plan['changes'])
        self.assertNotIn('file_manager/state/settings.ini', plan['changes'])
        engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual((self.live/'file_manager/state/settings.ini').read_text(), 'private bookmarks and columns\n')
        self.assertEqual((self.live/'file_manager/.build/xetal-files').stat().st_mode & 0o777, 0o755)

    def test_personal_text_conflict_is_preserved_without_blocking_release_files(self):
        self.write(self.live, 'keybindings.conf', 'bind = SUPER, Q, exec, old-terminal\n')
        self.register()
        custom = 'bind = SUPER, Q, exec, my-terminal\n'
        self.write(self.live, 'keybindings.conf', custom)
        self.write(self.upstream, 'keybindings.conf', 'bind = SUPER, Q, exec, new-terminal\n')
        self.write(self.upstream, 'scripts/helper.py', 'new helper\n')
        plan = self.prepare(); engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual((self.live/'keybindings.conf').read_text(), custom)
        self.assertEqual((self.live/'scripts/helper.py').read_text(), 'new helper\n')

    def test_generated_hardware_and_unrelated_files_keep_their_contents(self):
        keep = ('control_center/displays.conf', 'wallpaper/selection.json', 'waybar/style.css',
                'theme/hyprlock-raw.conf', 'theme/startup-raw.conf', 'wallpaper/profiles.json')
        private = ('scripts/my-own.py', 'control_panel/local_patch_iso/patch_iso.py',
                   'control_panel/state/settings.ini', 'dolphin/data/bookmarks.xbel')
        for name in (*keep, *private): self.write(self.live, name, 'mine\n')
        for name in keep: self.write(self.upstream, name, 'packaged default\n')
        plan = self.prepare(); engine.apply_plan(self.live, self.stage, plan, self.state)
        for name in (*keep, *private): self.assertEqual((self.live/name).read_text(), 'mine\n')
        for name in private: self.assertNotIn(name, plan['changes'])

    def test_runtime_state_created_by_a_builder_is_not_installed_over_user_state(self):
        settings = self.write(self.live, 'control_panel/state/preferences.ini', 'my preference\n')
        expected = engine.merge_profile(self.live, self.upstream, self.stage, NEW)
        self.write(self.stage, 'control_panel/state/preferences.ini', 'temporary default\n')
        self.write(self.stage, 'theme/cache/transient', 'temporary cache\n')
        plan = engine.prepare_plan(self.live, self.stage, expected, NEW)
        engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual(settings.read_text(), 'my preference\n')
        self.assertFalse((self.live/'theme/cache/transient').exists())

    def test_removing_a_preference_from_release_keeps_user_choice(self):
        path = self.write(self.live, 'recording/settings.json', '{"audio":false}')
        self.register()
        plan = self.prepare(); engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual(path.read_text(), '{"audio":false}')

    def test_backup_failure_cannot_overwrite_an_unknown_local_copy(self):
        path = self.write(self.live, 'scripts/helper.py', 'local copy\n')
        self.write(self.upstream, 'scripts/helper.py', 'new release\n')
        plan = self.prepare(); atomic = engine.atomic
        def no_space(target, data, mode=0o600):
            if target.is_relative_to(self.state/'backups') and target.name == 'helper.py':
                raise OSError('no space for backup')
            return atomic(target, data, mode)
        with patch.object(engine, 'atomic', side_effect=no_space):
            with self.assertRaisesRegex(OSError, 'no space'): engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual(path.read_text(), 'local copy\n')
        self.assertEqual(engine.installed(self.live)['revision'], OLD)

    def test_edit_after_staging_still_blocks_and_retains_latest_content(self):
        path = self.write(self.live, 'scripts/helper.py', 'local copy\n')
        self.write(self.upstream, 'scripts/helper.py', 'new release\n')
        plan = self.prepare(); path.write_text('edited during build\n')
        with self.assertRaisesRegex(RuntimeError, 'changed after'):
            engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual(path.read_text(), 'edited during build\n')

    def test_release_collision_cannot_follow_a_symlink(self):
        outside = self.write(self.root, 'outside.py', 'unrelated data\n')
        (self.live/'scripts').mkdir()
        (self.live/'scripts/helper.py').symlink_to(outside)
        self.write(self.upstream, 'scripts/helper.py', 'new release\n')
        with self.assertRaisesRegex(ValueError, 'symbolic link'): self.prepare()
        self.assertEqual(outside.read_text(), 'unrelated data\n')

    def test_packaged_metadata_and_templates_are_not_user_preferences(self):
        for name in ('runtime/manifest.json', 'runtime/fedora-44.json', 'control_panel/tools.json',
                     'theme/palettes.json', 'control_center/keybindings-defaults.conf', 'compat/entry.lua'):
            with self.subTest(name=name): self.assertEqual(file_policy.policy(name), 'release')
        for name in file_policy.PREFERENCES:
            with self.subTest(name=name): self.assertEqual(file_policy.policy(name), 'preferences')


if __name__ == '__main__': unittest.main()
