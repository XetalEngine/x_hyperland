#!/usr/bin/python3
"""Four colored quadrants on each isolated test output's background layer."""
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gdk, Gtk, GtkLayerShell

COLORS = ((230, 35, 45), (30, 210, 65), (40, 75, 230), (235, 205, 30))
windows = []
display = Gdk.Display.get_default()
for index in range(display.get_n_monitors()):
    window = Gtk.Window()
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, 'fusion-cube-test-wallpaper')
    GtkLayerShell.set_monitor(window, display.get_monitor(index))
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.BACKGROUND)
    GtkLayerShell.set_exclusive_zone(window, -1)
    for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
        GtkLayerShell.set_anchor(window, edge, True)
    area = Gtk.DrawingArea()
    def paint(widget, cr):
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        for i, color in enumerate(COLORS):
            cr.set_source_rgb(*(c / 255 for c in color))
            cr.rectangle((i % 2) * w / 2, (i // 2) * h / 2, w / 2, h / 2)
            cr.fill()
        return False
    area.connect('draw', paint)
    window.add(area)
    window.show_all()
    windows.append(window)
Gtk.main()
