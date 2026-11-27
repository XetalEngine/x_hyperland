"""Organizing preset cards never applies a theme or changes wallpaper hiding."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

import gallery_state
from gallery import DesignPage
import test_gallery as gallery_fixtures
QT=gallery_fixtures.QT


class HiddenPresetTests(unittest.TestCase):
    setUp=gallery_fixtures.GalleryTests.setUp
    dispose=gallery_fixtures.GalleryTests.dispose
    visible=gallery_fixtures.GalleryTests.visible

    def answer(self,action,reply):
        errors=[]
        def run():
            try:reply(self.page.dialog)
            except BaseException as error:errors.append(error)
            finally:
                if self.page.dialog.isVisible():self.page.dialog.reject()
        QTimer.singleShot(0,run);action()
        if errors:raise errors[0]

    def add(self,title):
        self.answer(self.page.hidden_dock.add_tab.click,lambda dialog:(dialog.name.setText(title),dialog.accept()))
        return self.page.options['active_hidden_tab']

    def test_hide_reflows_both_columns_and_reopens_without_applying(self):
        original=Path(self.directory.name,'state.json').read_bytes()
        self.page.resize(1280,740);QT.processEvents()
        for name in ('raw','shadowedge'):self.page.cards[name].hide_button.click()
        QTest.qWait(500)
        self.assertNotIn('raw',self.visible());self.assertNotIn('shadowedge',self.visible())
        self.assertEqual(self.page.cards['modern'].y(),self.page.cards['breakpoint'].y())
        self.assertTrue(self.page.cards['shadowedge'].isChecked())
        self.assertEqual(gallery_state.read()['hidden'],['raw','shadowedge'])
        reopened=DesignPage(self.owner)
        try:self.assertEqual([p.path for p in reopened.hidden_dock.pictures],['raw','shadowedge'])
        finally:reopened.hide();reopened.deleteLater()
        self.assertEqual(Path(self.directory.name,'state.json').read_bytes(),original)
        self.owner.select_preset.assert_not_called()

    def test_center_arrow_folds_to_strip_and_remembers_visibility_without_restoring(self):
        self.page.hide_preset('modern');QTest.qWait(500)
        dock=self.page.hidden_dock;expanded=dock.height();viewport=self.page.scroll.viewport().height()
        QTest.mouseClick(dock.fold_button,Qt.MouseButton.LeftButton);QTest.qWait(380)
        self.assertTrue(gallery_state.read()['hidden_dock_collapsed']);self.assertTrue(dock.fold_button.isChecked())
        self.assertEqual(dock.height(),46);self.assertGreater(self.page.scroll.viewport().height(),viewport)
        self.assertAlmostEqual(dock.fold_button.mapTo(dock,dock.fold_button.rect().center()).x(),dock.width()/2,delta=2)
        self.assertTrue(dock.header.isVisible());self.assertFalse(dock.scroll.isVisible())
        dock.setFocus();QTest.keyClick(dock,Qt.Key.Key_Return)
        self.assertEqual(gallery_state.read()['hidden'],['modern'])
        # Hiding additional cards and changing tabs keep the user's compact strip.
        self.page.hide_preset('raw');QTest.qWait(500);self.add('Later')
        self.assertTrue(dock.collapsed);self.assertEqual(dock.height(),46)
        self.page.switch_tab('hidden');self.assertTrue(dock.collapsed)
        reopened=DesignPage(self.owner)
        try:
            self.assertTrue(reopened.hidden_dock.collapsed);self.assertEqual(reopened.hidden_dock.height(),46)
        finally:reopened.hide();reopened.deleteLater()
        dock.fold_button.setFocus();QTest.keyClick(dock.fold_button,Qt.Key.Key_Space);QTest.qWait(380)
        self.assertFalse(gallery_state.read()['hidden_dock_collapsed']);self.assertEqual(dock.height(),expanded)
        self.assertEqual(gallery_state.read()['hidden'],['modern','raw']);self.owner.select_preset.assert_not_called()

    def test_fold_save_failure_and_legacy_preferences_keep_the_original_state(self):
        legacy={k:v for k,v in gallery_state.read().items() if k!='hidden_dock_collapsed'}
        target=gallery_state.path();target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(legacy))
        self.assertFalse(gallery_state.read()['hidden_dock_collapsed'])
        with patch.object(gallery_state,'save',side_effect=OSError('Disk full')):
            self.page.hidden_dock.fold_button.click()
        self.assertFalse(self.page.hidden_dock.collapsed);self.assertFalse(self.page.hidden_dock.fold_button.isChecked())
        self.assertEqual(json.loads(target.read_text()),legacy);self.assertIn('Disk full',self.page.status.text())
        with self.assertRaises(ValueError):gallery_state.normalize({**legacy,'hidden_dock_collapsed':'yes'})

    def test_tab_names_drag_highlight_move_and_last_tab_are_remembered(self):
        self.page.hide_preset('hp4');destination=self.add('Motors')
        self.page.switch_tab('hidden');dock=self.page.hidden_dock;bar=dock.tabbar
        dock.drag_path='hp4';mime=dock.drag_mime('hp4');index=next(i for i in range(bar.count()) if bar.tabData(i)==destination)
        point=bar.tabRect(index).center()
        bar.dragEnterEvent(QDragEnterEvent(point,Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
        bar.dragMoveEvent(QDragMoveEvent(point,Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
        self.assertEqual(bar.drop_index,index);self.assertIn('Motors',dock.drop_hint)
        drop=QDropEvent(QPointF(point),Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);bar.dropEvent(drop);dock.drag_path=''
        self.assertTrue(drop.isAccepted());self.assertEqual(gallery_state.read()['active_hidden_tab'],destination)
        self.assertEqual(gallery_state.hidden_tab(self.page.options)['paths'],['hp4'])
        self.assertNotIn('hp4',self.visible())
        self.answer(dock.rename_tab.click,lambda dialog:(dialog.name.setText('Cars & Bikes'),dialog.accept()))
        self.assertEqual(gallery_state.hidden_tab(gallery_state.read())['name'],'Cars & Bikes')
        self.owner.select_preset.assert_not_called()

    def test_delete_requires_destination_transfers_and_restore_only_unhides(self):
        self.page.hide_preset('raw');destination=self.add('Later');self.page.hide_preset('integra');self.page.switch_tab('hidden')
        before=copy.deepcopy(self.page.options)
        def cancel(dialog):
            self.assertIsNone(dialog.destination.currentData());self.assertFalse(dialog.confirm.isEnabled())
            dialog.accept();self.assertTrue(dialog.isVisible());dialog.reject()
        self.answer(self.page.hidden_dock.delete_tab.click,cancel);self.assertEqual(gallery_state.read(),before)
        def transfer(dialog):
            dialog.destination.setCurrentIndex(dialog.destination.findData(destination));dialog.confirm.click()
        self.answer(self.page.hidden_dock.delete_tab.click,transfer)
        self.assertEqual(set(gallery_state.hidden_tab(self.page.options)['paths']),{'raw','integra'})
        self.assertEqual(len(self.page.options['hidden_tabs']),1)
        self.page.search.setText('no-match');self.page.restore_preset('raw');QTest.qWait(500)
        self.assertIn('raw',self.visible());self.assertNotIn('integra',self.visible())
        self.assertEqual(gallery_state.read()['hidden'],['integra']);self.owner.select_preset.assert_not_called()

    def test_failed_save_and_corrupt_state_preserve_original_content(self):
        before=copy.deepcopy(self.page.options)
        with patch.object(gallery_state,'save',side_effect=OSError('Disk full')):self.page.hide_preset('raw')
        self.assertEqual(self.page.options,before);self.assertIn('raw',self.visible());self.assertIn('Disk full',self.page.status.text())
        target=gallery_state.path();target.parent.mkdir(parents=True,exist_ok=True);target.write_text('{broken')
        self.page.hide_preset('raw');self.assertEqual(target.read_text(),'{broken');self.assertIn('raw',self.visible())

    def test_concurrent_changes_and_missing_themes_keep_all_ownership(self):
        first=gallery_state.read();value=gallery_state.add_hidden_tab(first,'Archive')
        value['hidden']=['removed-theme','integra'];value=gallery_state.save(value,first)
        with self.assertRaisesRegex(ValueError,'elsewhere'):gallery_state.save(first,first)
        value=gallery_state.transfer_hidden_tab(value,'hidden',value['active_hidden_tab'])
        self.assertEqual(gallery_state.hidden_tab(value)['paths'],['removed-theme','integra'])
        for invalid in ('','Archive','x'*49,'New\nLine'):
            with self.assertRaises(ValueError):gallery_state.add_hidden_tab(value,invalid)


if __name__=='__main__':unittest.main()
