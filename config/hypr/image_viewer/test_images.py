import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QWheelEvent
from PyQt6.QtWidgets import QApplication
from PIL import Image
import app
import images

APPLICATION = QApplication.instance() or QApplication([])


def immediate(fn, done, failed):
    try: data = fn()
    except Exception as error: failed(str(error))
    else: done(data)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xetal-images-test-')
        self.root = Path(self.temp.name)
        for name in ('photo1.png', 'photo2.PNG', 'photo10.png'):
            Image.new('RGBA', (1200, 900), (90, 160, 190, 170)).save(self.root/name)
        self.first = self.root/'photo1.png'
    def tearDown(self): self.temp.cleanup()

    def test_natural_folder_order_excludes_directories_documents_and_unrelated_files(self):
        (self.root/'text.txt').write_text('not an image')
        (self.root/'drawing.pdf').write_bytes(b'%PDF')
        (self.root/'folder.png').mkdir()
        self.assertEqual([p.name for p in images.folder_images(self.first)], ['photo1.png', 'photo2.PNG', 'photo10.png'])

    def test_file_uri_literal_characters_and_symlinks_keep_original_folder(self):
        unusual = self.root/'image # $(literal).png'
        unusual.symlink_to(self.first)
        self.assertEqual(images.local_path(unusual.as_uri()), unusual)
        self.assertIn(unusual, images.folder_images(unusual))
        with self.assertRaises(ValueError): images.local_path('https://example.com/image.png')

    def test_exif_rotation_and_hidpi_filename_keep_actual_image_dimensions(self):
        self.assertEqual(images.load(self.first)['format'], 'PNG')
        path = self.root/'rotated.jpg'
        image = Image.new('RGB', (200, 100), 'navy')
        exif = image.getexif(); exif[274] = 6; image.save(path, exif=exif)
        result = images.load(path)['image']
        self.assertEqual((result.width(), result.height()), (100, 200))
        path = self.root/'photo@2x.png'; path.write_bytes(self.first.read_bytes())
        self.assertEqual(images.load(path)['image'].devicePixelRatio(), 1)

    def test_invalid_or_removed_images_are_reported(self):
        invalid = self.root/'broken.png'; invalid.write_bytes(b'bad')
        for path in (invalid, self.root/'gone.png'):
            with self.assertRaises(ValueError): images.load(path)

    def viewer(self, filename=None, loader=immediate):
        window = app.Viewer(filename, async_run=loader, remember=False)
        self.addCleanup(window.close)
        window.resize(900, 650); window.show(); APPLICATION.processEvents()
        return window

    def test_arrows_browse_images_and_stop_at_folder_ends(self):
        window = self.viewer(self.first)
        self.assertFalse(window.previous.isEnabled()); self.assertTrue(window.next.isEnabled())
        window.next.click(); self.assertEqual(window.current.name, 'photo2.PNG')
        window.next.click(); self.assertEqual(window.current.name, 'photo10.png')
        self.assertFalse(window.next.isEnabled())
        window.previous.click(); self.assertEqual(window.current.name, 'photo2.PNG')
        self.assertEqual(window.count.text(), '2 / 3')

    def test_real_wheel_zoom_actual_size_and_fit_on_resize(self):
        window = self.viewer(self.first); canvas = window.canvas
        before = canvas.transform().m11(); self.assertLess(before, 1)
        point = QPointF(canvas.viewport().rect().center())
        event = QWheelEvent(point, point, QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(canvas.viewport(), event)
        self.assertGreater(canvas.transform().m11(), before); self.assertFalse(canvas.fit_mode)
        window.actual.click(); self.assertAlmostEqual(canvas.transform().m11(), 1)
        window.fit.click(); self.assertTrue(canvas.fit_mode)
        window.resize(680, 480); APPLICATION.processEvents(); APPLICATION.processEvents()
        self.assertLess(canvas.transform().m11(), before)
        self.assertLessEqual(canvas.sceneRect().height()*canvas.transform().m11(), canvas.viewport().height())

    def test_old_background_load_cannot_replace_new_selection_or_closed_window(self):
        pending = []
        window = self.viewer(loader=lambda fn, done, failed: pending.append((fn, done, failed)))
        window.open_path(self.first); window.open_path(self.root/'photo2.PNG')
        fn, done, _ = pending[1]; done(fn())
        fn, done, _ = pending[0]; done(fn())
        self.assertEqual(window.current.name, 'photo2.PNG')
        self.assertEqual(window.name.text(), 'photo2.PNG')
        window.open_path(self.first); window.close()
        fn, done, _ = pending[-1]; done(fn())
        self.assertTrue(window.closed)

    def test_gif_animates_pauses_and_stops_when_navigating(self):
        gif = self.root/'animated.gif'
        Image.new('RGB', (80, 60), 'red').save(gif, save_all=True,
            append_images=[Image.new('RGB', (80, 60), 'blue')], duration=100, loop=0)
        window = self.viewer(gif)
        self.assertIsNotNone(window.movie)
        window.pause.click(); self.assertEqual(window.movie.state(), app.QMovie.MovieState.Paused)
        window.pause.click(); self.assertEqual(window.movie.state(), app.QMovie.MovieState.Running)
        window.open_path(self.first); self.assertIsNone(window.movie)

    def test_broken_image_keeps_folder_navigation_available(self):
        path = self.root/'photo3.png'; path.write_bytes(b'broken')
        window = self.viewer(path)
        self.assertIn('Could not open', window.message.text())
        self.assertTrue(window.previous.isEnabled()); self.assertTrue(window.next.isEnabled())
        window.next.click(); self.assertEqual(window.current.name, 'photo10.png')


if __name__ == '__main__': unittest.main()
