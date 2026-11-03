"""Visible backgrounds and centered icon-only tiles in every menu design."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QEvent,QRect,Qt
from PyQt6.QtGui import QColor,QImage,QPainter
from PyQt6.QtWidgets import QApplication
import app
from launcher_labels import positions

QT=QApplication.instance() or QApplication([])


class AppearanceTests(unittest.TestCase):
    def test_hidden_labels_keep_medium_icon_centered_and_small_tiles_unchanged(self):
        class Icon:
            def paint(self,painter,x,y,width,height):self.rect=QRect(x,y,width,height)
        with tempfile.TemporaryDirectory() as directory,patch.object(app.theme_runtime,'STATE',Path(directory)/'state.json'):
            for style in app.theme_runtime.DESIGNS:
                for small in (False,True):
                    app.theme_runtime.STATE.write_text(json.dumps({'design':style,'launcher_labels':{'names':False,'hotkeys':False}}))
                    size=(72,56) if small else (144,112)
                    picture=QImage(*size,QImage.Format.Format_ARGB32);picture.fill(Qt.GlobalColor.transparent)
                    painter=QPainter(picture);icon=Icon()
                    app.Tiles.draw(painter,QRect(0,0,*size),icon,'Firefox',['Super+F'],small=small);painter.end()
                    self.assertLessEqual(abs(icon.rect.center().x()-size[0]/2),1)
                    self.assertLessEqual(abs(icon.rect.center().y()-size[1]/2),1)
                    self.assertEqual(icon.rect.width(),27 if small else 38)

    def test_remaining_label_content_is_centered_and_stays_inside_tile(self):
        for names,hotkeys in ((False,False),(True,False),(False,True)):
            icon,name,key=positions(104,names,hotkeys)
            bottom=key+16 if hotkeys else name+31 if names else icon+38
            self.assertAlmostEqual(icon,104-bottom)
            self.assertGreaterEqual(icon,0);self.assertLessEqual(bottom,104)

    def test_background_changes_and_visibility_endpoints_render_in_every_style(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state.json'
            for name,color in [('red','#f02030'),('blue','#1040f0')]:
                image=QImage(50,50,QImage.Format.Format_RGB32);image.fill(QColor(color));image.save(str(root/(name+'.png')))
            with patch.object(app.theme_runtime,'STATE',state),patch.object(app.catalog,'applications',return_value={}),patch.object(app.catalog,'favorites',return_value=[]):
                for style in app.theme_runtime.DESIGNS:
                    def change(name,visibility):
                        state.write_text(json.dumps({'design':style,'launcher_wallpaper':True,
                            'launcher_background':str(root/(name+'.png')),'launcher_background_visibility':visibility}))
                    change('red',100);window=app.Menu(preview=True)
                    try:
                        window.show();QT.processEvents()
                        self.assertEqual(window.grab().toImage().pixelColor(12,190).name(),'#f02030')
                        change('blue',100);window.apply_design();QT.processEvents()
                        self.assertEqual(window.grab().toImage().pixelColor(12,190).name(),'#1040f0')
                        change('blue',0);window.apply_design();QT.processEvents()
                        opaque=window.grab().toImage().pixelColor(12,190)
                        # Opaque themes may use a material gradient. The image
                        # underneath must disappear, regardless of its color.
                        change('red',0);window.apply_design();QT.processEvents()
                        self.assertEqual(window.grab().toImage().pixelColor(12,190),opaque)
                    finally:window.close();window.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)


if __name__=='__main__':unittest.main()
