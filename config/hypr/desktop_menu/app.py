#!/usr/bin/env python3
"""A native wallpaper context menu, owned by this Hyprland session."""
from pathlib import Path
import fcntl
import os
import signal
import socket
import subprocess
import sys
import menu_config
import appearance
import menu_hotkeys
import menu_focus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'theme'))
import runtime as theme_runtime

# GTK preferences are private to this helper. App launches retain the original
# session environment and use the existing profile-specific launchers.
LAUNCH_ENV = os.environ.copy()
os.environ.update(theme_runtime.environment(LAUNCH_ENV))
os.environ.update(GDK_BACKEND='wayland', GSETTINGS_BACKEND='keyfile',
                  XDG_CONFIG_HOME=str(ROOT / 'apps'))

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell, Pango, Gio
from desktop_icons import Icons

NAMESPACE = 'xetal-desktop-menu'
def launch(ident):
    subprocess.Popen(['python3', str(ROOT/'desktop_menu/run.py'), '--item', ident],
                     env=theme_runtime.environment(LAUNCH_ENV), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class DesktopSurface(Gtk.Window):
    def __init__(self, monitor, owner):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.owner = owner
        self.desktop_monitor = monitor
        self.menu_context = None
        self.set_name('xetal-desktop-background')
        self.set_title('Xetal desktop menu')
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, NAMESPACE)
        # Transparent input surface above the wallpaper, beneath every app and
        # panel. Native popups keep their compositor-managed pointer grab.
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.BOTTOM)
        GtkLayerShell.set_monitor(self, monitor)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        GtkLayerShell.set_exclusive_zone(self, -1)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('button-press-event', self.pressed)
        self.menu = None
        owner.icons.attach(self)

    def build_menu(self, items, desktop=False, target=None):
        menu = Gtk.Menu()
        menu.get_style_context().add_class('desktop-context-menu')
        menu.set_reserve_toggle_size(False)
        style = self.owner.config['style']
        columns = appearance.columns(items)
        available = GtkLayerShell.get_monitor(self).get_geometry().width-40
        width = min(style['width'], max(100, (available-2*style['padding']-style['accent_width'])//max(1, len(columns))-12))
        offset = self.owner.icons.append_menu(menu, 0, target) if desktop else 0
        for col, entries in enumerate(columns):
            for index, entry in enumerate(entries):
                kind = entry['kind']
                height = appearance.height(entry, style)
                if kind == 'separator':
                    item = Gtk.MenuItem(); item.set_sensitive(False)
                    item.get_style_context().add_class('divider')
                    row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                    row.set_size_request(width-2, height)
                    line = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    line.set_valign(Gtk.Align.CENTER); line.set_margin_start(12); line.set_margin_end(12)
                    row.pack_start(line, True, True, 0); item.add(row)
                else:
                    item = Gtk.MenuItem()
                    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                    row.set_margin_start(12); row.set_margin_end(12)
                    row.set_size_request(width-2, appearance.height(entry, style)-2)
                    if kind == 'spacer':
                        item.get_style_context().add_class('spacer'); item.set_sensitive(False)
                    else:
                        if style['show_icons'] and kind != 'heading':
                            icon = Path(entry['icon']).expanduser()
                            image = Gtk.Image()
                            if icon.is_absolute() and icon.is_file():
                                from gi.repository import GdkPixbuf
                                try:
                                    image.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon), style['icon_size'], style['icon_size'], True))
                                except GLib.Error: pass
                            else:
                                image.set_from_icon_name(entry['icon'], Gtk.IconSize.LARGE_TOOLBAR)
                                image.set_pixel_size(style['icon_size'])
                            row.pack_start(image, False, False, 0)
                        label = Gtk.Label(label=entry['label'], xalign=0)
                        label.set_ellipsize(Pango.EllipsizeMode.END); label.set_max_width_chars(24)
                        row.pack_start(label, True, True, 0)
                        if kind == 'heading':
                            item.set_sensitive(False); label.get_style_context().add_class('section-title')
                        elif kind == 'submenu':
                            item.set_submenu(self.build_menu(entry['children']))
                        else:
                            if style['show_hotkeys'] and self.owner.hotkeys.get(entry['id']):
                                hint = Gtk.Label(label=self.owner.hotkeys[entry['id']][0])
                                hint.set_ellipsize(Pango.EllipsizeMode.END); hint.set_max_width_chars(18)
                                hint.get_style_context().add_class('hotkey'); row.pack_end(hint, False, False, 0)
                            item.connect('activate', self.activate, entry['id'])
                    item.add(row)
                if col: item.get_style_context().add_class('after-split')
                menu.attach(item, col, col+1, offset+index, offset+index+1)
        if not desktop and not columns:
            empty = Gtk.MenuItem(label='Empty submenu'); empty.set_sensitive(False); menu.append(empty)
        menu.show_all()
        return menu

    def pressed(self, _widget, event):
        modifiers = (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK |
                     Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.SUPER_MASK |
                     Gdk.ModifierType.HYPER_MASK | Gdk.ModifierType.META_MASK)
        if event.button != 3 or event.state & modifiers:
            return False
        self.owner.dismiss()
        self.owner.refresh_style()
        if not self.owner.config['enabled']:
            return False
        if self.menu:
            self.menu.destroy()
        target = self.owner.icons.pointer_target(self.owner.icons.canvases.get(self))
        self.menu = self.build_menu(self.owner.config['items'], desktop=True, target=target)
        self.menu.attach_to_widget(self, None)
        self.owner.watch_menu(self)
        self.menu.popup_at_pointer(event)
        return True

    def activate(self, _item, ident):
        self.menu.popdown()
        try:
            launch(ident)
        except OSError as error:
            print(f'Could not open desktop menu action: {error}', file=sys.stderr)

    def dispose(self):
        if self.menu:
            self.menu.popdown()
            self.menu.destroy()
        self.destroy()


