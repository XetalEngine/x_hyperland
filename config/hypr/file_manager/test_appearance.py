import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('files_appearance', ROOT/'appearance.py')
appearance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appearance)

class AppearanceTests(unittest.TestCase):
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

if __name__ == '__main__':
    unittest.main()
