"""Regression tests for safe hotkey edits; all writes use temporary directories."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

import keys


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / 'state'
        self.bindings = keys.parse('bind = $mainMod, Q, exec, kitty\nbindm = $mainMod, mouse:272, movewindow\n')
        self.original = keys.serialize(self.bindings).encode()
        (self.root / 'keybindings.conf').write_bytes(self.original)
        (self.root / 'hyprland.conf').write_text('$mainMod = SUPER\n' + keys.SOURCE + '\n')
        self.calls = []

    def tearDown(self):
        self.temporary.cleanup()

    def runner(self, argv):
        self.calls.append(argv)
        output = 'config ok' if argv[0] == 'Hyprland' else ('ok\n' if argv[1] == 'reload' else '')
        if argv[0] == 'Hyprland':
            text = Path(argv[-1]).read_text()
            self.assertNotIn(keys.SOURCE, text)
            self.assertIn('.hotkey-check-', text)
        return subprocess.CompletedProcess(argv, 0, output, '')

    def store(self, runner=None):
        return keys.Store(self.root, self.state, runner or self.runner)

    def test_roundtrip_mouse_flags_description_commas_and_disabled(self):
        data = keys.parse('bindm = SUPER, mouse:273, resizewindow 1\n'
                          'bindel = , XF86AudioRaiseVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+\n'
                          'bindd = SUPER, F, Focus editor, exec, sh -c "echo one,two"\n'
                          '# disabled: bind = SUPER, R, exec, rofi\n')
        serialized = keys.serialize(data)
        self.assertIn('bindm = SUPER, mouse:273, resizewindow 1\n', serialized)
        self.assertEqual(data, keys.parse(serialized))
        self.assertFalse(data[-1].enabled)

    def test_variable_modifier_conflict(self):
        extra = copy.deepcopy(self.bindings[0])
        extra.id, extra.mods, extra.key = 'extra', 'SUPER', 'q'
        self.assertTrue(keys.conflicts(self.bindings + [extra], {'mainMod': 'SUPER'}))
        extra.enabled = False
        self.assertFalse(keys.conflicts(self.bindings + [extra], {'mainMod': 'SUPER'}))

    def test_typing_shortcuts_require_super_outside_capture_map(self):
        for mods, key in [('SHIFT', 'code:61'), ('CTRL', 'C'), ('', 'space')]:
            binding = copy.deepcopy(self.bindings[0])
            binding.mods, binding.key = mods, key
            with self.assertRaisesRegex(keys.ConfigError, 'use SUPER'):
                keys.protect_typing([binding], {})
            binding.mods = 'SUPER ' + mods
            keys.protect_typing([binding], {})
        keys.protect_typing(keys.parse('bind = SHIFT, Print, exec, screenshot\n'
                                      'bind = , XF86AudioMute, exec, mute\n'
                                      'submap = hypr-control-capture\n'
                                      'bind = , Escape, submap, reset\n'), {})

    def test_apply_keeps_exact_backup_and_reloads(self):
        self.bindings[0].key = 'T'
        result, backup = self.store().apply(self.bindings, keys.digest(self.original))
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(result, keys.digest((self.root / 'keybindings.conf').read_bytes()))
        self.assertEqual(keys.parse((self.root / 'keybindings.conf').read_text())[0].key, 'T')
        self.assertEqual(self.calls[-2:], [['hyprctl', 'reload'], ['hyprctl', 'configerrors']])

    def test_external_edits_are_not_overwritten(self):
        external = self.original + b'# external change\n'
        (self.root / 'keybindings.conf').write_bytes(external)
        with self.assertRaisesRegex(keys.ConfigError, 'changed outside'):
            self.store().apply(self.bindings, keys.digest(self.original))
        self.assertEqual((self.root / 'keybindings.conf').read_bytes(), external)
        self.assertFalse(self.calls)

    def test_validator_failure_never_changes_active_file(self):
        def reject(argv):
            return subprocess.CompletedProcess(argv, 1, 'invalid dispatcher', '')
        self.bindings[0].dispatcher = 'doesnotexist'
        with self.assertRaisesRegex(keys.ConfigError, 'rejected'):
            self.store(reject).apply(self.bindings, keys.digest(self.original))
        self.assertEqual((self.root / 'keybindings.conf').read_bytes(), self.original)
        self.assertFalse(list(self.state.glob('keybindings-*.conf')))

    def test_live_reload_failure_rolls_back(self):
        count = 0
        def failing_reload(argv):
            nonlocal count
            if argv == ['hyprctl', 'reload']:
                count += 1
                if count == 1:
                    return subprocess.CompletedProcess(argv, 1, '', 'socket unavailable')
            return self.runner(argv)
        self.bindings[0].key = 'T'
        with self.assertRaisesRegex(keys.ConfigError, 'rolled back'):
            self.store(failing_reload).apply(self.bindings, keys.digest(self.original))
        self.assertEqual((self.root / 'keybindings.conf').read_bytes(), self.original)
        self.assertEqual(count, 2)

    def test_recovery_binding_cannot_be_deleted(self):
        self.bindings[0].protected = True
        original = keys.serialize(self.bindings).encode()
        (self.root / 'keybindings.conf').write_bytes(original)
        with self.assertRaisesRegex(keys.ConfigError, 'recovery'):
            self.store().apply(self.bindings[1:], keys.digest(original))
        self.assertEqual((self.root / 'keybindings.conf').read_bytes(), original)

    def test_unrecognized_configuration_is_preserved_by_refusing_edit(self):
        with self.assertRaises(keys.ConfigError):
            keys.parse('source = ~/.config/kdeglobals\n')

    def test_real_hyprland_rejects_invalid_dispatcher_without_writing(self):
        self.bindings[0].dispatcher = 'this_dispatcher_does_not_exist'
        store = keys.Store(self.root, self.state)
        with self.assertRaisesRegex(keys.ConfigError, 'rejected'):
            store.check(self.bindings, (self.root / 'hyprland.conf').read_text())
        self.assertEqual((self.root / 'keybindings.conf').read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
