"""Outside-focus dismissal with temporary popup/capture protection."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import app
import catalog
import favorite_layout
import geometry

QT = QApplication.instance() or QApplication([])


class DismissalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(catalog, 'applications', return_value={}),
                        patch.object(catalog, 'favorites', return_value=[]),
                        patch.object(favorite_layout, 'STATE', self.root / 'favorites.json'),
                        patch.object(geometry, 'STATE', self.root / 'window.json')]
        for item in self.patches:item.start()
        self.menu = app.Menu(preview=True)
        self.menu.show()
        QTest.qWait(30)
        self.menu.preview = False
        self.menu.started = 0
        self.focused = False
        self.capture = False
        self.patches += [patch.object(self.menu, 'isActiveWindow', side_effect=lambda: self.focused),
                         patch.object(app.capture_guard, 'active', side_effect=lambda: self.capture)]
        for item in self.patches[-2:]:item.start()

    def tearDown(self):
        self.menu.preview = True
        self.menu.close()
        self.menu.deleteLater()
        QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def focus_changed(self):
        self.menu.changeEvent(QEvent(QEvent.Type.ActivationChange))

    def test_outside_click_during_opening_delay_is_retried(self):
        self.menu.started = time.monotonic()
        self.focus_changed()
        QTest.qWait(180)
        self.assertTrue(self.menu.isVisible())
        QTest.qWait(650)
        self.assertFalse(self.menu.isVisible())

    def test_capture_end_rechecks_focus_without_another_activation_event(self):
        self.capture = True
        self.focus_changed()
        QTest.qWait(180)
        self.assertTrue(self.menu.isVisible())
        self.capture = False
        QTest.qWait(250)
        self.assertFalse(self.menu.isVisible())

    def test_dialog_protection_does_not_permanently_disable_dismissal(self):
        self.menu.interaction_depth = 1
        self.focus_changed()
        QTest.qWait(180)
        self.assertTrue(self.menu.isVisible())
        self.menu.interaction_depth = 0
        self.menu.started = time.monotonic()
        QTest.qWait(800)
        self.assertFalse(self.menu.isVisible())

    def test_returning_focus_cancels_pending_dismissal(self):
        self.menu.started = time.monotonic()
        self.focus_changed()
        QTest.qWait(150)
        self.focused = True
        self.focus_changed()
        QTest.qWait(650)
        self.assertTrue(self.menu.isVisible())
        self.focused = False
        self.focus_changed()
        QTest.qWait(200)
        self.assertFalse(self.menu.isVisible())


if __name__ == '__main__':unittest.main()
