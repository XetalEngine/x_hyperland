"""Anchor the clipboard beside the bar, in compositor logical coordinates."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from quick_panel.model import monitor_at
from quick_panel.placement import prepare

ROOT = Path(__file__).resolve().parents[1]


def geometry(monitor, cursor, edge='top', *, from_bar=False):
    width, height = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2:
        width, height = height, width
    scale = monitor.get('scale', 1) or 1
    width, height = width / scale, height / scale
    left, top, right, bottom = monitor.get('reserved', [0, 0, 0, 0])
    popup_width = max(1, min(440, width - left - right - 24))
    popup_height = max(1, min(1080, height - top - bottom - 20))
    # Bar clicks line up with the icon even with a centered/floating bar.
    # The keyboard shortcut uses the same output's right-hand tray area.
    x = cursor['x'] - monitor['x'] - popup_width + 24 if from_bar else width - right - popup_width - 12
    x = max(left + 12, min(x, width - right - popup_width - 12))
    edge = 'bottom' if edge == 'bottom' else 'top'
    y = height - bottom - popup_height - 10 if edge == 'bottom' else top + 10
    return dict(monitor=monitor['id'], edge=edge, relative_x=round(x), relative_y=round(y),
                width=round(popup_width), height=round(popup_height))


def prepare_popup(*, from_bar=False):
    def query(name):
        return json.loads(subprocess.check_output(['hyprctl', '-j', name], text=True,
                          stderr=subprocess.DEVNULL, timeout=1))
    cursor = query('cursorpos')
    monitor = monitor_at(query('monitors'), cursor)
    if monitor is None:
        raise RuntimeError('No display is available for clipboard history.')
    try:
        options = json.loads((ROOT / 'waybar/options.json').read_text())
        edge = options.get('position', 'top')
    except (OSError, ValueError, AttributeError):
        edge = 'top'
    return prepare(geometry(monitor, cursor, edge, from_bar=from_bar), rule='fusion-clipboard-history')
