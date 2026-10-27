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

from PyQt6.QtCore import Qt, QSize, QRectF, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QLinearGradient
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QListWidget, QListWidgetItem, QListView, QStyledItemDelegate, QStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'control_center'))
from desktop_settings import ctl
sys.path.insert(0,str(ROOT/'theme'))
import runtime as theme_runtime
from window_chrome import close_button

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
    name = client.get('class') or client.get('initialClass') or 'application-x-executable'
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


class Card(QStyledItemDelegate):
    def sizeHint(self, option, index): return QSize(222, 180)
    def paint(self, painter, option, index):
        painter.save(); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(option.rect).adjusted(5, 5, -5, -5)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        gradient = QLinearGradient(box.topLeft(), box.bottomRight())
        gradient.setColorAt(0, color('#2e5b65' if selected else '#202e3e'))
        gradient.setColorAt(1, color('#203f4b' if selected else '#172333'))
        painter.setBrush(gradient); painter.setPen(QPen(color('#84ead7' if selected else '#34465b'), 2 if selected else 1))
        painter.drawRoundedRect(box, 13, 13)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon: icon.paint(painter, int(box.center().x()-27), int(box.top()+17), 54, 54)
        painter.setPen(color('#eff8ff')); painter.setFont(QFont('Noto Sans', 11, QFont.Weight.DemiBold))
        title = index.data(Qt.ItemDataRole.DisplayRole)
        title = painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(box.width()-24)*2)
        painter.drawText(box.adjusted(12, 80, -12, -43), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, title)
        painter.setFont(QFont('Noto Sans', 9)); painter.setPen(color('#a8d9d6' if selected else '#98adc7'))
        painter.drawText(box.adjusted(8, box.height()-36, -8, -8), Qt.AlignmentFlag.AlignCenter,
                         index.data(Qt.ItemDataRole.UserRole+1))
        painter.restore()


