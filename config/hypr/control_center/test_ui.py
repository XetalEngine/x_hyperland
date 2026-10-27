"""Interaction regressions with temporary bindings and no live config changes."""
from pathlib import Path
import copy
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent, QTimer
from PyQt6.QtGui import QWheelEvent, QEnterEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QScrollArea, QFileDialog

import app
import keys

QT = QApplication.instance() or QApplication([])
QT.setStyle('Fusion')
QT.setStyleSheet(app.STYLE)


def synchronous(fn, done, failed):
    try: result = fn()
    except Exception as exc: failed(str(exc))
    else: done(result)


class EditorUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.records = keys.parse('bind = SUPER, Q, exec, kitty\nbind = SUPER, W, killactive\n')
        self.records[0].label = 'Open terminal'
        (self.root/'keybindings.conf').write_text(keys.serialize(self.records))
        (self.root/'hyprland.conf').write_text('$mainMod = SUPER\n' + keys.SOURCE + '\n')
        self.store = keys.Store(self.root,self.root/'state')
        with patch.object(keys,'Store',return_value=self.store): self.page = app.Hotkeys()
        self.page.resize(1200, 650); self.page.show(); QTest.qWait(20)
        self.original = (self.root/'keybindings.conf').read_bytes()

    def tearDown(self):
        self.assertEqual((self.root/'keybindings.conf').read_bytes(),self.original)
        self.page.close();self.page.deleteLater()
        # Dispose file watchers before removing the directory they observe.
        QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    def modify(self):
        field = self.page.fields['label']
        field.setFocus();field.selectAll();QTest.keyClicks(field,'Renamed terminal')
        QTest.qWait(210)

    def test_typing_opens_log_immediately_without_losing_characters(self):
        self.modify()
        self.assertEqual(self.page.fields['label'].text(),'Renamed terminal')
        self.assertTrue(self.page.dirty)
        self.assertFalse(self.page.change_panel.isHidden())
        self.assertIn('Renamed terminal',self.page.change_log.toPlainText())
        self.assertIn('Open terminal',self.page.change_log.toPlainText())
        self.assertEqual(self.page.change_panel.maximumHeight(),178)

    def test_discard_restores_values_and_hides_log(self):
        self.modify();self.page.discard();QTest.qWait(210)
        self.assertFalse(self.page.dirty)
        self.assertTrue(self.page.change_panel.isHidden())
        self.assertEqual(self.page.selected().label,'Open terminal')

    def test_successful_apply_clears_log(self):
        self.modify()
        with (patch.object(self.store,'apply',return_value=('new-hash',self.root/'backup')),
              patch.object(app,'async_run',side_effect=synchronous)):
            self.page.apply()
        QTest.qWait(210)
        self.assertFalse(self.page.dirty)
        self.assertTrue(self.page.change_panel.isHidden())

    def test_failed_apply_keeps_log_and_draft(self):
        self.modify()
        with (patch.object(self.store,'apply',side_effect=ValueError('Rejected for testing')),
              patch.object(app,'async_run',side_effect=synchronous),
              patch.object(QMessageBox,'warning')):
            self.page.apply()
        self.assertTrue(self.page.dirty)
        self.assertFalse(self.page.change_panel.isHidden())
        self.assertEqual(self.page.selected().label,'Renamed terminal')

    def test_remove_requires_confirmation_and_can_be_discarded(self):
        QTimer.singleShot(20, lambda: QApplication.activeModalWidget().button(QMessageBox.StandardButton.Cancel).click())
        self.page.remove()
        self.assertEqual(len(self.page.records),2)
        self.assertFalse(self.page.dirty)
        def confirm():
            box=QApplication.activeModalWidget()
            next(b for b in box.buttons() if b.text()=='Remove shortcut').click()
        QTimer.singleShot(20,confirm);self.page.remove();QTest.qWait(210)
        self.assertEqual(len(self.page.records),1)
        self.assertIn('Removed',self.page.change_log.toPlainText())
        self.page.discard();QTest.qWait(210)
        self.assertEqual(len(self.page.records),2)

    def test_inspector_has_room_for_help_text_with_log_open(self):
        self.modify()
        scroll=self.page.findChild(QScrollArea)
        self.assertIsNotNone(scroll)
        self.assertGreaterEqual(self.page.hint.height(),self.page.hint.heightForWidth(self.page.hint.width()))
        self.page.grab().save('/tmp/hypr-hotkey-log-preview.png')

    def test_external_app_hotkey_updates_applications_without_changing_filter(self):
        self.page.categories.setCurrentIndex(2)
        external=self.records+[keys.Binding('new-app','Open Example','Applications',True,'SUPER','F8','exec','example')]
        try:
            keys.atomic_write(self.store.path,keys.serialize(external).encode());QTest.qWait(300)
            self.assertEqual(self.page.categories.tabText(self.page.categories.currentIndex()),'Applications')
            self.assertIn('new-app',[b.id for b in self.page.records]);self.assertFalse(self.page.dirty)
            self.assertEqual(self.page.bindings_table.rowCount(),2)
        finally:self.store.path.write_bytes(self.original)

    def test_external_save_preserves_unapplied_draft_until_discard(self):
        self.modify();draft=self.page.fields['label'].text()
        external=self.records+[keys.Binding('new-app','Open Example','Applications',True,'SUPER','F8','exec','example')]
        try:
            self.store.path.write_text(keys.serialize(external));QTest.qWait(300)
            self.assertTrue(self.page.dirty);self.assertEqual(self.page.fields['label'].text(),draft)
            self.assertIn('another window',self.page.status.text())
            with self.assertRaisesRegex(keys.ConfigError,'changed outside'):self.store.apply(self.page.records,self.page.expected)
            self.page.discard();self.assertFalse(self.page.dirty);self.assertIn('new-app',[b.id for b in self.page.records])
        finally:self.store.path.write_bytes(self.original)

    def test_save_current_exports_all_categories_and_keeps_draft_unapplied(self):
        self.modify()
        self.page.categories.setCurrentIndex(2)
        self.page.search.setText('Renamed')
        target = self.root / 'favorites.conf'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.page.save_preset()
        exported = keys.parse(target.read_text())
        self.assertEqual(len(exported), 2)
        self.assertEqual(exported[0].label, 'Renamed terminal')
        self.assertTrue(self.page.dirty)
        self.assertFalse(self.page.change_panel.isHidden())

    def test_load_preset_from_history_shows_draft_and_discard_restores_active(self):
        preset = copy.deepcopy(self.records)
        preset[0].key = 'F9'
        preset[1].enabled = False
        target = self.root / 'import.conf'
        target.write_text(keys.serialize(preset))
        expected = self.page.expected
        self.page.categories.setCurrentIndex(7)
        self.page.search.setText('not visible')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(target), '')):
            self.page.load_preset()
        QTest.qWait(210)
        self.assertEqual(self.page.records, preset)
        self.assertEqual(self.page.expected, expected)
        self.assertEqual(self.page.categories.currentIndex(), 0)
        self.assertEqual(self.page.search.text(), '')
        self.assertTrue(self.page.dirty)
        self.assertIn('F9', self.page.change_log.toPlainText())
        self.page.discard()
        self.assertEqual(self.page.records, self.records)
        self.assertFalse(self.page.dirty)

    def test_cancelled_or_invalid_load_preserves_existing_draft(self):
        self.modify()
        draft = copy.deepcopy(self.page.records)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')):
            self.page.load_preset()
        self.assertEqual(self.page.records, draft)
        target = self.root / 'bad.conf'
        target.write_text('source = not-a-preset.conf\n')
        with (patch.object(QFileDialog, 'getOpenFileName', return_value=(str(target), '')),
              patch.object(self.page, 'confirm_discard') as confirm):
            self.page.load_preset()
            confirm.assert_not_called()
        self.assertEqual(self.page.records, draft)
        self.assertIn('Could not load preset', self.page.status.text())
        target.write_bytes(self.original)
        with (patch.object(QFileDialog, 'getOpenFileName', return_value=(str(target), '')),
              patch.object(self.page, 'confirm_discard', return_value=False)):
            self.page.load_preset()
        self.assertEqual(self.page.records, draft)

    def test_reset_defaults_requires_confirmation_and_uses_reviewable_draft(self):
        defaults = copy.deepcopy(self.records)
        defaults[0].key = 'F10'
        self.store.defaults.parent.mkdir()
        self.store.defaults.write_text(keys.serialize(defaults))
        self.modify()
        draft = copy.deepcopy(self.page.records)
        QTimer.singleShot(20, lambda: QApplication.activeModalWidget().button(QMessageBox.StandardButton.Cancel).click())
        self.page.reset_defaults()
        self.assertEqual(self.page.records, draft)
        def confirm():
            box = QApplication.activeModalWidget()
            next(b for b in box.buttons() if b.text() == 'Load defaults').click()
        QTimer.singleShot(20, confirm)
        self.page.reset_defaults()
        self.assertEqual(self.page.records, defaults)
        self.assertTrue(self.page.dirty)
        self.assertIn('F10', self.page.change_log.toPlainText())
        self.assertEqual(self.store.defaults.read_text(), keys.serialize(defaults))

    def test_preset_actions_fit_small_control_desk_and_stay_available_in_history(self):
        self.page.resize(970, 510)
        self.page.categories.setCurrentIndex(7)
        QTest.qWait(50)
        actions = (self.page.reset_defaults_button, self.page.save_preset_button, self.page.load_preset_button)
        for widget in actions:
            self.assertTrue(widget.isVisible())
            self.assertTrue(widget.isEnabled())
            self.assertTrue(self.page.rect().contains(widget.geometry()))
        self.assertLess(self.page.categories.geometry().right(), actions[0].geometry().left())


