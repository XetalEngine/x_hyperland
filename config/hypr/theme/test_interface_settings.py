"""Preference edits use temporary files and never touch the running desktop."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from interface_settings import InterfaceSettingsDialog, read_preferences, write_preferences

QT = QApplication.instance() or QApplication([])


class InterfaceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'state/interface.json'
        self.applied = Mock()
        self.entries = [(name, name.title(), QIcon(), 'Page ' + name) for name in ('audio', 'memory', 'network')]

    def dialog(self):
        dialog = InterfaceSettingsDialog('Example', self.path, self.entries, self.applied)
        self.addCleanup(lambda: (dialog.deleteLater(), QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)))
        return dialog

    def test_legacy_and_fresh_choices_stay_distinct_and_reset_matches_fresh(self):
        self.assertTrue(read_preferences(self.path)['show_window_controls'])
        write_preferences(self.path, dict(show_window_controls=False, hidden_pages=[], future_option='keep'))
        dialog = self.dialog(); self.assertFalse(dialog.buttons.isChecked())
        dialog.buttons.click(); self.assertTrue(read_preferences(self.path)['show_window_controls'])
        dialog.reset_page(); self.assertFalse(read_preferences(self.path)['show_window_controls'])
        self.assertEqual(json.loads(self.path.read_text())['future_option'], 'keep')

    def test_multiple_pages_hide_reopen_and_restore_without_losing_other_profile_choices(self):
        write_preferences(self.path, dict(show_window_controls=False, hidden_pages=['mac-only-page']))
        dialog = self.dialog()
        for row in (0, 2): dialog.shown.item(row).setSelected(True)
        dialog.hide_button.click()
        self.assertEqual(read_preferences(self.path)['hidden_pages'], ['audio', 'mac-only-page', 'network'])
        reopened = self.dialog(); self.assertEqual(reopened.hidden.count(), 2)
        reopened.hidden.selectAll(); reopened.show_button.click()
        self.assertEqual(read_preferences(self.path)['hidden_pages'], ['mac-only-page'])
        reopened.shown.selectAll(); reopened.hide_button.click(); self.assertEqual(reopened.shown.count(), 0)
        reopened.show_all(); self.assertEqual(reopened.shown.count(), 3)
        self.assertEqual(read_preferences(self.path)['hidden_pages'], ['mac-only-page'])

    def test_failed_save_does_not_change_the_window_or_saved_preferences(self):
        dialog = self.dialog()
        with patch('interface_settings.write_preferences', side_effect=OSError('Read only')):
            dialog.buttons.click()
        self.assertTrue(dialog.buttons.isChecked()); self.applied.assert_not_called()
        self.assertIn('Could not save', dialog.status.text()); self.assertFalse(self.path.exists())

    def test_invalid_file_recovers_without_hiding_access(self):
        self.path.parent.mkdir(); self.path.write_text('{"show_window_controls": "false", "hidden_pages": 7}')
        self.assertEqual(read_preferences(self.path)['hidden_pages'], [])
        self.assertTrue(read_preferences(self.path)['show_window_controls'])


if __name__ == '__main__': unittest.main()