class Switcher(QWidget):
    def __init__(self, preview=False):
        super().__init__()
        self.preview = preview; self.original = ''; self.monitor = None
        self.setWindowTitle('Switch applications')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dark_style = ('QWidget { color:#e6eef9; font:13px "Noto Sans"; background:transparent; } '
                           'QListWidget {border:none; outline:0;} QScrollBar:vertical {width:7px; background:#172333;} '
                           'QScrollBar::handle:vertical {background:#4c6b7e; min-height:25px;}')
        theme_runtime.install(QApplication.instance(), self.dark_style)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 22, 24, 18); layout.setSpacing(14)
        top = QHBoxLayout(); title = QLabel('Switch applications'); title.setStyleSheet('font-size:23px; font-weight:700;')
        top.addWidget(title); top.addStretch(); self.count = QLabel(); top.addWidget(self.count)
        self.close_button=close_button(self,self.cancel,'Cancel app switching');top.addWidget(self.close_button);layout.addLayout(top)
        self.list = QListWidget(); self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust); self.list.setMovement(QListView.Movement.Static)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection); self.list.setSpacing(0)
        self.list.setItemDelegate(Card(self.list)); self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.itemClicked.connect(lambda _: self.commit()); self.list.currentRowChanged.connect(self.describe)
        self.list.installEventFilter(self); layout.addWidget(self.list, 1)
        self.detail = QLabel(); self.detail.setStyleSheet('color:#88dfcf;'); layout.addWidget(self.detail)
        layout.addWidget(QLabel('Hold Super · Tab / Shift+Tab to cycle · Release Super to open · Esc to cancel'))
        self.resize(950, 290)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, color('#182a3b')); gradient.setColorAt(1, color('#0e1825'))
        painter.setBrush(gradient); painter.setPen(QPen(color('#5aaea8'), 1.5))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 19, 19)

    def begin(self, direction=1):
        if self.isVisible(): self.cycle(direction); return
        clients = json.loads(ctl('-j', 'clients'))
        self.original = json.loads(ctl('-j', 'activewindow')).get('address', '')
        monitors = json.loads(ctl('-j', 'monitors'))
        self.monitor = next((m for m in monitors if m.get('focused')), monitors[0] if monitors else None)
        names = {m['id']: (i+1, m['name']) for i, m in enumerate(monitors)}
        self.populate(windows(clients, self.original), names)
        if not self.list.count(): return
        self.list.setCurrentRow((direction if self.list.count() > 1 else 0) % self.list.count())
        self.show(); self.raise_(); self.activateWindow(); self.list.setFocus()
        QTimer.singleShot(30, self.position)

    def populate(self, clients, monitors):
        self.list.clear()
        for client in clients:
            workspace = client.get('workspace', {}).get('name', '?').removeprefix('special:')
            number, connector = monitors.get(client.get('monitor'), ('?', '?'))
            item = QListWidgetItem(window_icon(client), client.get('title') or client.get('class', 'Window'))
            item.setData(Qt.ItemDataRole.UserRole, client['address'])
            item.setData(Qt.ItemDataRole.UserRole+1, f'{"Workspace " if workspace.isdigit() else ""}{workspace} · Monitor {number}')
            item.setToolTip(f"{client.get('class', '')}\n{client.get('title', '')}\nWorkspace {workspace} · {connector}")
            self.list.addItem(item)
        self.count.setText(f'{len(clients)} windows · all workspaces')
        self.resize(950, 530 if len(clients)>4 else 350)

    def position(self):
        if not self.isVisible() or self.preview or not self.monitor: return
        try:
            own = next(c for c in json.loads(ctl('-j', 'clients')) if c.get('pid') == os.getpid())
            m = self.monitor
            width, height = m['width']/m['scale'], m['height']/m['scale']
            if m.get('transform', 0) % 2: width, height = height, width
            x, y = round(m['x']+(width-self.width())/2), round(m['y']+(height-self.height())/2)
            ctl('dispatch', 'movewindowpixel', f'exact {x} {y},address:'+own['address'])
            ctl('dispatch', 'focuswindow', 'address:'+own['address'])
        except (ValueError, StopIteration): pass

    def cycle(self, direction):
        if self.list.count():
            self.list.setCurrentRow((self.list.currentRow()+direction) % self.list.count())
            self.list.scrollToItem(self.list.currentItem())

    def describe(self, row):
        item = self.list.item(row)
        self.detail.setText(item.text() if item else '')

    def commit(self):
        if not self.isVisible(): return
        item = self.list.currentItem(); address = item.data(Qt.ItemDataRole.UserRole) if item else self.original
        self.hide()
        if address and not self.preview:
            if not focus(address) and self.original: focus(self.original)

    def cancel(self):
        self.hide()
        if self.original and not self.preview: focus(self.original)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape: self.cancel(); return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self.commit(); return True
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self.cycle(-1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1); return True
        return super().eventFilter(obj, event)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--preview'); args = parser.parse_args()
    app = QApplication(sys.argv[:1]); app.setApplicationName('xetal-switcher'); app.setDesktopFileName('xetal-switcher')
    app.setQuitOnLastWindowClosed(False); app.setStyle('Fusion')
    QIcon.setThemeSearchPaths([str(Path.home()/'.local/share/icons'),'/usr/share/icons'])
    QIcon.setFallbackThemeName('hicolor'); QIcon.setThemeName('Papirus-Dark')
    window = Switcher(bool(args.preview))
    if args.preview:
        window.populate([{'address':f'0x{i+1:x}', 'title':title, 'class':kind, 'workspace':{'name':ws}, 'monitor':mon}
                         for i,(title,kind,ws,mon) in enumerate([('Your project — Linux Studio','code','2',1),
                            ('Chrome — reference tabs','google-chrome','magic',1), ('Discord — general','discord','magic',1),
                            ('Pictures — Dolphin','org.kde.dolphin','3',2), ('Terminal','kitty','4',0)])],
                        {0:(1,'DP-4'),1:(2,'DP-5'),2:(3,'DP-6')})
        window.list.setCurrentRow(1); window.show()
        QTimer.singleShot(150, lambda: (window.grab().save(args.preview), app.quit()))
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
                    address = '0x'+command.split('>>',1)[1].removeprefix('0x')
                    for index in range(window.list.count()-1,-1,-1):
                        if window.list.item(index).data(Qt.ItemDataRole.UserRole)==address: window.list.takeItem(index)
                    if not window.list.count(): window.cancel()
            except Exception as error: print('Switcher:', error, file=sys.stderr, flush=True); window.hide()
    lifetime.readyRead.connect(read); lifetime.disconnected.connect(app.quit)
    lifetime.connectToServer(str(runtime/'.socket2.sock'))
    if not lifetime.waitForConnected(2000): return 1
    return app.exec()


if __name__ == '__main__': raise SystemExit(main())
