import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('files_appearance', ROOT/'appearance.py')
appearance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appearance)

class AppearanceTests(unittest.TestCase):
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
                    self.assertEqual(result['iconTheme'], 'Papirus-Light' if mode=='light' else 'Papirus-Dark')

if __name__ == '__main__':
    unittest.main()
