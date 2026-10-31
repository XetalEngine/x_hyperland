import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog
import places
import file_places


class PlacesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.file = self.root/'places.xbel'
        self.target = self.root/'A folder & files'; self.target.mkdir()
        self.file.write_text('<xbel><bookmark href="'+self.target.as_uri()+'"><title>My Projects ♥</title></bookmark></xbel>')
        self.env = patch.dict(os.environ, XETAL_PLACES_FILE=str(self.file)); self.env.start(); self.addCleanup(self.env.stop)
        for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
            QSettings.setPath(fmt, QSettings.Scope.UserScope, str(self.root))

    def wait(self, fn):
        for _ in range(300):
            if fn(): return
            QTest.qWait(10)
        self.fail('Places did not finish loading')

    def test_bookmark_metadata_hidden_groups_and_application_scope(self):
        self.file.write_text('''<xbel xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks">
        <info><metadata><GroupState-RecentlySaved-IsHidden>true</GroupState-RecentlySaved-IsHidden></metadata></info>
        <bookmark href="file:///tmp"><title>Work &amp; Play</title><info><metadata><bookmark:icon name="folder-blue"/></metadata></info></bookmark>
        <bookmark href="recentlyused:/files"><title>Recent</title></bookmark>
        <bookmark href="file:///hidden"><info><metadata><isHidden>true</isHidden></metadata></info></bookmark>
        <bookmark href="file:///app"><info><metadata><OnlyInApp>kdenlive</OnlyInApp></metadata></info></bookmark>
        <bookmark href="admin:///var/lib"><title>Admin</title></bookmark></xbel>''')
        result = places.bookmarks(self.file)
        self.assertEqual([v['name'] for v in result], ['Work & Play', 'Admin'])
        self.assertEqual(result[0]['icon'], 'folder-blue'); self.assertEqual(result[1]['group'], 'Places')

    def test_open_save_folder_modes_and_live_bookmark_refresh(self):
        for mode in (QFileDialog.FileMode.ExistingFile, QFileDialog.FileMode.AnyFile, QFileDialog.FileMode.Directory):
            dialog = QFileDialog(directory=str(self.root)); dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
            dialog.setFileMode(mode)
            if mode == QFileDialog.FileMode.AnyFile: dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            file_places.attach(dialog); dialog.show()
            side = dialog.xetal_places
            self.wait(lambda: bool(side.findItems('My Projects ♥', Qt.MatchFlag.MatchExactly)))
            item = side.findItems('My Projects ♥', Qt.MatchFlag.MatchExactly)[0]
            QTest.mouseClick(side.viewport(), Qt.MouseButton.LeftButton, pos=side.visualItemRect(item).center())
            self.assertEqual(dialog.directory().absolutePath(), str(self.target))
            self.assertEqual(dialog.fileMode(), mode)
            self.file.write_text(self.file.read_text().replace('My Projects ♥', 'Renamed bookmark'))
            side.load(); self.wait(lambda: bool(side.findItems('Renamed bookmark', Qt.MatchFlag.MatchExactly)))
            dialog.hide(); dialog.show(); file_places.attach(dialog)
            self.assertEqual(len(dialog.findChildren(file_places.Sidebar)), 1)
            dialog.reject(); QTest.qWait(50); dialog.deleteLater(); QTest.qWait(10)
            self.file.write_text(self.file.read_text().replace('Renamed bookmark', 'My Projects ♥'))

    def test_listing_never_mounts_a_volume(self):
        class Icon: pass
        class Volume:
            def get_identifier(self, _): return '/dev/fixture'
            def get_mount(self): return None
            def get_drive(self): return None
            def get_icon(self): return Icon()
            def get_name(self): return 'Unmounted test disk'
            def mount(self, *_): raise AssertionError('Listing must not mount')
        class Monitor:
            def get_volumes(self): return [Volume()]
            def get_mounts(self): return []
        with patch.object(places, 'volumes', return_value=Monitor()):
            entries = places.snapshot()
        entry = next(x for x in entries if x.get('device'))
        self.assertFalse(entry['mounted']); self.assertEqual(entry['url'], '')

    def test_malformed_bookmarks_are_safe(self):
        self.file.write_text('<xbel><broken>')
        self.assertEqual(places.bookmarks(self.file), [])


if __name__ == '__main__': unittest.main()
