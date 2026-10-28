import copy
import json
import os
import signal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from PIL import Image
import backend
import runtime
import build


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'images').mkdir()
        self.old=self.root/'old.png';self.new=self.root/'new.png'
        Image.new('RGB',(100,100),'navy').save(self.old);Image.new('RGB',(100,100),'teal').save(self.new)
        self.state={name:{'path':str(self.old),'original':str(self.old),'fit':'cover'} for name in ['DP-1','DP-2']}
        (self.root/'selection.json').write_text(json.dumps(self.state));(self.root/'hyprpaper.conf').write_text('previous configuration\n')
        self.patches=[patch.object(backend,'WALLPAPER',self.root),patch.object(backend.settings,'STATE',self.root/'state'),
                      patch.object(backend.settings,'monitors',return_value=[{'name':n} for n in self.state]),
                      patch.object(backend.settings,'ctl',return_value='')]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in self.patches:item.stop()
        self.temp.cleanup()
    def test_individual_display_does_not_change_other_wallpaper(self):
        with patch.object(backend,'set_wallpaper') as apply:
            state=backend.apply_wallpapers({'DP-1':{'path':str(self.new),'fit':'contain'}},self.state)
        self.assertEqual(state['DP-2'],self.state['DP-2']);self.assertEqual(state['DP-1']['fit'],'contain');self.assertEqual(apply.call_count,1)
        self.assertIn(str(self.root/'images'),state['DP-1']['path'])
    def test_partial_failure_rolls_back_outputs_and_files(self):
        before={p:p.read_bytes() for p in [self.root/'selection.json',self.root/'hyprpaper.conf']}
        with patch.object(backend,'set_wallpaper',side_effect=[None,ValueError('renderer failure'),None,None]) as apply:
            with self.assertRaises(ValueError):backend.apply_wallpapers({n:{'path':str(self.new),'fit':'cover'} for n in self.state},self.state)
        self.assertEqual(apply.call_args_list[-1].args,('DP-1',self.state['DP-1']))
        for p,data in before.items():self.assertEqual(p.read_bytes(),data)
    def test_external_change_and_disconnection_stop_before_apply(self):
        with patch.object(backend,'set_wallpaper') as apply:
            with self.assertRaisesRegex(ValueError,'changed outside'):backend.apply_wallpapers({}, {})
            with self.assertRaisesRegex(ValueError,'disconnected'):backend.apply_wallpapers({'DP-3':{'path':str(self.new),'fit':'cover'}},self.state)
            apply.assert_not_called()
    def test_corrupt_preferences_are_not_replaced(self):
        (self.root/'selection.json').write_text('broken')
        with self.assertRaises(ValueError):backend.apply_wallpapers({},self.state)
        self.assertEqual((self.root/'selection.json').read_text(),'broken')


class PaletteTests(unittest.TestCase):
    def test_folder_handler_paths_are_session_local_and_keep_existing_settings_locations(self):
        base={'XDG_CURRENT_DESKTOP':'KDE','XDG_CONFIG_HOME':'/keep/config','XDG_DATA_HOME':'/keep/data',
              'XDG_CONFIG_DIRS':'/custom/config:/etc/xdg','XDG_DATA_DIRS':'/flatpak/share:/usr/share'}
        self.assertEqual(runtime.environment(base),base)
        inside={**base,'HYPRLAND_INSTANCE_SIGNATURE':'test','XDG_CURRENT_DESKTOP':'Hyprland'}
        result=runtime.environment(inside)
        self.assertEqual(result['XDG_CONFIG_HOME'],base['XDG_CONFIG_HOME'])
        self.assertEqual(result['XDG_DATA_HOME'],base['XDG_DATA_HOME'])
        self.assertTrue(result['XDG_CONFIG_DIRS'].endswith(base['XDG_CONFIG_DIRS']))
        self.assertTrue(result['XDG_DATA_DIRS'].endswith(base['XDG_DATA_DIRS']))
        self.assertEqual(runtime.environment(result),result)

    def test_all_standard_and_disabled_text_contrast(self):
        def luminance(color):
            rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
            return sum(c*w for c,w in zip(linear,[.2126,.7152,.0722]))
        for design in runtime.DESIGNS:
            for mode in runtime.MODES:
                p=runtime.colors(mode,design)
                for fg,bg in [('Text','Base'),('WindowText','Window'),('ButtonText','Button'),('HighlightedText','Highlight'),('PlaceholderText','Window')]:
                    a,b=sorted([luminance(p[fg]),luminance(p[bg])]);self.assertGreaterEqual((b+.05)/(a+.05),4.5,(design,mode,fg,bg))

    def test_legacy_design_and_raw_styles_remain_unchanged(self):
        with patch.object(runtime,'state',return_value={'mode':'dark'}):self.assertEqual(runtime.design(),'raw')
        with patch.object(runtime,'state',return_value={'design':'unknown'}):self.assertEqual(runtime.design(),'raw')
        source='QWidget {background:#171b22; color:#ffffff;}'
        self.assertEqual(runtime.stylesheet(source,'dark','raw'),source)
        self.assertIn('QPushButton#railButton',runtime.stylesheet(source,'dark','modern'))
        gtk=runtime.stylesheet('window {background:#171b22;}','dark','modern',qt=False)
        self.assertNotIn('QPushButton',gtk)
        self.assertIn(runtime.colors('dark','modern')['Window'],gtk)
    def test_environment_is_confined_to_hyprland(self):
        self.assertEqual(runtime.environment({'DESKTOP_SESSION':'plasma'}),{'DESKTOP_SESSION':'plasma'})
        env=runtime.environment({'HYPRLAND_INSTANCE_SIGNATURE':'unit-test'},'light')
        self.assertEqual(env['QT_QPA_PLATFORMTHEME'],'xetal');self.assertEqual(env['GTK_THEME'],'Adwaita');self.assertNotIn('XDG_CONFIG_HOME',env)


