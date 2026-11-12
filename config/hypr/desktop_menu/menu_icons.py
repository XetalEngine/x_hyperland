"""Theme-colored menu symbols shared with Fusion Files, without changing actions."""
import json
from pathlib import Path
import cairo
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Rsvg', '2.0')
from gi.repository import GdkPixbuf, GLib, Gtk, Rsvg

try:
    SYMBOLS = json.loads((Path(__file__).resolve().parents[1]/'theme/menu_icons.json').read_text())
except (OSError, ValueError):
    SYMBOLS = {}

_size, _enabled = 22, True


def configure(style):
    global _size, _enabled
    _size, _enabled = style['icon_size'], style['show_icons']


def image(name, size=None):
    if not _enabled:
        return None
    size = size or _size
    widget = Gtk.Image()
    widget.set_pixel_size(size)
    widget.set_size_request(size, size)
    body = SYMBOLS.get(name)
    path = Path(name).expanduser()
    if body is None and path.is_absolute() and path.is_file():
        try:
            widget.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True))
            return widget
        except GLib.Error:
            pass
    if body is None and name and Gtk.IconTheme.get_default().has_icon(name):
        widget.set_from_icon_name(name, Gtk.IconSize.MENU)
        return widget
    body = body or SYMBOLS.get('application-x-executable')
    if not body:
        widget.set_from_icon_name(name or 'application-x-executable', Gtk.IconSize.MENU)
        return widget
    widget.get_style_context().add_class('menu-action-icon')
    previous = None

    def repaint(*_):
        nonlocal previous
        color = widget.get_style_context().get_color(widget.get_state_flags()).to_string()
        scale = max(1, widget.get_scale_factor())
        if previous == (color, scale):
            return
        svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
               f"stroke='{color}' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>{body}</svg>")
        try:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size*scale, size*scale)
            surface.set_device_scale(scale, scale)
            viewport = Rsvg.Rectangle()
            viewport.x = viewport.y = 0; viewport.width = viewport.height = size
            Rsvg.Handle.new_from_data(svg.encode()).render_document(cairo.Context(surface), viewport)
            widget.set_from_surface(surface)
            previous = (color, scale)
        except GLib.Error:
            widget.set_from_icon_name('application-x-executable', Gtk.IconSize.MENU)

    widget.connect('style-updated', repaint)
    widget.connect('state-flags-changed', repaint)
    widget.connect('notify::scale-factor', repaint)
    repaint()
    return widget


def decorate(item, name):
    """Leave Gtk's check/radio indicator and activation wiring on the original item."""
    icon = image(name)
    if icon is None:
        return item
    label = item.get_child()
    if label is None:
        return item
    item.remove(label)
    label.set_xalign(0)
    # Custom rows must keep the same accessible name as the original Gtk label.
    item.get_accessible().set_name(label.get_text())
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.pack_start(icon, False, False, 0)
    row.pack_start(label, True, True, 0)
    item.add(row)
    return item
