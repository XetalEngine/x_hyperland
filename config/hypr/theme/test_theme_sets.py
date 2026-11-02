"""Theme switches preserve monitor artwork, customized effect colors and rollback."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from PIL import Image

import backend
import runtime
import wallpaper_sets
import effect_colors
import test_theme
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from effects.burn import model as burn
from effects.cube import model as cube


class ThemeSetTests(unittest.TestCase):
    def setUp(self):
        test_theme.ThemeTransactionTests.setUp(self)
        root=self.root/'wallpaper';root.mkdir()
        catalog={design:[f'{design}/{i}.png' for i in range(3)] for design in runtime.DESIGNS}
        (root/'sets.json').write_text(json.dumps(catalog))
        for design,names in catalog.items():
            for name in names:
                path=root/name;path.parent.mkdir(exist_ok=True)
                Image.new('RGB',(16,9),'navy' if design=='binaryknife' else 'maroon').save(path)
        self.monitors=[{'name':'DP-3','x':3840,'mirrorOf':'none'},
                       {'name':'DP-1','x':0,'mirrorOf':'none'},
                       {'name':'DP-2','x':1920,'mirrorOf':'none'}]
        self.original=wallpaper_sets.bundled(root,'breakpoint',self.monitors)
        (root/'selection.json').write_bytes(wallpaper_sets.encode(self.original))
        (root/'hyprpaper.conf').write_text(backend.wallpaper_config(self.original))
        runtime.STATE.write_text(json.dumps({'design':'breakpoint','mode':'dark'}))
        self.fire={**burn.DEFAULTS,'enabled':False,'duration':475,'fire_color':[50000,15000,8000,65535]}
        self.cube={**copy.deepcopy(cube.DEFAULTS),'enabled':False,'zoom':.72,'window_depth':.48}
        for relative,value in [('effects/burn/settings.conf',burn.encode(self.fire)),('effects/cube/settings.json',cube.encode(self.cube))]:
            path=self.root/relative;path.parent.mkdir(parents=True);path.write_text(value)
        self.store.save.side_effect=None
        self.addCleanup(test_theme.ThemeTransactionTests.tearDown,self)
        for item in [patch.object(backend.settings,'monitors',return_value=self.monitors),
                     patch.object(backend.settings,'ctl',side_effect=lambda *args:'[]' if args==('-j','plugin','list') else ''),
                     patch.object(backend.Path,'iterdir',return_value=iter(()))]:
            item.start();self.addCleanup(item.stop)

    def apply(self,design):
        return backend.apply_mode('dark',backend.theme_token(),design)

    def test_binaryknife_assigns_three_displays_in_physical_order(self):
        self.apply('binaryknife')
        selection=json.loads((self.root/'wallpaper/selection.json').read_text())
        self.assertEqual([Path(selection[f'DP-{i}']['path']).name for i in (1,2,3)],['0.png','1.png','2.png'])
        self.assertTrue(all('/binaryknife/' in entry['path'] for entry in selection.values()))
        fire,_=burn.load(self.root/'effects/burn/settings.conf')
        self.assertEqual(fire['fire_color'],[14649,43433,65535,65535])
        self.assertEqual(fire['duration'],475);self.assertFalse(fire['enabled'])
        current,_=cube.load(self.root/'effects/cube/settings.json')
        self.assertEqual(current['zoom'],.72);self.assertEqual(current['window_depth'],.48)
        self.assertEqual(current['edge_color'],effect_colors.rgba('#39a9ff'))

    def test_disabled_and_mirrored_outputs_do_not_consume_artwork(self):
        monitors=self.monitors+[
            {'name':'OFF','x':-3840,'disabled':True},
            {'name':'MIRROR','x':-1920,'mirrorOf':'DP-1'},
            {'name':'OLD-MIRROR','x':-1920,'mirrorOf':0},
        ]
        assigned=wallpaper_sets.bundled(self.root/'wallpaper','binaryknife',monitors)
        self.assertEqual(list(assigned),['DP-1','DP-2','DP-3'])

    def test_each_theme_restores_its_own_three_screen_set(self):
        for design in (*runtime.DESIGNS,'raw'):
            self.apply(design)
            selection=json.loads((self.root/'wallpaper/selection.json').read_text())
            self.assertEqual({item['path'] for item in selection.values()},
                             {str(self.root/'wallpaper'/design/f'{i}.png') for i in range(3)})

    def test_refreshed_bundle_takes_precedence_over_stale_import_cache(self):
        root=self.root/'wallpaper'
        cached=self.root/'old-cache.png';Image.new('RGB',(16,9),'red').save(cached)
        saved=copy.deepcopy(self.original)
        saved['DP-1']['path']=str(cached)
        (root/'profiles.json').write_bytes(wallpaper_sets.encode({'version':1,'themes':{'breakpoint':saved}}))
        target,_=wallpaper_sets.switching(root,'raw','breakpoint',{},self.monitors)
        self.assertEqual(target['DP-1'],self.original['DP-1'])

    def test_custom_wallpaper_still_prefers_its_cache(self):
        root=self.root/'wallpaper'
        cached=self.root/'custom-cache.png';Image.new('RGB',(16,9),'blue').save(cached)
        original=self.root/'personal.png';Image.new('RGB',(16,9),'red').save(original)
        choice={'path':str(cached),'original':str(original),'fit':'contain'}
        (root/'profiles.json').write_bytes(wallpaper_sets.encode({'version':1,'themes':{'modern':{'DP-1':choice}}}))
        target,_=wallpaper_sets.switching(root,'raw','modern',{},self.monitors)
        self.assertEqual(target['DP-1'],choice)

    def test_round_trip_restores_custom_wallpapers_and_effect_colors(self):
        self.apply('binaryknife')
        custom=self.root/'custom.png';Image.new('RGB',(16,9),'blue').save(custom)
        selection=json.loads((self.root/'wallpaper/selection.json').read_text())
        with patch.object(backend,'WALLPAPER',self.root/'wallpaper'),patch.object(backend,'set_wallpaper'):
            selection=backend.apply_wallpapers({'DP-2':{'path':str(custom),'fit':'contain'}},selection)
        fire,_=burn.load(self.root/'effects/burn/settings.conf');fire['fire_color']=[20000,40000,55000,65535]
        (self.root/'effects/burn/settings.conf').write_text(burn.encode(fire))
        self.apply('breakpoint')
        self.assertEqual(json.loads((self.root/'wallpaper/selection.json').read_text()),self.original)
        self.assertEqual(burn.load(self.root/'effects/burn/settings.conf')[0]['fire_color'],self.fire['fire_color'])
        self.apply('binaryknife')
        self.assertEqual(json.loads((self.root/'wallpaper/selection.json').read_text()),selection)
        self.assertEqual(burn.load(self.root/'effects/burn/settings.conf')[0]['fire_color'],fire['fire_color'])

    def test_failed_compositor_reload_restores_artwork_and_effect_files(self):
        self.store.save.side_effect=ValueError('compositor reload failed')
        watched=[runtime.STATE,self.root/'wallpaper/selection.json',self.root/'wallpaper/hyprpaper.conf',
                 self.root/'effects/burn/settings.conf',self.root/'effects/cube/settings.json']
        old={path:path.read_bytes() for path in watched}
        with patch.object(backend,'set_wallpaper') as setter:
            with self.assertRaisesRegex(ValueError,'reload failed'):self.apply('binaryknife')
        self.assertEqual(setter.call_count,6)
        for path,data in old.items():self.assertEqual(path.read_bytes(),data)
        self.assertFalse((self.root/'wallpaper/profiles.json').exists())
        self.assertFalse((self.root/'theme/effect-colors.json').exists())

    def test_partial_wallpaper_failure_restores_every_attempted_output(self):
        with patch.object(backend,'set_wallpaper',side_effect=[None,ValueError('wallpaper failure'),None,None]) as setter:
            with self.assertRaisesRegex(ValueError,'wallpaper failure'):self.apply('binaryknife')
        self.assertEqual(setter.call_count,4)
        self.assertEqual(runtime.design(),'breakpoint')
        self.assertEqual(json.loads((self.root/'wallpaper/selection.json').read_text()),self.original)
        self.store.save.assert_not_called()

    def test_effect_reload_failure_rolls_back_theme_before_compositor_save(self):
        def ctl(*args):
            if args==('-j','plugin','list'):return '[{"name":"Xetal Burn"}]'
            if args==('dispatch','xetalburn:reload'):return 'error: unavailable'
            return ''
        with patch.object(backend.settings,'ctl',side_effect=ctl),patch.object(backend,'set_wallpaper'):
            with self.assertRaisesRegex(ValueError,'could not reload'):self.apply('binaryknife')
        self.assertEqual(runtime.design(),'breakpoint')
        self.assertEqual(burn.load(self.root/'effects/burn/settings.conf')[0],burn.validate(self.fire))
        self.store.save.assert_not_called()

    def test_missing_bundle_does_not_change_theme(self):
        (self.root/'wallpaper/binaryknife/1.png').unlink()
        with self.assertRaisesRegex(ValueError,'wallpaper.*missing'):self.apply('binaryknife')
        self.assertEqual(runtime.design(),'breakpoint');self.store.save.assert_not_called()

    def test_corrupt_profiles_are_preserved(self):
        profile=self.root/'wallpaper/profiles.json';profile.write_text('{broken')
        with self.assertRaises(ValueError):self.apply('binaryknife')
        self.assertEqual(profile.read_text(),'{broken');self.store.save.assert_not_called()

    def test_new_monitor_uses_its_position_in_the_theme_set(self):
        self.apply('binaryknife');self.apply('breakpoint')
        self.monitors[1]['name']='HDMI-A-1'
        self.apply('binaryknife')
        selection=json.loads((self.root/'wallpaper/selection.json').read_text())
        self.assertTrue(selection['HDMI-A-1']['path'].endswith('binaryknife/0.png'))


if __name__=='__main__':unittest.main()
