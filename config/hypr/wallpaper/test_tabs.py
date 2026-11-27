"""Tab ownership, persistence, dialogs and the native Qt drop contract."""
import copy
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
from PyQt6.QtCore import Qt, QPointF, QMimeData, QTimer
from PyQt6.QtGui import QColor, QContextMenuEvent, QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent, QImage, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QToolButton
from wallpaper import library
from wallpaper.browser import Browser
from wallpaper.tabs import MIME


class TabModelTests(unittest.TestCase):
    def test_original_hidden_collection_migrates_without_losing_any_paths(self):
        paths = [f'/pictures/wallpaper-{i}.png' for i in range(94)]
        value = library.normalize({'version':1,'hidden':paths})
        self.assertEqual(value['hidden'],paths)
        self.assertEqual(value['hidden_tabs'],[{'id':'hidden','name':'Hidden','paths':paths}])
        self.assertEqual(value['active_hidden_tab'],'hidden')

    def test_create_move_rename_and_delete_preserve_global_membership(self):
        paths = ['/pictures/one.png','/pictures/missing.png','/videos/clip.mp4']
        value = library.normalize({**library.DEFAULTS,'hidden':paths})
        original = copy.deepcopy(value)
        value = library.add_hidden_tab(value,'  Nature  '); nature = value['active_hidden_tab']
        value = library.move_hidden_picture(value,paths[0],nature)
        value = library.rename_hidden_tab(value,nature,'Favorites')
        self.assertEqual(library.hidden_tab(value)['name'],'Favorites')
        self.assertEqual(library.hidden_tab(value)['paths'],paths[:1])
        value = library.transfer_hidden_tab(value,'hidden',nature)
        self.assertEqual(value['hidden'],paths); self.assertEqual(set(library.hidden_tab(value)['paths']),set(paths))
        self.assertEqual(len(value['hidden_tabs']),1); self.assertEqual(original['hidden_tabs'][0]['paths'],paths)
        with self.assertRaises(ValueError): library.transfer_hidden_tab(value,nature,nature)

    def test_names_ids_and_ownership_are_validated(self):
        value = library.normalize({**library.DEFAULTS,'hidden':['/pictures/a.png']})
        for name in ('','  ','hidden','HIDDEN','a'*49,'Line\nbreak'):
            with self.subTest(name=name),self.assertRaises(ValueError): library.add_hidden_tab(value,name)
        value = library.add_hidden_tab(value,'Other')
        duplicate = copy.deepcopy(value); duplicate['hidden_tabs'][1]['paths']=['/pictures/a.png']
        with self.assertRaisesRegex(ValueError,'only one'): library.normalize(duplicate)
        invalid = copy.deepcopy(value); invalid['hidden_tabs'][1]['id']='../outside'
        with self.assertRaises(ValueError): library.normalize(invalid)
        value['active_hidden_tab']='deleted'; self.assertEqual(library.normalize(value)['active_hidden_tab'],'hidden')

    def test_unhide_removes_tab_membership_and_other_preferences_merge(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)/'browser.json'; first = library.read(path)
            value = library.add_hidden_tab(first,'Games')
            value = library.save({**value,'hidden':['/pictures/game.png']},first,path,fields=library.HIDDEN_FIELDS)
            self.assertEqual(library.hidden_tab(value)['paths'],value['hidden'])
            independent = library.save({**first,'transition':'fade'},first,path,fields=('transition',))
            self.assertEqual(independent['hidden_tabs'],value['hidden_tabs'])
            self.assertEqual(independent['active_hidden_tab'],value['active_hidden_tab'])
            after = library.save({**value,'hidden':[]},value,path,fields=library.HIDDEN_FIELDS)
            self.assertFalse(library.hidden_tab(after)['paths']); self.assertEqual(after['transition'],'fade')
            with self.assertRaisesRegex(ValueError,'elsewhere'):
                library.save(first,first,path,fields=library.HIDDEN_FIELDS)


class TabInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([]); cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.windows = []; self.pictures = []
        self.image = QImage(160,90,QImage.Format.Format_RGB32); self.image.fill(QColor('#268ac0'))
        for i in range(4):
            path = self.root/f'Picture-{i}.png'; self.image.save(str(path)); self.pictures.append(library.Picture(str(path),'Test'))
        for mock in (patch.object(library,'PREFERENCES',self.root/'browser.json'),patch.object(Browser,'scan')):
            mock.start(); self.addCleanup(mock.stop)
        self.window = self.make_window()

    def make_window(self):
        w = Browser(preview=True,style='overlay'); self.windows.append(w)
        w.reduced_motion = True; w.carousel.reduced_motion = True
        for picture in self.pictures:
            w.thumbnails.cache[picture.path] = QPixmap.fromImage(self.image)
            w.hidden_dock.thumbnails.cache[picture.path] = QPixmap.fromImage(self.image)
        w.scanned(w.cancel_scan,(list(self.pictures),[],'')); w.resize(1200,800); w.show(); QTest.qWait(20)
        return w

    def tearDown(self):
        for w in self.windows: w.hide(); w.shutdown(); w.deleteLater()
        self.app.processEvents()

    def dialog(self, action, answer):
        errors = []
        def reply():
            try: answer(self.window.dialog)
            except BaseException as error: errors.append(error)
            finally:
                if self.window.dialog.isVisible(): self.window.dialog.reject()
        QTimer.singleShot(0,reply); action()
        if errors: raise errors[0]

    def add_tab(self, name):
        self.dialog(self.window.hidden_dock.add_tab.click,lambda d:(d.name.setText(name),d.accept()))
        return self.window.options['active_hidden_tab']

    def test_buttons_create_rename_remember_active_and_hide_into_that_tab(self):
        w = self.window; first = self.pictures[0]; w.hide_picture(first)
        nature = self.add_tab('Nature'); self.assertEqual(w.hidden_dock.pictures,[])
        w.hide_picture(self.pictures[1])
        self.assertEqual(w.hidden_dock.pictures,[self.pictures[1]])
        self.assertNotIn(first,w.carousel.pictures); self.assertNotIn(self.pictures[1],w.carousel.pictures)
        self.dialog(w.hidden_dock.rename_tab.click,lambda d:(d.name.setText('Landscapes'),d.accept()))
        reopened = self.make_window()
        self.assertEqual(reopened.options['active_hidden_tab'],nature)
        self.assertEqual(library.hidden_tab(reopened.options)['name'],'Landscapes')
        self.assertEqual(reopened.hidden_dock.pictures,[self.pictures[1]])
        w.switch_hidden_tab('hidden'); self.assertEqual(w.hidden_dock.pictures,[first])
        self.assertEqual(library.read()['active_hidden_tab'],'hidden')

    def test_delete_requires_destination_and_cancel_preserves_everything(self):
        w = self.window; w.hide_picture(self.pictures[0]); destination = self.add_tab('Favorites')
        w.hide_picture(self.pictures[1]); w.switch_hidden_tab('hidden')
        before = library.read()
        def cancel(d):
            self.assertIsNone(d.destination.currentData()); self.assertFalse(d.confirm.isEnabled())
            self.assertEqual(d.destination.count(),2); d.accept(); self.assertTrue(d.isVisible())
            QTest.keyClick(d,Qt.Key.Key_Escape)
        self.dialog(w.hidden_dock.delete_tab.click,cancel)
        self.assertEqual(library.read(),before); self.assertTrue(w.isVisible())
        def transfer(d):
            d.destination.setCurrentIndex(d.destination.findData(destination)); self.assertTrue(d.confirm.isEnabled()); d.confirm.click()
        self.dialog(w.hidden_dock.delete_tab.click,transfer)
        self.assertEqual(len(w.options['hidden_tabs']),1); self.assertEqual(w.options['active_hidden_tab'],destination)
        self.assertEqual(set(w.options['hidden']),{p.path for p in self.pictures[:2]})
        self.assertEqual(set(p.path for p in w.hidden_dock.pictures),set(w.options['hidden']))
        self.assertFalse(w.hidden_dock.delete_tab.isEnabled())
        for p in self.pictures: self.assertTrue(Path(p.path).is_file())

    def test_delete_save_failure_keeps_source_and_membership(self):
        w = self.window; w.hide_picture(self.pictures[0]); destination = self.add_tab('Other'); w.switch_hidden_tab('hidden')
        before = library.read()
        def fail(d):
            d.destination.setCurrentIndex(d.destination.findData(destination))
            with patch.object(library,'save',side_effect=PermissionError('Read-only preferences')): d.accept()
            self.assertTrue(d.isVisible()); self.assertIn('Read-only',d.error.text()); d.reject()
        self.dialog(w.hidden_dock.delete_tab.click,fail); self.assertEqual(library.read(),before)

    def test_duplicate_name_stays_in_dialog_until_corrected_or_cancelled(self):
        self.add_tab('Favorites'); before = library.read()
        def invalid(d):
            d.name.setText(' hidden '); d.accept(); self.assertTrue(d.isVisible()); self.assertIn('own name',d.error.text()); d.reject()
        self.dialog(self.window.hidden_dock.add_tab.click,invalid); self.assertEqual(library.read(),before)

    def prepare_drag(self):
        w = self.window; w.hide_picture(self.pictures[0]); other = self.add_tab('Move here'); w.switch_hidden_tab('hidden')
        dock = w.hidden_dock; dock.drag_path = self.pictures[0].path
        bar = dock.tabbar; point = bar.tabRect(1).center(); mime = dock.drag_mime(dock.drag_path)
        return w,dock,bar,point,mime,other

    def event(self, event_type, point, mime):
        return event_type(point,Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)

    def test_drop_highlights_destination_moves_once_and_keeps_wallpaper_hidden(self):
        w,dock,bar,point,mime,other = self.prepare_drag()
        enter = self.event(QDragEnterEvent,point,mime); bar.dragEnterEvent(enter); self.assertTrue(enter.isAccepted())
        move = self.event(QDragMoveEvent,point,mime); bar.dragMoveEvent(move)
        self.assertTrue(move.isAccepted()); self.assertEqual(bar.drop_index,1); self.assertIn('Release to move',dock.drop_hint)
        drop = self.event(QDropEvent,QPointF(point),mime); bar.dropEvent(drop)
        self.assertTrue(drop.isAccepted()); self.assertEqual(w.options['active_hidden_tab'],other)
        self.assertEqual(library.hidden_tab(w.options,other)['paths'],[dock.drag_path])
        self.assertFalse(library.hidden_tab(w.options,'hidden')['paths'])
        self.assertEqual(w.options['hidden'],[dock.drag_path]); self.assertNotIn(self.pictures[0],w.carousel.pictures)
        self.assertEqual(bar.drop_index,-1); self.assertEqual(library.read()['active_hidden_tab'],other)
        dock.drag_path = ''

    def test_drag_cancel_foreign_payload_and_same_tab_do_not_mutate_preferences(self):
        w,dock,bar,point,mime,_ = self.prepare_drag(); before = library.read()
        bar.dragMoveEvent(self.event(QDragMoveEvent,point,mime)); bar.dragLeaveEvent(QDragLeaveEvent())
        self.assertEqual(bar.drop_index,-1); self.assertEqual(library.read(),before)
        own = self.event(QDropEvent,QPointF(bar.tabRect(0).center()),mime); bar.dropEvent(own); self.assertFalse(own.isAccepted())
        for payload in (b'invalid',json.dumps({'path':dock.drag_path,'token':'another-app','tab':'hidden'}).encode()):
            foreign = QMimeData(); foreign.setData(MIME,payload)
            enter = self.event(QDragEnterEvent,point,foreign); bar.dragEnterEvent(enter); self.assertFalse(enter.isAccepted())
        self.assertEqual(library.read(),before); dock.drag_path = ''

    def test_failed_tab_activation_restores_previous_selection(self):
        w = self.window; self.add_tab('Other'); w.switch_hidden_tab('hidden')
        with patch.object(library,'save',side_effect=PermissionError('Read-only preferences')):
            w.hidden_dock.tabbar.setCurrentIndex(1)
        self.assertEqual(w.options['active_hidden_tab'],'hidden'); self.assertEqual(w.hidden_dock.tabbar.currentIndex(),0)

    def test_thumbnail_menu_moves_to_a_tab_without_restoring(self):
        w,dock,_,_,_,other = self.prepare_drag(); dock.drag_path = ''
        point = dock.location(self.pictures[0].path).center().toPoint()
        errors=[]
        def choose():
            menu=QApplication.activePopupWidget()
            try:
                submenu=menu.actions()[1].menu(); submenu.actions()[1].trigger()
            except BaseException as error: errors.append(error)
            finally: menu.close()
        QTimer.singleShot(0,choose)
        dock.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse,point,dock.mapToGlobal(point)))
        if errors: raise errors[0]
        self.assertEqual(w.options['active_hidden_tab'],other)
        self.assertEqual(w.options['hidden'],[self.pictures[0].path]); self.assertNotIn(self.pictures[0],w.carousel.pictures)

    def test_hovering_over_tab_scroll_arrows_reaches_overflow_without_moving_a_picture(self):
        w,dock,bar,_,mime,_ = self.prepare_drag(); value = w.options
        for i in range(12): value = library.add_hidden_tab(value,f'Collection {i+1}')
        value['active_hidden_tab']='hidden'; w.options=library.save(value,w.options,fields=library.HIDDEN_FIELDS)
        w.refresh_hidden_dock(); dock.setFixedWidth(600); QTest.qWait(30)
        arrow = next(b for b in bar.findChildren(QToolButton) if b.isVisible() and b.arrowType()==Qt.ArrowType.RightArrow)
        point = arrow.geometry().center(); before = library.read(); old_x = bar.tabRect(0).x()
        bar.dragEnterEvent(self.event(QDragEnterEvent,point,mime)); bar.dragMoveEvent(self.event(QDragMoveEvent,point,mime))
        self.assertTrue(bar.scroll_timer.isActive()); self.assertEqual(bar.drop_index,-1)
        QTest.qWait(530); self.assertLess(bar.tabRect(0).x(),old_x)
        drop = self.event(QDropEvent,QPointF(point),mime); bar.dropEvent(drop)
        self.assertFalse(drop.isAccepted()); self.assertFalse(bar.scroll_timer.isActive())
        self.assertEqual(library.read(),before); dock.drag_path = ''


if __name__=='__main__': unittest.main()