class OverlayUITests(unittest.TestCase):
    def test_wheel_and_scrollbar_and_hover_lifetime(self):
        bindings=keys.parse((keys.ROOT/'keybindings.conf').read_text())
        overlay=app.HintOverlay({'title':'Test window','class':'test','workspace':{'name':'1'}},bindings)
        QTest.qWait(220)
        self.assertFalse(bool(overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus))
        scroll=overlay.rows.verticalScrollBar()
        self.assertGreater(scroll.maximum(),0)
        viewport=overlay.rows.viewport();pos=QPointF(viewport.rect().center())
        event=QWheelEvent(pos,QPointF(viewport.mapToGlobal(pos.toPoint())),QPoint(),QPoint(0,-120),
                          Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(viewport,event)
        self.assertGreater(scroll.value(),0)
        scroll.setValue(0)
        QTest.mouseClick(scroll,Qt.MouseButton.LeftButton,pos=QPoint(scroll.width()//2,scroll.height()-8))
        self.assertGreater(scroll.value(),0)
        overlay.idle_timer.start(18000)
        QApplication.sendEvent(overlay,QEnterEvent(QPointF(10,10),QPointF(10,10),QPointF(10,10)))
        self.assertFalse(overlay.idle_timer.isActive())
        QApplication.sendEvent(overlay,QEvent(QEvent.Type.Leave))
        self.assertTrue(overlay.idle_timer.isActive())
        overlay.close();overlay.deleteLater()


if __name__=='__main__':unittest.main(verbosity=2)
