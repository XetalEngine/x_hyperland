"""Offscreen native UI checks; no real password or system login service is used."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QApplication, QLineEdit, QMessageBox
from app import Controller, SignIn
from model import DESIGNS


class LoginUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def window(self, count=1):
        controller = Controller(preview=True)
        controller.users = [{'username': 'alice', 'name': 'Alice Example', 'uid': 1000},
                            {'username': 'bob', 'name': 'Bob Example', 'uid': 1001}][:count]
        controller.user_index = 0
        window = SignIn(controller); window.resize(1024, 768); window.show()
        self.app.processEvents()
        self.addCleanup(window.close)
        return controller, window

    def test_selector_only_for_multiple_users_and_password_is_hidden(self):
        _, single = self.window()
        self.assertTrue(single.user_select.isHidden())
        controller, multiple = self.window(2)
        self.assertFalse(multiple.user_select.isHidden())
        self.assertEqual(multiple.password.echoMode(), QLineEdit.EchoMode.Password)
        controller.notify('secret', 'Password:')
        multiple.user_select.setCurrentIndex(1)
        self.assertEqual(controller.users[controller.user_index]['username'], 'bob')
        self.assertEqual(multiple.fullname.text(), 'Bob Example')

    def test_compact_multiuser_form_is_centered_and_fits_inside_window(self):
        _, window = self.window(2)
        self.app.processEvents()
        self.assertTrue(window.hero.isHidden())
        self.assertLess(abs(window.card.geometry().center().x()-window.rect().center().x()), 4)
        self.assertGreaterEqual(window.card.geometry().top(), 0)
        self.assertLessEqual(window.card.geometry().bottom(), window.height())
        self.assertLessEqual(window.height(), 768)

    def test_animated_avatar_and_error_clear_password(self):
        controller, window = self.window()
        self.assertIsNotNone(window.avatar.movie)
        self.assertEqual(window.avatar.movie.state(), QMovie.MovieState.Running)
        controller.notify('secret', 'Password:')
        window.password.setText('test-only-secret')
        controller.notify('error', 'Sign-in failed. Please try again.')
        self.assertEqual(window.password.text(), '')
        self.assertFalse(window.password.isEnabled())
        self.assertTrue(window.enter.isEnabled())

    def test_every_design_and_mode_has_a_valid_palette(self):
        controller, window = self.window()
        for design in DESIGNS:
            for mode in ('dark', 'light', 'contrast'):
                controller.theme_override, controller.mode_override = design, mode
                window.update_user(0)
                self.assertEqual(window.design, design)
                self.assertEqual(window.mode, mode)
                self.assertTrue(window.avatar.accent.isValid())

    def test_greeter_closes_only_after_the_authenticated_session_is_acknowledged(self):
        controller, window = self.window()
        controller.preview = False
        controller.phase = 'secret'
        self.assertFalse(window.close())
        self.assertTrue(window.isVisible())
        controller.phase = 'launched'
        self.assertTrue(window.close())
        self.assertFalse(window.isVisible())

    def test_power_menu_is_visible_and_cancel_never_sends_a_request(self):
        controller, window = self.window()
        controller.power.refresh()
        self.assertTrue(window.power_button.isVisible())
        self.assertTrue(window.rect().contains(window.power_button.geometry()))
        self.assertEqual([a.text() for a in window.power_menu.actions()], ['Restart…', 'Shut down…'])
        def cancel():
            dialog = self.app.activeModalWidget()
            self.assertIsInstance(dialog, QMessageBox)
            self.assertEqual(dialog.defaultButton(), dialog.button(QMessageBox.StandardButton.Cancel))
            dialog.button(QMessageBox.StandardButton.Cancel).click()
        with patch.object(controller.power, 'request') as request:
            QTimer.singleShot(0, cancel); window.confirm_power('reboot')
            request.assert_not_called()

    def test_power_confirmation_routes_each_action_and_preview_stays_harmless(self):
        controller, window = self.window(); controller.power.refresh()
        def confirm():
            dialog = self.app.activeModalWidget()
            next(b for b in dialog.buttons() if dialog.buttonRole(b) == QMessageBox.ButtonRole.AcceptRole).click()
        with patch.object(controller.power, 'call', side_effect=AssertionError('Preview must not contact logind')):
            for action in ('reboot', 'poweroff'):
                QTimer.singleShot(0, confirm); window.confirm_power(action)
                self.assertIn('Preview only', window.power_message.text())

    def test_power_request_disables_all_screens_and_failure_reenables_login(self):
        controller, first = self.window()
        second = SignIn(controller); second.show(); self.addCleanup(second.close)
        controller.notify('secret', 'Password:')
        controller.power.busy = True; controller.power.changed.emit()
        for window in (first, second):
            self.assertFalse(window.password.isEnabled())
            self.assertFalse(window.power_button.isEnabled())
        with patch.object(controller.flow, 'answer') as answer:
            controller.preview = False; controller.submit('test-only-password')
            answer.assert_not_called()
        controller.power.busy = False; controller.power.changed.emit()
        self.assertTrue(first.password.isEnabled()); self.assertTrue(second.password.isEnabled())
        controller.preview = True


if __name__ == '__main__': unittest.main()
