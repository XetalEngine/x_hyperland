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
from wallpaper.page import SelectorSettings
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit
from PyQt6.QtGui import QKeySequence, QShortcut
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
        for changes in ({'folders':['../Pictures']},{'transition':'bad'},{'bundled':'yes'},{'style':'bad'}):
            with self.assertRaises(ValueError): library.normalize({**library.DEFAULTS,**changes})

    def test_selector_preferences_migrate_and_merge_independent_controls(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'browser.json'
            path.write_text(json.dumps({'version':1,'folders':[],'bundled':True,'transition':'fade'}))
            before=library.read(path); self.assertEqual(before['style'],'overlay')
            library.save({**before,'style':'window'},before,path,fields=('style',))
            folder=library.save({**before,'folders':[name]},before,path,fields=('folders','bundled'))
            self.assertEqual(folder['style'],'window'); self.assertEqual(folder['transition'],'fade')
            with self.assertRaisesRegex(ValueError,'elsewhere'):
                library.save(before,before,path,fields=('style',))

    def test_physical_layout_preserves_scale_rotation_and_negative_offsets(self):
        monitors=sample_monitors(); monitors[0]['x']=-2560; monitors[1]['x']=0; monitors[0]['scale']=2
        boxes=library.screen_rectangles(monitors,1000,600)
        a,b=boxes['DP-1'],boxes['DP-2']
        self.assertLess(a[0],b[0]); self.assertLess(b[1],a[1]); self.assertAlmostEqual(a[2]/a[3],2560/1440)
        self.assertAlmostEqual(b[2]/b[3],1080/1920)
        for x,y,w,h in boxes.values(): self.assertGreaterEqual(x,0); self.assertGreaterEqual(y,0); self.assertLessEqual(x+w,1000); self.assertLessEqual(y+h,600)
        monitors[1]['mirror']='DP-1'; self.assertEqual(len(library.screen_rectangles(monitors,1000,600)),1)

    def test_current_wallpaper_matches_its_source_without_duplicating_cached_copy(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); source=root/'landscape.png'; source.touch(); cached=root/'cached.png'; cached.touch()
            alias=root/'alias.png'; alias.symlink_to(source)
            pictures=[library.Picture(str(source),'Favorites')]
            result,selected=library.include_current(pictures,{'path':str(cached),'original':str(alias)})
            self.assertEqual(result,pictures); self.assertEqual(selected,str(source))

    def test_current_wallpaper_remains_available_when_its_folder_or_source_is_gone(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); cached=root/'cached.png'; cached.touch()
            pictures=[library.Picture('/another/wallpaper.png','Favorites')]
            result,selected=library.include_current(pictures,{'original':str(root/'missing.png'),'path':str(cached)})
            self.assertEqual(selected,str(cached)); self.assertEqual(result[0].title,'Current wallpaper')
            self.assertEqual(result[1:],pictures); self.assertEqual(len(pictures),1)
            cached.unlink()
            self.assertEqual(library.include_current(pictures,{'path':str(cached)}),(pictures,''))

    def test_random_is_saved_as_a_choice_and_resolved_afresh_for_each_animation(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'browser.json'; before=library.read(path)
            library.save({**before,'transition':'random'},before,path,fields=('transition',))
            for effect in library.ANIMATED_TRANSITIONS:
                with patch.object(transitions.random,'choice',return_value=effect) as choose, \
                     patch.object(transitions.build,'build',return_value=Path('/test/transition')), \
                     patch.object(transitions.subprocess,'Popen') as spawn, patch.object(transitions,'Transition'):
                    transitions.prepare(sample_monitors()[0],{}, {'path':'/test/image.png','fit':'cover'},library.read(path)['transition'])
                    self.assertEqual(spawn.call_args.args[0][-1],effect)
                    self.assertNotIn('none',choose.call_args.args[0]); self.assertNotIn('random',choose.call_args.args[0])
            self.assertEqual(library.read(path)['transition'],'random')

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
        self.window=Browser(preview=True,style='window')
        self.window.pictures=[library.Picture(str(library.ROOT/'modern'/f'workstation-{i}.png'),'Modern') for i in (1,2,3)]
        self.window.filter(); self.window.show(); QTest.qWait(30)

    def tearDown(self):
        self.window.hide(); self.window.shutdown()
        self.app.processEvents(); self.window.deleteLater(); self.app.processEvents(); self.scan.stop(); self.prefs.stop()

    def test_single_display_applies_without_opening_picker(self):
        with patch.object(self.window,'begin_apply') as apply,patch('wallpaper.browser.ScreenPicker') as picker:
            self.window.pick_screen(self.window.pictures[0],(sample_monitors()[:1],{})); picker.assert_not_called(); apply.assert_called_once()

    def test_escape_closes_from_each_control_and_with_competing_shortcut(self):
        for style in library.STYLES:
            for control in ('carousel', 'search', 'collection', 'transition', 'apply'):
                with self.subTest(style=style, control=control):
                    window = Browser(preview=True, style=style)
                    try:
                        window.show(); window.activateWindow(); QTest.qWait(20)
                        target = getattr(window, control); target.setFocus()
                        competing = QShortcut(QKeySequence(Qt.Key.Key_Escape), window)
                        QTest.keyClick(target, Qt.Key.Key_Escape)
                        self.assertFalse(window.isVisible())
                    finally:
                        window.hide(); window.shutdown(); window.deleteLater(); self.app.processEvents()

    def test_escape_cancels_own_dialog_first_and_ignores_other_windows(self):
        other = QLineEdit(); other.show()
        try:
            QTest.keyClick(other, Qt.Key.Key_Escape)
            self.assertTrue(self.window.isVisible())
            dialog = QDialog(self.window); self.window.dialog = dialog; dialog.show()
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            self.assertFalse(dialog.isVisible()); self.assertTrue(self.window.isVisible())
            self.window.dialog = None; dialog.deleteLater()
        finally:
            other.close(); other.deleteLater(); self.app.processEvents()

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

    def test_open_centers_current_wallpaper_but_browsing_and_rescans_keep_user_selection(self):
        pictures=self.window.pictures; selected=pictures[2]
        self.window.scanned(self.window.cancel_scan,(pictures,[],selected.path))
        self.assertEqual(self.window.carousel.current(),selected)
        self.assertEqual(self.window.carousel.position,2.)
        self.window.carousel.go(1)
        self.window.filter()
        self.assertEqual(self.window.carousel.current(),pictures[1])
        self.window.scanned(self.window.cancel_scan,(pictures,[],selected.path))
        self.assertEqual(self.window.carousel.current(),pictures[1])

    def test_reduced_motion_bypasses_even_random_animation(self):
        self.window.preview=False; self.window.reduced_motion=True; self.window.options['transition']='random'
        with patch.object(self.window.jobs,'run') as jobs, patch.object(transitions,'prepare') as prepare:
            self.window.begin_apply(self.window.pictures[0],sample_monitors()[0],{})
            jobs.call_args.args[0]()
            self.assertEqual(prepare.call_args.args[-1],'none')

    def test_monitor_picker_returns_only_clicked_screen(self):
        dialog=ScreenPicker(sample_monitors(),{},self.window.pictures[0],self.window.thumbnails,self.window)
        dialog.choose(sample_monitors()[1]); self.assertEqual(dialog.selected['name'],'DP-2'); self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)

    def test_floating_style_keeps_empty_desktop_space_transparent(self):
        floating=Browser(preview=True,style='overlay')
        try:
            floating.pictures=self.window.pictures; floating.filter(); floating.show(); QTest.qWait(30)
            surface=floating.grab().toImage()
            self.assertEqual(surface.pixelColor(0,0).alpha(),0)
            # The space between the floating toolbar and cards must be clear too.
            point=floating.carousel.pos()+QPoint(floating.carousel.width()//2,2)
            self.assertEqual(surface.pixelColor(point).alpha(),0)
            self.assertGreater(self.window.grab().toImage().pixelColor(0,0).alpha(),250)
            self.assertTrue(floating.search.isVisible()); self.assertTrue(floating.folder_button.isVisible())
        finally:
            floating.hide(); floating.shutdown(); floating.deleteLater(); self.app.processEvents()


class SelectorTests(unittest.TestCase):
    def test_theme_control_saves_the_style_and_preserves_the_gallery_collection(self):
        app=QApplication.instance() or QApplication([])
        def run(fn, done, failed):
            try: done(fn())
            except (OSError, ValueError) as error: failed(str(error))
        with tempfile.TemporaryDirectory() as name, patch.object(library,'PREFERENCES',Path(name)/'browser.json'):
            expected=library.read(); library.save({**expected,'transition':'sweep','folders':[name]},expected)
            control=SelectorSettings(run)
            try:
                for style in library.STYLES:
                    control.style.setCurrentIndex(control.style.findData(style))
                    self.assertEqual(library.read()['style'], style)
                    self.assertEqual(control.description.text(), library.DESCRIPTIONS[style])
                control.style.setCurrentIndex(control.style.findData('overlay'))
                saved=library.read(); self.assertEqual(saved['style'],'overlay')
                self.assertEqual(saved['transition'],'sweep'); self.assertEqual(saved['folders'],[name])
                with patch('wallpaper.page.subprocess.Popen') as start:
                    control.open.click(); self.assertIn('--show',start.call_args.args[0])
                library.save({**saved,'style':'window'},saved,fields=('style',)); control.refresh()
                self.assertEqual(control.style.currentData(),'window')
            finally:
                control.deleteLater(); app.processEvents()


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([]); cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        for mock in (patch.object(library, 'read', return_value=library.normalize(library.DEFAULTS)),
                     patch.object(Browser, 'scan')):
            mock.start(); self.addCleanup(mock.stop)
        self.windows = []
        self.pictures = [library.Picture(str(library.ROOT / style / f'workstation-{i}.png'), title)
                         for style, title in [('raw', 'Original'), ('modern', 'Modern'), ('breakpoint', 'Breakpoint')]
                         for i in (1, 2, 3)]

    def tearDown(self):
        for window in self.windows:
            window.hide(); window.shutdown(); window.deleteLater()
        self.app.processEvents()

    def window(self, style):
        window = Browser(preview=True, style=style); self.windows.append(window)
        window.scanned(window.cancel_scan, (self.pictures, [], ''))
        window.carousel.reduced_motion = True; window.resize(1440, 850); window.show(); QTest.qWait(30)
        return window

    def test_thumbnails_preview_until_user_explicitly_applies(self):
        for style in ('frame-lab', 'orbit-atlas'):
            with self.subTest(style=style):
                window = self.window(style); scene = window.presentation.strip or window.carousel
                hero = window.carousel.boxes[-1][1] if style == 'orbit-atlas' else None
                index, path = next((i, path) for i, path in scene.boxes
                    if i % len(window.carousel.pictures) != window.carousel.index % len(window.carousel.pictures)
                    and scene.rect().contains(path.boundingRect().center().toPoint())
                    and (hero is None or not hero.contains(path.boundingRect().center())))
                with patch.object(window, 'pick_screen') as apply:
                    QTest.mouseClick(scene, Qt.MouseButton.LeftButton, pos=path.boundingRect().center().toPoint())
                    self.assertEqual(window.carousel.current(), self.pictures[index % len(self.pictures)])
                    apply.assert_not_called()
                    QTest.keyClick(window.carousel, Qt.Key.Key_Right)
                    apply.assert_not_called()
                    self.assertEqual(window.presentation.counter.text(), f'{(index + 1) % len(self.pictures) + 1:02d} / 09')
                    QTest.keyClick(window.carousel, Qt.Key.Key_Return)
                    self.assertEqual(apply.call_args.args[0], window.carousel.current())
                    self.assertTrue(window.busy); self.assertFalse(window.presentation.collections.isEnabled())
                    window.set_busy(False)

    def test_collection_search_slideshow_and_empty_results_share_selection(self):
        for style in ('frame-lab', 'orbit-atlas'):
            with self.subTest(style=style):
                window = self.window(style)
                window.presentation.collections.setCurrentRow(2)
                self.assertEqual(window.collection.currentData(), 'Modern')
                self.assertTrue(all(p.collection == 'Modern' for p in window.carousel.pictures))
                self.assertEqual(window.presentation.seek.maximum(), 2)
                with patch.object(window, 'begin_apply') as apply:
                    window.toggle_play(); self.assertTrue(window.play.isChecked()); window.advance()
                    self.assertEqual(window.carousel.current(), self.pictures[4])
                    window.search.setText('workstation 3'); self.assertFalse(window.play.isChecked())
                    self.assertEqual(window.carousel.current(), self.pictures[5])
                    window.search.setText('not a wallpaper'); self.assertIsNone(window.carousel.current())
                    self.assertFalse(window.apply.isEnabled()); self.assertFalse(window.play.isEnabled())
                    self.assertEqual(window.presentation.counter.text(), '00 / 00'); apply.assert_not_called()
                    window.search.clear(); self.assertEqual(len(window.carousel.pictures), 3)

    def test_small_and_large_layouts_keep_actions_reachable(self):
        for style in ('frame-lab', 'orbit-atlas'):
            with self.subTest(style=style):
                window = self.window(style)
                for width, height in ((960, 700), (1440, 850)):
                    # place() resolves the selected monitor and fits controls
                    # before imposing its available size on the window.
                    window.fit_layout(width, height); window.resize(width, height); QTest.qWait(25)
                    self.assertLessEqual(window.width(), width); self.assertLessEqual(window.height(), height)
                    self.assertEqual(window.presentation.sidebar.isVisible(), width >= 1120)
                    for widget in (window.search, window.collection, window.folder_button, window.apply, window.transition):
                        self.assertTrue(widget.isVisible(), widget.objectName())
                        point = widget.mapTo(window, widget.rect().center())
                        self.assertTrue(window.rect().contains(point), (style, widget.objectName(), point))
                    self.assertEqual(window.play.height(), window.play.width())

    def test_display_selection_cancel_and_confirm_use_shared_backend(self):
        for style in ('frame-lab', 'orbit-atlas'):
            with self.subTest(style=style):
                window = self.window(style)
                with patch.object(window, 'begin_apply') as apply, patch('wallpaper.browser.ScreenPicker') as picker:
                    picker.return_value.exec.return_value = QDialog.DialogCode.Rejected
                    window.choose(window.carousel.current()); apply.assert_not_called(); self.assertFalse(window.busy)
                    picker.return_value.exec.return_value = QDialog.DialogCode.Accepted
                    picker.return_value.selected = sample_monitors()[1]
                    window.choose(window.carousel.current()); self.assertEqual(apply.call_args.args[1]['name'], 'DP-2')
                    window.set_busy(False)

    def test_stale_metadata_cannot_replace_selected_image_details(self):
        for style in ('frame-lab', 'orbit-atlas'):
            with self.subTest(style=style):
                window = self.window(style); first = window.carousel.current()
                window.carousel.step(1); current = window.carousel.current()
                window.presentation.show_metadata(current.path, (2560, 1440, 'PNG'))
                window.presentation.show_metadata(first.path, (100, 100, 'JPEG'))
                self.assertEqual(window.presentation.resolution.text(), '2560 × 1440')
                self.assertEqual(window.presentation.format.text(), 'PNG')
                window.search.setText('missing picture')
                window.presentation.show_metadata(current.path, (2560, 1440, 'PNG'))
                self.assertEqual(window.presentation.resolution.text(), '—')


if __name__=='__main__': unittest.main()
