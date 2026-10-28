"""The first keystroke after Apps opens belongs to search, without a focus timer."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent,Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import app
import catalog
import favorite_layout
import geometry
import shortcuts

QT=QApplication.instance() or QApplication([])


class SearchFocusTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        entry=shortcuts.Entry('firefox.desktop',None,{'name':'Firefox','command':'firefox'},custom=True)
        self.patches=[patch.object(catalog,'applications',return_value={entry.get_id():entry}),
            patch.object(catalog,'favorites',return_value=[entry.get_id()]),
            patch.object(favorite_layout,'STATE',self.root/'favorites.json'),
            patch.object(geometry,'STATE',self.root/'window.json'),
            patch.object(app.theme_runtime,'STATE',self.root/'theme.json')]
        for item in self.patches:item.start()
        self.windows=[]

    def tearDown(self):
        for window in self.windows:window.close();window.deleteLater()
        QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        for item in reversed(self.patches):item.stop()
        self.temporary.cleanup()

    def open(self,style='raw'):
        (self.root/'theme.json').write_text(json.dumps({'design':'modern' if style=='raw' else 'raw','launcher_style':style}))
        window=app.Menu(preview=True);self.windows.append(window);window.show();QT.processEvents()
        return window

    def test_first_keystroke_goes_to_search_in_both_menu_styles(self):
        for style in ('raw','modern','breakpoint'):
            with self.subTest(style=style):
                window=self.open(style)
                self.assertIsNone(window.views.graphicsEffect(),'Opening must not add a second tile fade')
                self.assertIs(QT.focusWidget(),window.search)
                QTest.keyClicks(QT.focusWidget(),'fire')
                self.assertEqual(window.search.text(),'fire')
                self.assertEqual(window.heading.text(),'Search results')
                self.assertEqual(window.grid.count(),1)
                window.close()

    def test_opening_does_not_take_focus_back_after_keyboard_navigation(self):
        window=self.open();window.search.setFocus()
        QTest.keyClick(window.search,Qt.Key.Key_Down)
        selected=QT.focusWidget()
        self.assertIsNot(selected,window.search)
        QTest.qWait(150)
        self.assertIs(QT.focusWidget(),selected)

    def test_showing_again_starts_in_search_after_previous_tile_focus(self):
        window=self.open();window.favorites_board.focus_selected();window.hide()
        window.show();QT.setActiveWindow(window);QT.processEvents()
        self.assertIs(QT.focusWidget(),window.search)


if __name__=='__main__':unittest.main()
