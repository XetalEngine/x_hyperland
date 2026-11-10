import copy
import json
from pathlib import Path
import unittest

import bar_styles
import designs
import runtime


class BarStylesTests(unittest.TestCase):
    def test_designs_rearrange_modules_without_losing_user_actions(self):
        original=json.loads((Path(__file__).resolve().parents[1]/'waybar/config.json').read_text())
        original['modules-right'].append('custom/my-widget')
        original['custom/my-widget']={'exec':'my-widget','on-click':'my-action'}
        before=copy.deepcopy(original)
        expected=set(sum([original['modules-'+z] for z in ('left','center','right')],[]))
        for design in designs.DESIGNS:
            result=bar_styles.configure(original,design)
            modules=sum([result['modules-'+z] for z in ('left','center','right')],[])
            self.assertEqual(set(modules),expected,design)
            self.assertEqual(len(modules),len(expected),design)
            for key,value in original.items():
                if isinstance(value,dict):self.assertEqual(result[key],value,(design,key))
        self.assertEqual(original,before)

    def test_all_variations_keep_actions_and_place_workspaces_as_selected(self):
        original=json.loads((Path(__file__).resolve().parents[1]/'waybar/config.json').read_text())
        original['hyprland/workspaces']['on-click-right']='keep-my-workspace-overrides'
        original['modules-right'].append('custom/personal');original['custom/personal']={'exec':'personal-widget'}
        expected=set(sum([original['modules-'+z] for z in ('left','center','right')],[]))
        for design in designs.DESIGNS:
            for variation in bar_styles.VARIANTS:
                with self.subTest(design=design,variation=variation):
                    result=bar_styles.configure([original],design,variation)[0]
                    modules=sum([result['modules-'+z] for z in ('left','center','right')],[])
                    self.assertEqual(set(modules),expected);self.assertEqual(len(modules),len(expected))
                    zone='center' if variation=='centered' else 'left'
                    self.assertIn('hyprland/workspaces',result['modules-'+zone])
                    self.assertIn('cffi/new-workspace',result['modules-'+zone])
                    left=result['modules-left'];keys=left.index('custom/keys')
                    self.assertEqual(left[keys+1:keys+3],['cffi/workspace-mode','custom/updates'])
                    for key,value in original.items():
                        if isinstance(value,dict):self.assertEqual(result[key],value)

    def test_every_bar_parses_with_every_palette(self):
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk
        source=(runtime.ROOT/'waybar-dark.css').read_text()
        for palette in designs.DESIGNS:
            for mode in runtime.MODES:
                colors=runtime.colors(mode,palette)
                for design in designs.DESIGNS:
                    css=runtime.stylesheet(source,mode,palette,qt=False)
                    if design!='raw':css+=designs.waybar_style(colors,design)
                    for variation in bar_styles.VARIANTS:
                        full=css+bar_styles.stylesheet(colors,design,variation=variation)
                        with self.subTest(design=design,palette=palette,mode=mode,variation=variation):
                            provider=Gtk.CssProvider();provider.load_from_data(full.encode())

    def test_older_native_temperature_and_lan_modules_keep_their_group(self):
        config={'modules-left':['custom/launcher'],'modules-center':[],
                'modules-right':['cpu','temperature','network#lan','clock','custom/power']}
        forge=bar_styles.configure(config,'obsidianforge')
        self.assertEqual(forge['modules-center'],['cpu','temperature'])
        self.assertEqual(forge['modules-right'],['network#lan','clock','custom/power'])


if __name__=='__main__':unittest.main()
