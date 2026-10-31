import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cursors import model,art,controller

class CursorsTests(unittest.TestCase):
    def test_staged_build_does_not_register_themes_until_explicitly_requested(self):
        from cursors import build
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cache=root/'.build';cache.mkdir()
            fingerprint=build.hashlib.sha256((build.ROOT/'art.py').read_bytes()+(build.ROOT/'build.py').read_bytes()).hexdigest()
            (cache/'version').write_text(fingerprint)
            with patch.object(build,'register_themes') as register:
                self.assertEqual(build.build(root),cache/'data')
                register.assert_not_called()
                build.build(root,register=True)
                register.assert_called_once_with(cache/'data')

    def test_private_artwork_is_discoverable_without_replacing_other_themes(self):
        from cursors.build import register_themes
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=root/'profile/data';registry=root/'icons'
            for style in art.STYLES:(data/'icons'/('Xetal-Cursor-'+style)).mkdir(parents=True)
            register_themes(data,registry);register_themes(data,registry)
            for style in art.STYLES:
                target=registry/('Xetal-Cursor-'+style)
                self.assertTrue(target.is_symlink());self.assertEqual(target.resolve(),data/'icons'/target.name)
            target=registry/'Xetal-Cursor-cyan';target.unlink();target.mkdir()
            marker=target/'user-file';marker.write_text('keep')
            with self.assertRaises(RuntimeError):register_themes(data,registry)
            self.assertEqual(marker.read_text(),'keep')

    def test_portable_defaults_validation_and_migration(self):
        self.assertEqual(model.validate({}),model.DEFAULTS)
        for key,value in [('size',8),('duration',-1),('intensity',True),('click_ripple',1),('style','../../elsewhere'),('color','#red'),('trail','unknown')]:
            with self.subTest(key=key),self.assertRaises(ValueError):model.validate({key:value})
    def test_custom_presets_include_cursors_as_an_independent_component(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'theme'))
        import presets
        value=presets.validate(dict(version=1,theme=dict(design='raw',mode='dark'),cursors=dict(model.DEFAULTS,style='orchid',trail='glow')))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            files,reloads=presets.resources(root,value,{'cursors'},'raw')
            self.assertEqual(files[root/'cursors/settings.json'],model.encode(value['cursors']))
            self.assertIn(('Xetal Desktop Cube','xetalcube:cursor'),reloads)
            files,_=presets.resources(root,value,{'layout'},'raw')
            self.assertNotIn(root/'cursors/settings.json',files)

    def test_failed_native_reload_restores_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json';path.write_bytes(model.encode(model.DEFAULTS))
            before=path.read_bytes();values,token=model.load(path);values['trail']='comet'
            with patch.object(controller,'prepare'),patch.object(controller.cube,'instance_dir'),patch.object(controller,'apply',side_effect=RuntimeError('native adapter absent')):
                with self.assertRaises(RuntimeError):controller.save(values,token,path)
            self.assertEqual(path.read_bytes(),before)
    def test_external_edit_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json';path.write_bytes(model.encode(model.DEFAULTS));values,token=model.load(path)
            path.write_bytes(model.encode(dict(values,style='orchid')))
            with patch.object(controller,'prepare'),patch.object(controller.cube,'instance_dir'),patch.object(controller,'apply') as apply:
                with self.assertRaises(ValueError):controller.save(values,token,path)
            apply.assert_not_called()
    def test_every_style_has_legible_functional_shapes_and_valid_hotspots(self):
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtSvg import QSvgRenderer
        for style in art.STYLES:
            for shape in art.ALIASES:
                svg,hot=art.svg(style,shape)
                self.assertTrue(QSvgRenderer(QByteArray(svg.encode())).isValid(),(style,shape))
                self.assertTrue(all(0<=n<36 for n in hot))
    def test_preview_controls_keep_independent_options_and_preserve_dirty_edits(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QPointF
        from cursors.page import CursorsPage
        app=QApplication.instance() or QApplication([])
        page=CursorsPage(lambda *args:None);page.resize(900,650);page.show();app.processEvents()
        page.choose_style('cyan');page.fields['trail'].setCurrentIndex(page.fields['trail'].findData('sparkle'))
        page.fields['click_ripple'].setChecked(True);page.refresh()
        self.assertTrue(page.dirty);self.assertEqual(page.draft['style'],'cyan');self.assertTrue(page.draft['click_ripple'])
        import time
        page.preview.points=[(QPointF(30,80),time.monotonic())];page.preview.ripples=[(QPointF(60,80),time.monotonic())]
        page.preview.grab();page.fill(page.baseline);self.assertFalse(page.dirty);page.close()

if __name__=='__main__':unittest.main()
