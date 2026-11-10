"""Keep a drawer's top edge anchored when Hyprland resizes a Wayland window.

Wayland does not expose a toplevel's global position to Qt. Resolve this exact
window once, then address only it. IPC is asynchronous and animation updates
are coalesced; file transfers never depend on compositor replies.
"""
import json
import os
from pathlib import Path
import re
import sys
import uuid

from PyQt6.QtCore import QElapsedTimer, QObject, QTimer
from PyQt6.QtNetwork import QLocalSocket


def anchored_geometry(client, monitor, width, height):
    scale = monitor.get('scale', 1) or 1
    w, h = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2: w, h = h, w
    left, top, right, bottom = monitor.get('reserved', [0, 0, 0, 0])
    x, y = monitor['x'] + left, monitor['y'] + top
    w, h = round(w / scale) - left - right, round(h / scale) - top - bottom
    height = min(height, max(1, h-16))
    px, py = client['at']
    return max(x, min(px, x+w-width)), max(y, min(py, y+h-height)), height


class Placement(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.socket_path = str(Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']/'.socket.sock')
        self.binding_title = 'Fusion transfer · ' + uuid.uuid4().hex
        self.address, self.stable_id = None, None
        self.anchor = None
        self.pending_size = None
        self.sending = False
        self.generation = 0
        self.clock = QElapsedTimer()

    def request(self, command, callback):
        connection = QLocalSocket(self)
        timeout = QTimer(connection); timeout.setSingleShot(True)
        data, finished = bytearray(), [False]
        def read(): data.extend(bytes(connection.readAll()))
        def finish(ok):
            if finished[0]: return
            finished[0] = True; timeout.stop(); read(); connection.abort()
            connection.deleteLater(); callback(bytes(data) if ok else None)
        connection.connected.connect(lambda: connection.write(command.encode()))
        connection.readyRead.connect(read)
        connection.disconnected.connect(lambda: finish(True))
        connection.errorOccurred.connect(lambda error: None if error == QLocalSocket.LocalSocketError.PeerClosedError else finish(False))
        timeout.timeout.connect(lambda: finish(False)); timeout.start(400)
        connection.connectToServer(self.socket_path)

    def shown(self):
        if self.clock.isValid(): return
        self.clock.start()
        QTimer.singleShot(60, self.bind)

    def match(self, clients):
        if not self.address and not self.binding_title: return None
        for client in clients:
            if client.get('pid') != os.getpid() or not client.get('mapped') or not client.get('floating'): continue
            address = client.get('address', '')
            if not re.fullmatch(r'0x[0-9a-fA-F]+', address): continue
            if self.address:
                if address != self.address or client.get('stableId') != self.stable_id: continue
            elif self.binding_title not in (client.get('initialTitle'), client.get('title')): continue
            return client
        return None

    def bind(self):
        if self.address or self.window.closed: return
        def received(raw):
            try: client = self.match(json.loads(raw)) if raw else None
            except (ValueError, TypeError): client = None
            if client:
                self.address, self.stable_id = client['address'], client.get('stableId')
                self.binding_title = ''; self.window.refresh()
            elif self.clock.elapsed() < 1200 and not self.window.closed:
                QTimer.singleShot(80, self.bind)
            else:
                self.binding_title = ''; self.window.refresh()
        self.request('j/clients', received)

    def prepare(self, height, callback):
        self.generation += 1
        generation = self.generation
        self.anchor = None; self.pending_size = None
        def finish(target=height):
            if generation == self.generation and not self.window.closed: callback(target)
        def clients_received(raw):
            if generation != self.generation or self.window.closed: return
            try: client = self.match(json.loads(raw)) if raw else None
            except (ValueError, TypeError): client = None
            if not client or client.get('fullscreen') or client.get('fullscreenClient'): finish(); return
            self.address, self.stable_id = client['address'], client.get('stableId')
            self.binding_title = ''
            def monitors_received(raw):
                if generation != self.generation or self.window.closed: return
                try:
                    monitor = next(m for m in json.loads(raw) if m.get('id') == client.get('monitor'))
                    x, y, target = anchored_geometry(client, monitor, self.window.width(), height)
                    self.anchor = (x, y); finish(target)
                except (ValueError, TypeError, KeyError, StopIteration): finish()
            self.request('j/monitors', monitors_received)
        # Let the ordinary initial position restore settle before taking the
        # anchor. Later expansions use the card's current (possibly dragged) position.
        delay = max(0, 900-self.clock.elapsed()) if self.clock.isValid() else 0
        QTimer.singleShot(delay, lambda: self.request('j/clients', clients_received)
                          if generation == self.generation and not self.window.closed else None)

    def resize(self, width, height):
        if not self.anchor or not self.address or self.window.closed: return
        self.pending_size = (width, height)
        if not self.sending: self.flush()

    def flush(self):
        if not self.pending_size or not self.anchor or self.window.closed: return
        w, h = self.pending_size; self.pending_size = None
        x, y = self.anchor
        commands = [f'dispatch resizewindowpixel exact {w} {h},address:{self.address}',
                    f'dispatch movewindowpixel exact {x} {y},address:{self.address}']
        if os.environ.get('XETAL_HYPRLAND_LUA') == '1':
            root = str(Path(__file__).resolve().parents[1])
            if root not in sys.path: sys.path.insert(0, root)
            from compat.hypr_compat import ipc
            commands = [ipc(command).replace('\\', '\\\\').replace(';', '\\;') for command in commands]
        self.sending = True
        def sent(_):
            self.sending = False
            if self.pending_size: self.flush()
        self.request('[[BATCH]]' + ';'.join(commands), sent)

    def release(self):
        self.generation += 1; self.anchor = None; self.pending_size = None
