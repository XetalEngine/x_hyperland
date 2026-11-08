"""Transparent, session-owned desktop icons on the existing bottom layer."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
import icons_model as model
from desktop_files import Files
from desktop_clipboard import Clipboard
from trash_animation import Flights, snapshot
from drag_feedback import DragFeedback, drop_operation, wire_action
import math

PROFILE_ROOT = Path(__file__).resolve().parents[1]
if str(PROFILE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROFILE_ROOT))
from icon_themes import model as icon_library

TARGETS = [Gtk.TargetEntry.new('application/x-xetal-desktop-icons', Gtk.TargetFlags.SAME_APP, 0),
           Gtk.TargetEntry.new('text/uri-list', 0, 1),
           Gtk.TargetEntry.new('application/x-hyperfusion-file-drag', 0, 2)]
ATTRIBUTES = 'standard::name,standard::display-name,standard::type,standard::icon,standard::is-hidden,standard::is-symlink,thumbnail::path,thumbnail::is-valid'


def style_item(item):
    item.set_size_request(220, 36)
    child = item.get_child()
    if child:
        child.set_margin_start(12); child.set_margin_end(12)
    return item


def action(menu, label, callback, sensitive=True):
    item = style_item(Gtk.MenuItem(label=label))
    item.set_sensitive(sensitive)
    item.connect('activate', lambda *_: callback())
    menu.append(item)
    return item


class Tile(Gtk.EventBox):
    def __init__(self, canvas, name, info):
        super().__init__()
        self.canvas, self.name, self.info = canvas, name, info
        self.press = None
        self.editor = None
        self.renaming = False
        self.drag_context = None
        self.drag_payload, self.drag_urls = {}, []
        # Paint the themed selection/hover background on the tile's RGBA
        # window; an input-only EventBox would paint only the label color.
        self.set_visible_window(True); self.set_above_child(True)
        self.get_style_context().add_class('desktop-icon')
        self.set_tooltip_text(info.get_display_name())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(7); box.set_margin_bottom(7)
        box.set_margin_start(4); box.set_margin_end(4)
        self.image = Gtk.Image.new_from_gicon(info.get_icon(), Gtk.IconSize.DIALOG)
        self.shortcut = info.get_is_symlink() or name.casefold().endswith('.desktop')
        self.image.connect_after('draw', self.draw_shortcut)
        box.pack_start(self.image, False, False, 0)
        label = Gtk.Label(label=info.get_display_name())
        label.set_justify(Gtk.Justification.CENTER)
        label.set_line_wrap(True); label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_lines(2); label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(16); label.set_xalign(.5); label.set_yalign(0)
        self.label = label
        self.box = box
        box.pack_start(label, True, True, 0)
        self.add(box)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('button-press-event', self.pressed)
        self.connect('button-release-event', self.released)
        self.connect('motion-notify-event', self.motion)
        self.connect('drag-begin', self.drag_begin)
        self.connect('drag-data-get', self.drag_data)
        self.connect('drag-end', self.drag_end)
        self.connect('unmap', self.cancel_drag)
        self.connect('destroy', self.cancel_drag)
        self.drag_feedback = None
        self.resize_icon()

    def update_info(self, info):
        # Directory enumeration returns fresh Gio.FileInfo objects even for
        # unchanged files. Replacing their widgets destroys the GTK drag source
        # (and its callbacks) while another app may still be requesting URLs.
        self.info = info
        self.set_tooltip_text(info.get_display_name())
        self.shortcut = info.get_is_symlink() or self.name.casefold().endswith('.desktop')
        if not self.editor: self.label.set_text(info.get_display_name())
        self.image.set_from_gicon(info.get_icon(), Gtk.IconSize.DIALOG)

    def resize_icon(self):
        settings = self.canvas.controller.settings
        self.set_size_request(*model.cell(settings))
        self.image.set_pixel_size(settings['size'])
        self.label.set_size_request(model.cell(settings)[0]-12, 38)
        thumbnail = self.info.get_attribute_byte_string('thumbnail::path')
        if thumbnail and self.info.get_attribute_boolean('thumbnail::is-valid'):
            try:
                scale = self.get_scale_factor(); size = settings['size']*scale
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(thumbnail, size, size, True)
                self.image.set_from_surface(Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, None))
            except GLib.Error:
                pass

    def draw_shortcut(self, image, cr):
        if not self.shortcut: return False
        size = self.canvas.controller.settings['size']
        badge = max(15, round(size*.30))
        x, y = (image.get_allocated_width()-size)/2, (image.get_allocated_height()+size)/2-badge
        cr.save(); cr.translate(x, y)
        r = 4
        for cx, cy, angle in [(badge-r,r,-90),(badge-r,badge-r,0),(r,badge-r,90),(r,r,180)]:
            cr.arc(cx, cy, r, math.radians(angle), math.radians(angle+90))
        cr.close_path(); cr.set_source_rgba(.06,.08,.11,.94); cr.fill_preserve()
        color = self.canvas.controller.accent
        cr.set_source_rgba(color.red, color.green, color.blue, 1); cr.set_line_width(1.2); cr.stroke()
        cr.set_line_width(1.8); cr.set_line_cap(1); cr.set_line_join(1)
        cr.move_to(badge*.26,badge*.72); cr.line_to(badge*.26,badge*.42)
        cr.line_to(badge*.72,badge*.42); cr.move_to(badge*.53,badge*.24)
        cr.line_to(badge*.73,badge*.42); cr.line_to(badge*.53,badge*.61); cr.stroke(); cr.restore()
        return False

    def begin_rename(self):
        if self.name == model.TRASH or self.editor or self.renaming: return
        self.canvas.controller.cancel_rename()
        self.canvas.controller.select({self.name})
        self.press = None
        self.set_above_child(False)
        self.label.hide(); self.label.set_no_show_all(True)
        self.editor = Gtk.Entry()
        self.editor.set_width_chars(1); self.editor.set_alignment(.5)
        self.editor.set_text(self.name)
        self.editor.get_style_context().add_class('desktop-rename')
        self.box.pack_start(self.editor, False, False, 0)
        self.editor.connect('activate', lambda *_: self.commit_rename())
        self.editor.connect('key-press-event', self.rename_key)
        self.editor.connect('focus-out-event', lambda *_: self.commit_rename())
        self.editor.show(); self.editor.grab_focus()
        end = len(self.name)
        if self.info.get_file_type() != Gio.FileType.DIRECTORY and '.' in self.name[1:]: end = self.name.rfind('.')
        self.editor.select_region(0, end)

    def rename_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.end_rename(); self.canvas.grab_focus(); return True
        return False

    def commit_rename(self):
        if not self.editor or self.renaming: return False
        name = self.editor.get_text()
        if name == self.name: self.end_rename(); return False
        if not model.valid_name(name):
            self.editor.set_tooltip_text('Choose a name without /, and different from . or ..')
            self.editor.get_style_context().add_class('error'); self.editor.grab_focus(); return False
        self.renaming = True; self.editor.set_editable(False)
        self.canvas.controller.files.call('RenameTo', '(ss)', self.canvas.controller.uri(self.name), name,
            on_reply=lambda accepted: None if accepted else self.end_rename())
        return False

    def end_rename(self, error=None):
        editor, self.editor = self.editor, None
        self.renaming = False
        if editor: editor.destroy()
        self.label.set_no_show_all(False); self.label.show(); self.set_above_child(True)
        if error: self.canvas.controller.error(error)

    def pressed(self, _widget, event):
        if self.editor: return False
        if event.button not in (1, 3): return False
        controller = self.canvas.controller
        self.canvas.grab_focus()
        if event.button == 3:
            if self.name not in controller.selected:
                controller.select({self.name})
            self.canvas.file_menu(event)
        elif event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            controller.files.open(controller.urls())
            self.press = None
        else:
            control = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
            shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
            toggle_on_release = control and not shift and self.name in controller.selected
            if shift and controller.anchor in self.canvas.positions:
                names = list(self.canvas.positions)
                a, b = sorted((names.index(controller.anchor), names.index(self.name)))
                controller.select(set(names[a:b+1]) | (controller.selected if control else set()))
            elif control:
                # Ctrl may already be held to start a copy drag. Defer removing
                # a selected item until release so it remains a drag source.
                controller.select(controller.selected | {self.name})
            elif self.name not in controller.selected:
                controller.select({self.name})
            controller.anchor = self.name
            self.press = (event.x, event.y, bool(control or shift), toggle_on_release)
        return True

    def released(self, _widget, event):
        if event.button == 1 and self.press:
            if not self.press[2]: self.canvas.controller.select({self.name})
            elif self.press[3]: self.canvas.controller.select(self.canvas.controller.selected ^ {self.name})
            self.press = None
        return True

    def motion(self, _widget, event):
        if self.editor: return False
        if not self.press or not event.state & Gdk.ModifierType.BUTTON1_MASK: return False
        if not self.drag_check_threshold(int(self.press[0]), int(self.press[1]), int(event.x), int(event.y)): return False
        controller = self.canvas.controller
        controller.drag = dict(names=controller.ordered_selection(), anchor=self.name,
                               offset=[self.press[0], self.press[1]])
        self.press = None
        virtual = model.TRASH in controller.drag['names']
        context = self.drag_begin_with_coordinates(Gtk.TargetList.new(TARGETS[:1]+TARGETS[2:] if virtual else TARGETS),
            Gdk.DragAction.MOVE if virtual else Gdk.DragAction.COPY | Gdk.DragAction.MOVE | Gdk.DragAction.LINK, 1, event, -1, -1)
        if context and self.drag_context == context:
            self.drag_feedback = DragFeedback(self, context, len(self.drag_payload['names']))
        else:
            self.drag_end()
        return True

    def drag_begin(self, _widget, context):
        self.drag_context = context
        self.drag_payload = dict(self.canvas.controller.drag)
        self.drag_urls = self.canvas.controller.urls(self.drag_payload.get('names', []))

    def drag_data(self, _widget, _context, selection, info, _time):
        if info == 0:
            selection.set(selection.get_target(), 8, json.dumps(self.drag_payload).encode())
        elif info == 1:
            selection.set_uris(self.drag_urls)
        else:
            selection.set(selection.get_target(), 8, b'1')

    def drag_end(self, *_):
        self.drag_context = None
        if self.drag_feedback: self.drag_feedback.close(); self.drag_feedback = None
        self.drag_payload, self.drag_urls = {}, []
        self.press = None
        self.canvas.controller.drag = {}
        for canvas in self.canvas.controller.canvases.values(): canvas.highlight(None)

    def cancel_drag(self, *_):
        # Removal, hidden icons, monitor unplug and shutdown must release the
        # native grab before the source window/signal handlers disappear.
        context = self.drag_context
        if context is not None:
            self.drag_context = None
            Gtk.drag_cancel(context)
            self.drag_end()


class Canvas(Gtk.Layout):
    def __init__(self, controller, surface):
        super().__init__()
        self.controller, self.surface = controller, surface
        self.monitor = ''
        self.positions, self.tiles = {}, {}
        self.last_layout = None
        self.rubber = None
        self.drop_name = None
        self.drop_action = Gdk.DragAction(0)
        self.drop_operation = Gdk.DragAction(0)
        self.search, self.search_time = '', 0
        self.set_can_focus(True)
        self.get_style_context().add_class('desktop-icons')
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('button-press-event', self.pressed)
        self.connect('button-release-event', self.released)
        self.connect('motion-notify-event', self.motion)
        self.connect('key-press-event', self.key)
        self.connect_after('draw', self.draw_selection)
        self.drag_dest_set(Gtk.DestDefaults(0), TARGETS[:2], Gdk.DragAction.COPY | Gdk.DragAction.MOVE | Gdk.DragAction.LINK)
        self.connect('drag-motion', self.drag_motion)
        self.connect('drag-leave', lambda *_: self.highlight(None))
        self.connect('drag-drop', self.drop)
        self.connect('drag-data-received', self.received)

    def update(self, positions):
        area = self.controller.areas.get(self.monitor, (0, 0, 1, 1))
        state = (positions, area, self.controller.settings['size'],
                 {name: self.controller.entries[name] for name in positions})
        if state == self.last_layout: return
        self.last_layout = state
        self.positions = positions
        for name in list(self.tiles):
            if name not in positions:
                tile = self.tiles.pop(name)
                tile.cancel_drag()
                tile.destroy()
        for name, point in positions.items():
            if name not in self.tiles:
                self.tiles[name] = Tile(self, name, self.controller.entries[name])
                self.put(self.tiles[name], *point)
                self.tiles[name].show_all()
            else:
                self.tiles[name].update_info(self.controller.entries[name])
                self.tiles[name].resize_icon()
                self.move(self.tiles[name], *point)
        width, height = model.cell(self.controller.settings)
        self.set_size(max([area[0]+area[2], *[p[0]+width+12 for p in positions.values()]]),
                      max([area[1]+area[3], *[p[1]+height+12 for p in positions.values()]]))
        self.update_selection()

    def update_selection(self):
        for name, tile in self.tiles.items():
            context = tile.get_style_context()
            (context.add_class if name in self.controller.selected else context.remove_class)('selected')
            tile.image.set_opacity(.45 if self.controller.clipboard.owned and self.controller.clipboard.cut
                                   and self.controller.uri(name) in self.controller.clipboard.urls else 1)
        self.queue_draw()

    def hit(self, x, y):
        width, height = model.cell(self.controller.settings)
        return next((name for name, (a, b) in reversed(list(self.positions.items()))
                     if a <= x < a+width and b <= y < b+height), None)

    def pressed(self, _widget, event):
        if not self.controller.settings['enabled'] or event.button != 1: return False
        self.grab_focus()
        keep = bool(event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK))
        initial = set(self.controller.selected) if keep else set()
        self.controller.select(initial)
        self.rubber = [event.x, event.y, event.x, event.y, initial]
        return True

    def motion(self, _widget, event):
        if not self.rubber: return False
        self.rubber[2:4] = [event.x, event.y]
        x1, x2 = sorted((self.rubber[0], event.x)); y1, y2 = sorted((self.rubber[1], event.y))
        width, height = model.cell(self.controller.settings)
        selected = {name for name, (x, y) in self.positions.items()
                    if x < x2 and x+width > x1 and y < y2 and y+height > y1}
        self.controller.select(selected | self.rubber[4])
        return True

    def released(self, _widget, event):
        if event.button != 1 or not self.rubber: return False
        self.rubber = None; self.queue_draw(); return True

    def draw_selection(self, _widget, cr):
        if not self.rubber: return False
        x, y, endx, endy = self.rubber[:4]
        cr.rectangle(min(x, endx), min(y, endy), abs(endx-x), abs(endy-y))
        color = self.controller.accent
        cr.set_source_rgba(color.red, color.green, color.blue, .20); cr.fill_preserve()
        cr.set_source_rgba(color.red, color.green, color.blue, .9); cr.set_line_width(1); cr.stroke()
        return False

    def key(self, _widget, event):
        if not self.controller.settings['enabled']: return False
        key = Gdk.keyval_name(event.keyval)
        control = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        selected = self.controller.ordered_selection()
        if key == 'Escape': self.controller.select(set())
        elif control and key.lower() == 'a': self.controller.select(set(self.positions))
        elif control and key.lower() in ('c', 'x'):
            self.controller.copy(key.lower() == 'x')
        elif control and key.lower() == 'v': self.controller.paste()
        elif control and event.state & Gdk.ModifierType.SHIFT_MASK and key.lower() == 'n':
            self.controller.new_folder()
        elif alt and key in ('Return', 'KP_Enter') and selected:
            self.controller.files.call('Properties', '(as)', self.controller.urls())
        elif key in ('Return', 'KP_Enter') and selected:
            self.controller.files.open(self.controller.urls())
        elif key == 'Delete' and selected:
            self.controller.trash(self.controller.urls(real_only=True))
        elif key == 'F2' and len(selected) == 1:
            if selected[0] in self.tiles: self.tiles[selected[0]].begin_rename()
        elif key == 'F5': self.controller.refresh()
        elif key in ('Menu', 'F10') and selected:
            self.file_menu(None)
        elif key in ('Left', 'Right', 'Up', 'Down', 'Home', 'End') and self.positions:
            names = list(self.positions)
            current = next((name for name in selected if name in self.positions), names[0])
            if key in ('Home', 'End'): target = names[0 if key == 'Home' else -1]
            else:
                x, y = self.positions[current]
                vector = dict(Left=(-1, 0), Right=(1, 0), Up=(0, -1), Down=(0, 1))[key]
                candidates = []
                for name, (a, b) in self.positions.items():
                    along, across = (a-x)*vector[0]+(b-y)*vector[1], abs((a-x)*vector[1]-(b-y)*vector[0])
                    if along > 0: candidates.append((across*5+along, name))
                target = min(candidates)[1] if candidates else current
            self.controller.anchor = target
            self.controller.select((self.controller.selected if event.state & Gdk.ModifierType.SHIFT_MASK else set()) | {target})
        elif not control and event.string and event.string.isprintable():
            now = time.monotonic()
            self.search = (self.search if now-self.search_time < 1 else '')+event.string.casefold()
            self.search_time = now
            match = next((name for name in self.positions if name.casefold().startswith(self.search)), None)
            if match: self.controller.select({match})
        else: return False
        return True

    def file_menu(self, event):
        target = self.controller.pointer_target(self)
        self.controller.owner.dismiss()
        self.controller.owner.refresh_style()
        menu = Gtk.Menu(); menu.get_style_context().add_class('desktop-context-menu')
        names = self.controller.ordered_selection()
        if not names: return
        urls = self.controller.urls(names)
        trigger = event.copy() if event else Gtk.get_current_event()
        anchor = Gdk.Rectangle()
        if event:
            anchor.x, anchor.y = round(event.x), round(event.y)
            anchor.width = anchor.height = 1
        def popup(popup_menu):
            if event:
                # The loading popup owns the pointer by the time D-Bus replies.
                # Anchor both windows to the original click in the icon surface.
                popup_menu.popup_at_rect(trigger.get_window(), anchor,
                    Gdk.Gravity.NORTH_WEST, Gdk.Gravity.NORTH_WEST, trigger)
            else:
                tile = self.tiles.get(names[0])
                popup_menu.popup_at_widget(tile or self, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, trigger)
        action(menu, 'Loading file actions…', lambda: None, False)
        def activate(entry):
            identifier = entry.get('local')
            if identifier == 'cut': self.controller.copy(True, names)
            elif identifier == 'copy': self.controller.copy(False, names)
            elif identifier == 'copyPath':
                clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                clipboard.set_text('\n'.join(Gio.File.new_for_uri(url).get_path() or url for url in urls), -1)
            elif identifier == 'paste': self.controller.paste(target)
            elif identifier == 'newFolder': self.controller.new_folder(target)
            elif identifier == 'rename':
                tile = self.tiles.get(names[0])
                if tile: tile.begin_rename()
            elif identifier == 'trash': self.controller.trash(urls)
            elif 'action' in entry: self.controller.files.call('MenuAction', '(s)', entry['action'])
        def populate(entries):
            if self.surface.menu is not menu or not menu.get_visible(): return
            # GTK's mapped Wayland popup retains the loading row's configured
            # height. Build its replacement before mapping it, so the compositor
            # gets the complete size. Keep the original event and dismissal guard.
            ready = Gtk.Menu(); ready.get_style_context().add_class('desktop-context-menu')
            def append(parent, entries):
                for entry in entries:
                    if entry.get('separator'):
                        parent.append(Gtk.SeparatorMenuItem()); continue
                    item = action(parent, entry['name'], lambda entry=entry: activate(entry), entry.get('enabled', True))
                    if 'children' in entry:
                        submenu = Gtk.Menu(); submenu.get_style_context().add_class('desktop-context-menu')
                        append(submenu, entry['children']); item.set_submenu(submenu)
            append(ready, entries)
            if names == [model.TRASH]:
                action(ready, 'Empty Trash…', lambda: self.controller.files.call('EmptyTrash', '()'))
                action(ready, 'Hide Trash', lambda: self.controller.setting('show_trash', False))
            ready.append(Gtk.SeparatorMenuItem())
            action(ready, 'Customize desktop file menu…', lambda: self.controller.files.call('ConfigureMenu', '()'))
            ready.attach_to_widget(self, None); ready.show_all()
            menu.popdown(); menu.destroy()
            self.surface.menu = ready
            popup(ready)
        if self.surface.menu: self.surface.menu.destroy()
        self.surface.menu = menu
        menu.attach_to_widget(self, None); menu.show_all()
        popup(menu)
        self.controller.files.menu(urls, populate)

    def highlight(self, name):
        if name == self.drop_name: return
        if self.drop_name in self.tiles: self.tiles[self.drop_name].get_style_context().remove_class('drop-target')
        self.drop_name = name
        if name in self.tiles: self.tiles[name].get_style_context().add_class('drop-target')

    def destination(self, x, y):
        name = self.hit(x, y)
        if (name and name not in self.controller.drag.get('names', [])
                and self.controller.entries[name].get_file_type() == Gio.FileType.DIRECTORY): return name
        return None

    def drag_motion(self, _widget, context, x, y, timestamp):
        if not self.controller.settings['enabled']: return False
        if not self.drag_dest_find_target(context, None): return False
        # A GDK drag-motion event has no button/modifier state. Read the
        # keyboard state directly so holding Ctrl really selects Copy.
        state = Gdk.Keymap.get_for_display(self.get_display()).get_modifier_state()
        possible = context.get_actions()
        operation = drop_operation(state, possible)
        destination = self.destination(x, y)
        if destination == model.TRASH and operation != Gdk.DragAction.MOVE: operation = Gdk.DragAction(0)
        if model.TRASH in self.controller.drag.get('names', []) and (destination or operation != Gdk.DragAction.MOVE): operation = Gdk.DragAction(0)
        self.drop_operation = operation
        self.drop_action = wire_action(operation, possible)
        self.highlight(destination if operation else None)
        Gdk.drag_status(context, self.drop_action, timestamp)
        return bool(operation)

    def drop(self, _widget, context, x, y, timestamp):
        target = self.drag_dest_find_target(context, None)
        if not target or not self.controller.settings['enabled']: return False
        if not self.drag_motion(self, context, x, y, timestamp): return False
        if target == Gdk.Atom.intern('application/x-xetal-desktop-icons', False) and self.controller.drag:
            # SAME_APP already identifies our in-process drag. Its selection
            # request can be cancelled by GTK's Wayland handoff; use the owned
            # snapshot while the source is alive, including its anchor/offset.
            self.received(self, context, x, y, None, 0, timestamp)
            return True
        self.drag_get_data(context, target, timestamp)
        return True

    def received(self, _widget, context, x, y, data, info, timestamp):
        success = False
        try:
            if data is not None and data.get_length() < 0: raise ValueError('The drag source did not supply its files. Please try again.')
            if data is not None and data.get_length() > 2*1024*1024: raise ValueError('Too many files in this drop.')
            drag = {}
            if info == 0:
                drag = dict(self.controller.drag) if data is None else json.loads(bytes(data.get_data()))
                names = drag.get('names', [])
                if not isinstance(names, list) or not names or not all(name in self.controller.entries for name in names):
                    raise ValueError('The dragged files changed. Select them again.')
                urls = self.controller.urls(names)
            else:
                urls = data.get_uris() or []
                names = [name for name in self.controller.entries if self.controller.uri(name) in urls]
            if not urls or len(urls) > 10000: raise ValueError('No files were supplied by this drop.')
            # GTK's Wayland context can still report the previous action while
            # its new drag status is being committed. Use our accepted action.
            operation = self.drop_operation
            if not operation: raise ValueError('This location does not accept the selected drag operation.')
            destination = self.destination(x, y)
            if destination == model.TRASH:
                self.controller.trash([url for url in urls if url != model.TRASH])
            elif destination is None and operation == Gdk.DragAction.MOVE and len(names) == len(urls):
                offset = drag.get('offset', [model.cell(self.controller.settings)[0]/2, 20])
                self.controller.reposition(self.monitor, names, (x-offset[0], y-offset[1]), drag.get('anchor'))
            else:
                if model.TRASH in urls: raise ValueError('Trash can be repositioned on the desktop, but cannot be moved into a folder.')
                target = (self.monitor, (x, y))
                if operation == Gdk.DragAction.LINK:
                    self.controller.link(urls, self.controller.uri(destination), target)
                else:
                    self.controller.transfer(urls, self.controller.uri(destination), operation == Gdk.DragAction.COPY, target)
            success = True
        except (ValueError, TypeError, KeyError, IndexError) as error:
            self.controller.error(str(error))
        self.highlight(None)
        Gtk.drag_finish(context, success, False, timestamp)


class Icons:
    def __init__(self, owner, launch_env):
        self.owner, self.launch_env = owner, launch_env
        self.root = Path.home()/'Desktop'
        self.store = model.Store()
        self.settings = model.defaults()
        self.entries, self.canvases, self.areas = {}, {}, {}
        self.bounds, self.placements = {}, {}
        self.selected, self.anchor, self.drag = set(), None, {}
        self.monitor = None
        self.generation = 0
        self.pending = 0
        self.layout_pending = 0
        self.monitor_poll = 0
        self.trash_full = False
        self.trash_pending = {}
        self.pastes = {}
        self.flights = {}
        self.cancellable = Gio.Cancellable()
        self.files = Files(self.error, self.trashed, self.trash_state, self.transferred, self.renamed,
                           self.placement_target, self.placement_finished)
        self.clipboard = Clipboard(self.clipboard_changed)
        self.accent = Gdk.RGBA(); self.accent.parse('#88b6d8')
        try: self.settings = self.store.load()
        except (OSError, ValueError) as error: self.error(str(error))
        if self.settings['enabled']: self.start()

    def error(self, message):
        print('Desktop icons: '+message, file=sys.stderr)
        try:
            subprocess.Popen(['notify-send', '-a', 'Fusion Files', 'Desktop icons', message],
                             env=self.launch_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError: pass

    def uri(self, name=None):
        if name == model.TRASH: return model.TRASH
        return Gio.File.new_for_path(str(self.root/name if name else self.root)).get_uri()

    def ordered_selection(self):
        return [name for canvas in self.canvases.values() for name in canvas.positions if name in self.selected]

    def urls(self, names=None, real_only=False):
        return [self.uri(name) for name in (self.ordered_selection() if names is None else names)
                if not real_only or name != model.TRASH]

    def clipboard_changed(self):
        for canvas in self.canvases.values(): canvas.update_selection()

    def copy(self, cut=False, names=None):
        urls = self.urls(names, real_only=True)
        if urls and not self.clipboard.write(urls, cut): self.error('Could not copy the selected files to the clipboard.')

    def pointer_target(self, fallback=None):
        # Wayland does not expose a reliable global GDK pointer position.
        # Hyprland reports logical coordinates, including negative origins.
        try:
            cursor = json.loads(subprocess.check_output(['hyprctl', '-j', 'cursorpos'],
                                env=self.launch_env, timeout=1, stderr=subprocess.DEVNULL))
            for canvas in self.canvases.values():
                x, y, width, height = self.bounds.get(canvas.monitor, (0, 0, 0, 0))
                if x <= cursor['x'] < x+width and y <= cursor['y'] < y+height:
                    return canvas.monitor, (cursor['x']-x+canvas.get_hadjustment().get_value(),
                                            cursor['y']-y+canvas.get_vadjustment().get_value())
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError): pass
        canvas = fallback or next(iter(self.canvases.values()), None)
        return (canvas.monitor, self.areas.get(canvas.monitor, (16, 48))[:2]) if canvas else None

    def begin_placement(self, target):
        if target is None: return None
        request = uuid.uuid4().hex
        try: existing = {path.name for path in self.root.iterdir()}
        except OSError: existing = set(self.entries)
        self.placements[request] = dict(target=target, existing=existing, names=[], applied=set(), finished=False)
        return request

    def placement_target(self, request, destination):
        pending = self.placements.get(request)
        if pending is None: return
        file = Gio.File.new_for_uri(destination)
        parent = file.get_parent(); name = file.get_basename()
        if (parent and parent.equal(Gio.File.new_for_path(str(self.root))) and model.valid_name(name)
                and name not in pending['existing'] and name not in pending['names']):
            pending['names'].append(name)
            self.schedule_layout()

    def placement_finished(self, request):
        pending = self.placements.get(request)
        if pending:
            pending['finished'] = True
            self.refresh()

    def place_incoming(self):
        for pending in self.placements.values():
            names = [name for name in pending['names'] if name in self.entries and name not in pending['applied']]
            if names and self.areas:
                monitor, point = pending['target']
                if self.change(lambda settings: model.place_new(settings, self.entries, self.areas, monitor, names, point)):
                    pending['applied'].update(names)

    def new_folder(self, target=None):
        request = self.begin_placement(target or self.pointer_target())
        self.files.call('NewFolderWithPlacement', '(ss)', self.uri(), request or '',
                        on_reply=lambda accepted: None if accepted else self.placements.pop(request, None))

    def transfer(self, urls, destination, copy, target=None):
        if destination != self.uri():
            self.files.transfer(urls, destination, copy); return
        request = self.begin_placement(target or self.pointer_target())
        self.files.call('TransferWithPlacement', '(assbs)', urls, destination, copy, request or '',
                        on_reply=lambda accepted: None if accepted else self.placements.pop(request, None))

    def link(self, urls, destination, target=None):
        request = self.begin_placement(target or self.pointer_target()) if destination == self.uri() else None
        self.files.call('LinkWithPlacement', '(asss)', urls, destination, request or '',
                        on_reply=lambda accepted: None if accepted else self.placements.pop(request, None))

    def paste(self, target=None):
        # The desktop is the current folder; selecting an icon does not change
        # Ctrl+V's destination. Open a folder to paste into it instead.
        destination = self.uri()
        target = target or self.pointer_target()
        def received(urls, cut, generation):
            if not urls or not self.settings['enabled']: return
            if cut: self.pastes[(tuple(urls), destination)] = generation
            self.transfer(urls, destination, not cut, target)
        self.clipboard.read(received)

    def transferred(self, sources, destination, copy, success):
        generation = self.pastes.pop((tuple(sources), destination), None)
        if success and not copy and generation is not None: self.clipboard.complete_move(sources, generation)

    def cancel_rename(self):
        for canvas in self.canvases.values():
            for tile in canvas.tiles.values():
                if tile.editor and not tile.renaming: tile.end_rename()

    def renamed(self, source, destination, success, message):
        name = Gio.File.new_for_uri(source).get_basename()
        for canvas in self.canvases.values():
            if name in canvas.tiles: canvas.tiles[name].end_rename(None if success else message)
        if success: self.refresh()

    def trash_info(self):
        info = Gio.FileInfo(); info.set_name(model.TRASH); info.set_display_name('Trash')
        info.set_is_symlink(False)
        info.set_file_type(Gio.FileType.DIRECTORY)
        info.set_icon(Gio.ThemedIcon.new('user-trash-full' if self.trash_full else 'user-trash'))
        return info

    def trash_state(self, full):
        if full == self.trash_full: return
        self.trash_full = full
        if model.TRASH in self.entries:
            self.entries[model.TRASH] = self.trash_info(); self.schedule_layout()

    def trash(self, urls):
        urls = [url for url in urls if url != model.TRASH and url not in self.trash_pending]
        if not urls: return
        for index, url in enumerate(urls):
            image = None
            for surface, canvas in (self.canvases.items() if index < 8 else []):
                name = next((name for name in canvas.tiles if self.uri(name) == url), None)
                if name:
                    image = snapshot(canvas.tiles[name], surface, self.settings['size']); break
            self.trash_pending[url] = image
        def accepted(ok):
            if not ok:
                for url in urls: self.trash_pending.pop(url, None)
        self.files.call('Trash', '(as)', urls, on_reply=accepted)

    def trashed(self, requested, removed, animate):
        images = [self.trash_pending[url] for url in removed if self.trash_pending.get(url)][:8]
        for url in requested: self.trash_pending.pop(url, None)
        target = None
        for surface, canvas in self.canvases.items():
            if model.TRASH in canvas.tiles:
                captured = snapshot(canvas.tiles[model.TRASH], surface, self.settings['size'])
                if captured: target = captured[1]; break
        if images and not target:
            # Keep the existing animation even when the optional Trash icon is
            # hidden. Its destination is the source display's lower right edge.
            for surface, canvas in self.canvases.items():
                g = surface.desktop_monitor.get_geometry(); x, y = images[0][1]
                if g.x <= x < g.x+g.width and g.y <= y < g.y+g.height:
                    a = self.areas[canvas.monitor]; target = (g.x+a[0]+a[2]-32, g.y+a[1]+a[3]-32); break
        if animate and images and target:
            for flights in self.flights.values(): flights.fly(images, target)
        self.refresh()

    def select(self, names):
        self.selected = set(names) & self.entries.keys()
        for canvas in self.canvases.values(): canvas.update_selection()

    def attach(self, surface):
        canvas = Canvas(self, surface)
        scroll = Gtk.ScrolledWindow()
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class('desktop-icons')
        overlay = Gtk.Overlay(); overlay.add(scroll)
        flights = Flights(surface, lambda: self.accent)
        overlay.add_overlay(flights); overlay.set_overlay_pass_through(flights, True)
        scroll.add(canvas); surface.add(overlay)
        self.flights[surface] = flights
        self.canvases[surface] = canvas
        surface.connect('size-allocate', lambda *_: self.schedule_layout())
        signal = surface.desktop_monitor.connect('notify::geometry', lambda *_: self.schedule_layout())
        surface.connect('destroy', lambda *_: surface.desktop_monitor.disconnect(signal))
        self.schedule_layout()

    def detach(self, surface):
        flights = self.flights.pop(surface, None)
        if flights: flights.stop()
        self.canvases.pop(surface, None)
        self.schedule_layout()

    def schedule_layout(self):
        if not self.layout_pending:
            self.layout_pending = GLib.timeout_add(80, self.relayout)

    def relayout(self):
        self.layout_pending = 0
        try:
            monitors = json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors'],
                                 env=self.launch_env, timeout=1, stderr=subprocess.DEVNULL))
        except (OSError, ValueError, subprocess.SubprocessError): monitors = []
        surfaces = []
        self.bounds = {}
        for surface, canvas in self.canvases.items():
            monitor = surface.desktop_monitor
            geometry = monitor.get_geometry()
            match = next((item for item in monitors if item['name'] == canvas.monitor), None)
            if match is None:
                match = next((item for item in monitors if item['x'] == geometry.x and item['y'] == geometry.y), {})
            canvas.monitor = match.get('name') or f'{monitor.get_model()}-{geometry.x}-{geometry.y}'
            left, top, right, bottom = match.get('reserved', [0, 32, 0, 0])
            width, height = match.get('width', geometry.width), match.get('height', geometry.height)
            if match.get('transform', 0) % 2: width, height = height, width
            scale = match.get('scale', 1)
            area = (int(left+16), int(top+16), max(1, round(width/scale)-int(left+right)-32),
                    max(1, round(height/scale)-int(top+bottom)-32))
            x, y = match.get('x', geometry.x), match.get('y', geometry.y)
            self.bounds[canvas.monitor] = (x, y, round(width/scale), round(height/scale))
            surfaces.append((x != 0 or y != 0, x, y, canvas.monitor, area))
        self.areas = {row[3]: row[4] for row in sorted(surfaces)}
        if self.settings['enabled']: self.place_incoming()
        layout = model.layout(self.entries if self.settings['enabled'] else [], self.areas, self.settings)
        if (self.settings['enabled'] and self.areas and not self.settings['auto_arrange']
                and any(name not in self.settings['positions'] for name in self.entries)):
            # New files get a vacant cell once. Removing an earlier file must
            # leave a gap instead of implicitly arranging the remaining icons.
            self.change(lambda settings: model.capture(settings, self.entries, self.areas, only_new=True))
        for canvas in self.canvases.values(): canvas.update(layout.get(canvas.monitor, {}))
        return False

    def change(self, update):
        try:
            self.settings = self.store.change(update)
        except (OSError, ValueError) as error:
            self.error(str(error)); return False
        self.schedule_layout()
        return True

    def setting(self, key, value):
        if key == 'enabled' and value:
            try: self.root.mkdir(exist_ok=True)
            except OSError as error: self.error(str(error)); return
        was_enabled = self.settings['enabled']
        def update(settings):
            if key in ('auto_align', 'auto_arrange'):
                model.capture(settings, self.entries, self.areas)
            settings[key] = value
            if key == 'auto_align' and value:
                model.align(settings, self.entries, self.areas)
            elif key == 'auto_arrange' and value:
                model.arrange(settings, self.entries, self.areas)
        if not self.change(update): return
        if self.settings['enabled'] and not was_enabled: self.start()
        elif was_enabled and not self.settings['enabled']:
            self.stop(); self.entries = {}; self.select(set())
        elif key == 'show_trash' and self.settings['enabled']:
            self.refresh(); self.files.refresh_trash()

    def reposition(self, monitor, names, point, anchor=None):
        self.change(lambda settings: model.move(settings, self.entries, self.areas, monitor, names, point, anchor))

    def append_menu(self, menu, row, target=None):
        separator = Gtk.SeparatorMenuItem(); menu.attach(separator, 0, 1, row, row+1); row += 1
        show = style_item(Gtk.CheckMenuItem(label='Show Desktop icons'))
        show.set_active(self.settings['enabled'])
        show.connect('toggled', lambda item: self.setting('enabled', item.get_active()))
        menu.attach(show, 0, 1, row, row+1); row += 1
        trash = style_item(Gtk.CheckMenuItem(label='Show Trash'))
        trash.set_active(self.settings['show_trash']); trash.set_sensitive(self.settings['enabled'])
        trash.connect('toggled', lambda item: self.setting('show_trash', item.get_active()))
        menu.attach(trash, 0, 1, row, row+1); row += 1
        arrange = style_item(Gtk.MenuItem(label='Arrange icons'))
        arrange.set_sensitive(self.settings['enabled'])
        submenu = Gtk.Menu(); submenu.get_style_context().add_class('desktop-context-menu')
        group = None
        for value, label in [('columns', 'Columns'), ('rows', 'Rows')]:
            item = style_item(Gtk.RadioMenuItem.new_with_label_from_widget(group, label))
            group = item; item.set_active(self.settings['flow'] == value)
            item.connect('toggled', lambda item, value=value: item.get_active() and self.setting('flow', value))
            submenu.append(item)
        submenu.append(Gtk.SeparatorMenuItem())
        auto = style_item(Gtk.CheckMenuItem(label='Auto align'))
        auto.set_tooltip_text('Snap icons to grid cells while keeping your chosen positions.')
        auto.set_active(self.settings['auto_align'])
        auto.connect('toggled', lambda item: self.setting('auto_align', item.get_active()))
        submenu.append(auto)
        automatic = style_item(Gtk.CheckMenuItem(label='Auto arrange'))
        automatic.set_tooltip_text('Keep icons packed together in the selected row or column order.')
        automatic.set_active(self.settings['auto_arrange'])
        automatic.connect('toggled', lambda item: self.setting('auto_arrange', item.get_active()))
        submenu.append(automatic)
        action(submenu, 'Align now', lambda: self.change(lambda settings: model.align(settings, self.entries, self.areas)))
        action(submenu, 'Arrange now', lambda: self.change(lambda settings: model.arrange(settings, self.entries, self.areas)))
        submenu.append(Gtk.SeparatorMenuItem())
        group = None
        for value, label in [(40, 'Small icons'), (56, 'Medium icons'), (72, 'Large icons')]:
            item = style_item(Gtk.RadioMenuItem.new_with_label_from_widget(group, label))
            group = item; item.set_active(self.settings['size'] == value)
            item.connect('toggled', lambda item, value=value: item.get_active() and self.setting('size', value))
            submenu.append(item)
        arrange.set_submenu(submenu)
        menu.attach(arrange, 0, 1, row, row+1); row += 1
        configure = style_item(Gtk.MenuItem(label='Configure desktop file menu…'))
        configure.connect('activate', lambda *_: self.files.call('ConfigureMenu', '()'))
        menu.attach(configure, 0, 1, row, row+1); row += 1
        if self.settings['enabled']:
            target = target or self.pointer_target()
            paste = style_item(Gtk.MenuItem(label='Paste'))
            paste.connect('activate', lambda *_: self.paste(target))
            menu.attach(paste, 0, 1, row, row+1); row += 1
            new = style_item(Gtk.MenuItem(label='New folder…'))
            new.connect('activate', lambda *_: self.new_folder(target))
            menu.attach(new, 0, 1, row, row+1)

    def start(self):
        try:
            self.root.mkdir(exist_ok=True)
            self.monitor = Gio.File.new_for_path(str(self.root)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
            self.monitor.connect('changed', self.changed)
            if not self.monitor_poll:
                # Output scale and panel reservations can change without a
                # GTK allocation event. Keep the usable desktop bounds current.
                self.monitor_poll = GLib.timeout_add_seconds(3, self.poll_monitors)
            self.refresh()
            if self.settings['show_trash']: self.files.refresh_trash()
        except (OSError, GLib.Error) as error: self.error(str(error))

    def stop(self):
        self.generation += 1
        self.cancellable.cancel(); self.cancellable = Gio.Cancellable()
        if self.monitor: self.monitor.cancel(); self.monitor = None
        if self.pending: GLib.source_remove(self.pending); self.pending = 0
        if self.monitor_poll: GLib.source_remove(self.monitor_poll); self.monitor_poll = 0
        self.trash_pending.clear()
        self.placements.clear()
        for flights in self.flights.values(): flights.stop()

    def poll_monitors(self):
        self.schedule_layout()
        if self.settings['show_trash']: self.files.refresh_trash()
        return True

    def changed(self, _monitor, source, other, event):
        if event == Gio.FileMonitorEvent.RENAMED and other:
            before, after = source.get_basename(), other.get_basename()
            def rename(settings):
                if before in settings['positions']:
                    settings['positions'][after] = settings['positions'].pop(before)
            self.change(rename)
            if before in self.selected:
                self.selected.discard(before); self.selected.add(after)
        if self.pending: GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(180, self.refresh)

    def refresh(self):
        self.pending = 0
        if not self.settings['enabled']: return False
        self.generation += 1; generation = self.generation
        self.cancellable.cancel(); self.cancellable = Gio.Cancellable()
        pending = {}
        def batch(enumerator, result, _data):
            try:
                entries = enumerator.next_files_finish(result)
                if generation != self.generation: enumerator.close(None); return
                for entry in entries:
                    name = entry.get_name()
                    if not entry.get_is_hidden() and model.valid_name(name):
                        if name.casefold().endswith('.desktop'):
                            launcher = Gio.DesktopAppInfo.new_from_filename(str(self.root/name))
                            if launcher:
                                entry.set_display_name(launcher.get_display_name())
                                # Legacy Fusion shortcuts used absolute artwork.
                                # Only that known default is replaced; a custom
                                # shortcut image remains the owner's choice.
                                original=launcher.get_string('Icon') or ''
                                themed=icon_library.application_name(name,original)
                                known=original in ('system-file-manager','computer','fusion-computer','accessories-calculator','preferences-system','image-x-generic','preferences-desktop-wallpaper','xetal-kvm-settings','virt-manager') or original.endswith(('/file_manager/computer.svg','/calculator/programmer_calculator/assets/calculator.svg','/kvm/icon.svg'))
                                if themed and known:
                                    fallback=['computer-vm','virt-manager','computer'] if themed=='xetal-kvm-settings' else ['application-x-executable']
                                    entry.set_icon(Gio.ThemedIcon.new_from_names([themed,*fallback]))
                                elif launcher.get_icon(): entry.set_icon(launcher.get_icon())
                        pending[name] = entry
                if entries:
                    enumerator.next_files_async(128, GLib.PRIORITY_DEFAULT, self.cancellable, batch, None)
                else:
                    enumerator.close(None)
                    if self.settings['show_trash']: pending[model.TRASH] = self.trash_info()
                    self.entries = pending; self.selected.intersection_update(pending)
                    self.place_incoming()
                    self.placements = {key: value for key, value in self.placements.items() if not value['finished']}
                    self.schedule_layout()
            except GLib.Error as error:
                if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED): self.error(error.message)
        def opened(file, result, _data):
            try:
                enumerator = file.enumerate_children_finish(result)
                if generation != self.generation: enumerator.close(None); return
                enumerator.next_files_async(128, GLib.PRIORITY_DEFAULT, self.cancellable, batch, None)
            except GLib.Error as error:
                if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED): self.error(error.message)
        Gio.File.new_for_path(str(self.root)).enumerate_children_async(ATTRIBUTES, Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT, self.cancellable, opened, None)
        return False

    def dispose(self):
        self.stop()
        self.files.dispose(); self.clipboard.dispose()
        if self.layout_pending: GLib.source_remove(self.layout_pending); self.layout_pending = 0
        self.canvases.clear()
