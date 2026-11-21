"""Native config checks use disposable profiles; never reload the live desktop.

Set HYPRLAND_LUA_BINARY to an extracted 0.57+ binary to exercise the actual
Lua reader/validator as well as the locally installed Hyprland version.
"""
import contextlib
import io
import json
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

    def test_css_gaps_and_lazy_cube_bindings_keep_native_semantics(self):
        (self.root/'hyprland.conf').write_text(
            'general:gaps_in = 2 4\ngeneral:gaps_out = 1 2 3 4\n'
            'bind = CTRL ALT, mouse:272, event, xetal-cube:rotate\n')
        source = compat.Renderer(self.root).render()
        self.assertIn('["top"]=2', source)
        self.assertIn('["right"]=4', source)
        self.assertIn('["bottom"]=2', source)
        self.assertIn('["left"]=4', source)
        self.assertIn('["description"]="Rotate desktop cube"', source)
        for invalid in ('1 2 3 4 5', 'one'):
            with self.assertRaises(ValueError): compat.gaps(invalid)
        command = compat.ipc('dispatch xetalcube:workspace switch "two"')
        self.assertIn('function() return hl.plugin["xetalcube"]["workspace"](', command)
        self.assertIn(r'switch \"two\"', command)

    def test_staged_sources_and_candidate_edits_do_not_borrow_live_profile(self):
        (self.root/'hyprland.conf').write_text('source = ~/.config/hypr/input.conf\n')
        (self.root/'input.conf').write_text('input:sensitivity = -0.25\n')
        candidate = compat.candidate(self.root, self.root, overrides={self.root/'input.conf': 'input:sensitivity = 0.75\n'}, modern=True)
        self.assertIn('0.75', candidate.read_text())
        self.assertNotIn('-0.25', candidate.read_text())
        self.assertEqual((self.root/'input.conf').read_text(), 'input:sensitivity = -0.25\n')
        legacy = compat.candidate(self.root, self.root, modern=False)
        self.assertIn(str(self.root/'input.conf'), legacy.read_text())

    def test_native_wobble_stays_off_after_sources_and_config_reload(self):
        (self.root/'hyprland.conf').write_text('source = theme.conf\nsubmap = test\n')
        (self.root/'theme.conf').write_text('decoration {\nwobble {\nenabled = true\n}\n}\n')
        for _ in range(2):
            source = compat.Renderer(self.root).render()
            self.assertNotIn('["decoration.wobble.enabled"]=true', source)
            self.assertTrue(source.endswith(compat.compiz_wobble_policy()+'\n'))
            self.assertIn('end)\n-- Hyper Fusion', source)
            self.assertEqual(source.count('hyperfusion-disable-native-wobble'), 1)
        # The desktop's editable settings remain intact; this is runtime policy.
        self.assertIn('enabled = true', (self.root/'theme.conf').read_text())

    def test_live_native_wobble_requests_cannot_replace_compiz(self):
        for key in ('decoration:wobble:enabled', 'decoration.wobble.enabled'):
            self.assertEqual(compat.ipc('keyword '+key+' true'),
                             'eval hl.config({["decoration.wobble.enabled"]=false})')

    def test_wallpaper_layer_rules_preserve_namespace_and_animation_policy(self):
        (self.root/'hyprland.conf').write_text(
            'layerrule = no_anim on, match:namespace ^xetal-wallpaper-transition$\n'
            'layerrule {\nname = overlay\nmatch:namespace = ^overlay$\nblur = on\n}\n')
        source = compat.Renderer(self.root).render()
        self.assertIn('hl.layer_rule({["no_anim"]=true, ["match"]={["namespace"]="^xetal-wallpaper-transition$"}})', source)
        self.assertIn('hl.layer_rule({["name"]="overlay", ["blur"]=true, ["match"]={["namespace"]="^overlay$"}})', source)
        self.assertEqual(compat.ipc('keyword layerrule[overlay]:blur off'),
                         'eval hl.layer_rule({["name"]="overlay", ["blur"]=false})')

    def test_legacy_candidate_does_not_receive_an_unsupported_native_wobble_key(self):
        original = 'animations:enabled = true\n'
        (self.root/'hyprland.conf').write_text(original)
        directory = self.root/'legacy'; directory.mkdir()
        candidate = compat.candidate(self.root, directory, modern=False)
        self.assertEqual(candidate.read_text(), original)

    def test_missing_recursive_and_unsupported_sources_fail_with_location(self):
        for value, message in [('source = absent.conf', 'absent.conf'),
                               ('source = hyprland.conf', 'Recursive source'),
                               ('unknown = silently ignored', 'Unsupported managed setting'),
                               ('general {\nborder_size = 2', 'unclosed')]:
            with self.subTest(value=value):
                (self.root/'hyprland.conf').write_text(value+'\n')
                with self.assertRaisesRegex(ValueError, message): compat.Renderer(self.root).render()

    def test_retained_old_config_gets_sdr_default_without_overriding_explicit_choice(self):
        (self.root/'hyprland.conf').write_text('monitor = ,preferred,auto,1\n')
        source = compat.Renderer(self.root).render()
        default = 'hl.config({["render.cm_auto_hdr"]=0})'
        self.assertIn(default, source)
        (self.root/'hyprland.conf').write_text('render:cm_auto_hdr = 2\n')
        source = compat.Renderer(self.root).render()
        self.assertLess(source.index(default), source.index('hl.config({["render.cm_auto_hdr"]=2})'))

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
        self.assertEqual(compat.ipc('dispatch xetalcube:workspace switch 2'),
                         'dispatch function() return hl.plugin["xetalcube"]["workspace"]("switch 2") end')
        with self.assertRaisesRegex(ValueError, 'Invalid dispatcher'): compat.ipc('dispatch not-a-plugin:unknown')
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

    def test_native_editor_without_session_path_translates_preview_and_apply(self):
        adapter = str(PAYLOAD/'compat/bin')
        result = subprocess.CompletedProcess([], 0, '{"version":"0.57.2"}', '')
        with patch.dict(os.environ, {'PATH':'/usr/bin:/bin'}, clear=True), \
                patch.object(compat.subprocess, 'run', return_value=result) as run:
            compat.prepare_session_ipc()
            run.assert_called_once_with(['/usr/bin/hyprctl', '-j', 'version'],
                capture_output=True, text=True, timeout=2, check=True)
            self.assertEqual(shutil.which('hyprctl'), adapter+'/hyprctl')
            self.assertEqual(os.environ['XETAL_HYPRLAND_LUA'], '1')
            compat.prepare_session_ipc()
            self.assertEqual(os.environ['PATH'].split(':').count(adapter), 1)
            payload = json.dumps({'action':'update','rule':{'titlebar':False},'name':'a "quoted" title'})
            run.return_value = subprocess.CompletedProcess([], 0, 'ok\n', '')
            with contextlib.redirect_stdout(io.StringIO()):
                compat.cli(['dispatch', 'xetalwindowclose:preview', payload])
            self.assertEqual(run.call_args.args[0], ['/usr/bin/hyprctl', 'dispatch',
                'function() return hl.plugin["xetalwindowclose"]["preview"]('+compat.lua(payload)+') end'])
            with contextlib.redirect_stdout(io.StringIO()):
                compat.cli(['dispatch', 'xetalwindowclose:reload'])
            self.assertIn('hl.plugin["xetalwindowclose"]["reload"]', run.call_args.args[0][2])

    def test_native_editor_uses_running_legacy_version_and_rejects_unknown_versions(self):
        adapter = str(PAYLOAD/'compat/bin')
        environment = {'PATH':adapter+':/usr/bin', 'XETAL_HYPRLAND_LUA':'1', 'XDG_CURRENT_DESKTOP':'Hyprland'}
        with patch.dict(os.environ, environment, clear=True), \
                patch.object(compat.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"tag":"v0.56.2"}', '')) as run:
            compat.prepare_session_ipc()
            self.assertEqual(os.environ['PATH'], '/usr/bin')
            self.assertNotIn('XETAL_HYPRLAND_LUA', os.environ)
            self.assertEqual(os.environ['XDG_CURRENT_DESKTOP'], 'Hyprland')
            before = dict(os.environ)
            run.return_value = subprocess.CompletedProcess([], 0, '{"version":"unknown"}', '')
            with self.assertRaisesRegex(ValueError, 'running Hyprland'):
                compat.prepare_session_ipc()
            self.assertEqual(dict(os.environ), before)


