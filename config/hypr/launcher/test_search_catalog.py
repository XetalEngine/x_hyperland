from pathlib import Path
import tempfile,unittest
from search_catalog import entries
from shortcuts import Entry
ROOT=Path(__file__).resolve().parents[1]


class SearchCatalogTests(unittest.TestCase):
    def test_each_destination_opens_the_corresponding_editor(self):
        catalog=entries(ROOT,Entry)
        self.assertEqual(catalog['fusion-control-panel:grub'].argv(),[str(ROOT/'scripts/control-panel.sh'),'--section','grub'])
        self.assertEqual(catalog['fusion-settings:power'].argv(),[str(ROOT/'scripts/control-center.sh'),'--tab','power'])
        self.assertEqual(catalog['fusion-control-panel:rdp-host'].argv(),[str(ROOT/'scripts/control-panel.sh'),'--section','rdp-host'])
        self.assertIn('vnc',catalog['fusion-control-panel:rdp-host'].get_keywords())
        self.assertNotIn('fusion-settings:remote-desktop',catalog)
        self.assertIn('whatsapp',catalog['fusion-settings:phone'].get_keywords())
        self.assertEqual(len([k for k in catalog if k.startswith('fusion-control-panel:')]),36)

    def test_missing_tool_catalog_keeps_settings_search_available(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=entries(Path(directory),Entry)
        self.assertIn('fusion-settings:displays',catalog)
