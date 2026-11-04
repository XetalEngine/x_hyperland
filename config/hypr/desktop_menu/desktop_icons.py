"""Transparent, session-owned desktop icons on the existing bottom layer."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
import icons_model as model
from desktop_files import Files

TARGETS = [Gtk.TargetEntry.new('application/x-xetal-desktop-icons', Gtk.TargetFlags.SAME_APP, 0),
           Gtk.TargetEntry.new('text/uri-list', 0, 1)]
ATTRIBUTES = 'standard::name,standard::display-name,standard::type,standard::icon,standard::is-hidden,thumbnail::path,thumbnail::is-valid'


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
        # Paint the themed selection/hover background on the tile's RGBA
        # window; an input-only EventBox would paint only the label color.
        self.set_visible_window(True); self.set_above_child(True)
        self.get_style_context().add_class('desktop-icon')
        self.set_tooltip_text(info.get_display_name())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(7); box.set_margin_bottom(7)
        box.set_margin_start(4); box.set_margin_end(4)
        self.image = Gtk.Image.new_from_gicon(info.get_icon(), Gtk.IconSize.DIALOG)
        box.pack_start(self.image, False, False, 0)
        label = Gtk.Label(label=info.get_display_name())
        label.set_justify(Gtk.Justification.CENTER)
        label.set_line_wrap(True); label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_lines(2); label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(16); label.set_xalign(.5); label.set_yalign(0)
        self.label = label
        box.pack_start(label, True, True, 0)
        self.add(box)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('button-press-event', self.pressed)
        self.connect('button-release-event', self.released)
        self.connect('motion-notify-event', self.motion)
        self.connect('drag-data-get', self.drag_data)
        self.connect('drag-end', self.drag_end)
        self.resize_icon()

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

    def pressed(self, _widget, event):
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
            if shift and controller.anchor in self.canvas.positions:
                names = list(self.canvas.positions)
                a, b = sorted((names.index(controller.anchor), names.index(self.name)))
                controller.select(set(names[a:b+1]) | (controller.selected if control else set()))
            elif control:
                controller.select(controller.selected ^ {self.name})
            elif self.name not in controller.selected:
                controller.select({self.name})
            controller.anchor = self.name
            self.press = (event.x, event.y, bool(control or shift))
        return True

    def released(self, _widget, event):
        if event.button == 1 and self.press:
            if not self.press[2]: self.canvas.controller.select({self.name})
            self.press = None
        return True

    def motion(self, _widget, event):
        if not self.press or not event.state & Gdk.ModifierType.BUTTON1_MASK: return False
        if not self.drag_check_threshold(int(self.press[0]), int(self.press[1]), int(event.x), int(event.y)): return False
        controller = self.canvas.controller
        controller.drag = dict(names=controller.ordered_selection(), anchor=self.name,
                               offset=[self.press[0], self.press[1]])
        self.press = None
        context = self.drag_begin_with_coordinates(Gtk.TargetList.new(TARGETS),
            Gdk.DragAction.COPY | Gdk.DragAction.MOVE, 1, event, -1, -1)
        Gtk.drag_set_icon_gicon(context, self.info.get_icon(), 0, 0)
        return True

    def drag_data(self, _widget, _context, selection, info, _time):
        controller = self.canvas.controller
        if info == 0:
            selection.set(selection.get_target(), 8, json.dumps(controller.drag).encode())
        else:
            selection.set_uris(controller.urls(controller.drag.get('names', [])))

    def drag_end(self, *_):
        self.press = None
        self.canvas.controller.drag = {}
        for canvas in self.canvas.controller.canvases.values(): canvas.highlight(None)


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
        self.search, self.search_time = '', 0
        self.set_can_focus(True)
        self.get_style_context().add_class('desktop-icons')
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('button-press-event', self.pressed)
        self.connect('button-release-event', self.released)
        self.connect('motion-notify-event', self.motion)
        self.connect('key-press-event', self.key)
        self.connect_after('draw', self.draw_selection)
        self.drag_dest_set(Gtk.DestDefaults(0), TARGETS, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
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
            if name not in positions or self.tiles[name].info != self.controller.entries.get(name):
                self.tiles.pop(name).destroy()
        for name, point in positions.items():
            if name not in self.tiles:
                self.tiles[name] = Tile(self, name, self.controller.entries[name])
                self.put(self.tiles[name], *point)
                self.tiles[name].show_all()
            else:
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
        selected = self.controller.ordered_selection()
        if key == 'Escape': self.controller.select(set())
        elif control and key.lower() == 'a': self.controller.select(set(self.positions))
        elif key in ('Return', 'KP_Enter') and selected:
            self.controller.files.open(self.controller.urls())
        elif key == 'Delete' and selected:
            self.controller.files.call('Trash', '(as)', self.controller.urls())
        elif key == 'F2' and len(selected) == 1:
            self.controller.files.call('Rename', '(s)', self.controller.uri(selected[0]))
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
        self.controller.owner.dismiss()
        self.controller.owner.refresh_style()
        menu = Gtk.Menu(); menu.get_style_context().add_class('desktop-context-menu')
        names = self.controller.ordered_selection()
        action(menu, 'Open', lambda: self.controller.files.open(self.controller.urls(names)))
        if all(self.controller.entries[name].get_file_type() != Gio.FileType.DIRECTORY for name in names):
            action(menu, 'Open with…', lambda: self.controller.files.open(self.controller.urls(names), True))
        menu.append(Gtk.SeparatorMenuItem())
        action(menu, 'Rename…', lambda: self.controller.files.call('Rename', '(s)', self.controller.uri(names[0])), len(names) == 1)
        action(menu, 'Move to Trash', lambda: self.controller.files.call('Trash', '(as)', self.controller.urls(names)))
        menu.append(Gtk.SeparatorMenuItem())
        action(menu, 'Properties', lambda: self.controller.files.call('Properties', '(as)', self.controller.urls(names)))
        if self.surface.menu: self.surface.menu.destroy()
        self.surface.menu = menu
        menu.attach_to_widget(self, None); menu.show_all()
        if event: menu.popup_at_pointer(event)
        else:
            tile = self.tiles.get(names[0])
            menu.popup_at_widget(tile or self, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

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
        copy = bool(state & Gdk.ModifierType.CONTROL_MASK)
        possible = context.get_actions()
        selected = Gdk.DragAction.COPY if copy or not possible & Gdk.DragAction.MOVE else Gdk.DragAction.MOVE
        if not selected & possible: selected = Gdk.DragAction.COPY if possible & Gdk.DragAction.COPY else Gdk.DragAction(0)
        self.drop_action = selected
        self.highlight(self.destination(x, y))
        Gdk.drag_status(context, selected, timestamp)
        return bool(selected)

    def drop(self, _widget, context, x, y, timestamp):
        target = self.drag_dest_find_target(context, None)
        if not target or not self.controller.settings['enabled']: return False
        if not self.drag_motion(self, context, x, y, timestamp): return False
        self.drag_get_data(context, target, timestamp)
        return True

    def received(self, _widget, context, x, y, data, info, timestamp):
        success = False
        try:
            if data.get_length() > 2*1024*1024: raise ValueError('Too many files in this drop.')
            drag = {}
            if info == 0:
                drag = json.loads(bytes(data.get_data()))
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
            copy = self.drop_action == Gdk.DragAction.COPY
            destination = self.destination(x, y)
            if destination is None and not copy and len(names) == len(urls):
                offset = drag.get('offset', [model.cell(self.controller.settings)[0]/2, 20])
                self.controller.reposition(self.monitor, names, (x-offset[0], y-offset[1]), drag.get('anchor'))
            else:
                self.controller.files.transfer(urls, self.controller.uri(destination), copy)
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
        self.selected, self.anchor, self.drag = set(), None, {}
        self.monitor = None
        self.generation = 0
        self.pending = 0
        self.layout_pending = 0
        self.monitor_poll = 0
        self.cancellable = Gio.Cancellable()
        self.files = Files(self.error)
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
        return Gio.File.new_for_path(str(self.root/name if name else self.root)).get_uri()

    def ordered_selection(self):
        return [name for canvas in self.canvases.values() for name in canvas.positions if name in self.selected]

    def urls(self, names=None):
        return [self.uri(name) for name in (self.ordered_selection() if names is None else names)]

    def select(self, names):
        self.selected = set(names) & self.entries.keys()
        for canvas in self.canvases.values(): canvas.update_selection()

    def attach(self, surface):
        canvas = Canvas(self, surface)
        scroll = Gtk.ScrolledWindow()
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class('desktop-icons')
        scroll.add(canvas); surface.add(scroll)
        self.canvases[surface] = canvas
        surface.connect('size-allocate', lambda *_: self.schedule_layout())
        signal = surface.desktop_monitor.connect('notify::geometry', lambda *_: self.schedule_layout())
        surface.connect('destroy', lambda *_: surface.desktop_monitor.disconnect(signal))
        self.schedule_layout()

    def detach(self, surface):
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
            surfaces.append((x != 0 or y != 0, x, y, canvas.monitor, area))
        self.areas = {row[3]: row[4] for row in sorted(surfaces)}
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

    def reposition(self, monitor, names, point, anchor=None):
        self.change(lambda settings: model.move(settings, self.entries, self.areas, monitor, names, point, anchor))

    def append_menu(self, menu, row):
        separator = Gtk.SeparatorMenuItem(); menu.attach(separator, 0, 1, row, row+1); row += 1
        show = style_item(Gtk.CheckMenuItem(label='Show Desktop icons'))
        show.set_active(self.settings['enabled'])
        show.connect('toggled', lambda item: self.setting('enabled', item.get_active()))
        menu.attach(show, 0, 1, row, row+1); row += 1
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
        if self.settings['enabled']:
            new = style_item(Gtk.MenuItem(label='New folder…'))
            new.connect('activate', lambda *_: self.files.call('NewFolder', '(s)', self.uri()))
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
        except (OSError, GLib.Error) as error: self.error(str(error))

    def stop(self):
        self.generation += 1
        self.cancellable.cancel(); self.cancellable = Gio.Cancellable()
        if self.monitor: self.monitor.cancel(); self.monitor = None
        if self.pending: GLib.source_remove(self.pending); self.pending = 0
        if self.monitor_poll: GLib.source_remove(self.monitor_poll); self.monitor_poll = 0

    def poll_monitors(self):
        self.schedule_layout()
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
                    if not entry.get_is_hidden() and model.valid_name(entry.get_name()): pending[entry.get_name()] = entry
                if entries:
                    enumerator.next_files_async(128, GLib.PRIORITY_DEFAULT, self.cancellable, batch, None)
                else:
                    enumerator.close(None)
                    self.entries = pending; self.selected.intersection_update(pending)
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
        if self.layout_pending: GLib.source_remove(self.layout_pending); self.layout_pending = 0
        self.canvases.clear()
