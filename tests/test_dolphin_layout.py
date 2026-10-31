"""Restore the shipped Qt dock layout without launching Dolphin or a shell."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'config/hypr'))
from dolphin import profile
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget


class DolphinLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_places_and_terminal_visible_and_folders_hidden(self):
        window=QMainWindow();window.setCentralWidget(QWidget());docks={}
        for name in ('infoDock','foldersDock','terminalDock','placesDock'):
            dock=QDockWidget(name,window);dock.setObjectName(name);dock.setWidget(QWidget())
            window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,dock);docks[name]=dock
        data=(Path(profile.__file__).parent/'default-layout.state').read_bytes()
        self.assertTrue(window.restoreState(QByteArray.fromBase64(data)))
        window.show();self.app.processEvents()
        self.assertFalse(docks['foldersDock'].isVisible())
        self.assertTrue(docks['placesDock'].isVisible())
        self.assertTrue(docks['terminalDock'].isVisible())
        self.assertEqual(window.dockWidgetArea(docks['placesDock']),Qt.DockWidgetArea.LeftDockWidgetArea)
        self.assertEqual(window.dockWidgetArea(docks['terminalDock']),Qt.DockWidgetArea.BottomDockWidgetArea)
        window.close();window.deleteLater()

    def test_seed_once_and_preserve_recipient_and_legacy_layouts(self):
        with tempfile.TemporaryDirectory(prefix='xetal-dolphin-layout-') as temporary:
            root=Path(temporary);(root/'dolphin/config').mkdir(parents=True)
            template=root/'dolphin/default-layout.state'
            template.write_bytes((Path(profile.__file__).parent/template.name).read_bytes())
            profile.prepare_layout(root)
            state=root/'dolphin/state/dolphinstaterc'
            self.assertIn('State=AAAA',state.read_text())
            state.write_text('[State]\nState=recipient-layout\n')
            profile.prepare_layout(root)
            self.assertEqual(state.read_text(),'[State]\nState=recipient-layout\n')
            state.unlink()
            (root/'dolphin/config/dolphinrc').write_text('[MainWindow]\nState=legacy-layout\n')
            profile.prepare_layout(root)
            self.assertFalse(state.exists())


if __name__=='__main__':unittest.main()
