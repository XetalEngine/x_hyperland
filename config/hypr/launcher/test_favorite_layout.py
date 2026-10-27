import copy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import app
import catalog
import favorite_board
import favorite_layout as layout
import shortcuts

QT = QApplication.instance() or QApplication([])
QT.setStyle('Fusion')
QT.setStyleSheet(app.STYLE)


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = layout.Store(Path(self.temp.name) / 'layout.json')
        self.ids = [f'app-{i}.desktop' for i in range(10)]
        self.data, self.token = self.store.load(self.ids)

    def test_migrates_favorites_without_writing_or_changing_their_order(self):
        self.assertFalse(self.store.path.exists())
        self.assertEqual([t['app'] for t in self.data['groups'][0]['tiles']], self.ids)

    def test_order_group_and_size_survive_reload_and_new_favorites(self):
        other = layout.group('Tools', 2)
        self.data['groups'].append(other)
        layout.move_tile(self.data, self.ids[5], other['id'])
        layout.find_tile(self.data, self.ids[5])[1]['size'] = 'small'
        layout.move_tile(self.data, self.ids[1], self.data['groups'][0]['id'], self.ids[0])
        self.store.save(self.data, self.token)
        reloaded, _ = self.store.load([*reversed(self.ids), 'new.desktop'])
        self.assertEqual(reloaded['groups'][1], other)
        self.assertEqual(reloaded['groups'][0]['tiles'][0]['app'], self.ids[1])
        self.assertEqual(reloaded['groups'][0]['tiles'][-1]['app'], 'new.desktop')

    def test_unpin_removes_tile_without_deleting_its_group(self):
        self.store.save(self.data, self.token)
        updated, _ = self.store.load(self.ids[1:])
        self.assertEqual(len(updated['groups']), 1)
        self.assertNotIn(self.ids[0], [t['app'] for t in updated['groups'][0]['tiles']])

    def test_four_small_tiles_fill_one_medium_slot(self):
        tiles = [{'app': str(i), 'size': 'small' if i < 4 else 'medium'} for i in range(6)]
        result = layout.packed(tiles)
        self.assertEqual({(x, y) for _, x, y, _, _ in result[:4]}, {(0, 0), (71, 0), (0, 56), (71, 56)})
        self.assertEqual(result[4][1:], (142, 0, 142, 112))
        self.assertEqual(result[5][1:], (284, 0, 142, 112))

    def test_three_medium_tiles_per_row_and_no_mixed_tile_overlap(self):
        tiles = self.data['groups'][0]['tiles']
        self.assertEqual(layout.packed(tiles)[3][1:], (0, 112, 142, 112))
        for i in (0, 2, 4, 6, 7):tiles[i]['size'] = 'small'
        occupied = set()
        for _, x, y, w, h in layout.packed(tiles):
            cells = {(a, b) for a in range(x, x + w, 71) for b in range(y, y + h, 56)}
            self.assertFalse(occupied.intersection(cells))
            self.assertLessEqual(x + w, layout.COLUMN_WIDTH)
            occupied.update(cells)

    def test_removing_group_retains_apps_and_last_nonempty_group(self):
        other = layout.group('Keep apps')
        self.data['groups'].append(other)
        layout.remove_group(self.data, self.data['groups'][0]['id'])
        self.assertEqual([t['app'] for t in other['tiles']], self.ids)
        with self.assertRaises(ValueError):layout.remove_group(self.data, other['id'])

    def test_bad_state_and_external_edits_are_not_overwritten(self):
        self.store.path.write_text('{invalid')
        with self.assertRaises(ValueError):self.store.load(self.ids)
        with self.assertRaises(ValueError):self.store.save(self.data, self.token)
        self.assertEqual(self.store.path.read_text(), '{invalid')

    def test_duplicate_app_and_invalid_size_or_column_are_rejected(self):
        for change in ('duplicate', 'size', 'column'):
            data = copy.deepcopy(self.data)
            if change == 'duplicate':data['groups'][0]['tiles'].append(data['groups'][0]['tiles'][0])
            elif change == 'size':data['groups'][0]['tiles'][0]['size'] = 'large'
            else:data['groups'][0]['column'] = -1
            with self.subTest(change=change), self.assertRaises(ValueError):self.store.save(data, self.token)
        self.assertFalse(self.store.path.exists())

    def test_small_tiles_keep_a_vertical_column_and_empty_cells_after_reload(self):
        for ident in self.ids[:3]:layout.resize_tile(self.data, ident, 'small')
        group = self.data['groups'][0]
        for ident, row in zip(self.ids[:3], (0, 1, 4)):
            layout.place_tile(self.data, ident, group['id'], [0, row])
        self.store.save(self.data, self.token)
        reloaded, _ = self.store.load(self.ids)
        positions = {ident: (x, y) for ident, x, y, _, _ in layout.packed(reloaded['groups'][0]['tiles'])}
        self.assertEqual([positions[ident] for ident in self.ids[:3]], [(0, 0), (0, 56), (0, 224)])
        self.assertNotIn((71, 0), positions.values())

    def test_drop_on_occupied_cell_only_displaces_the_colliding_tile(self):
        group = self.data['groups'][0]
        before = {ident: (x, y) for ident, x, y, _, _ in layout.packed(group['tiles'])}
        layout.place_tile(self.data, self.ids[2], group['id'], [0, 0])
        after = {ident: (x, y) for ident, x, y, _, _ in layout.packed(group['tiles'])}
        self.assertEqual(after[self.ids[2]], (0, 0))
        self.assertEqual(after[self.ids[0]], before[self.ids[2]])
        for ident in self.ids[3:] + [self.ids[1]]:self.assertEqual(after[ident], before[ident])
        layout.validate(self.data)

    def test_growing_small_tile_makes_room_without_overlap_or_lost_apps(self):
        group = self.data['groups'][0]
        for ident in self.ids[:4]:layout.resize_tile(self.data, ident, 'small')
        for ident, cell in zip(self.ids[:4], ([0, 0], [1, 0], [0, 1], [1, 1])):
            layout.place_tile(self.data, ident, group['id'], cell)
        layout.resize_tile(self.data, self.ids[0], 'medium')
        self.assertEqual(layout.find_tile(self.data, self.ids[0])[1]['cell'], [0, 0])
        layout.validate(self.data)
        self.assertEqual({tile['app'] for tile in group['tiles']}, set(self.ids))

    def test_unpin_and_new_pin_keep_deliberate_gaps(self):
        group = self.data['groups'][0]
        layout.place_tile(self.data, self.ids[0], group['id'], [4, 8])
        layout.resize_tile(self.data, self.ids[1], 'small')
        expected = layout.find_tile(self.data, self.ids[0])[1]['cell'][:]
        updated = layout.reconcile(self.data, self.ids[2:] + [self.ids[0], 'new.desktop'])
        self.assertEqual(layout.find_tile(updated, self.ids[0])[1]['cell'], expected)
        layout.freeze(updated['groups'][0]);layout.validate(updated)

    def test_overlapping_or_out_of_bounds_saved_positions_are_rejected(self):
        for cell in ([0, 0], [5, 0], [-1, 2], [0, 999999], ['0', 1]):
            data = copy.deepcopy(self.data)
            data['groups'][0]['tiles'][0]['cell'] = [0, 0]
            data['groups'][0]['tiles'][1]['cell'] = cell
            with self.subTest(cell=cell), self.assertRaises(ValueError):layout.validate(data)


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ids = [f'test-{i}.desktop' for i in range(10)]
        self.entries = {ident: shortcuts.Entry(ident, None, {'name': f'Application {i}',
                        'command': '/usr/bin/printf test', 'icon': 'utilities-terminal'}, custom=True)
                        for i, ident in enumerate(self.ids)}
        self.patches = [patch.object(layout, 'STATE', self.root / 'layout.json'),
                        patch.object(app.geometry, 'STATE', self.root / 'window.json'),
                        patch.object(catalog, 'applications', return_value=self.entries),
                        patch.object(catalog, 'favorites', return_value=self.ids)]
        for p in self.patches:p.start()
        self.menu = app.Menu(preview=True)
        self.menu.resize(1400, 850)
        self.menu.show()
        QTest.qWait(220)
        self.calls = []
        self.menu.launch_app = lambda *args: self.calls.append(args)

    def tearDown(self):
        self.menu.close()
        self.menu.deleteLater()
        QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def add_group(self, title='Tools', column=1):
        item = layout.group(title, column)
        self.menu.change_layout(lambda data: data['groups'].append(item))
        QT.processEvents()
        return item['id']

    def drop(self, kind, ident, point):
        board = self.menu.favorites_board
        mime = board.mime(kind, ident)
        enter = QDragEnterEvent(point, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QT.sendEvent(board.canvas, enter)
        self.assertTrue(enter.isAccepted())
        event = QDropEvent(QPointF(point), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QT.sendEvent(board.canvas, event)
        self.assertTrue(event.isAccepted())
        QT.processEvents()

    def test_native_drop_reorders_and_moves_to_another_group_without_launching(self):
        board = self.menu.favorites_board
        point = board.tiles[self.ids[0]].geometry().topLeft() + QPoint(12, 12)
        self.drop('tile', self.ids[2], point)
        self.assertEqual(self.menu.favorite_layout['groups'][0]['tiles'][0]['app'], self.ids[2])
        second = self.add_group()
        region = next(g for g in board.regions if g['id'] == second)
        self.drop('tile', self.ids[2], region['body'].center())
        self.assertEqual(layout.find_tile(self.menu.favorite_layout, self.ids[2])[0]['id'], second)
        self.assertEqual(self.calls, [])
        self.menu.select_page('Favorites')
        self.assertEqual(layout.find_tile(self.menu.favorite_layout, self.ids[2])[0]['id'], second)

    def test_drop_in_new_column_creates_group_and_group_title_can_move_back(self):
        board = self.menu.favorites_board
        self.drop('tile', self.ids[0], board.empty_columns[1].center())
        created = self.menu.favorite_layout['groups'][-1]
        self.assertEqual(created['column'], 1)
        self.assertEqual(created['tiles'][0]['app'], self.ids[0])
        first = board.regions[0]
        self.drop('group', created['id'], first['header'].center())
        self.assertEqual(self.menu.favorite_layout['groups'][0]['id'], created['id'])
        self.assertEqual(self.menu.favorite_layout['groups'][0]['column'], 0)

    def test_resize_hides_columns_without_repositioning_or_saving(self):
        second = self.add_group()
        self.menu.perform('tile-group:' + second, self.ids[0])
        board = self.menu.favorites_board
        original = board.tiles[self.ids[0]].geometry()
        saved = layout.STATE.read_bytes()
        self.menu.resize(780, 700)
        QTest.qWait(20)
        self.assertTrue(board.tiles[self.ids[0]].isHidden())
        self.assertEqual(board.tiles[self.ids[0]].geometry(), original)
        self.menu.resize(1400, 900)
        QTest.qWait(20)
        self.assertFalse(board.tiles[self.ids[0]].isHidden())
        self.assertEqual(board.tiles[self.ids[0]].geometry(), original)
        self.assertEqual(layout.STATE.read_bytes(), saved)

    def test_size_menu_persists_quarter_area_and_small_tile_omits_text(self):
        for ident in self.ids[:4]:self.menu.perform('tile-size:small', ident)
        board = self.menu.favorites_board
        small, medium = board.tiles[self.ids[0]], board.tiles[self.ids[4]]
        self.assertEqual(small.width() * small.height() * 4, medium.width() * medium.height())
        self.menu.select_page('Favorites')
        self.assertEqual(board.tiles[self.ids[0]].size_name, 'small')
        icon = app.icon_for(self.entries[self.ids[0]])
        def render(name, keys, small):
            image = QImage(71 if small else 142, 56 if small else 112, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            app.Tiles.draw(painter, image.rect(), icon, name, keys, small=small)
            painter.end()
            return image
        self.assertEqual(render('Name one', ['Super+A'], True), render('Different name', ['Super+B'], True))
        self.assertNotEqual(render('Name one', ['Super+A'], False), render('Different name', ['Super+B'], False))

    def test_cancelled_drag_does_not_launch_and_following_click_still_works(self):
        board = self.menu.favorites_board
        tile = board.tiles[self.ids[0]]
        depths = []
        drag = MagicMock()
        drag.exec.side_effect = lambda action: depths.append(self.menu.interaction_depth)
        QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(60, 60), QPointF(tile.mapToGlobal(QPoint(60, 60))),
                            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        with patch.object(favorite_board, 'QDrag', return_value=drag):QT.sendEvent(tile, event)
        QTest.mouseRelease(tile, Qt.MouseButton.LeftButton, pos=QPoint(60, 60))
        self.assertEqual(self.calls, [])
        self.assertEqual(depths, [1])
        self.assertEqual(self.menu.interaction_depth, 0)
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton, pos=tile.rect().center())
        self.assertEqual(self.calls, [(self.ids[0],)])

    def test_group_creation_rename_and_keyboard_navigation(self):
        with patch.object(app.QInputDialog, 'getText', return_value=('My tools', True)):
            self.menu.new_group(1)
        group = self.menu.favorite_layout['groups'][-1]
        with patch.object(app.QInputDialog, 'getText', return_value=('Work', True)):
            self.menu.rename_group(group['id'])
        self.assertEqual(self.menu.favorite_layout['groups'][-1]['title'], 'Work')
        self.menu.search.setFocus()
        QTest.keyClick(self.menu.search, Qt.Key.Key_Down)
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Right)
        self.assertEqual(self.menu.favorites_board.selected, self.ids[1])
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Return)
        self.assertEqual(self.calls, [(self.ids[1],)])

    def test_search_keeps_alphabetical_grid_and_restores_grouped_layout(self):
        self.menu.search.setText('Application 8')
        self.assertIs(self.menu.views.currentWidget(), self.menu.grid)
        self.assertEqual(self.menu.grid.count(), 1)
        self.menu.search.clear()
        self.assertIs(self.menu.views.currentWidget(), self.menu.favorites_board)
        self.menu.select_page('All apps')
        self.assertIs(self.menu.views.currentWidget(), self.menu.grid)

    def test_foreign_drag_is_rejected(self):
        board = self.menu.favorites_board
        mime = board.mime('tile', self.ids[0])
        payload = json.loads(bytes(mime.data(favorite_board.MIME)))
        payload['token'] = 'different menu'
        mime.setData(favorite_board.MIME, json.dumps(payload).encode())
        event = QDragEnterEvent(QPoint(20, 80), Qt.DropAction.MoveAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QT.sendEvent(board.canvas, event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(layout.STATE.exists())

    def test_small_tile_can_drop_below_another_without_filling_the_row(self):
        for ident in self.ids[:2]:self.menu.perform('tile-size:small', ident)
        board = self.menu.favorites_board
        origin = board.regions[0]['body'].topLeft()
        point = origin + QPoint(25, 56 + 20)
        payload = {'kind': 'tile', 'id': self.ids[1]}
        board.hover_drop(payload, point)
        self.assertEqual(board.drop_hint.topLeft(), origin + QPoint(0, 56))
        self.drop('tile', self.ids[1], point)
        first, second = board.tiles[self.ids[0]], board.tiles[self.ids[1]]
        self.assertEqual(second.geometry().topLeft(), first.geometry().topLeft() + QPoint(0, 56))
        self.menu.select_page('Favorites')
        self.assertEqual(board.tiles[self.ids[1]].geometry().topLeft(), origin + QPoint(0, 56))
        self.assertEqual(self.calls, [])

    def test_creation_actions_are_only_in_empty_space_and_properties_is_last(self):
        for ident in (None, self.ids[0]):
            menu = self.menu.build_context_menu(ident)
            actions = [action.data() for action in menu.actions()]
            self.assertEqual('new' in actions, ident is None)
            self.assertEqual('new-group' in actions, ident is None)
            if ident:
                self.assertEqual(menu.actions()[-1].text(), 'Properties')
                self.assertEqual(actions[-1], 'edit')
            menu.deleteLater()

    def test_screenshot_focus_loss_keeps_menu_until_capture_lock_is_released(self):
        runtime = self.root / 'runtime'
        path = runtime / 'hypr' / 'test' / 'screenshot-active.lock'
        path.parent.mkdir(parents=True)
        self.menu.preview = False
        self.menu.started -= 2
        with (patch.dict(os.environ, XDG_RUNTIME_DIR=str(runtime), HYPRLAND_INSTANCE_SIGNATURE='test'),
              patch.object(self.menu, 'isActiveWindow', return_value=False),
              patch.object(self.menu, 'close') as close, path.open('wb') as guard):
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.menu.close_if_outside()
            close.assert_not_called()
            fcntl.flock(guard, fcntl.LOCK_UN)
            self.menu.close_if_outside()
            close.assert_called_once_with()
        self.menu.preview = True


if __name__ == '__main__':unittest.main()