class KittyReloadTests(unittest.TestCase):
    def test_reload_excludes_startup_shared_and_other_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            proc=Path(directory)
            fixtures=[(101,backend.ROOT/'kitty.conf','current'),
                      (102,backend.ROOT/'startup/kitty.conf','current'),
                      (103,Path.home()/'.config/kitty/kitty.conf','current'),
                      (104,backend.ROOT/'kitty.conf','another-session'),
                      (105,backend.ROOT/'kitty.conf','')]
            for pid,profile,session in fixtures:
                p=proc/str(pid);p.mkdir();(p/'comm').write_text('kitty\n')
                (p/'cmdline').write_bytes(b'kitty\0--config\0'+os.fsencode(profile)+b'\0')
                (p/'environ').write_bytes(b'HYPRLAND_INSTANCE_SIGNATURE='+session.encode()+b'\0')
            with patch.dict(os.environ,{'HYPRLAND_INSTANCE_SIGNATURE':'current'}),patch.object(backend.os,'kill') as kill:
                self.assertEqual(backend.reload_kitty(proc),[101]);kill.assert_called_once_with(101,signal.SIGUSR1)


class ThemeTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);theme=self.root/'theme'
        for folder in ('theme','dolphin/config','waybar','swaync'): (self.root/folder).mkdir(parents=True,exist_ok=True)
        (theme/'palettes.json').write_bytes((runtime.ROOT/'palettes.json').read_bytes())
        (theme/'state.json').write_text('{"mode":"dark"}\n')
        (theme/'current.colors').write_text('original colors\n');(theme/'waybar-dark.css').write_text('window { background: #171b22; }\n')
        (theme/'kitty-colors.conf').write_text('background #123456\n')
        (self.root/'dolphin/config/kdeglobals').write_text('[General]\nColorScheme=Original\n')
        (self.root/'waybar/style.css').write_text('original bar\n');(self.root/'swaync/style.css').write_text('original notifications\n')
        self.files={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.store=Mock();self.store.load.return_value=('old config','token');self.store.save.side_effect=ValueError('compositor reload failed')
        self.patches=[patch.object(runtime,'ROOT',theme),patch.object(runtime,'STATE',theme/'state.json'),patch.object(backend,'ROOT',self.root),
                      patch.object(backend.settings,'STATE',self.root/'state'),patch.object(backend.settings,'Store',return_value=self.store),patch.object(build,'build')]
        self.reload=Mock();self.patches.append(patch.object(backend,'reload_kitty',self.reload))
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()
    def test_reload_failure_restores_every_theme_file(self):
        with self.assertRaisesRegex(ValueError,'reload failed'):backend.apply_mode('light',backend.theme_token())
        for path,original in self.files.items():self.assertEqual(path.read_bytes(),original)
        self.reload.assert_not_called()
    def test_external_theme_edit_is_rejected_before_writes(self):
        token=backend.theme_token();runtime.STATE.write_text('{"mode":"contrast"}\n')
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):backend.apply_mode('light',token)
        self.store.save.assert_not_called()
        for path,original in self.files.items():
            if path!=runtime.STATE:self.assertEqual(path.read_bytes(),original)

    def test_success_updates_terminal_palette_before_reload(self):
        self.store.save.side_effect=None
        with patch.object(backend.Path,'iterdir',return_value=iter(())):
            backend.apply_mode('light',backend.theme_token())
        self.assertIn('background #ffffff\n',(runtime.ROOT/'kitty-colors.conf').read_text())
        self.reload.assert_called_once_with(include_startup=True)

    def add_raw_profiles(self):
        (self.root/'startup').mkdir()
        for target,template in [('hyprlock.conf','hyprlock-raw.conf'),('startup/kitty.conf','startup-raw.conf')]:
            (self.root/target).write_text('personal raw '+target+'\n')
            (runtime.ROOT/template).write_text('packaged raw '+target+'\n')
        (self.root/'keybindings.conf').write_text('unchanged hotkeys\n')
        (self.root/'favorites.json').write_text('unchanged favorites\n')
        self.files={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_both_designs_round_trip_without_touching_personal_settings(self):
        self.add_raw_profiles();self.store.save.side_effect=None
        with patch.object(backend.Path,'iterdir',return_value=iter(())):
            backend.apply_mode('dark',backend.theme_token(),'modern')
            self.assertEqual(runtime.design(),'modern')
            self.assertIn('Xetal Modern',(self.root/'hyprlock.conf').read_text())
            self.assertIn('rounding = 18',self.store.save.call_args.args[0])
            backend.apply_mode('dark',backend.theme_token(),'raw')
        for name in ('hyprlock.conf','startup/kitty.conf','keybindings.conf','favorites.json'):
            self.assertEqual((self.root/name).read_bytes(),self.files[self.root/name])
        self.assertNotIn('rounding',self.store.save.call_args.args[0])
        self.assertEqual(runtime.design(),'raw')

    def test_failed_design_change_restores_raw_backups_too(self):
        self.add_raw_profiles()
        with self.assertRaisesRegex(ValueError,'reload failed'):backend.apply_mode('dark',backend.theme_token(),'modern')
        for path,original in self.files.items():self.assertEqual(path.read_bytes(),original,path)

    def test_external_lock_edit_stops_theme_change(self):
        self.add_raw_profiles();token=backend.theme_token()
        (self.root/'hyprlock.conf').write_text('user edited lock\n')
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):backend.apply_mode('dark',token,'modern')
        self.store.save.assert_not_called()
        self.assertEqual((self.root/'hyprlock.conf').read_text(),'user edited lock\n')


if __name__=='__main__':unittest.main()
