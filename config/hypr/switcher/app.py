#!/usr/bin/env python3
"""Session-owned MRU switcher. Ordered compositor events make fast taps reliable."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import signal

from functools import lru_cache

from PyQt6.QtCore import Qt, QEvent, QRectF, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QLinearGradient
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QSizePolicy)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'control_center'))
from desktop_settings import ctl
sys.path.insert(0,str(ROOT/'theme'))
import runtime as theme_runtime
from window_chrome import close_button
sys.path.insert(0, str(ROOT))
from switcher import preferences
from switcher.scene import Scene, sample_clients, sample_pictures
from switcher.previews import PreviewQueue

def color(value): return QColor(theme_runtime.recolor(value,theme_runtime.mode()))

EXCLUDED = {'xetal-switcher', 'xetal-launcher', 'hypr-display-id'}


def windows(clients, active=''):
    result = [c for c in clients if c.get('mapped') and c.get('class') not in EXCLUDED
              and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))]
    return sorted(result, key=lambda c: (c['address'] != active,
                  c.get('focusHistoryID', -1) if c.get('focusHistoryID', -1) >= 0 else 100000))


def focus(address):
    # Resolve the live address again: titles, monitors and workspaces may have changed.
    client = next((c for c in json.loads(ctl('-j', 'clients')) if c['address'] == address and c.get('mapped')), None)
    if client is None: return False
    # focuswindow reveals the window's existing workspace, including special workspaces.
    # No move-to-workspace or move-to-monitor dispatcher is used here.
    if ctl('dispatch', 'focuswindow', 'address:'+address) != 'ok': return False
    return True


def window_icon(client):
    return icon_for_class(client.get('class') or client.get('initialClass') or 'application-x-executable')


@lru_cache(maxsize=256)
def icon_for_class(name):
    for candidate in (name, name.lower(), name.replace(' ', '-').lower()):
        icon = QIcon.fromTheme(candidate)
        if not icon.isNull(): return icon
    try:
        from gi.repository import Gio
        for info in Gio.AppInfo.get_all():
            if name.lower() in ((info.get_id() or '').removesuffix('.desktop').lower(),
                                (info.get_startup_wm_class() or '').lower() if hasattr(info, 'get_startup_wm_class') else ''):
                icon = info.get_icon()
                if hasattr(icon, 'get_file'): return QIcon(icon.get_file().get_path())
                if hasattr(icon, 'get_names'):
                    for candidate in icon.get_names():
                        found = QIcon.fromTheme(candidate)
                        if not found.isNull(): return found
    except (ImportError, AttributeError): pass
    return QIcon.fromTheme('application-x-executable')


def scoped(clients, options, active, monitor):
    ordered = windows(clients, active.get('address', ''))
    scope = options['scope']
    if scope == 'monitor':
        return [c for c in ordered if c.get('monitor') == (monitor or {}).get('id')]
    if scope == 'workspace':
        workspace = active.get('workspace') or (monitor or {}).get('activeWorkspace', {})
        return [c for c in ordered if c.get('workspace', {}).get('id') == workspace.get('id')]
    if scope == 'application':
        return [c for c in ordered if c.get('class') == active.get('class')] if active else ordered
    return ordered


class Switcher(QWidget):
    def __init__(self, preview=False):
        super().__init__()
        self.preview = preview; self.original = ''; self.monitor = None; self.clients = []; self.index = 0
        self.options = preferences.current(); self.monitors = {}; self.generation = 0
        self.setWindowTitle('Switch applications')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        theme_runtime.install(QApplication.instance(),
            'QWidget { color:#e6eef9; font:13px "Noto Sans"; background:transparent; }')
        root = QVBoxLayout(self); root.setContentsMargins(24, 18, 24, 18); root.setSpacing(8)
        top = QHBoxLayout(); self.title = QLabel(); self.title.setStyleSheet('font-size:21px; font-weight:700;')
        top.addWidget(self.title); top.addStretch(); self.count = QLabel(); top.addWidget(self.count)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.count.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.setStretch(0, 1); top.setStretch(1, 0); top.setStretch(2, 1)
        self.close_button = close_button(self, self.cancel, 'Cancel app switching'); top.addWidget(self.close_button)
        root.addLayout(top)
        self.scene = Scene(); self.scene.activated.connect(self.choose); self.scene.stepped.connect(self.cycle)
        root.addWidget(self.scene, 1)
        self.detail = QLabel(); self.detail.setWordWrap(False); root.addWidget(self.detail)
        self.detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.hint = QLabel('Hold Super · Tab / Shift+Tab to cycle · Release Super to open · Esc to cancel')
        self.hint.setWordWrap(True); root.addWidget(self.hint)
        self.queue = PreviewQueue(self); self.queue.changed.connect(lambda _: self.scene.update())
        self.scene.pictures = self.queue.cache
        self.position_timer = QTimer(self); self.position_timer.setSingleShot(True)
        self.position_timer.timeout.connect(self.position)
        for obj in (self, self.scene, self.close_button): obj.installEventFilter(self)
        self.resize(1100, 640)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = theme_runtime.colors(); fill = QColor(colors['Window']); fill.setAlpha(round(self.options['opacity']*2.55))
        p.setBrush(fill); p.setPen(QPen(QColor(colors['Accent']), 1.5))
        radius = 4 if theme_runtime.design() == 'binaryknife' else 12
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), radius, radius)

    def begin(self, direction=1):
        if self.isVisible(): self.cycle(direction); return
        self.options = preferences.current()
        clients = json.loads(ctl('-j', 'clients'))
        active = json.loads(ctl('-j', 'activewindow')); self.original = active.get('address', '')
        monitors = json.loads(ctl('-j', 'monitors'))
        self.monitor = next((m for m in monitors if m.get('focused')), monitors[0] if monitors else None)
        self.monitors = {m['id']: (i+1, m['name']) for i, m in enumerate(monitors)}
        chosen = scoped(clients, self.options, active, self.monitor)
        self.populate(chosen, self.monitors)
        if not self.clients: return
        # When the active window is excluded, start at the first candidate rather
        # than skipping it. A backwards invocation starts at the last candidate.
        starts_here = self.clients[0]['address'] == self.original
        self.select((direction if starts_here else (0 if direction > 0 else -1)) % len(self.clients), False)
        self.fit_monitor(); self.generation += 1
        self.show(); self.raise_(); self.activateWindow(); self.scene.setFocus()
        if self.options['live_previews'] and self.options['style'] != 'fusion':
            self.queue.start(); self.request_previews()
        self.position_timer.start(30)

    def populate(self, clients, monitors=None):
        self.clients = [{**client, '_icon': client.get('_icon') or window_icon(client)} for client in clients]
        self.monitors = monitors or self.monitors
        self.scene.configure(self.options, self.clients); self.index = 0
        self.title.setText(preferences.STYLES[self.options['style']]); self.describe()

    def fit_monitor(self):
        if not self.monitor: return
        m = self.monitor; scale = max(.25, m.get('scale', 1))
        width, height = m['width']/scale, m['height']/scale
        if m.get('transform', 0) % 2: width, height = height, width
        left, top, right, bottom = (m.get('reserved') or [0, 0, 0, 0])
        width, height = max(200, width-left-right-24), max(200, height-top-bottom-24)
        size = self.options['size']/100
        self.resize(round(min(width, max(480, width*size))), round(min(height, max(300, height*size))))

    def position(self):
        if not self.isVisible() or self.preview or not self.monitor: return
        try:
            own = next(c for c in json.loads(ctl('-j', 'clients')) if c.get('pid') == os.getpid())
            m = self.monitor; width, height = m['width']/m['scale'], m['height']/m['scale']
            if m.get('transform', 0) % 2: width, height = height, width
            left, top, right, bottom = (m.get('reserved') or [0, 0, 0, 0])
            x = round(m['x']+left+(width-left-right-self.width())/2)
            y = round(m['y']+top+(height-top-bottom-self.height())/2)
            ctl('dispatch', 'movewindowpixel', f'exact {x} {y},address:'+own['address'])
            ctl('dispatch', 'focuswindow', 'address:'+own['address'])
        except (ValueError, StopIteration, KeyError): pass

    def select(self, index, animate=True):
        if not self.clients: return
        self.index = index % len(self.clients); self.scene.select(self.index, animate)
        self.describe(); self.request_previews()

    def cycle(self, direction):
        self.select(self.index+direction)

    def request_previews(self):
        if self.preview: return
        # Capture the incoming selection immediately, then visible neighbors.
        wanted = ([self.clients[self.index]['address']] if self.clients else [])+self.scene.visible_addresses()
        self.queue.request(wanted)

    def describe(self):
        total = len(self.clients)
        self.count.setText(f'{self.index+1 if total else 0} / {total} · {preferences.SCOPES[self.options["scope"]]}')
        if not total: self.detail.clear(); return
        client = self.clients[self.index]
        workspace = str(client.get('workspace', {}).get('name', '?')).removeprefix('special:')
        monitor = self.monitors.get(client.get('monitor'), ('?', '?'))[0]
        text = f'{client.get("title") or client.get("class", "Window")}  ·  Workspace {workspace}  ·  Monitor {monitor}'
        self.detail.setToolTip(text)
        self.detail.setText(self.detail.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(100, self.width()-60)))

    def remove_window(self, address):
        if not self.clients: return
        chosen = self.clients[self.index]['address']
        clients = [c for c in self.clients if c['address'] != address]
        if len(clients) == len(self.clients): return
        old_index = self.index
        self.populate(clients)
        if not clients: self.cancel(); return
        self.select(next((i for i, c in enumerate(clients) if c['address'] == chosen), min(old_index, len(clients)-1)), False)

    def choose(self, index):
        self.select(index, False); self.commit()

    def commit(self):
        if not self.isVisible(): return
        address = self.clients[self.index]['address'] if self.clients else self.original
        self.hide()
        if address and not self.preview:
            if not focus(address) and self.original: focus(self.original)
        if self.preview: QApplication.instance().quit()

    def cancel(self):
        was_visible = self.isVisible(); self.hide()
        if was_visible and self.original and not self.preview: focus(self.original)
        if self.preview: QApplication.instance().quit()

    def hideEvent(self, event):
        self.generation += 1; self.position_timer.stop(); self.queue.stop(); self.scene.animation.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        event.ignore(); self.cancel()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape: self.cancel(); return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self.commit(); return True
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                reverse = key in (Qt.Key.Key_Backtab, Qt.Key.Key_Left, Qt.Key.Key_Up) or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self.cycle(-1 if reverse else 1); return True
        return super().eventFilter(obj, event)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--preview'); parser.add_argument('--demo', action='store_true')
    parser.add_argument('--style', choices=preferences.STYLES); args = parser.parse_args()
    app = QApplication(sys.argv[:1]); app.setApplicationName('xetal-switcher'); app.setDesktopFileName('xetal-switcher')
    app.setQuitOnLastWindowClosed(False); app.setStyle('Fusion')
    QIcon.setThemeSearchPaths([str(Path.home()/'.local/share/icons'), '/usr/share/icons'])
    QIcon.setFallbackThemeName('hicolor'); QIcon.setThemeName('Papirus-Dark')
    window = Switcher(bool(args.preview or args.demo)); app.aboutToQuit.connect(window.queue.shutdown)
    if args.preview or args.demo:
        if args.style: window.options['style'] = args.style
        window.populate(sample_clients(), {0: (1, 'Left'), 1: (2, 'Center'), 2: (3, 'Right')})
        window.scene.pictures = sample_pictures(window.clients); window.select(1, False)
        window.hint.setText('Example windows · Tab / arrows to explore · Esc to close')
        window.show(); window.scene.setFocus()
        if args.preview: QTimer.singleShot(150, lambda: (window.grab().save(args.preview), app.quit()))
        return app.exec()
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']
    lock = (runtime/'switcher.lock').open('a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: return 0
    lifetime = QLocalSocket(app); buffer = bytearray()
    def read():
        buffer.extend(bytes(lifetime.readAll()))
        while b'\n' in buffer:
            line, _, rest = buffer.partition(b'\n'); buffer[:] = rest
            command = line.decode(errors='replace')
            try:
                if command == 'custom>>xetal-switcher:next': window.begin(1)
                elif command == 'custom>>xetal-switcher:previous': window.begin(-1)
                elif command == 'custom>>xetal-switcher:commit': window.commit()
                elif command == 'custom>>xetal-switcher:cancel': window.cancel()
                elif command.startswith('closewindow>>') and window.isVisible():
                    window.remove_window('0x'+command.split('>>', 1)[1].removeprefix('0x'))
            except Exception as error:
                print('Switcher:', error, file=sys.stderr, flush=True); window.cancel()
    lifetime.readyRead.connect(read); lifetime.disconnected.connect(app.quit)
    lifetime.connectToServer(str(runtime/'.socket2.sock'))
    if not lifetime.waitForConnected(2000): return 1
    signal.signal(signal.SIGTERM, lambda *_: app.quit()); signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Give Python's signal handlers a turn even while the resident UI is hidden.
    signal_timer = QTimer(app); signal_timer.timeout.connect(lambda: None); signal_timer.start(500)
    return app.exec()


if __name__ == '__main__': raise SystemExit(main())