@unittest.skipUnless(os.environ.get('HYPRLAND_LUA_BINARY'), 'Set HYPRLAND_LUA_BINARY for native Lua regression tests')
class NativeLuaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-lua-test-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name); self.root = self.home/'.config/hypr'
        # Only the config graph and reader are needed, not wallpaper/native assets.
        for name in ('hyprland.conf', 'keybindings.conf', 'desktop/environment.conf',
                     'startup/window-rules.conf', 'window_rules/rules.conf', 'control_center/displays.conf', 'control_center/workspaces.conf',
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

    def test_hdr_display_edits_pass_the_real_compositor_validator(self):
        model = dict(name='DP-1', enabled=True, width=2560, height=1440, rate=120,
                     x=0, y=0, scale=1, transform=0, mirror='', bitdepth=10,
                     sdrbrightness=1.25, sdrsaturation=.9, sdr_min_luminance=.2, sdr_max_luminance=100)
        for mode in ('srgb', 'hdr', 'hdredid'):
            with self.subTest(mode=mode):
                model['cm'] = mode
                (self.root/'control_center/displays.conf').write_text(desktop_settings.display_config([model]))
                code, output = self.verify(self.root/'hyprland.lua')
                self.assertEqual(code, 0, output)
                self.assertIn('config ok', output)


if __name__ == '__main__': unittest.main()
