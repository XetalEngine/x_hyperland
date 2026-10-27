#!/usr/bin/env python3
"""Brief, noninteractive labels on the connected Hyprland displays."""
import json
import os
from pathlib import Path
import subprocess
import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QLabel
import desktop_settings as settings


def main():
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'): return 1
    q = QApplication(sys.argv[:1]); q.setDesktopFileName('hypr-display-id')
    displays = [m for m in settings.monitors() if not m.get('disabled')]
    labels = []
    for number, monitor in enumerate(displays, 1):
        w = QLabel(f"<span style='font-size:56px;font-weight:700'>{number}</span><br>{monitor['name']} · {monitor.get('model', '')}")
        w.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        w.setWindowTitle(monitor['name']); w.setAlignment(Qt.AlignmentFlag.AlignCenter); w.resize(360, 150)
        w.setStyleSheet('background:#182d38;color:#91f0df;border:2px solid #64dace;border-radius:14px;padding:12px;font-size:15px;')
        w.show(); labels.append(w)
    def position():
        clients = json.loads(settings.ctl('-j', 'clients'))
        for monitor in displays:
            client = next((c for c in clients if c['pid'] == os.getpid() and c['title'] == monitor['name']), None)
            if not client: continue
            width = monitor['width']/monitor['scale']; height = monitor['height']/monitor['scale']
            if monitor.get('transform', 0) % 2: width, height = height, width
            x, y = round(monitor['x']+(width-360)/2), round(monitor['y']+(height-150)/2)
            settings.ctl('dispatch', 'movewindowpixel', f"exact {x} {y},address:{client['address']}")
    QTimer.singleShot(180, position); QTimer.singleShot(4000, q.quit)
    return q.exec()


if __name__ == '__main__': raise SystemExit(main())
