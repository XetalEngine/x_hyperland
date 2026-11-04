"""The Fusion Files 720 ms fly-to-Trash motion, on the desktop bottom layer."""
import math
import time
import cairo
from gi.repository import Gdk, Gtk, GLib


def snapshot(tile, surface, size):
    image = tile.image
    point = image.translate_coordinates(surface, 0, 0)
    if point is None: return None
    width, height = image.get_allocated_width(), image.get_allocated_height()
    scale = image.get_scale_factor()
    bitmap = cairo.ImageSurface(cairo.FORMAT_ARGB32, size*scale, size*scale)
    bitmap.set_device_scale(scale, scale)
    cr = cairo.Context(bitmap)
    # A directory notification can queue a new allocation immediately before
    # Delete. Render its icon asset directly instead of drawing an unallocated
    # Gtk.Image, which GTK refuses and would leave an empty animation frame.
    asset = image.get_property('surface') if image.get_storage_type() == Gtk.ImageType.SURFACE else None
    if asset:
        sx, sy = asset.get_device_scale()
        cr.set_source_surface(asset, (size-asset.get_width()/sx)/2, (size-asset.get_height()/sy)/2)
        cr.paint()
    else:
        try:
            icon = Gtk.IconTheme.get_for_screen(image.get_screen()).lookup_by_gicon_for_scale(
                tile.info.get_icon(), size, scale, Gtk.IconLookupFlags.FORCE_SIZE)
            if not icon: return None
            pixbuf = icon.load_icon()
            cr.scale(1/scale, 1/scale)
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, (size*scale-pixbuf.get_width())/2,
                                       (size*scale-pixbuf.get_height())/2)
            cr.paint()
        except GLib.Error: return None
    geometry = surface.desktop_monitor.get_geometry()
    center = (geometry.x+point[0]+width/2, geometry.y+point[1]+height/2)
    return bitmap, center, size


def point_on_curve(origin, target, t):
    lift = min(140, abs(target[0]-origin[0])*.22+50)
    points = (origin, (origin[0]-30, origin[1]-lift), (target[0]+60, target[1]-lift), target)
    weights = ((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)
    return tuple(sum(p[axis]*weight for p, weight in zip(points, weights)) for axis in (0, 1))


class Flights(Gtk.DrawingArea):
    def __init__(self, surface, accent):
        super().__init__()
        self.surface, self.accent = surface, accent
        self.batches, self.tick = [], 0
        self.set_no_show_all(True)
        self.set_can_focus(False)
        self.connect('draw', self.draw_flights)

    def fly(self, images, target):
        if not images or not self.get_settings().get_property('gtk-enable-animations'): return
        self.batches.append((time.monotonic(), images[:8], target))
        self.show()
        if not self.tick: self.tick = self.add_tick_callback(self.frame)

    def frame(self, *_):
        now = time.monotonic()
        self.batches = [batch for batch in self.batches if now-batch[0] < .720]
        self.queue_draw()
        if self.batches: return True
        self.tick = 0; self.hide(); return False

    def stop(self):
        if self.tick: self.remove_tick_callback(self.tick); self.tick = 0
        self.batches.clear(); self.hide()

    def draw_flights(self, _widget, cr):
        geometry = self.surface.desktop_monitor.get_geometry()
        cr.save(); cr.translate(-geometry.x, -geometry.y)
        color = self.accent()
        for started, images, target in self.batches:
            progress = min(1, (time.monotonic()-started)/.720)
            for i, (bitmap, origin, size) in enumerate(images):
                t = max(0, min(1, (progress-i*.025)/(1-i*.025)))
                eased = t*t*(3-2*t)
                cr.new_path()
                for step in range(11):
                    p = point_on_curve(origin, target, max(0, eased-.18)+min(.18, eased)*step/10)
                    (cr.move_to if step == 0 else cr.line_to)(*p)
                cr.set_source_rgba(color.red, color.green, color.blue, .22*(1-t))
                cr.set_line_width(2); cr.stroke()
                cr.save(); cr.translate(*point_on_curve(origin, target, eased))
                cr.rotate(math.radians(-18*math.sin(math.pi*t)))
                factor = max(8, size*(1-.84*eased))/size
                cr.scale(factor, factor); cr.set_source_surface(bitmap, -size/2, -size/2)
                cr.paint_with_alpha(1 if t < .8 else (1-t)*5); cr.restore()
            if progress > .7:
                pulse = (progress-.7)/.3
                cr.arc(*target, 14+18*pulse, 0, math.tau)
                cr.set_source_rgba(color.red, color.green, color.blue, .7*(1-pulse))
                cr.set_line_width(2); cr.stroke()
        cr.restore()
        return False
