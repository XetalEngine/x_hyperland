import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import backend
import runtime
import presets
from test_theme import ThemeTransactionTests


class PresetTests(unittest.TestCase):
    def setUp(self):
        ThemeTransactionTests.setUp(self)
        runtime.STATE.write_text(json.dumps({'design':'binaryknife','mode':'dark','avatar':'auto','layout':'classic'}))
        for name in ('file_jobs','switcher','terminal_fetch','effects/burn','effects/cube','control_center'):(self.root/name).mkdir(parents=True,exist_ok=True)
        (self.root/'file_jobs/preferences.json').write_bytes(presets.encode(presets.transfer.DEFAULTS))
        (self.root/'switcher/preferences.json').write_bytes(presets.encode(presets.switcher.DEFAULTS))
        (self.root/'terminal_fetch/settings.json').write_bytes(presets.encode(presets.terminal.DEFAULTS))
        (self.root/'control_center/appearance.conf').write_text('decoration:rounding = 17\n')
        self.store.load.return_value=('decoration:rounding = 17\nanimations:enabled = true\n','token')
        self.store.save.side_effect=None
    def tearDown(self):ThemeTransactionTests.tearDown(self)
    def test_layout_only_keeps_palette_files_and_component_preferences(self):
        target=presets.builtin('modern','light',self.root);target['theme']['layout']='sidebar'
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p!=runtime.STATE}
        with patch.object(backend.Path,'iterdir',return_value=iter(())):
            backend.apply_components(target,{'layout'},backend.theme_token())
        self.assertEqual(runtime.layout(),'sidebar');self.assertEqual(runtime.design(),'binaryknife');self.assertEqual(runtime.mode(),'dark')
        for path,data in before.items():
            self.assertEqual(path.read_bytes(),data,path)
        self.store.save.assert_not_called();self.reload.assert_not_called()

    def test_all_builtin_presets_default_dark_and_preserve_explicit_mode(self):
        for design in runtime.DESIGNS:
            self.assertEqual(presets.builtin(design,root=self.root)['theme']['mode'],'dark')
            self.assertEqual(presets.builtin(design,'light',self.root)['theme']['mode'],'light')

    def test_waybar_only_changes_bar_design_and_preserves_desktop_palette(self):
        config=self.root/'waybar/config.json'
        config.write_text(json.dumps({'modules-left':['custom/launcher','hyprland/workspaces'],
            'modules-right':['clock','tray'],'clock':{'format':'{:%H:%M}'}}))
        colors=(self.root/'theme/current.colors').read_bytes()
        target=presets.builtin('hollowgrove','light',self.root)
        with patch.object(presets.bar_styles,'reload_session') as reload_bar:
            backend.apply_components(target,{'waybar'},backend.theme_token())
        self.assertEqual(runtime.design(),'binaryknife');self.assertEqual(runtime.mode(),'dark')
        self.assertEqual(json.loads(runtime.STATE.read_text())['bar_style'],'hollowgrove')
        self.assertEqual((self.root/'theme/current.colors').read_bytes(),colors)
        self.assertEqual(json.loads(config.read_text())['clock'],{'format':'{:%H:%M}'})
        self.assertIn('Independent Waybar design: hollowgrove',(self.root/'waybar/style.css').read_text())
        self.store.save.assert_not_called();reload_bar.assert_called_once_with(self.root)

    def test_color_only_pins_previously_followed_bar(self):
        previous={'design':'binaryknife','bar_style':'follow'}
        target=presets.builtin('hollowgrove',root=self.root)
        self.assertEqual(presets.merged_theme(previous,target,{'colors'})['bar_style'],'binaryknife')

    def test_dock_component_uses_each_theme_and_preserves_minimizer_controls(self):
        path=self.root/'effects/minimize/settings.conf';path.parent.mkdir(parents=True)
        original=dict(presets.minimize.DEFAULTS,presentation='stack',hide_delay=5300,dock_edge='right')
        path.write_text(presets.minimize.encode(original))
        colors=(self.root/'theme/current.colors').read_bytes()
        for design in runtime.DESIGNS:
            target=presets.builtin(design,root=self.root)
            files,reloads=presets.resources(self.root,target,{'dock'},'binaryknife')
            self.assertEqual(set(files),{path})
            self.assertEqual(presets.minimize.decode(files[path].decode()),dict(original,dock_style=design))
            self.assertIn(('Xetal Minimize','xetalminimize:reload'),reloads)
        with patch.object(backend.effect_colors,'reload_active') as reload_effect,patch.object(backend.Path,'iterdir',return_value=iter(())):
            backend.apply_components(presets.builtin('candycloud',root=self.root),{'dock'},backend.theme_token())
        self.assertEqual(presets.minimize.load(path)[0],dict(original,dock_style='candycloud'))
        self.assertEqual((self.root/'theme/current.colors').read_bytes(),colors)
        self.store.save.assert_not_called();reload_effect.assert_called_once()

    def test_custom_effects_and_dock_can_be_applied_independently(self):
        path=self.root/'effects/minimize/settings.conf';path.parent.mkdir(parents=True)
        original=dict(presets.minimize.DEFAULTS,dock_style='hollowgrove')
        path.write_text(presets.minimize.encode(original))
        target=presets.current(self.root);target['minimize'].update(dock_style='modern',size=130)
        files,_=presets.resources(self.root,target,{'effects'},'binaryknife')
        self.assertEqual(presets.minimize.decode(files[path].decode()),dict(original,size=130))
        files,_=presets.resources(self.root,target,{'dock'},'binaryknife')
        self.assertEqual(presets.minimize.decode(files[path].decode()),dict(original,dock_style='modern'))
        files,_=presets.resources(self.root,target,{'effects','dock'},'binaryknife')
        self.assertEqual(presets.minimize.decode(files[path].decode()),target['minimize'])

    def test_colors_only_pins_the_followed_dock_without_changing_its_controls(self):
        path=self.root/'effects/minimize/settings.conf';path.parent.mkdir(parents=True)
        original=dict(presets.minimize.DEFAULTS,hide_delay=3500,dock_edge='top')
        path.write_text(presets.minimize.encode(original));target=presets.builtin('hollowgrove',root=self.root)
        files,reloads=presets.resources(self.root,target,{'colors'},'binaryknife')
        self.assertEqual(presets.minimize.decode(files[path].decode()),dict(original,dock_style='binaryknife'))
        self.assertIn(('Xetal Minimize','xetalminimize:reload'),reloads)
        files,_=presets.resources(self.root,target,{'colors','dock'},'binaryknife')
        self.assertEqual(presets.minimize.decode(files[path].decode()),dict(original,dock_style='hollowgrove'))

    def test_wobbly_snapshot_and_skin_switch_preserve_physics(self):
        path=self.root/'effects/wobbly/settings.json';path.parent.mkdir(parents=True)
        values=dict(presets.wobbly.DEFAULTS,enabled=True,friction=5,snap_inverted=True)
        path.write_text(presets.wobbly.encode(values));before=path.read_bytes()
        target=presets.builtin('modern',root=self.root);self.assertNotIn('wobbly',target)
        self.assertNotIn(path,presets.resources(self.root,target,{'effects'},'raw')[0])
        snapshot=presets.current(self.root);self.assertEqual(snapshot['wobbly'],values)
        files,reloads=presets.resources(self.root,snapshot,{'effects'},'raw')
        self.assertEqual(json.loads(files[path]),values)
        self.assertIn(('Xetal Wobbly Windows','xetalwobbly:reload'),reloads)
        self.assertEqual(path.read_bytes(),before)
    def test_colors_do_not_replace_layout_wallpapers_effects_or_followed_menu(self):
        target=presets.builtin('modern','light',self.root)
        with patch.object(backend.Path,'iterdir',return_value=iter(())),patch.object(backend,'set_wallpaper') as wallpaper,patch.object(backend.effect_colors,'plan') as effects:
            backend.apply_components(target,{'colors'},backend.theme_token())
        self.assertEqual(runtime.layout(),'classic');self.assertEqual(runtime.launcher_design(),'binaryknife')
        self.assertEqual(runtime.design(),'modern');self.assertEqual(runtime.mode(),'light')
        self.assertEqual(json.loads((self.root/'file_jobs/preferences.json').read_text())['style'],'binaryknife')
        self.assertIn('decoration:rounding = 17',self.store.save.call_args.args[0]);wallpaper.assert_not_called();effects.assert_not_called()
    def test_custom_round_trip_and_failed_apply_restore_all_files(self):
        (self.root/'icon_themes').mkdir()
        (self.root/'icon_themes/packs').symlink_to(Path(__file__).resolve().parents[1]/'icon_themes/packs',target_is_directory=True)
        original=presets.current(self.root);original['theme']['layout']='modern';original['transfer']['animation']['speed']=160
        path=self.root/'custom.json';item=presets.save('Blue workshop',original,path=path)
        saved=presets.library(path)['presets'][0];self.assertEqual(saved['config'],original)
        with self.assertRaisesRegex(ValueError,'already'):presets.save('blue WORKSHOP',original,path=path)
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p.suffix!='.lock'}
        self.store.save.side_effect=ValueError('reload failed')
        with patch.object(backend.effect_colors,'plan',return_value=({},[])),patch.object(backend.effect_colors,'reload_active'),self.assertRaisesRegex(ValueError,'reload failed'):
            backend.apply_components(saved['config'],set(presets.COMPONENTS)-{'wallpaper'},backend.theme_token())
        for p,data in before.items():self.assertEqual(p.read_bytes(),data,p)
        self.store.save.side_effect=None
        with patch.object(backend.Path,'iterdir',return_value=iter(())),patch.object(backend.effect_colors,'plan',return_value=({},[])),patch.object(backend.effect_colors,'reload_active'):
            backend.apply_components(saved['config'],{'layout','transfer','terminal'},backend.theme_token())
        self.assertEqual(runtime.layout(),'modern');self.assertEqual(presets.transfer.load(self.root/'file_jobs/preferences.json')[0]['animation']['speed'],160)
        presets.remove(item['id'],path);self.assertEqual(presets.library(path)['presets'],[])
    def test_changed_component_token_stops_apply(self):
        target=presets.builtin('modern','dark',self.root);token=backend.theme_token()
        (self.root/'switcher/preferences.json').write_text('{}')
        before=runtime.STATE.read_bytes()
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):backend.apply_components(target,{'layout'},token)
        self.assertEqual(runtime.STATE.read_bytes(),before)
    def test_preset_cannot_inject_compositor_commands_or_paths(self):
        target=presets.current(self.root)
        for text in ('exec = touch /tmp/not-allowed','source = other.conf','decoration:rounding = 12; exec = nope'):
            with self.assertRaises(ValueError):presets.validate({**target,'appearance':text})
        with self.assertRaises(ValueError):presets.validate({**target,'wallpapers':{'bad\nexec':{'path':'x','fit':'cover'}}})
        with self.assertRaises(ValueError):presets.save('\n',target,path=self.root/'bad.json')

    def test_minimize_color_follow_and_rollback_without_replacing_preferences(self):
        path=self.root/'effects/minimize/settings.conf';path.parent.mkdir(parents=True)
        values=dict(presets.minimize.DEFAULTS,effect='fireball',shape='claw',color='#65dd44',size=110,
                    dock_style='hollowgrove',hide_delay=2000)
        path.write_text(presets.minimize.encode(values));before=path.read_bytes()
        target=presets.builtin('modern','light',self.root)
        self.assertNotIn('minimize',target)
        seen=[]
        palette=self.root/'theme/current.colors';old_palette=palette.read_bytes()
        def ctl(*args):
            if args==('-j','plugin','list'):return '[{"name":"Xetal Minimize"}]'
            if args==('dispatch','xetalminimize:reload'):
                seen.append(palette.read_bytes());return 'ok'
            return ''
        self.store.save.side_effect=ValueError('reload failed')
        with patch.object(backend.settings,'ctl',side_effect=ctl),self.assertRaisesRegex(ValueError,'reload failed'):
            backend.apply_components(target,{'colors'},backend.theme_token())
        self.assertEqual(len(seen),2);self.assertNotEqual(seen[0],old_palette);self.assertEqual(seen[1],old_palette)
        self.assertEqual(path.read_bytes(),before)
        self.store.save.side_effect=None;seen.clear()
        with patch.object(backend.settings,'ctl',side_effect=ctl),patch.object(backend.Path,'iterdir',return_value=iter(())):
            backend.apply_components(target,{'colors'},backend.theme_token())
        self.assertEqual(len(seen),1);self.assertEqual(path.read_bytes(),before)
        snapshot=presets.current(self.root);self.assertEqual(snapshot['minimize'],values)
        files,reloads=presets.resources(self.root,snapshot,{'effects'},'modern')
        self.assertEqual(files[path],before);self.assertIn(('Xetal Minimize','xetalminimize:reload'),reloads)
        self.assertNotIn(path,presets.resources(self.root,snapshot,{'layout'},'modern')[0])


if __name__=='__main__':unittest.main()
