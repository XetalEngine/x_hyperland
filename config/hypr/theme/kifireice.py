"""Killer Instinct · Fire & Ice: dedicated material entry point."""
from functools import partial
import ki_materials as _material

STYLE = 'kifireice'

armor = partial(_material.armor, style=STYLE)
enamel = partial(_material.enamel, style=STYLE)
chrome_style = partial(_material.chrome_style, style=STYLE)
qt_style = partial(_material.qt_style, style=STYLE)
files_style = partial(_material.files_style, style=STYLE)
waybar_style = partial(_material.waybar_style, style=STYLE)
bar_controls = partial(_material.bar_controls, style=STYLE)
notification_style = partial(_material.notification_style, style=STYLE)
compositor = partial(_material.compositor, style=STYLE)
paint_surface = partial(_material.paint_surface, style=STYLE)
paint_tile = partial(_material.paint_tile, style=STYLE)
