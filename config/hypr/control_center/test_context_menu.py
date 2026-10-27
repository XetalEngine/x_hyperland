"""Editor drafts and tree operations; no real apps or compositor changes."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent,Qt
from PyQt6.QtWidgets import QApplication,QMessageBox
import context_menu_page as page

QT=QApplication.instance() or QApplication([])


class ContextMenuTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=page.menu_config.Store(self.root/'menu.json',self.root/'history')
        self.store.save(page.menu_config.defaults(),'missing')
        def synchronous(job,done,failed):
            try:done(job())
            except Exception as error:failed(str(error))
        self.page=page.ContextMenuPage(synchronous,self.store);self.page.resize(1190,640);self.page.show();QT.processEvents()

    def tearDown(self):
        self.page.close();self.page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()

    def test_draft_edit_preview_apply_and_discard(self):
        original=self.store.path.read_bytes()
        self.page.inputs['label'].setText('My files');self.page.edit_item()
        self.page.style_inputs['accent_width'].setValue(7)
        self.assertTrue(self.page.dirty);self.assertEqual(self.page.preview.config['style']['accent_width'],7)
        self.assertEqual(self.store.path.read_bytes(),original)
        self.page.discard_changes();self.assertEqual(self.page.inputs['label'].text(),'File Manager')
        self.page.style_inputs['width'].setValue(320);self.page.apply()
        self.assertFalse(self.page.dirty);self.assertEqual(self.store.load()[0]['style']['width'],320)

    def test_reorder_nested_submenu_and_duplicate_ids(self):
        self.page.move_item(1)
        self.assertEqual([item['id'] for item in self.page.draft['items']],['wallpaper','file-manager','displays'])
        self.page.add_item('submenu');group=self.page.current['id']
        self.page.add_item('separator');self.assertEqual(page.menu_config.find(self.page.draft,group)['children'][0]['kind'],'separator')
        self.page.select_id(group);self.page.duplicate()
        groups=[item for item in self.page.draft['items'] if item['kind']=='submenu']
        self.assertEqual(len(groups),2);self.assertNotEqual(groups[0]['children'][0]['id'],groups[1]['children'][0]['id'])
        page.menu_config.validate(self.page.draft)

    def test_drag_tree_roundtrip_preserves_actions(self):
        self.page.add_item('submenu');group=self.page.tree.currentItem()
        root=self.page.tree.invisibleRootItem();node=root.takeChild(0);group.addChild(node);self.page.read_tree()
        nested=page.menu_config.find(self.page.draft,'file-manager')
        self.assertEqual(nested['target'],'file_manager');self.assertEqual(self.page.draft['items'][0]['kind'],'submenu')

    def test_incomplete_shortcut_blocks_apply_and_removed_item_confirms(self):
        self.page.add_item('action');self.assertFalse(self.page.apply_button.isEnabled())
        self.page.inputs['value'].setText('/usr/bin/printf hello');self.page.edit_item();self.assertTrue(self.page.apply_button.isEnabled())
        before=copy.deepcopy(self.page.draft)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):self.page.remove()
        self.assertEqual(self.page.draft,before)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):self.page.remove()
        self.assertEqual(len(self.page.draft['items']),3)

    def test_external_changes_preserve_draft_and_block_overwrite(self):
        self.page.style_inputs['width'].setValue(300)
        external,expected=self.store.load();external['style']['rounding']=22;self.store.save(external,expected)
        self.page.external_change();self.assertEqual(self.page.draft['style']['width'],300)
        self.page.apply();self.assertTrue(self.page.dirty);self.assertIn('changed elsewhere',self.page.status.text())
        self.assertEqual(self.store.load()[0]['style']['rounding'],22)

    def test_global_hotkey_editor_waits_for_saved_menu(self):
        self.assertTrue(self.page.hotkey_button.isEnabled())
        self.page.style_inputs['width'].setValue(310);self.assertFalse(self.page.hotkey_button.isEnabled())
        self.page.discard_changes();self.assertTrue(self.page.hotkey_button.isEnabled())

    def test_presets_are_drafts_and_invalid_load_does_not_replace_edits(self):
        source=self.root/'preset.json';data=page.menu_config.defaults();data['style']['width']=390;self.store.export(source,data)
        with patch.object(page.QFileDialog,'getOpenFileName',return_value=(str(source),'')):self.page.load_preset()
        self.assertTrue(self.page.dirty);self.assertEqual(self.page.draft,data);self.assertEqual(self.store.load()[0]['style']['width'],260)
        source.write_text('not JSON')
        with patch.object(page.QFileDialog,'getOpenFileName',return_value=(str(source),'')):self.page.load_preset()
        self.assertEqual(self.page.draft,data)


if __name__=='__main__':unittest.main()
