"""Native config checks use disposable profiles; never reload the live desktop.

Set HYPRLAND_LUA_BINARY to an extracted 0.57+ binary to exercise the actual
Lua reader/validator as well as the locally installed Hyprland version.
"""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = REPO/'config/hypr'
sys.path.insert(0, str(PAYLOAD/'compat'))
sys.path.insert(0, str(PAYLOAD/'control_center'))
import hypr_compat as compat
import keys
import desktop_settings


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-config-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_complete_packaged_config_preserves_every_enabled_binding(self):
        source = compat.Renderer(PAYLOAD).render()
        enabled = sum(binding.enabled for binding in keys.parse((PAYLOAD/'keybindings.conf').read_text()))
        self.assertEqual(source.count('hl.bind('), enabled+5)  # five passive mouse notifications
        self.assertIn('hl.define_submap("hypr-control-capture"', source)
        self.assertIn('"ignore_mods"', source)
        self.assertIn('"non_consuming"', source)
        self.assertIn('"mouse"', source)
        self.assertIn('"release"', source)
        self.assertIn('"XDG_CURRENT_DESKTOP", "Hyprland"', source)

    def test_staged_sources_and_candidate_edits_do_not_borrow_live_profile(self):
        (self.root/'hyprland.conf').write_text('source = ~/.config/hypr/input.conf\n')
        (self.root/'input.conf').write_text('input:sensitivity = -0.25\n')
        candidate = compat.candidate(self.root, self.root, overrides={self.root/'input.conf': 'input:sensitivity = 0.75\n'}, modern=True)
        self.assertIn('0.75', candidate.read_text())
        self.assertNotIn('-0.25', candidate.read_text())
        self.assertEqual((self.root/'input.conf').read_text(), 'input:sensitivity = -0.25\n')
        legacy = compat.candidate(self.root, self.root, modern=False)
        self.assertIn(str(self.root/'input.conf'), legacy.read_text())

    def test_missing_recursive_and_unsupported_sources_fail_with_location(self):
        for value, message in [('source = absent.conf', 'absent.conf'),
                               ('source = hyprland.conf', 'Recursive source'),
                               ('unknown = silently ignored', 'Unsupported managed setting'),
                               ('general {\nborder_size = 2', 'unclosed')]:
            with self.subTest(value=value):
                (self.root/'hyprland.conf').write_text(value+'\n')
                with self.assertRaisesRegex(ValueError, message): compat.Renderer(self.root).render()

    def test_quoted_commands_comments_commas_and_binding_descriptions(self):
        (self.root/'hyprland.conf').write_text('### heading\n$terminal = printf "one,two ##three"\n'
            'bindd = SUPER, Q, Terminal, exec, $terminal\nbindm = SUPER, mouse:273, resizewindow 1\n')
        source = compat.Renderer(self.root).render()
        self.assertIn('one,two #three', source)
        self.assertIn('["description"]="Terminal"', source)
        self.assertIn('["keep_aspect_ratio"]=true', source)
        self.assertIn('XETAL_HYPRLAND_LUA=1', source)
        self.assertNotIn('hl.env("PATH"', source)

    def test_hotkey_converter_rejection_never_writes_or_backs_up(self):
        (self.root/'hyprland.conf').write_text('$mainMod = SUPER\n'+keys.SOURCE+'\n')
        original = 'bind = SUPER, Q, exec, kitty\n'
        (self.root/'keybindings.conf').write_text(original)
        bindings = keys.parse(original); bindings[0].dispatcher = 'no_such_action'
        with patch.object(compat, 'uses_lua', return_value=True):
            with self.assertRaisesRegex(keys.ConfigError, 'rejected'):
                keys.Store(self.root, self.root/'state').apply(bindings, keys.digest(original.encode()))
        self.assertEqual((self.root/'keybindings.conf').read_text(), original)
        self.assertFalse(list((self.root/'state').glob('keybindings-*.conf')))

    def test_live_commands_keep_arguments_and_queries_intact(self):
        self.assertEqual(compat.ipc('j/clients'), 'j/clients')
        self.assertEqual(compat.ipc('dispatch hl.dsp.exit()'), 'dispatch hl.dsp.exit()')
        self.assertIn('["workspace"]="2"', compat.ipc('dispatch workspace 2'))
        self.assertIn('["window"]="address:0x123"', compat.ipc('dispatch movewindowpixel exact 50 60,address:0x123'))
        self.assertIn('["relative"]=false', compat.ipc('dispatch movewindowpixel exact 50 60,address:0x123'))
        self.assertIn('["follow"]=false', compat.ipc('dispatch movetoworkspacesilent 3,address:0x123'))
        self.assertIn('["name"]="xetal-launcher"', compat.ipc('keyword windowrule[xetal-launcher]:size 500 600'))
        with self.assertRaisesRegex(ValueError, 'Invalid dispatcher'): compat.ipc('dispatch xetalcube:workspace switch 2')
        batch = 'dispatch exec [float on; center on] printf "one;two"; dispatch workspace 2'
        calls = []
        def run(argv, **kwargs):
            calls.append(argv); return subprocess.CompletedProcess(argv, 0, 'ok\nok\n', '')
        with patch.object(compat.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            compat.cli(['--batch', batch])
            compat.cli(['notify', '-1', '3000', '0', 'dispatch'])
            compat.cli(['-j', 'monitors', 'all'])
        self.assertEqual(calls[0][2].count('dispatch hl.dsp.'), 2)
        self.assertIn(r'one\;two', calls[0][2])
        self.assertEqual(calls[1][1:], ['notify', '-1', '3000', '0', 'dispatch'])
        self.assertEqual(calls[2][1:], ['-j', 'monitors', 'all'])

    def test_runtime_command_environment_does_not_change_parent_or_shared_files(self):
        before = dict(os.environ)
        result = subprocess.run(compat.session_command('printf "%s|%s" "$XETAL_HYPRLAND_LUA" "$PATH"'),
                                shell=True, capture_output=True, text=True, check=True,
                                env={**os.environ, 'HOME': str(self.root), 'PATH': '/usr/bin:/bin'})
        self.assertEqual(result.stdout, '1|'+str(self.root/'.config/hypr/compat/bin')+':/usr/bin:/bin')
        self.assertEqual(dict(os.environ), before)


@unittest.skipUnless(os.environ.get('HYPRLAND_LUA_BINARY'), 'Set HYPRLAND_LUA_BINARY for native Lua regression tests')
class NativeLuaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-lua-test-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name); self.root = self.home/'.config/hypr'
        # Only the config graph and reader are needed, not wallpaper/native assets.
        for name in ('hyprland.conf', 'keybindings.conf', 'desktop/environment.conf',
                     'startup/window-rules.conf', 'control_center/displays.conf', 'control_center/workspaces.conf',
                     'control_center/input.conf', 'control_center/theme.conf', 'control_center/appearance.conf',
                     'compat/hypr_compat.py', 'compat/entry.lua'):
            destination = self.root/name; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text((PAYLOAD/name).read_text().replace('@HOME@', str(self.home)).replace('@HYPR@', str(self.root)))
        self.binary = os.environ['HYPRLAND_LUA_BINARY']
        compat.install_entry(self.root, self.binary)

    def verify(self, path):
        result = subprocess.run([self.binary, '--verify-config', '--config', str(path)], capture_output=True, text=True, timeout=15)
        return result.returncode, result.stdout+result.stderr

    def test_real_lua_entry_and_edits_are_read_on_each_reload(self):
        candidate = compat.candidate(self.root, self.home, modern=True)
        self.assertEqual(candidate, self.root/'hyprland.lua')
        code, output = self.verify(candidate)
        self.assertEqual(code, 0, output); self.assertIn('config ok', output)
        (self.root/'control_center/input.conf').write_text('input:setting_does_not_exist = 1\n')
        code, output = self.verify(candidate)
        self.assertNotEqual(code, 0); self.assertNotIn('config ok', output)

    def test_display_and_hotkey_editor_candidates_use_native_lua(self):
        def run(argv):
            argv = [self.binary, *argv[1:]]
            return subprocess.run(argv, capture_output=True, text=True, timeout=15)
        with patch.object(compat, 'uses_lua', return_value=True):
            bindings = keys.parse((self.root/'keybindings.conf').read_text())
            bindings[0].key = 'F12'
            keys.Store(self.root, self.home/'state', run).check(bindings, (self.root/'hyprland.conf').read_text())
            def checked(argv):
                result = run(argv)
                if result.returncode: raise ValueError(result.stdout+result.stderr)
                return result.stdout.strip()
            store = desktop_settings.Store('displays', self.root, self.home/'state', checked)
            content, token = store.load()
            store.check('monitor = HDMI-A-1,2560x1440@144,0x0,1,transform,0\nmonitor = DP-1,disable\n', token)
            self.assertEqual(store.load()[0], content)

    def test_verification_never_runs_startup_or_reload_commands(self):
        marker = self.home/'must-not-exist'
        with (self.root/'hyprland.conf').open('a') as stream:
            stream.write(f'\nexec = touch {marker}\nexec-once = touch {marker}\n')
        code, output = self.verify(self.root/'hyprland.lua')
        self.assertEqual(code, 0, output)
        self.assertFalse(marker.exists(), 'Config verification executed an application')


if __name__ == '__main__': unittest.main()
