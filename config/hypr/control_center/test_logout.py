"""Logout confirmation interactions; never dispatch to a real compositor."""
import subprocess
import unittest
from unittest.mock import Mock

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

import keys
import logout

QT = QApplication.instance() or QApplication([])


class LogoutTests(unittest.TestCase):
    def setUp(self):
        self.runner = Mock(return_value=subprocess.CompletedProcess([], 0, 'ok\n', ''))
        self.window = logout.LogoutDialog(runner=self.runner, exit_sound=lambda parent,done:done())
        self.window.present()
        QTest.qWait(10)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_opening_or_repeating_the_shortcut_never_logs_out(self):
        self.window.logout.setFocus()
        self.window.present()
        QTest.keyClick(self.window, Qt.Key.Key_M, Qt.KeyboardModifier.MetaModifier)
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.cancel.hasFocus())
        self.runner.assert_not_called()

    def test_enter_uses_cancel_by_default(self):
        self.assertTrue(self.window.cancel.isDefault())
        self.assertFalse(self.window.logout.autoDefault())
        QTest.keyClick(self.window.cancel, Qt.Key.Key_Return)
        self.assertFalse(self.window.isVisible())
        self.runner.assert_not_called()

    def test_escape_cancels(self):
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertFalse(self.window.isVisible())
        self.runner.assert_not_called()

    def test_cancel_and_close_button_leave_the_session_running(self):
        for control in (self.window.cancel, self.window.close_control):
            self.window.present()
            QTest.mouseClick(control, Qt.MouseButton.LeftButton)
            self.assertFalse(self.window.isVisible())
            self.runner.assert_not_called()

    def test_window_manager_close_leaves_the_session_running(self):
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.runner.assert_not_called()

    def test_only_explicit_logout_dispatches_once(self):
        QTest.mouseClick(self.window.logout, Qt.MouseButton.LeftButton)
        self.window.confirm_logout()
        self.runner.assert_called_once_with(['hyprctl', 'dispatch', 'exit'],
                                            capture_output=True, text=True, timeout=4)
        self.assertEqual(self.window.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(self.window.isVisible())

    def test_logout_waits_for_music_and_cannot_be_submitted_twice(self):
        pending=[]
        self.window.exit_sound=lambda parent,done:pending.append(done)
        self.window.confirm_logout();self.window.confirm_logout()
        self.assertEqual(len(pending),1);self.runner.assert_not_called()
        self.assertFalse(self.window.cancel.isEnabled())
        pending[0]();self.runner.assert_called_once()

    def test_failure_keeps_dialog_open_and_can_be_cancelled(self):
        self.runner.return_value = subprocess.CompletedProcess([], 1, '', 'Session unavailable')
        QTest.mouseClick(self.window.logout, Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.isVisible())
        self.assertIn('Session unavailable', self.window.error.text())
        self.assertTrue(self.window.cancel.hasFocus())
        QTest.keyClick(self.window.cancel, Qt.Key.Key_Return)
        self.assertFalse(self.window.isVisible())
        self.runner.assert_called_once()

    def test_missing_command_and_timeout_do_not_close_or_retry(self):
        for error in (FileNotFoundError('hyprctl unavailable'), subprocess.TimeoutExpired('hyprctl', 4)):
            self.runner.reset_mock()
            self.runner.side_effect = error
            QTest.mouseClick(self.window.logout, Qt.MouseButton.LeftButton)
            self.assertTrue(self.window.isVisible())
            self.assertTrue(self.window.logout.isEnabled())
            self.assertFalse(self.window.submitted)
            self.runner.assert_called_once()

    def test_reset_defaults_keeps_the_confirmation_binding(self):
        records = []
        for path in (logout.ROOT / 'keybindings.conf', logout.ROOT / 'control_center/keybindings-defaults.conf'):
            bindings = keys.parse(path.read_text())
            target = next(b for b in bindings if keys.trigger(b, {'mainMod': 'SUPER'}) ==
                          (('SUPER',), 'm', False, 'reset'))
            self.assertEqual(target.dispatcher, 'exec')
            self.assertTrue(target.args.endswith('/scripts/logout.sh'))
            self.assertEqual(target.category, 'System')
            records.append(target)
        self.assertEqual(*records)


if __name__ == '__main__':
    unittest.main()
