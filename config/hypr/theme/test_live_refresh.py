"""Live style changes stay responsive without losing atomic/in-place saves."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QEvent
import runtime


class RefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'theme';self.root.mkdir()
        (self.root/'palettes.json').write_bytes((runtime.ROOT/'palettes.json').read_bytes())
        self.state=self.root/'state.json'
        self.state.write_text(json.dumps({'design':'mycelium','mode':'dark'}))
        self.patches=[patch.object(runtime,'ROOT',self.root),patch.object(runtime,'STATE',self.state)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.theme=runtime.install(self.app,'QWidget {color:#ffffff; background:#171b22;}')
        self.widget=QWidget();self.widget.show();QTest.qWait(80)
        self.changes=QSignalSpy(self.theme.changed)

    def tearDown(self):
        self.theme.deleteLater();self.widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_unrelated_build_files_and_equal_replacement_do_not_refresh_widgets(self):
        for number in range(6):
            (self.root/f'build-{number}.tmp').write_text('compiler output')
        self.state.with_suffix('.new').write_bytes(self.state.read_bytes())
        self.state.with_suffix('.new').replace(self.state)
        QTest.qWait(100)
        self.assertEqual(len(self.changes),0)
        # The equal replacement must not break watching the next in-place save.
        self.state.write_text(json.dumps({'design':'mycelium','mode':'light'}))
        QTest.qWait(100)
        self.assertEqual(len(self.changes),1)
        self.assertEqual(self.app.palette().color(QPalette.ColorRole.Window).name(),runtime.colors()['Window'])

    def test_preference_change_updates_consumers_without_reapplying_same_stylesheet(self):
        with patch.object(self.app,'setStyleSheet',wraps=self.app.setStyleSheet) as style:
            self.state.write_text(json.dumps({'design':'mycelium','mode':'dark','avatar':'auto'}))
            QTest.qWait(100)
            self.assertEqual(len(self.changes),1)
            style.assert_not_called()

    def test_atomic_save_burst_applies_final_theme_once(self):
        with patch.object(self.app,'setStyleSheet',wraps=self.app.setStyleSheet) as style:
            for design in ('blackwood','atomicafterglow','hyperfusionblue'):
                pending=self.root/'pending.json'
                pending.write_text(json.dumps({'design':design,'mode':'dark'}));pending.replace(self.state)
                QTest.qWait(5)
            QTest.qWait(100)
            self.assertEqual(len(self.changes),1)
            self.assertEqual(style.call_count,1)
            self.assertEqual(self.app.palette().color(QPalette.ColorRole.Window).name(),runtime.colors()['Window'])


if __name__=='__main__':unittest.main()
