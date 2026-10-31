import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'theme'),str(ROOT/'control_center')]
from wallpaper import library, transitions
from wallpaper.browser import Browser, ScreenPicker, sample_monitors
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt, QPoint


class LibraryTests(unittest.TestCase):
    def test_all_bundled_and_recursive_folders_without_duplicates_or_symlink_loops(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); (root/'sets.json').write_text(json.dumps({'modern':['a.png']})); (root/'a.png').write_bytes(b'a')
            folder=root/'personal'; folder.mkdir(); (folder/'b.PNG').write_bytes(b'b'); (folder/'nested').mkdir()
            (folder/'nested/c.webp').write_bytes(b'c'); (folder/'nested/loop').symlink_to(folder,target_is_directory=True)
            (folder/'duplicate.png').symlink_to(root/'a.png'); (folder/'notes.txt').write_text('not an image')
            options={**library.DEFAULTS,'folders':[str(folder),str(folder/'nested')]}
            pictures,notices=library.scan(options,root)
            self.assertEqual({Path(p.path).name for p in pictures},{'a.png','b.PNG','c.webp'}); self.assertFalse(notices)

    def test_missing_folder_and_cancel_do_not_remove_user_preferences(self):
        options={**library.DEFAULTS,'bundled':False,'folders':['/no-such-wallpaper-folder']}
        pictures,notices=library.scan(options); self.assertFalse(pictures); self.assertIn('unavailable',notices[0])
        self.assertEqual(options['folders'],['/no-such-wallpaper-folder'])
        self.assertEqual(library.scan(options,cancelled=lambda:True),([],[]))

    def test_preferences_detect_external_edits_and_removal_keeps_images(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); image=root/'a.png'; image.write_bytes(b'keep'); path=root/'state/browser.json'
            before=library.read(path); after=library.save({**before,'folders':[str(root)]},before,path)
            with self.assertRaisesRegex(ValueError,'elsewhere'): library.save(before,before,path)
            library.save({**after,'folders':[]},after,path)
            self.assertEqual(image.read_bytes(),b'keep'); self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_relative_folders_and_unknown_effects_rejected(self):
        for changes in ({'folders':['../Pictures']},{'transition':'bad'},{'bundled':'yes'}):
            with self.assertRaises(ValueError): library.normalize({**library.DEFAULTS,**changes})

    def test_physical_layout_preserves_scale_rotation_and_negative_offsets(self):
        monitors=sample_monitors(); monitors[0]['x']=-2560; monitors[1]['x']=0; monitors[0]['scale']=2
        boxes=library.screen_rectangles(monitors,1000,600)
        a,b=boxes['DP-1'],boxes['DP-2']
        self.assertLess(a[0],b[0]); self.assertLess(b[1],a[1]); self.assertAlmostEqual(a[2]/a[3],2560/1440)
        self.assertAlmostEqual(b[2]/b[3],1080/1920)
        for x,y,w,h in boxes.values(): self.assertGreaterEqual(x,0); self.assertGreaterEqual(y,0); self.assertLessEqual(x+w,1000); self.assertLessEqual(y+h,600)
        monitors[1]['mirror']='DP-1'; self.assertEqual(len(library.screen_rectangles(monitors,1000,600)),1)

    def test_transition_cover_is_removed_on_commit_failure(self):
        overlay=Mock()
        with self.assertRaisesRegex(ValueError,'disconnected'):
            transitions.commit(overlay,Mock(side_effect=ValueError('disconnected')))
        overlay.play.assert_not_called(); overlay.close.assert_called_once()

    def test_animation_failure_keeps_successfully_saved_wallpaper(self):
        overlay=Mock(); overlay.play.side_effect=RuntimeError('renderer exited')
        self.assertEqual(transitions.commit(overlay,lambda:{'saved':True}),{'saved':True}); overlay.close.assert_called_once()


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([]); cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.prefs=patch.object(library,'read',return_value=library.normalize(library.DEFAULTS)); self.prefs.start()
        self.scan=patch.object(Browser,'scan'); self.scan.start()
        self.window=Browser(preview=True)
        self.window.pictures=[library.Picture(str(library.ROOT/'modern'/f'workstation-{i}.png'),'Modern') for i in (1,2,3)]
        self.window.filter(); self.window.show(); QTest.qWait(30)

    def tearDown(self):
        self.window.hide(); self.window.shutdown()
        self.app.processEvents(); self.window.deleteLater(); self.app.processEvents(); self.scan.stop(); self.prefs.stop()

    def test_single_display_applies_without_opening_picker(self):
        with patch.object(self.window,'begin_apply') as apply,patch('wallpaper.browser.ScreenPicker') as picker:
            self.window.pick_screen(self.window.pictures[0],(sample_monitors()[:1],{})); picker.assert_not_called(); apply.assert_called_once()

    def test_multiple_displays_wait_for_selection_and_cancel_writes_nothing(self):
        with patch.object(self.window,'begin_apply') as apply,patch('wallpaper.browser.ScreenPicker') as picker:
            picker.return_value.exec.return_value=QDialog.DialogCode.Rejected
            self.window.pick_screen(self.window.pictures[0],(sample_monitors(),{})); apply.assert_not_called()
            picker.return_value.exec.return_value=QDialog.DialogCode.Accepted; picker.return_value.selected=sample_monitors()[1]
            self.window.pick_screen(self.window.pictures[0],(sample_monitors(),{}))
            self.assertEqual(apply.call_args.args[1]['name'],'DP-2')

    def test_click_any_card_selects_it_and_drag_does_not_apply(self):
        carousel=self.window.carousel; carousel.activated.disconnect(self.window.choose); chosen=[]; carousel.activated.connect(chosen.append); self.app.processEvents()
        index,path=next((i,p) for i,p in carousel.boxes if i!=carousel.index and carousel.rect().contains(p.boundingRect().center().toPoint()))
        point=path.boundingRect().center().toPoint(); QTest.mouseClick(carousel,Qt.MouseButton.LeftButton,pos=point)
        self.assertEqual(chosen[-1],carousel.pictures[index%len(carousel.pictures)])
        QTest.mousePress(carousel,Qt.MouseButton.LeftButton,pos=point); QTest.mouseMove(carousel,point+QPoint(120,0)); QTest.mouseRelease(carousel,Qt.MouseButton.LeftButton,pos=point+QPoint(120,0))
        self.assertEqual(len(chosen),1)

    def test_slideshow_and_search_never_apply_wallpaper(self):
        with patch.object(self.window,'begin_apply') as apply:
            self.window.toggle_play(); self.assertTrue(self.window.slideshow.isActive()); self.window.advance(); self.assertEqual(self.window.carousel.current(),self.window.pictures[1])
            self.window.search.setText('workstation 3'); self.assertFalse(self.window.slideshow.isActive()); self.assertEqual(len(self.window.carousel.pictures),1)
            self.window.search.setText('nothing matches'); self.assertFalse(self.window.apply.isEnabled()); apply.assert_not_called()

    def test_loop_wrap_and_reduced_motion(self):
        carousel=self.window.carousel; carousel.reduced_motion=True; carousel.step(-1)
        self.assertEqual(carousel.current(),self.window.pictures[-1]); self.assertEqual(carousel.position,-1.)
        carousel.step(1); self.assertEqual(carousel.current(),self.window.pictures[0])

    def test_monitor_picker_returns_only_clicked_screen(self):
        dialog=ScreenPicker(sample_monitors(),{},self.window.pictures[0],self.window.thumbnails,self.window)
        dialog.choose(sample_monitors()[1]); self.assertEqual(dialog.selected['name'],'DP-2'); self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)


if __name__=='__main__': unittest.main()
