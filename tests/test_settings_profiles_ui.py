"""Offscreen interaction with the actual settings page; no live configuration."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from settings_profiles import archive, backend, catalog
from settings_profiles.page import DefaultSettingsPage


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.enterContext(patch.object(backend, 'STATE', self.state))
        self.enterContext(patch.object(backend, 'factory_status', return_value={'desktop':True,'system':True,'detail':'Fixture defaults available.'}))
        self.pending = []
        self.page = DefaultSettingsPage(lambda fn,ok,fail:self.pending.append((fn,ok,fail)))
        self.page.inventory_started = True
        self.addCleanup(self.page.deleteLater)
        data = archive.encode({'enabled':True,'volume':35,'password':'private'})
        self.doc = archive.manifest(['audio'], [{'scope':'profile','path':'sounds/settings.json','category':'audio','kind':'file',
                                   'mode':0o600,'size':len(data),'sha256':archive.digest(data)}])
        self.blobs = {archive.digest(data):data}

    def test_three_tabs_and_select_all_on_both_flows(self):
        self.assertEqual([self.page.tabs.tabText(i) for i in range(3)],['Save System Settings','Load','Reset Defaults'])
        self.page.save_selection.select(False); self.assertEqual(self.page.save_selection.groups(),[])
        self.assertFalse(self.page.save_button.isEnabled())
        self.page.save_selection.select(True);self.assertEqual(set(self.page.save_selection.groups()),set(catalog.BY_ID))
        self.page.loaded=(self.doc,self.blobs);self.page.load_selection.available(['audio'])
        self.page.load_selection.select(False);self.assertFalse(self.page.load_button.isEnabled())
        self.page.load_selection.select(True);self.assertEqual(self.page.load_selection.groups(),['audio'])
        self.assertTrue(self.page.load_button.isEnabled())

    def test_expand_inventory_and_search_hidden_leaf_values(self):
        inventory=self.page.save_inventory;inventory.populate(self.doc,self.blobs)
        group=inventory.groups['audio'];file=group.child(0);inventory.expand(file)
        self.assertEqual(file.childCount(),3)
        values={file.child(i).text(0):file.child(i).text(1) for i in range(file.childCount())}
        self.assertEqual(values['volume'],'35');self.assertEqual(values['password'],'Included · hidden')
        inventory.filter('volume');self.assertFalse(group.isHidden())
        inventory.filter('private');self.assertTrue(group.isHidden())

    def test_unchecked_category_is_not_displayed_as_selected(self):
        self.page.save_inventory.populate(self.doc,self.blobs)
        self.page.save_selection.checks['audio'].setChecked(False)
        self.assertTrue(self.page.save_inventory.groups['audio'].isHidden())

    def test_background_operation_disables_duplicate_actions_and_keeps_error(self):
        self.page.work(lambda:None,lambda _:None,'Saving…')
        self.assertTrue(self.page.busy);self.assertFalse(self.page.tabs.isEnabled())
        self.page.work(lambda:None,lambda _:None,'Duplicate');self.assertEqual(len(self.pending),1)
        self.pending[0][2]('Fixture authentication cancelled')
        self.assertFalse(self.page.busy);self.assertTrue(self.page.tabs.isEnabled())
        self.assertEqual(self.page.status.text(),'Fixture authentication cancelled')

    def test_reset_is_one_action_and_selects_every_category(self):
        with patch.object(backend,'factory_snapshot',return_value=(self.doc,self.blobs)), patch.object(backend,'load',return_value={'status':'pending-sign-in','recovery':'fixture'}) as load:
            self.page.reset();fn,done,fail=self.pending.pop();result=fn();done(result)
            self.assertEqual(set(load.call_args.args[2]),set(catalog.BY_ID))
            self.assertIn('next sign-in',self.page.status.text())

    def test_missing_factory_baseline_is_visible_and_reset_disabled(self):
        with patch.object(backend,'factory_status',return_value={'desktop':True,'system':False,'detail':'Original system baseline unavailable.'}):
            self.page.refresh();self.assertFalse(self.page.reset_button.isEnabled())
            self.assertIn('unavailable',self.page.factory_label.text())


if __name__ == '__main__': unittest.main()