class Desktop:
    def __init__(self, display):
        self.display = display
        self.surfaces = {}
        self.events = bytearray()
        self.config = menu_config.defaults()
        self.hotkeys = {}
        self.store = menu_config.Store()
        self.icons = Icons(self, LAUNCH_ENV)
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(display.get_default_screen(), self.provider,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.refresh_style()
        self.theme_monitor=Gio.File.new_for_path(str(ROOT/'theme')).monitor_directory(Gio.FileMonitorFlags.NONE,None)
        self.theme_refresh=0
        self.theme_monitor.connect('changed',self.theme_changed)
        self.monitor_signals = [display.connect('monitor-added', self.add_monitor),
                                display.connect('monitor-removed', self.remove_monitor)]
        for index in range(display.get_n_monitors()):
            self.add_monitor(display, display.get_monitor(index))

    def refresh_style(self):
        try:
            self.config, _ = self.store.load()
            self.hotkeys = menu_hotkeys.labels(menu_hotkeys.keys.Store(ROOT))
        except (OSError, ValueError, menu_hotkeys.keys.ConfigError) as error:
            print('Keeping the last valid desktop menu:', error, file=sys.stderr)
        self.provider.load_from_data(appearance.css(self.config['style']).encode())
        self.icons.accent.parse(appearance.colors(self.config['style'])['accent'])
        settings = Gtk.Settings.get_default()
        icons=theme_runtime.icon_library.info(ROOT)
        Gtk.IconTheme.get_default().set_search_path(icons['iconSearchPaths'])
        settings.set_property('gtk-icon-theme-name',icons['iconTheme'])

    def theme_changed(self,_monitor,source,_other,_event):
        if source.get_basename() not in ('icons.json','state.json'):return
        if self.theme_refresh:GLib.source_remove(self.theme_refresh)
        def refresh():
            self.theme_refresh=0;self.refresh_style();return False
        self.theme_refresh=GLib.timeout_add(100,refresh)

    def add_monitor(self, _display, monitor):
        if monitor not in self.surfaces:
            window = DesktopSurface(monitor, self)
            self.surfaces[monitor] = window
            window.show_all()

    def remove_monitor(self, _display, monitor):
        window = self.surfaces.pop(monitor, None)
        if window:
            self.icons.detach(window)
            window.dispose()

    def dismiss(self):
        for window in self.surfaces.values():
            if window.menu: window.menu.popdown()
            window.menu_context = None

    def menu_context(self, window, session):
        canvas = self.icons.canvases.get(window)
        geometry = window.desktop_monitor.get_geometry()
        return menu_focus.MenuContext.capture(session, canvas.monitor if canvas else None,
                                              (geometry.x, geometry.y))

    def watch_menu(self, window):
        # Capture once for the invocation. The asynchronous file-actions popup
        # replacement must inherit this context, rather than start a new one.
        window.menu_context = self.menu_context(window, menu_focus.read_session(LAUNCH_ENV))

    def check_menu_context(self):
        visible = [window for window in self.surfaces.values()
                   if window.menu and window.menu.get_visible()]
        if not visible:
            return
        session = menu_focus.read_session(LAUNCH_ENV)
        for window in visible:
            if window.menu_context is None:
                window.menu_context = self.menu_context(window, session)
            elif window.menu_context.changed(session):
                window.menu.popdown()
                window.menu_context = None

    def session_event(self, stream, condition):
        if condition & (GLib.IOCondition.HUP | GLib.IOCondition.ERR):
            Gtk.main_quit()
            return False
        try:
            data = stream.recv(65536)
        except BlockingIOError:
            return True
        if not data:
            Gtk.main_quit()
            return False
        self.events.extend(data)
        context_event = False
        while b'\n' in self.events:
            line, _, self.events = self.events.partition(b'\n')
            if line.startswith((b'monitoradded', b'monitorremoved', b'configreloaded')):
                self.icons.schedule_layout()
            if line.startswith((b'workspacev2>>', b'focusedmonv2>>', b'activespecialv2>>',
                                b'activewindowv2>>', b'moveworkspacev2>>', b'monitorremoved')):
                context_event = True
        if context_event:
            self.check_menu_context()
        return True

    def dispose(self):
        if self.theme_refresh:GLib.source_remove(self.theme_refresh)
        self.theme_monitor.cancel()
        self.icons.dispose()
        for identifier in self.monitor_signals:
            self.display.disconnect(identifier)
        for window in self.surfaces.values():
            window.dispose()
        self.surfaces.clear()
        Gtk.StyleContext.remove_provider_for_screen(self.display.get_default_screen(), self.provider)


def main():
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not runtime:
        return 1
    instance = Path(runtime) / 'hypr' / signature
    with (instance / 'desktop-menu.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        if not Gtk.init_check()[0] or not GtkLayerShell.is_supported():
            return 1
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.connect(str(instance / '.socket2.sock'))
            stream.setblocking(False)
            desktop = Desktop(Gdk.Display.get_default())
            GLib.io_add_watch(stream, GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
                              desktop.session_event)
            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (Gtk.main_quit(), False)[1])
            try:
                Gtk.main()
            finally:
                desktop.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
