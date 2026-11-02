"""Offscreen native UI checks; no real password or system login service is used."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QApplication, QLineEdit
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


if __name__ == '__main__': unittest.main()
