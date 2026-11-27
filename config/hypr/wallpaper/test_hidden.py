"""Exercise actual hide/restore controls using disposable pictures and preferences."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'theme'),str(ROOT/'control_center')]
from PyQt6.QtCore import Qt, QPoint, QVariantAnimation
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from wallpaper import library
from wallpaper.browser import Browser
from wallpaper.hidden import HiddenDock


class HiddenWallpapers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.windows = []; self.pictures = []
        self.image = QImage(160,90,QImage.Format.Format_RGB32); self.image.fill(QColor('#2487bb'))
        for i in range(6):
            path = self.root/f'Landscape-{i}.png'; self.image.save(str(path))
            self.pictures.append(library.Picture(str(path),'Local pictures'))
        self.prefs = patch.object(library,'PREFERENCES',self.root/'state/browser.json'); self.prefs.start(); self.addCleanup(self.prefs.stop)
        self.scan = patch.object(Browser,'scan'); self.scan.start(); self.addCleanup(self.scan.stop)

    def tearDown(self):
        for window in self.windows:
            window.hide(); window.shutdown(); window.deleteLater()
        self.app.processEvents()

    def window(self, style='overlay', reduced=False):
        w = Browser(preview=True,style=style); self.windows.append(w)
        w.reduced_motion = reduced; w.carousel.reduced_motion = reduced
        for picture in self.pictures:
            w.thumbnails.cache[picture.path] = QPixmap.fromImage(self.image)
            w.hidden_dock.thumbnails.cache[picture.path] = QPixmap.fromImage(self.image)
        w.scanned(w.cancel_scan,(list(self.pictures),[],'')); w.resize(1200,800); w.show(); w.carousel.setFocus(); QTest.qWait(30)
        return w

    def test_card_button_hides_without_applying_and_reopens_persistently(self):
        w = self.window(); chosen = w.carousel.current()
        before = Path(chosen.path).read_bytes()
        with patch.object(w,'begin_apply') as apply:
            button = next(b for b in w.carousel.hide_buttons if b.isVisible() and b.picture == chosen)
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
            self.assertNotIn(chosen,w.carousel.pictures); self.assertEqual(w.hidden_dock.pictures,[chosen])
            self.assertIsNotNone(w.flight); QTest.qWait(500); self.assertIsNone(w.flight)
            self.assertEqual(w.carousel.current(),self.pictures[1]); apply.assert_not_called()
        self.assertEqual(library.read()['hidden'],[chosen.path]); self.assertEqual(Path(chosen.path).read_bytes(),before)
        reopened = self.window(reduced=True)
        self.assertNotIn(chosen,reopened.carousel.pictures); self.assertEqual(reopened.hidden_dock.pictures,[chosen])

    def test_restore_from_dock_clears_filters_and_does_not_apply(self):
        w = self.window(reduced=True); chosen = w.carousel.current(); w.hide_picture(chosen)
        w.search.setText('no results'); self.assertFalse(w.carousel.pictures)
        self.assertEqual(w.hidden_dock.pictures,[chosen])
        with patch.object(w,'begin_apply') as apply:
            QTest.mouseClick(w.hidden_dock,Qt.MouseButton.LeftButton,pos=w.hidden_dock.location(chosen.path).center().toPoint())
            self.assertEqual(w.carousel.current(),chosen); self.assertEqual(w.search.text(),'')
            self.assertEqual(library.read()['hidden'],[]); apply.assert_not_called()
        self.assertEqual(w.hidden_dock.height(),74); self.assertIsNone(w.flight)

    def test_hide_all_and_restore_with_keyboard(self):
        w = self.window(reduced=True)
        for picture in self.pictures: w.hide_picture(picture)
        self.assertFalse(w.carousel.pictures); self.assertFalse(w.apply.isEnabled()); self.assertFalse(w.play.isEnabled())
        w.hidden_dock.setFocus(); QTest.keyClick(w.hidden_dock,Qt.Key.Key_Home); QTest.keyClick(w.hidden_dock,Qt.Key.Key_Return)
        self.assertEqual(w.carousel.current(),self.pictures[0]); self.assertTrue(w.apply.isEnabled())
        self.assertEqual(len(w.hidden_dock.pictures),5)

    def test_failed_save_leaves_gallery_and_original_files_untouched(self):
        w = self.window(); chosen = w.carousel.current()
        with patch.object(library,'save',side_effect=PermissionError('Read-only settings')):
            w.hide_picture(chosen)
        self.assertIn(chosen,w.carousel.pictures); self.assertFalse(w.hidden_dock.pictures)
        self.assertIn('Read-only',w.status.text()); self.assertTrue(Path(chosen.path).exists())

    def test_restoring_a_hidden_video_selects_video_mode(self):
        video = self.root/'clip.mp4'; video.write_bytes(b'fixture')
        before = library.read(); library.save({**before,'hidden':[str(video)]},before)
        w = self.window(reduced=True)
        w.hidden_dock.thumbnails.cache[str(video)] = QPixmap.fromImage(self.image)
        chosen = w.hidden_dock.pictures[0]; w.restore_picture(chosen)
        self.assertEqual(w.media.currentData(),'videos'); self.assertEqual(w.carousel.current(),chosen)
        self.assertFalse(w.transition.isEnabled()); self.assertEqual(library.read()['hidden'],[])
        self.assertEqual(library.read()['media'],'videos'); self.assertEqual(w.restore_selection,chosen)

    def test_missing_hidden_files_can_be_unhidden_without_changing_wallpaper(self):
        path = str(self.root/'gone.png'); before = library.read(); library.save({**before,'hidden':[path]},before)
        w = self.window(reduced=True); w.restore_picture(w.hidden_dock.pictures[0])
        self.assertEqual(library.read()['hidden'],[]); self.assertIn('unavailable',w.status.text())
        self.assertNotIn(path,[p.path for p in w.carousel.pictures])

    def test_each_presentation_exposes_buttons_and_fits_short_window(self):
        before = library.read(); library.save({**before,'hidden':[p.path for p in self.pictures[:3]]},before)
        for style in library.STYLES:
            with self.subTest(style=style):
                w = self.window(style,reduced=True); w.resize(1000,600); QTest.qWait(30)
                self.assertEqual(w.height(),600)
                self.assertLessEqual(w.hidden_dock.geometry().bottom(),w.height())
                self.assertTrue(w.hidden_dock.isVisible()); self.assertTrue(w.apply.isVisible())
                buttons = [b for b in w.carousel.hide_buttons if b.isVisible()]
                self.assertTrue(buttons)
                QTest.mouseClick(buttons[-1],Qt.MouseButton.LeftButton)
                self.assertEqual(len(library.read()['hidden']),4)
                w.restore_picture(w.hidden_dock.pictures[-1])

    def test_long_shelf_scrolls_to_last_thumbnail_and_drag_never_restores(self):
        dock = HiddenDock(); dock.reduced_motion = True; dock.resize(600,200)
        pictures = [library.Picture(f'/not-read/landscape-{i}.png','Test') for i in range(1000)]
        try:
            with patch.object(dock.thumbnails,'get',return_value=QPixmap.fromImage(self.image)) as read:
                dock.populate(pictures); dock.show(); dock.setFocus(); self.app.processEvents()
                self.assertLess(read.call_count,40); self.assertGreater(dock.scroll.maximum(),0)
                self.assertGreater(dock.picture_rect(1).left(),dock.picture_rect(0).left())
                self.assertGreater(dock.picture_rect(1).top(),dock.picture_rect(0).top())
                restored = []; dock.restored.connect(restored.append)
                QTest.mousePress(dock,Qt.MouseButton.LeftButton,pos=QPoint(260,65))
                QTest.mouseMove(dock,QPoint(100,65)); QTest.mouseRelease(dock,Qt.MouseButton.LeftButton,pos=QPoint(100,65))
                self.assertFalse(restored); self.assertGreater(dock.scroll.value(),0)
                QTest.keyClick(dock,Qt.Key.Key_End); self.assertEqual(dock.focus_index,999)
                self.assertLessEqual(dock.picture_rect(999).right(),dock.width()-18)
                QTest.keyClick(dock,Qt.Key.Key_Return); self.assertEqual(restored,[pictures[-1]])
        finally:
            dock.hide(); dock.stop(); dock.thumbnails.jobs.shutdown(cancel_queued=True); dock.deleteLater(); self.app.processEvents()


class HiddenPreferences(unittest.TestCase):
    def test_old_preferences_upgrade_and_concurrent_independent_saves_merge(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)/'browser.json'; path.write_text('{"version":1,"folders":[]}')
            original = library.read(path); self.assertEqual(original['hidden'],[])
            hidden = library.save({**original,'hidden':['/wallpapers/a.png']},original,path,fields=('hidden',))
            result = library.save({**original,'transition':'fade'},original,path,fields=('transition',))
            self.assertEqual(result['hidden'],hidden['hidden'])
            with self.assertRaisesRegex(ValueError,'elsewhere'):
                library.save(original,original,path,fields=('hidden',))

    def test_invalid_hidden_registry_rejected(self):
        for hidden in ('image.png',[3],['relative.png'],['/null\x00.png']):
            with self.subTest(hidden=hidden),self.assertRaises(ValueError): library.normalize({**library.DEFAULTS,'hidden':hidden})


if __name__ == '__main__': unittest.main()
