"""Actual alpha composition and GIF decoding/lifetime, independent of layout."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from PyQt6.QtCore import Qt, QRectF, QEvent
from PyQt6.QtGui import QImage, QPainter, QPixmap, QMovie
from PyQt6.QtTest import QTest, QSignalSpy
from PyQt6.QtWidgets import QApplication, QWidget

import runtime
from launcher_surfaces import StripImage, normalize, paint_group, paint_tile

APP=QApplication.instance() or QApplication([])


class SurfaceTests(unittest.TestCase):
    def test_opacity_is_exact_with_and_without_group_art_in_all_palettes(self):
        picture=QPixmap(40,20);picture.fill(Qt.GlobalColor.white)
        for style in runtime.DESIGNS:
            for mode in runtime.MODES:
                colors=runtime.colors(mode,style)
                for opacity in (0,50,100):
                    for art in (None,picture):
                        with self.subTest(style=style,mode=mode,opacity=opacity,art=bool(art)):
                            canvas=QImage(100,40,QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(0)
                            painter=QPainter(canvas)
                            paint_group(painter,QRectF(0,0,100,40),colors,style,opacity,art);painter.end()
                            self.assertLessEqual(abs(canvas.pixelColor(50,20).alpha()-round(255*opacity/100)),1)
                    canvas=QImage(100,40,QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(0)
                    painter=QPainter(canvas)
                    paint_tile(painter,QRectF(0,0,100,40),colors,style,mode,opacity);painter.end()
                    self.assertLessEqual(abs(canvas.pixelColor(50,20).alpha()-round(255*opacity/100)),1)

    def test_gif_advances_pauses_when_hidden_and_releases_when_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            gif=Path(directory)/'strip.gif';png=Path(directory)/'still.png'
            Image.new('RGB',(40,20),'red').save(gif,save_all=True,
                append_images=[Image.new('RGB',(40,20),'blue')],duration=[50,70],loop=0)
            Image.new('RGB',(40,20),'green').save(png)
            host=QWidget();image=StripImage(host);frames=QSignalSpy(image.changed)
            try:
                image.load(str(gif))
                self.assertFalse(image.frame.isNull())
                self.assertNotEqual(image.movie.state(),QMovie.MovieState.Running)
                host.show();QTest.qWait(180)
                self.assertGreater(len(frames),2)
                host.hide();count=len(frames);QTest.qWait(160)
                self.assertEqual(len(frames),count)
                self.assertEqual(image.movie.state(),QMovie.MovieState.Paused)
                host.show();QTest.qWait(150);self.assertGreater(len(frames),count)
                image.set_enabled(False);count=len(frames);QTest.qWait(140)
                self.assertEqual(len(frames),count)
                image.load(str(png));self.assertIsNone(image.movie)
                self.assertEqual(image.frame.toImage().pixelColor(10,10).name(),'#008000')
                image.load('');self.assertTrue(image.frame.isNull())
            finally:
                host.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_older_or_malformed_preferences_fall_back_without_sharing_drafts(self):
        defaults=normalize({})
        bad=normalize({'raw':{'tile_opacity':False,'group_opacity':-1,'group_image':42},'modern':None})
        self.assertEqual(bad,defaults)
        bad['raw']['tile_opacity']=99
        self.assertEqual(normalize({}),defaults)


if __name__=='__main__':unittest.main()
