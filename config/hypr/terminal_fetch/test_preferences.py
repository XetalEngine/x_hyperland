"""Persistence, safe clearing and the actual terminal settings controls."""
import copy
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terminal_fetch import preferences, model


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_roundtrip_preserves_each_control_and_generates_kitty_settings(self):
        value = dict(preferences.DEFAULTS, history_size=43210, opacity=83, font_size=13.5,
                     cursor_shape='beam', scrollback_lines=54321, audio_bell=True)
        preferences.save(value, root=self.root)
        self.assertEqual(preferences.load(self.root), value)
        config = (self.root/'kitty-settings.conf').read_text()
        for setting in ('font_size 13.5', 'cursor_shape beam', 'background_opacity 0.83',
                        'scrollback_lines 54321', 'enable_audio_bell yes'):
            self.assertIn(setting, config)
        for name in ('preferences.json', 'kitty-settings.conf'):
            self.assertEqual((self.root/name).stat().st_mode & 0o777, 0o600)

    def test_rejects_config_injection_invalid_types_and_ranges(self):
        for key, value in [('font_family', 'monospace\nshell malicious'),
                           ('font_family', 'bad\x1bfont'), ('cursor_shape', 'round'),
                           ('history_enabled', 1), ('history_size', True),
                           ('history_size', -1), ('font_size', float('nan')),
                           ('shell', '/bin/unknown'), ('scrollback_lines', 1000001)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                preferences.save(dict(preferences.DEFAULTS, **{key: value}), root=self.root)
        self.assertFalse((self.root/'preferences.json').exists())

    def test_concurrent_editor_conflict_and_write_failure_keep_previous_preferences(self):
        original = preferences.save(preferences.DEFAULTS, root=self.root)
        changed = dict(original, history_size=30000)
        preferences.save(changed, root=self.root)
        with self.assertRaisesRegex(ValueError, 'changed elsewhere'):
            preferences.save(original, root=self.root, expected=original)
        before = (self.root/'kitty-settings.conf').read_bytes()
        atomic = preferences.atomic
        def fail_json(path, content, **kwargs):
            if path.name == 'preferences.json': raise OSError('disk full')
            return atomic(path, content, **kwargs)
        with patch.object(preferences, 'atomic', side_effect=fail_json), self.assertRaises(OSError):
            preferences.save(original, root=self.root, expected=changed)
        self.assertEqual(preferences.load(self.root), changed)
        self.assertEqual((self.root/'kitty-settings.conf').read_bytes(), before)

    def test_clear_retires_old_directory_and_never_reimports_original_history(self):
        original = self.root/'bash_history'; original.write_text('echo existing\n')
        state = self.root/'state'
        old_token, old_file = preferences.prepare_history(state, import_from=original)
        self.assertEqual(old_file.read_text(), original.read_text())
        self.assertEqual(old_file.stat().st_mode & 0o777, 0o600)
        new_token = preferences.clear_history(state)
        self.assertNotEqual(new_token, old_token)
        with self.assertRaises(FileNotFoundError): old_file.write_text('stale session\n')
        token, file = preferences.prepare_history(state, import_from=original)
        self.assertEqual(token, new_token); self.assertEqual(file.read_text(), '')
        self.assertEqual(original.read_text(), 'echo existing\n')
        self.assertEqual(state.stat().st_mode & 0o777, 0o700)

    def test_history_directory_symlinks_are_rejected_and_disabled_history_writes_nothing(self):
        link = self.root/'link'; link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): preferences.prepare_history(link)
        state = self.root/'not-created'
        values = preferences.shell_settings(dict(preferences.DEFAULTS, history_enabled=False), state)
        self.assertIn("FUSION_HISTORY_FILE=''", values)
        self.assertFalse(state.exists())

    def test_updater_and_default_settings_own_preferences_but_not_history_or_vendor_code(self):
        from updates import file_policy
        from settings_profiles import catalog
        for name in ('terminal_fetch/preferences.json', 'terminal_fetch/kitty-settings.conf'):
            self.assertEqual(file_policy.policy(name), 'preferences')
            self.assertEqual(catalog.profile_category(name), 'terminal')
        self.assertIsNone(catalog.profile_category('terminal_fetch/vendor/blesh/ble.sh'))
        self.assertIsNone(catalog.home_category('.local/state/hyperfusion/terminal/generation'))


class SettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for mocked in (patch.object(preferences, 'ROOT', self.root), patch.object(model, 'ROOT', self.root),
                       patch.dict(os.environ, {'XDG_STATE_HOME': str(self.root/'state'), 'XDG_CACHE_HOME': str(self.root/'cache')})):
            mocked.start(); self.addCleanup(mocked.stop)
        from terminal_fetch.settings_page import TerminalPage
        self.page = TerminalPage(lambda fn, done, failed: done({'os': 'Test OS'}))
        self.page.resize(1080, 800); self.page.show(); self.app.processEvents()
        self.addCleanup(self.page.close)

    def test_all_preferences_edit_save_discard_and_reset_without_erasing_history(self):
        self.assertEqual(set(self.page.inputs), set(preferences.DEFAULTS) - {'version'})
        self.assertFalse(self.page.dirty)
        self.page.inputs['history_size'].setValue(98765)
        self.page.inputs['autosuggestions'].setChecked(False)
        self.assertTrue(self.page.dirty); self.assertTrue(self.page.apply_button.isEnabled())
        self.page.save()
        self.assertEqual(preferences.load()['history_size'], 98765)
        self.assertFalse(preferences.load()['autosuggestions']); self.assertFalse(self.page.dirty)
        self.page.inputs['history_size'].setValue(12345); self.page.discard()
        self.assertEqual(self.page.inputs['history_size'].value(), 98765)
        with patch.object(preferences, 'clear_history', side_effect=AssertionError('unexpected deletion')):
            self.page.reset(); self.assertTrue(self.page.dirty)
        self.assertEqual(self.page.inputs['history_size'].value(), preferences.DEFAULTS['history_size'])

    def test_history_clear_requires_confirmation_and_does_not_save_pending_edits(self):
        from PyQt6.QtWidgets import QMessageBox
        self.page.inputs['history_size'].setValue(777)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel), \
             patch.object(preferences, 'clear_history') as clear:
            self.page.clear_history(); clear.assert_not_called()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.page.clear_history()
        self.assertEqual(preferences.history_path(preferences.state_root(),
                         preferences.generation(preferences.state_root())).read_bytes(), b'')
        self.assertTrue(self.page.dirty)
        self.assertFalse((self.root/'preferences.json').exists())

    def test_welcome_still_participates_in_unsaved_change_detection(self):
        self.page.welcome.enabled.setChecked(False)
        self.assertTrue(self.page.dirty)
        self.page.refresh()
        self.assertFalse(self.page.welcome.enabled.isChecked())
        self.page.welcome.save(); self.assertFalse(self.page.dirty)


if __name__ == '__main__': unittest.main()
