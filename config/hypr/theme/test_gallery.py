"""Browsing, filtering and previewing must not apply a theme or lose a choice."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox
import runtime
from gallery import DesignPage

QT = QApplication.instance() or QApplication([])


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        state = Path(self.directory.name)/'state.json'; state.write_text(json.dumps({'design': 'shadowedge', 'mode': 'dark'}))
        patched = patch.object(runtime, 'STATE', state); patched.start(); self.addCleanup(patched.stop)
        self.owner = Mock(); self.owner.design = QComboBox(); self.owner.mode = QComboBox()
        for name, title in runtime.DESIGNS.items(): self.owner.design.addItem(title, name)
        for name, title in runtime.MODES.items(): self.owner.mode.addItem(title, name)
        self.owner.design.setCurrentIndex(self.owner.design.findData('shadowedge'))
        self.owner.mode.setCurrentIndex(self.owner.mode.findData('dark'))
        self.page = DesignPage(self.owner); self.page.refresh(); self.page.resize(1040, 740); self.page.show()
        self.page.search.setFocus(); QT.processEvents(); self.addCleanup(self.dispose)

    def dispose(self):
        self.page.hide(); self.page.deleteLater(); QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def visible(self): return [name for name, card in self.page.cards.items() if not card.isHidden()]

    def test_search_across_collections_keeps_selection_and_handles_no_results(self):
        for query, expected in (('  BLUE  ', ['modern', 'binaryknife', 'tidalglass']),
                                ('moon rain', ['shadowedge']), ('CANDY', ['candycloud']),
                                ('no-such-theme', [])):
            self.page.search.setText(query); self.page.refresh(); QT.processEvents()
            self.assertEqual(self.visible(), expected)
            self.assertEqual(self.page.empty.isVisible(), not expected)
            self.assertTrue(self.page.cards['shadowedge'].isChecked())
        self.owner.select_preset.assert_not_called()
        self.page.search.clear(); QT.processEvents()
        self.assertEqual(self.visible(), list(runtime.DESIGNS))
        self.assertFalse(self.page.empty.isVisible())

    def test_wallpaper_preview_closes_on_leave_even_after_click_and_never_selects_a_preset(self):
        self.page.search.setText('shadow'); QT.processEvents()
        card = self.page.cards['shadowedge']; reveal = card.wallpapers
        self.assertIsNone(reveal.pictures)
        QT.sendEvent(reveal, QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
        QTest.qWait(200); self.assertEqual(reveal.amount, 1.)
        self.assertEqual(len(reveal.pictures), 3); self.assertTrue(all(not p.isNull() for p in reveal.pictures))
        QTest.mouseClick(reveal, Qt.MouseButton.LeftButton)
        self.assertFalse(reveal.hasFocus()); self.assertFalse(reveal.isCheckable())
        QT.sendEvent(reveal, QEvent(QEvent.Type.Leave)); QTest.qWait(200); self.assertEqual(reveal.amount, 0.)
        reveal.setFocus(); QTest.qWait(200); self.assertEqual(reveal.amount, 1.)
        QTest.keyClick(reveal, Qt.Key.Key_Space)
        self.page.search.setFocus(); QTest.qWait(200); self.assertEqual(reveal.amount, 0.)
        reveal.setFocus(); QTest.keyClick(reveal, Qt.Key.Key_Escape); QTest.qWait(200)
        self.assertEqual(reveal.amount, 0.)
        reveal.setFocus(); QTest.qWait(200)
        QT.sendEvent(reveal, QEvent(QEvent.Type.Leave)); QTest.qWait(200); self.assertEqual(reveal.amount, 0.)
        reveal.setFocus(); self.page.search.setText('ocean'); QT.processEvents()
        self.assertFalse(reveal.animation.state().value)
        self.owner.select_preset.assert_not_called()
        self.page.search.clear(); card.click(); self.owner.select_preset.assert_called_once_with('shadowedge')

    def test_all_presets_scroll_in_one_column_and_refresh_keeps_browsing_position(self):
        for width in (1280, 720):
            self.page.resize(width, 600); QT.processEvents()
            previous = None
            for card in self.page.cards.values():
                self.assertEqual(card.x(), 0)
                self.assertLessEqual(card.width(), self.page.scroll.viewport().width())
                if previous is not None: self.assertGreater(card.y(), previous.y()+previous.height())
                previous = card
            self.assertEqual(self.page.scroll.horizontalScrollBar().maximum(), 0)
            self.page.scroll.ensureWidgetVisible(self.page.cards['shadowedge'], 0, 0); QT.processEvents()
            value = self.page.scroll.verticalScrollBar().value(); self.assertGreater(value, 0)
            self.page.refresh(); self.assertEqual(self.page.scroll.verticalScrollBar().value(), value)
            self.assertTrue(self.page.scroll.viewport().rect().contains(
                self.page.cards['shadowedge'].mapTo(self.page.scroll.viewport(), QPoint(5, 5))))


if __name__ == '__main__': unittest.main()
