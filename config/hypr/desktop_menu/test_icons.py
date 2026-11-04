"""Layouts use temporary files; GUI checks opt in on a private test display."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock, ANY
import icons_model as model


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'icons.json'
        self.store = model.Store(self.path)
        self.settings = model.defaults()
        self.areas = {'MAIN': (16, 48, 500, 380), 'SIDE': (16, 48, 700, 500)}
        self.names = ['Folder', 'notes # 100% café.txt', 'photo.png', 'video.mp4']

    def test_opt_in_and_columns_are_fresh_defaults(self):
        self.assertFalse(self.settings['enabled']); self.assertTrue(self.settings['auto_align'])
        self.assertFalse(self.settings['auto_arrange'])
        points = list(model.layout(self.names, self.areas, self.settings)['MAIN'].values())
        self.assertEqual(points[0][0], points[1][0]); self.assertGreater(points[1][1], points[0][1])
        self.settings['flow'] = 'rows'
        points = list(model.layout(self.names, self.areas, self.settings)['MAIN'].values())
        self.assertEqual(points[0][1], points[1][1]); self.assertGreater(points[1][0], points[0][0])
        self.assertFalse(self.path.exists())

    def test_arrangement_and_settings_survive_restart(self):
        self.store.change(lambda data: data.update(enabled=True, auto_align=False, flow='rows'))
        self.store.change(lambda data: model.move(data, self.names, self.areas, 'SIDE', [self.names[0]], (210, 190)))
        saved = model.Store(self.path).load()
        self.assertTrue(saved['enabled']); self.assertFalse(saved['auto_align']); self.assertEqual(saved['flow'], 'rows')
        self.assertEqual(model.layout(self.names, self.areas, saved)['SIDE'][self.names[0]], (210, 190))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_auto_arrange_packs_and_reorders(self):
        self.settings['auto_arrange'] = True
        model.move(self.settings, self.names, self.areas, 'MAIN', ['video.mp4'], (16, 48))
        arranged = model.layout(self.names, self.areas, self.settings)['MAIN']
        self.assertEqual(next(iter(arranged)), 'video.mp4')
        self.assertEqual(len(set(arranged.values())), len(self.names))

    def test_auto_align_keeps_custom_grid_cells_and_gaps_after_restart(self):
        before = model.layout(self.names, self.areas, self.settings)['MAIN']
        self.store.change(lambda data: model.move(data, self.names, self.areas, 'MAIN', ['video.mp4'], (340, 260)))
        settings = model.Store(self.path).load()
        placed = model.layout(self.names, self.areas, settings)['MAIN']
        self.assertEqual(placed['video.mp4'], (352, 276))
        self.assertNotIn(before['video.mp4'], placed.values())
        for name in self.names[:-1]: self.assertEqual(placed[name], before[name])
        changed = model.layout([*self.names[1:], 'a new file.txt'], self.areas, settings)['MAIN']
        for name in self.names[1:]: self.assertEqual(changed[name], placed[name])
        self.assertEqual(changed['a new file.txt'], before['Folder'])

    def test_auto_align_occupied_cell_keeps_the_other_icons_in_place(self):
        before = model.layout(self.names, self.areas, self.settings)['MAIN']
        model.move(self.settings, self.names, self.areas, 'MAIN', ['Folder'], before['photo.png'])
        after = model.layout(self.names, self.areas, self.settings)['MAIN']
        self.assertEqual(after['Folder'], (128, 276))
        for name in self.names[1:]: self.assertEqual(after[name], before[name])
        self.assertEqual(len(set(after.values())), len(self.names))

    def test_auto_align_group_keeps_offsets_on_another_monitor(self):
        before = model.layout(self.names, self.areas, self.settings)['MAIN']
        model.move(self.settings, self.names, self.areas, 'SIDE', self.names[:2], (245, 175), 'Folder')
        after = model.layout(self.names, self.areas, self.settings)['SIDE']
        self.assertEqual(after['Folder'], (240, 162))
        a, b = self.names[:2]
        self.assertEqual((after[b][0]-after[a][0], after[b][1]-after[a][1]),
                         (before[b][0]-before[a][0], before[b][1]-before[a][1]))

    def test_align_now_preserves_gaps_and_arrange_now_compacts(self):
        self.settings['auto_align'] = False
        model.move(self.settings, self.names, self.areas, 'MAIN', ['video.mp4'], (340, 260))
        model.align(self.settings, self.names, self.areas)
        self.assertEqual(model.layout(self.names, self.areas, self.settings)['MAIN']['video.mp4'], (352, 276))
        model.arrange(self.settings, self.names, self.areas)
        self.assertEqual(set(model.layout(self.names, self.areas, self.settings)['MAIN'].values()),
                         {model.grid(self.areas['MAIN'], self.settings, i) for i in range(len(self.names))})

    def test_legacy_preferences_default_to_manual_grid_positions(self):
        legacy = model.defaults(); legacy.pop('auto_arrange')
        self.path.write_text(json.dumps(legacy))
        before = self.path.read_bytes()
        self.assertFalse(self.store.load()['auto_arrange'])
        self.assertEqual(self.path.read_bytes(), before)
        legacy['auto_arrange'] = 'yes'
        with self.assertRaises(ValueError): model.validate(legacy)

    def test_free_group_placement_keeps_offsets(self):
        model.align(self.settings, self.names, self.areas)
        self.settings['auto_align'] = False
        original = model.layout(self.names, self.areas, self.settings)['MAIN']
        model.move(self.settings, self.names, self.areas, 'SIDE', self.names[:2], (200, 100))
        moved = model.layout(self.names, self.areas, self.settings)['SIDE']
        a, b = self.names[:2]
        self.assertEqual((moved[b][0]-moved[a][0], moved[b][1]-moved[a][1]),
                         (original[b][0]-original[a][0], original[b][1]-original[a][1]))

    def test_missing_monitor_falls_back_and_returns_without_rewriting_memory(self):
        self.settings['auto_align'] = False
        model.move(self.settings, self.names, self.areas, 'SIDE', ['Folder'], (220, 180))
        before = copy.deepcopy(self.settings)
        fallback = model.layout(self.names, {'MAIN': self.areas['MAIN']}, self.settings)
        self.assertIn('Folder', fallback['MAIN'])
        self.assertEqual(self.settings, before)
        self.assertEqual(model.layout(self.names, self.areas, self.settings)['SIDE']['Folder'], (220, 180))

    def test_resize_keeps_free_positions_inside_workarea(self):
        self.settings['auto_align'] = False
        model.move(self.settings, self.names, self.areas, 'MAIN', ['Folder'], (10000, -50))
        area = (10, 60, 200, 170)
        x, y = model.layout(self.names, {'MAIN': area}, self.settings)['MAIN']['Folder']
        width, height = model.cell(self.settings)
        self.assertGreaterEqual(x, area[0]); self.assertGreaterEqual(y, area[1])
        self.assertLessEqual(x+width, area[0]+area[2]); self.assertLessEqual(y+height, area[1]+area[3])

    def test_invalid_settings_are_preserved(self):
        self.path.write_text('{broken')
        with self.assertRaises(ValueError): self.store.change(lambda data: data.update(enabled=True))
        self.assertEqual(self.path.read_text(), '{broken')
        for name, position in [('../escape', dict(monitor='MAIN', order=0, x=0, y=0)),
                               ('File', dict(monitor='MAIN', order=0, x=float('nan'), y=0))]:
            value = model.defaults(); value['positions'][name] = position
            with self.assertRaises(ValueError): model.validate(value)

    def test_separate_writers_keep_unrelated_settings(self):
        other = model.Store(self.path)
        self.store.change(lambda data: data.update(enabled=True))
        other.change(lambda data: data.update(size=72))
        self.assertTrue(self.store.load()['enabled']); self.assertEqual(self.store.load()['size'], 72)

    def test_optional_trash_has_persistent_position_without_a_fake_file(self):
        self.assertFalse(self.settings['show_trash'])
        self.assertFalse(model.valid_name(model.TRASH))
        self.store.change(lambda data: data.update(show_trash=True))
        names = [*self.names, model.TRASH]
        self.store.change(lambda data: model.move(data, names, self.areas, 'SIDE', [model.TRASH], (240, 162)))
        saved = self.store.load()
        self.assertTrue(saved['show_trash'])
        self.assertEqual(model.layout(names, self.areas, saved)['SIDE'][model.TRASH], (240, 162))


@unittest.skipUnless(os.environ.get('FUSION_DESKTOP_TEST_GUI') == '1', 'Run on a private display with FUSION_DESKTOP_TEST_GUI=1')
class CanvasTests(unittest.TestCase):
    def setUp(self):
        import desktop_icons as icons
        self.icons = icons
        self.Gtk, self.Gdk, self.GLib = icons.Gtk, icons.Gdk, icons.GLib
        self.assertTrue(self.Gtk.init_check()[0])
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root/'Desktop').mkdir()
        (root/'Desktop/Folder').mkdir()
        (root/'Desktop/notes # café.txt').write_text('fixture')
        (root/'Desktop/.hidden').write_text('hidden')
        self.owner = Mock()
        self.fake_files = Mock()
        self.store = model.Store(root/'icons.json')
        with patch.object(icons.model, 'Store', return_value=self.store), patch.object(icons, 'Files', return_value=self.fake_files):
            self.controller = icons.Icons(self.owner, {})
        self.controller.root = root/'Desktop'
        self.window = self.Gtk.Window(); self.window.desktop_monitor = self.Gdk.Display.get_default().get_monitor(0)
        self.window.menu = None
        self.window.set_default_size(760, 560)
        self.controller.attach(self.window)
        self.window.show_all()
        self.addCleanup(self.finish)
        self.controller.setting('enabled', True)
        self.wait(lambda: len(self.controller.entries) == 2)
        self.wait(lambda: len(next(iter(self.controller.canvases.values())).tiles) == 2)
        self.canvas = self.controller.canvases[self.window]

    def finish(self):
        self.controller.dispose(); self.window.destroy()
        while self.GLib.MainContext.default().pending(): self.GLib.MainContext.default().iteration(False)

    def wait(self, predicate):
        deadline = time.monotonic()+4
        while time.monotonic() < deadline:
            while self.GLib.MainContext.default().pending(): self.GLib.MainContext.default().iteration(False)
            if predicate(): return
            time.sleep(.01)
        self.fail('Timed out waiting for the desktop view')

    def test_real_files_watch_rename_and_saved_free_positions(self):
        self.controller.setting('auto_align', False)
        self.controller.reposition(self.canvas.monitor, ['Folder'], (230, 190))
        self.wait(lambda: self.canvas.positions['Folder'] == (230, 190))
        (self.controller.root/'Folder').rename(self.controller.root/'Renamed')
        self.wait(lambda: 'Renamed' in self.canvas.positions and 'Folder' not in self.canvas.positions)
        self.assertEqual(self.canvas.positions['Renamed'], (230, 190))
        (self.controller.root/'new.txt').write_text('new')
        self.wait(lambda: 'new.txt' in self.canvas.positions)
        (self.controller.root/'new.txt').unlink()
        self.wait(lambda: 'new.txt' not in self.canvas.positions)

    def test_menu_toggle_and_layout_controls(self):
        menu = self.Gtk.Menu(); self.controller.append_menu(menu, 0)
        items = {item.get_label(): item for item in menu.get_children() if hasattr(item, 'get_label')}
        self.assertTrue(items['Show Desktop icons'].get_active())
        arrange = {item.get_label(): item for item in items['Arrange icons'].get_submenu().get_children() if hasattr(item, 'get_label')}
        self.assertTrue(arrange['Columns'].get_active())
        self.assertTrue(arrange['Auto align'].get_active())
        self.assertFalse(arrange['Auto arrange'].get_active())
        before = dict(self.canvas.positions)
        arrange['Rows'].set_active(True)
        self.assertEqual(self.store.load()['flow'], 'rows')
        self.wait(lambda: not self.controller.layout_pending)
        self.assertEqual(self.canvas.positions, before)
        arrange['Auto arrange'].set_active(True)
        self.wait(lambda: len(set(p[1] for p in self.canvas.positions.values())) == 1)
        packed = dict(self.canvas.positions)
        arrange['Auto arrange'].set_active(False)
        self.wait(lambda: not self.controller.layout_pending)
        self.assertEqual(self.canvas.positions, packed)
        items['Show Desktop icons'].set_active(False)
        self.wait(lambda: not self.canvas.tiles)
        self.assertFalse(self.store.load()['enabled'])
        menu.destroy()

    def test_selection_opens_through_files_and_keyboard_trashes(self):
        tile = self.canvas.tiles['Folder']
        event = self.Gdk.EventButton(); event.type = self.Gdk.EventType.DOUBLE_BUTTON_PRESS
        event.button = 1; event.x = 25; event.y = 25; event.state = self.Gdk.ModifierType(0)
        self.controller.select({'Folder'}); tile.pressed(tile, event)
        self.fake_files.open.assert_called_once_with([self.controller.uri('Folder')])
        key = self.Gdk.EventKey(); key.type = self.Gdk.EventType.KEY_PRESS
        key.keyval = self.Gdk.KEY_Delete; key.state = self.Gdk.ModifierType(0)
        self.canvas.key(self.canvas, key)
        self.fake_files.call.assert_called_once_with('Trash', '(as)', [self.controller.uri('Folder')], on_reply=ANY)

    def test_trash_icon_open_hide_and_success_animation(self):
        before = dict(self.canvas.positions)
        self.controller.setting('show_trash', True)
        self.wait(lambda: model.TRASH in self.canvas.tiles)
        self.assertEqual({name: self.canvas.positions[name] for name in before}, before)
        self.assertFalse((self.controller.root/'Trash').exists())
        self.controller.select({model.TRASH})
        self.assertEqual(self.controller.urls(), ['trash:/'])
        self.assertEqual(self.controller.urls(real_only=True), [])
        self.controller.trash_state(True)
        self.wait(lambda: 'user-trash-full' in self.canvas.tiles[model.TRASH].info.get_icon().get_names())
        url = self.controller.uri('Folder')
        self.controller.trash([url, model.TRASH])
        self.assertFalse(self.controller.flights[self.window].batches)
        self.controller.trashed([url], [], True)
        self.assertFalse(self.controller.flights[self.window].batches)
        self.assertFalse(self.controller.trash_pending)
        self.controller.trash([url])
        self.controller.trashed([url], [url], True)
        self.assertTrue(self.controller.flights[self.window].batches)
        self.wait(lambda: not self.controller.flights[self.window].batches)
        self.controller.trash([url]); self.controller.trashed([url], [url], False)
        self.assertFalse(self.controller.flights[self.window].batches)
        self.controller.setting('show_trash', False)
        self.wait(lambda: model.TRASH not in self.canvas.tiles)
        self.assertEqual(self.canvas.positions, before)

    def test_inline_rename_selects_stem_escape_cancels_enter_delegates(self):
        tile = self.canvas.tiles['notes # café.txt']
        tile.begin_rename()
        self.assertEqual(tile.editor.get_selection_bounds(), (0, len('notes # café')))
        tile.editor.set_text('changed.txt')
        event = self.Gdk.EventKey(); event.keyval = self.Gdk.KEY_Escape
        tile.rename_key(tile.editor, event)
        self.assertIsNone(tile.editor); self.fake_files.call.assert_not_called()
        tile.begin_rename(); tile.editor.set_text('../bad'); tile.commit_rename()
        self.fake_files.call.assert_not_called(); self.assertIsNotNone(tile.editor)
        tile.editor.set_text('changed.txt'); tile.commit_rename()
        self.fake_files.call.assert_called_once_with('RenameTo', '(ss)', self.controller.uri(tile.name), 'changed.txt', on_reply=ANY)
        self.controller.renamed(self.controller.uri(tile.name), self.controller.uri('changed.txt'), False, 'File exists')
        self.assertIsNone(tile.editor)
        self.assertEqual(tile.label.get_text(), tile.name)

    def test_clipboard_formats_cut_feedback_paste_and_no_clobber(self):
        from desktop_clipboard import GNOME, CUT
        self.controller.select({'notes # café.txt'})
        self.controller.copy(True)
        clipboard = self.controller.clipboard
        result = []
        clipboard.read(lambda *values: result.append(values))
        self.wait(lambda: result)
        self.assertEqual(result[0][:2], ([self.controller.uri('notes # café.txt')], True))
        self.assertAlmostEqual(self.canvas.tiles['notes # café.txt'].image.get_opacity(), .45, places=2)
        for mime, wanted in [(CUT, b'1'), (GNOME, ('cut\n'+self.controller.uri('notes # café.txt')).encode())]:
            contents = []
            clipboard.clipboard.request_contents(self.Gdk.Atom.intern(mime, False),
                lambda _clipboard, data, _extra: contents.append(bytes(data.get_data())), None)
            self.wait(lambda: contents); self.assertEqual(contents[0], wanted)
        self.controller.paste()
        self.wait(lambda: self.fake_files.transfer.called)
        urls = [self.controller.uri('notes # café.txt')]
        self.fake_files.transfer.assert_called_once_with(urls, self.controller.uri(), False)
        clipboard.clipboard.set_text('copied while transfer was running', -1)
        self.controller.transferred(urls, self.controller.uri(), False, True)
        texts = []; clipboard.clipboard.request_text(lambda _c, value, _d: texts.append(value), None)
        self.wait(lambda: texts)
        self.assertEqual(texts, ['copied while transfer was running'])
        self.assertEqual(self.canvas.tiles['notes # café.txt'].image.get_opacity(), 1)

    def test_shortcut_badge_only_for_links_and_launchers(self):
        (self.controller.root/'Folder link').symlink_to(self.controller.root/'Folder', target_is_directory=True)
        (self.controller.root/'Example.desktop').write_text('[Desktop Entry]\nType=Application\nName=Example\nExec=true\nIcon=folder\n')
        self.wait(lambda: 'Example.desktop' in self.canvas.tiles and 'Folder link' in self.canvas.tiles)
        self.assertTrue(self.canvas.tiles['Folder link'].shortcut)
        self.assertTrue(self.canvas.tiles['Example.desktop'].shortcut)
        self.assertFalse(self.canvas.tiles['Folder'].shortcut)


if __name__ == '__main__': unittest.main()
