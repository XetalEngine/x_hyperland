"""Layouts/scans use temporary files; GUI checks opt in on a private display."""
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

    def test_incoming_group_uses_requested_monitor_and_keeps_existing_icons(self):
        model.capture(self.settings, self.names, self.areas)
        before = model.layout(self.names, self.areas, self.settings)['MAIN']
        incoming = ['new.txt', 'new folder', 'copied photo.png']
        model.place_new(self.settings, self.names+incoming, self.areas, 'SIDE', incoming, (245, 175))
        after = model.layout(self.names+incoming, self.areas, self.settings)
        self.assertEqual(before, after['MAIN'])
        self.assertEqual(after['SIDE']['new.txt'], (240, 162))
        self.assertEqual(len(set(after['SIDE'].values())), 3)
        self.store.change(lambda settings: settings.update(self.settings))
        self.assertEqual(model.layout(self.names+incoming, self.areas, self.store.load()), after)

    def test_incoming_free_and_arranged_placement_stays_on_target_monitor(self):
        for arranged in (False, True):
            with self.subTest(arranged=arranged):
                settings = dict(model.defaults(), auto_align=False, auto_arrange=arranged)
                model.place_new(settings, self.names+['new'], self.areas, 'SIDE', ['new'], (233, 190))
                placed = model.layout(self.names+['new'], self.areas, settings)
                self.assertEqual(placed['SIDE']['new'], (16, 48) if arranged else (233, 190))
                self.assertEqual(set(placed['MAIN']), set(self.names))

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


class EnumerationTests(unittest.TestCase):
    """Exercise real asynchronous GIO scans without a display or file service."""
    def setUp(self):
        import desktop_icons as icons
        self.icons = icons
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        desktop = self.root/'Desktop'; desktop.mkdir()
        store = model.Store(self.root/'icons.json')
        with patch.object(icons.model, 'Store', return_value=store), \
                patch.object(icons, 'Files'), patch.object(icons, 'Clipboard'):
            self.controller = icons.Icons(Mock(), {})
        self.controller.root = desktop
        self.controller.settings.update(enabled=True, show_trash=True)
        self.controller.schedule_layout = Mock()
        self.controller.error = Mock()
        self.addCleanup(self.controller.dispose)

    def scan(self):
        self.controller.schedule_layout.reset_mock()
        context = self.icons.GLib.MainContext.default()
        with patch('sys.excepthook') as uncaught:
            self.controller.refresh()
            deadline = time.monotonic()+4
            while time.monotonic() < deadline:
                while context.pending(): context.iteration(False)
                self.assertFalse(uncaught.called, f'Directory scan raised: {uncaught.call_args}')
                if self.controller.schedule_layout.called: break
                time.sleep(.01)
            else:
                self.fail('Directory scan did not finish')
        self.controller.error.assert_not_called()
        return self.controller.entries

    def test_unusable_launchers_do_not_abort_batches_or_hide_files_and_trash(self):
        desktop = self.controller.root
        # More than one batch, with real launcher parsing rather than a mocked
        # constructor. A missing Exec target reproduces the fresh-install bug.
        for index in range(135): (desktop/f'file-{index:03}.txt').touch()
        (desktop/'Folder').mkdir()
        (desktop/'Folder.desktop').mkdir()
        (desktop/'Missing.desktop').write_text(
            f'[Desktop Entry]\nType=Application\nName=Missing app\nExec={self.root}/missing-program\n')
        (desktop/'Malformed.desktop').write_text('not a desktop entry\n')
        (desktop/'Broken.desktop').symlink_to(self.root/'missing.desktop')
        (desktop/'Working.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Working app\nExec=true\nIcon=utilities-terminal\n')
        (desktop/'.Hidden.desktop').write_text('not a desktop entry\n')
        expected = {p.name for p in desktop.iterdir() if not p.name.startswith('.')} | {model.TRASH}
        entries = self.scan()
        self.assertEqual(set(entries), expected)
        for name in ('Missing.desktop', 'Malformed.desktop', 'Broken.desktop', 'Folder.desktop'):
            self.assertEqual(entries[name].get_display_name(), name)
            self.assertIsNotNone(entries[name].get_icon())
        self.assertEqual(entries['Working.desktop'].get_display_name(), 'Working app')
        self.assertIn('utilities-terminal', entries['Working.desktop'].get_icon().get_names())

    def test_launcher_target_disappearing_and_returning_keeps_refresh_working(self):
        desktop = self.controller.root
        program = self.root/'program'
        program.write_text('#!/bin/sh\nexit 0\n'); program.chmod(0o755)
        launcher = desktop/'App.desktop'
        launcher.write_text(f'[Desktop Entry]\nType=Application\nName=App label\nExec={program}\n')
        self.assertEqual(self.scan()[launcher.name].get_display_name(), 'App label')
        program.unlink()
        (desktop/'New folder').mkdir()
        entries = self.scan()
        self.assertEqual(set(entries), {launcher.name, 'New folder', model.TRASH})
        self.assertEqual(entries[launcher.name].get_display_name(), launcher.name)
        program.write_text('#!/bin/sh\nexit 0\n'); program.chmod(0o755)
        self.assertEqual(self.scan()[launcher.name].get_display_name(), 'App label')


