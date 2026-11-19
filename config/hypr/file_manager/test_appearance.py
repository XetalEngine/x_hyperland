import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('files_appearance', ROOT/'appearance.py')
appearance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appearance)

class AppearanceTests(unittest.TestCase):
    def test_pinned_theme_keeps_its_palette_and_icons_without_writing_desktop_preferences(self):
        runtime = appearance.runtime
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'theme').mkdir()
            shutil.copy2(runtime.ROOT/'palettes.json',root/'theme/palettes.json')
            (root/'icon_themes').mkdir()
            (root/'icon_themes/packs').symlink_to(runtime.ROOT.parent/'icon_themes/packs',target_is_directory=True)
            state = root/'theme/state.json'
            icons = root/'theme/icons.json'
            icons.write_text(json.dumps({'version':1,'system':'builtin:killerinstinct','other':'auto','overrides':{}}))
            saved_icons = icons.read_bytes()
            with patch.object(runtime,'ROOT',root/'theme'),patch.object(runtime,'STATE',state):
                for desktop,mode in (('killerinstinct','dark'),('kifireice','light'),('raw','contrast')):
                    state.write_text(json.dumps({'design':desktop,'mode':mode,'layout':'classic'}))
                    saved_state = state.read_bytes()
                    result = appearance.appearance('kitemple')
                    self.assertEqual(result['colors'],runtime.colors(mode,'kitemple'))
                    self.assertEqual(result['design'],'kitemple')
                    self.assertEqual(result['theme'],'kitemple')
                    system_icon = root/'icon_themes/.build/icons'/result['iconTheme']/'scalable/folder.svg'
                    self.assertEqual(system_icon.read_bytes(),(root/'icon_themes/packs/Xetal-System-kitemple/scalable/folder.svg').read_bytes())
                    self.assertEqual(state.read_bytes(),saved_state)
                    self.assertEqual(icons.read_bytes(),saved_icons)
                    followed = appearance.appearance('follow')
                    self.assertEqual(followed['colors'],runtime.colors(mode,desktop))
                    self.assertEqual(appearance.appearance('removed-theme')['theme'],'follow')

    def test_gallery_sidebar_default_preserves_explicit_layout_choices(self):
        runtime = appearance.runtime
        for design in runtime.DESIGNS:
            for saved in (None,'follow','invalid','classic','modern','ribbon','sidebar'):
                with self.subTest(design=design,saved=saved),patch.object(runtime,'state',return_value={'design':design,'layout':saved}):
                    self.assertEqual(runtime.layout(),saved if saved in runtime.layouts.LAYOUTS else 'sidebar')

    def test_marker_is_off_by_default_and_independent_of_every_theme(self):
        runtime=appearance.runtime
        for design in runtime.DESIGNS:
            for marker in ('none','line','curve'):
                with self.subTest(design=design,marker=marker),patch.object(runtime,'state',return_value={'design':design,'mode':'dark','selection_marker':marker}):
                    style=appearance.appearance()['stylesheet']
                    self.assertTrue(style.endswith(appearance.selection_marker.stylesheet(runtime.colors(),marker)))
            with patch.object(runtime,'state',return_value={'design':design,'mode':'dark'}):
                self.assertEqual(runtime.selection_marker(),'none')
                self.assertIn('item:selected {border-left:0px solid transparent;}',appearance.appearance()['stylesheet'])
    def test_every_desktop_design_and_palette_supplies_native_colors(self):
        runtime = appearance.runtime
        for design in runtime.DESIGNS:
            for mode in runtime.MODES:
                with self.subTest(design=design, mode=mode), patch.object(runtime, 'state', return_value={'design':design, 'mode':mode}), patch.object(runtime, 'mode', return_value=mode):
                    result = appearance.appearance()
                    self.assertEqual(result['colors'], runtime.colors())
                    self.assertIn(result['colors']['Window'], result['stylesheet'])
                    self.assertIn(result['colors']['Highlight'], result['stylesheet'])
                    self.assertIn('QTreeWidget#places', result['stylesheet'])
                    self.assertEqual(result['iconTheme'],runtime.icon_library.info(runtime.ROOT.parent,runtime.design(),mode)['iconTheme'])
                    self.assertIn(str(runtime.ROOT.parent/'icon_themes/packs'),result['iconSearchPaths'])
                    self.assertTrue(result['background'].startswith('qlineargradient('))

if __name__ == '__main__':
    unittest.main()