@unittest.skipUnless(os.environ.get('FUSION_DESKTOP_TEST_GUI') == '1', 'Run on a private display with FUSION_DESKTOP_TEST_GUI=1')
class CanvasTests(unittest.TestCase):
    def test_control_press_preserves_drag_source_until_click_release(self):
        name='notes # café.txt';self.controller.select({name})
        tile=self.canvas.tiles[name]
        event=Mock(button=1,type=self.Gdk.EventType.BUTTON_PRESS,state=self.Gdk.ModifierType.CONTROL_MASK,x=20,y=20)
        tile.pressed(tile,event)
        self.assertEqual(self.controller.selected,{name})
        tile.released(tile,event)
        self.assertEqual(self.controller.selected,set())

    def test_drag_modifiers_and_wayland_link_transport(self):
        from drag_feedback import drop_operation, wire_action
        copy, move, link = self.Gdk.DragAction.COPY, self.Gdk.DragAction.MOVE, self.Gdk.DragAction.LINK
        ctrl, shift = self.Gdk.ModifierType.CONTROL_MASK, self.Gdk.ModifierType.SHIFT_MASK
        for keys, expected in [(0,move),(ctrl,copy),(shift,move),(ctrl|shift,link)]:
            self.assertEqual(drop_operation(keys,copy|move|link),expected)
            self.assertEqual(drop_operation(keys,copy|move),expected)
        self.assertEqual(wire_action(link,copy|move),copy)
        self.assertEqual(wire_action(link,copy|move|link),link)
        self.assertEqual(drop_operation(shift,copy),0)
        self.assertEqual(drop_operation(ctrl,move),0)
        self.assertEqual(drop_operation(ctrl|shift,move),0)

    def test_shortcut_drop_uses_link_service_and_placement(self):
        from unittest.mock import ANY
        urls=[self.controller.uri('notes # café.txt')]
        self.canvas.drop_operation=self.Gdk.DragAction.LINK
        self.canvas.drop_action=self.Gdk.DragAction.COPY
        data=Mock();data.get_length.return_value=100;data.get_uris.return_value=urls
        with patch.object(self.Gtk,'drag_finish') as finish:
            self.canvas.received(self.canvas,Mock(),550,380,data,1,1)
        self.assertEqual(finish.call_args.args[1],True)
        calls=[call for call in self.fake_files.call.call_args_list if call.args[0]=='LinkWithPlacement']
        self.assertEqual(len(calls),1)
        self.fake_files.call.assert_any_call('LinkWithPlacement','(asss)',urls,self.controller.uri(),calls[0].args[4],on_reply=ANY)
        self.assertIn(calls[0].args[4],self.controller.placements)
        self.fake_files.transfer.assert_not_called()

    def test_local_shortcut_uses_owned_drag_and_invalid_data_changes_nothing(self):
        name='notes # café.txt'
        self.controller.drag=dict(names=[name],anchor=name,offset=[35,25])
        self.canvas.drop_operation=self.Gdk.DragAction.LINK
        self.canvas.drop_action=self.Gdk.DragAction.COPY
        with patch.object(self.Gtk,'drag_finish') as finish:
            self.canvas.received(self.canvas,Mock(),550,380,None,0,1)
            self.assertTrue(finish.call_args.args[1])
        self.assertTrue(any(call.args[0]=='LinkWithPlacement' for call in self.fake_files.call.call_args_list))
        self.fake_files.reset_mock()
        data=Mock();data.get_length.return_value=-1
        with patch.object(self.Gtk,'drag_finish') as finish, patch.object(self.controller,'error') as error:
            self.canvas.received(self.canvas,Mock(),550,380,data,0,1)
            self.assertFalse(finish.call_args.args[1]);error.assert_called_once()
        data.get_data.assert_not_called()
        self.fake_files.call.assert_not_called()

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

    def test_archive_refresh_keeps_drag_source_and_selected_urls(self):
        names = ['Folder', 'notes # café.txt']
        self.controller.select(set(names))
        tile = self.canvas.tiles[names[1]]
        destroyed = Mock(); tile.connect('destroy', destroyed)
        payload = dict(names=names, anchor=tile.name, offset=[30, 20])
        self.controller.drag = payload
        context = Mock()
        tile.drag_begin(tile, context)
        feedback = tile.drag_feedback = Mock()
        info = tile.info
        # The watcher reads every file again when an archive is created.
        (self.controller.root/'in progress.zip').write_bytes(b'PK\x03\x04')
        self.wait(lambda: 'in progress.zip' in self.canvas.tiles)
        self.assertIs(self.canvas.tiles[tile.name], tile)
        self.assertIsNot(tile.info, info)
        self.assertIs(tile.drag_context, context)
        destroyed.assert_not_called(); feedback.close.assert_not_called()
        # Changing the selection after starting a drag cannot change its URLs.
        self.controller.select({'in progress.zip'})
        selection = Mock()
        tile.drag_data(tile, context, selection, 1, 0)
        selection.set_uris.assert_called_once_with(self.controller.urls(names))
        tile.drag_data(tile, context, selection, 0, 0)
        self.assertEqual(json.loads(selection.set.call_args.args[2]), payload)
        tile.drag_end(tile, context)
        feedback.close.assert_called_once()
        self.assertIsNone(tile.drag_context)
        self.assertEqual(self.controller.drag, {})

    def test_removed_drag_source_cancels_before_widget_destruction(self):
        name = 'notes # café.txt'; tile = self.canvas.tiles[name]
        self.controller.drag = dict(names=[name], anchor=name, offset=[20, 20])
        context = Mock(); tile.drag_begin(tile, context)
        feedback = tile.drag_feedback = Mock()
        destroyed = Mock(); tile.connect('destroy', destroyed)
        def cancel(current):
            self.assertIs(current, context)
            destroyed.assert_not_called()
            tile.drag_end(tile, context)
        with patch.object(self.Gtk, 'drag_cancel', side_effect=cancel) as cancelled:
            (self.controller.root/name).unlink()
            self.wait(lambda: name not in self.canvas.tiles)
            cancelled.assert_called_once_with(context)
        feedback.close.assert_called_once(); destroyed.assert_called_once()
        self.assertEqual(self.controller.drag, {})

    def test_hidden_drag_source_releases_context_and_feedback_once(self):
        name = 'notes # café.txt'; tile = self.canvas.tiles[name]
        self.controller.drag = dict(names=[name], anchor=name, offset=[20, 20])
        context = Mock(); tile.drag_begin(tile, context)
        feedback = tile.drag_feedback = Mock()
        with patch.object(self.Gtk, 'drag_cancel') as cancel:
            self.controller.setting('enabled', False)
            self.wait(lambda: not self.canvas.tiles)
            cancel.assert_called_once_with(context)
        tile.drag_end(tile, context)
        feedback.close.assert_called_once()
        self.assertIsNone(tile.drag_context)
        self.assertEqual(tile.drag_urls, [])
        self.assertEqual(self.controller.drag, {})

    def test_refresh_preserves_inline_rename_and_updates_icon_metadata(self):
        tile = self.canvas.tiles['notes # café.txt']
        tile.begin_rename(); editor = tile.editor
        editor.set_text('name being edited.txt')
        info = tile.info
        self.controller.refresh()
        self.wait(lambda: tile.info is not info)
        self.assertIs(self.canvas.tiles[tile.name], tile)
        self.assertIs(tile.editor, editor)
        self.assertEqual(editor.get_text(), 'name being edited.txt')
        updated = info.dup(); updated.set_display_name('Updated name')
        updated.set_is_symlink(True)
        tile.update_info(updated)
        self.assertTrue(tile.shortcut)
        self.assertEqual(tile.get_tooltip_text(), 'Updated name')
        self.assertEqual(editor.get_text(), 'name being edited.txt')

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

    def test_delayed_file_actions_respect_dismissal_and_newer_selection(self):
        # Native Wayland geometry is covered by check-desktop-icons.py. Here
        # control D-Bus reply order to exercise cancellation without real grabs.
        entries = [{'name': 'Copy', 'local': 'copy'}]
        with patch.object(self.Gtk.Menu, 'popup_at_widget', lambda menu, *_: menu.show()):
            self.controller.select({'Folder'}); self.canvas.file_menu(None)
            dismissed = self.window.menu
            reply = self.fake_files.menu.call_args.args[1]
            dismissed.popdown(); self.assertFalse(dismissed.get_visible())
            reply(entries)
            self.assertIs(self.window.menu, dismissed)
            self.assertFalse(dismissed.get_visible())

            self.canvas.file_menu(None)
            older_reply = self.fake_files.menu.call_args.args[1]
            self.controller.select({'notes # café.txt'}); self.canvas.file_menu(None)
            loading = self.window.menu
            latest_reply = self.fake_files.menu.call_args.args[1]
            older_reply(entries)
            self.assertIs(self.window.menu, loading)
            latest_reply(entries)
            ready = self.window.menu
            self.assertIsNot(ready, loading)
            with patch.object(self.controller, 'copy') as copy:
                ready.get_children()[0].activate()
                copy.assert_called_once_with(False, ['notes # café.txt'])
            ready.destroy(); self.window.menu = None

    def test_archive_submenu_does_not_dispatch_a_missing_action(self):
        entries = [{'name': 'Ark', 'children': [{'name': 'Compress…', 'action': 'archive:1'}]}]
        with patch.object(self.Gtk.Menu, 'popup_at_widget', lambda menu, *_: menu.show()):
            self.controller.select({'Folder'}); self.canvas.file_menu(None)
            self.fake_files.menu.call_args.args[1](entries)
            row = self.window.menu.get_children()[0]
            with patch('sys.excepthook') as uncaught:
                row.activate()
                uncaught.assert_not_called()
            self.fake_files.call.assert_not_called()
            row.get_submenu().get_children()[0].activate()
            self.fake_files.call.assert_called_once_with('MenuAction', '(s)', 'archive:1')
            self.window.menu.destroy(); self.window.menu = None

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
        self.wait(lambda: any(call.args[0] == 'TransferWithPlacement' for call in self.fake_files.call.call_args_list))
        urls = [self.controller.uri('notes # café.txt')]
        request = next(iter(self.controller.placements))
        self.fake_files.call.assert_any_call('TransferWithPlacement', '(assbs)', urls, self.controller.uri(), False, request, on_reply=ANY)
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

    def test_menu_creation_keeps_click_position_and_does_not_move_overwrites(self):
        self.controller.setting('auto_align', False)
        target = (self.canvas.monitor, (310, 220))
        menu = self.Gtk.Menu(); self.controller.append_menu(menu, 0, target)
        new = next(item for item in menu.get_children() if hasattr(item, 'get_label') and item.get_label() == 'New folder…')
        with patch.object(self.controller, 'pointer_target', return_value=(self.canvas.monitor, (600, 450))):
            new.activate()
        request = next(iter(self.controller.placements))
        self.fake_files.call.assert_any_call('NewFolderWithPlacement', '(ss)', self.controller.uri(), request, on_reply=ANY)
        original = self.canvas.positions['Folder']
        self.controller.placement_target(request, self.controller.uri('Folder'))
        self.controller.placement_target(request, self.controller.uri('Created here'))
        (self.controller.root/'Created here').mkdir()
        self.controller.placement_finished(request)
        self.wait(lambda: 'Created here' in self.canvas.positions)
        self.assertEqual(self.canvas.positions['Created here'], (310, 220))
        self.assertEqual(self.canvas.positions['Folder'], original)
        self.assertFalse(self.controller.placements)
        menu.destroy()

    def test_parallel_operations_keep_separate_origins_and_cancel_cleanly(self):
        self.controller.setting('auto_align', False)
        a = self.controller.begin_placement((self.canvas.monitor, (280, 190)))
        b = self.controller.begin_placement((self.canvas.monitor, (510, 330)))
        self.controller.placement_target(b, self.controller.uri('b.txt'))
        (self.controller.root/'b.txt').write_text('b')
        self.controller.placement_finished(b)
        self.wait(lambda: 'b.txt' in self.canvas.positions)
        self.controller.placement_target(a, self.controller.uri('a_copy1.txt'))
        (self.controller.root/'a_copy1.txt').write_text('a')
        self.controller.placement_finished(a)
        self.wait(lambda: 'a_copy1.txt' in self.canvas.positions)
        self.assertEqual(self.canvas.positions['a_copy1.txt'], (280, 190))
        self.assertEqual(self.canvas.positions['b.txt'], (510, 330))
        cancelled = self.controller.begin_placement((self.canvas.monitor, (0, 0)))
        self.controller.placement_target(cancelled, self.controller.uri('never created'))
        self.controller.placement_finished(cancelled)
        self.wait(lambda: not self.controller.placements)
        self.assertNotIn('never created', self.store.load()['positions'])

    def test_paste_snapshots_pointer_on_scaled_monitor_before_clipboard_reply(self):
        second = Mock()
        second.monitor = 'SIDE'
        second.get_hadjustment.return_value.get_value.return_value = 0
        second.get_vadjustment.return_value.get_value.return_value = 0
        self.controller.canvases['fixture'] = second
        self.addCleanup(lambda: self.controller.canvases.pop('fixture', None))
        self.controller.bounds = {self.canvas.monitor: (-760, 40, 760, 560), 'SIDE': (0, 0, 800, 600)}
        self.controller.areas['SIDE'] = (16, 48, 768, 536)
        with patch.object(self.icons.subprocess, 'check_output', return_value=b'{"x":250,"y":190}'), \
             patch.object(self.controller.clipboard, 'read') as read:
            self.controller.paste()
        with patch.object(self.icons.subprocess, 'check_output', return_value=b'{"x":-540,"y":200}'):
            self.assertEqual(self.controller.pointer_target(), (self.canvas.monitor, (220, 160)))
            read.call_args.args[0](['file:///tmp/received.txt'], False, 1)
        self.assertEqual(next(iter(self.controller.placements.values()))['target'], ('SIDE', (250, 190)))


if __name__ == '__main__': unittest.main()
