"""Resolve compositor clicks in Hyprland's global, logical coordinates."""
import json
import math
import os
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalSocket

CLICK_EVENT = b'custom>>xetal-launcher-click'


def outside_menu(payload, pid):
    """Return None when the IPC reply cannot identify this menu reliably."""
    try:
        decoder = json.JSONDecoder()
        text = payload.decode().lstrip()
        cursor, end = decoder.raw_decode(text)
        clients = json.loads(text[end:])
        menu = next(c for c in clients if c.get('pid') == pid
                    and c.get('title') == 'Xetal applications' and c.get('mapped')
                    and not c.get('hidden'))
        x, y = cursor['x'], cursor['y']
        left, top = menu['at']
        width, height = menu['size']
        if not all(math.isfinite(v) for v in (x, y, left, top, width, height)):
            return None
        if width <= 0 or height <= 0:
            return None
        return not (left <= x < left + width and top <= y < top + height)
    except (ValueError, TypeError, KeyError, AttributeError, StopIteration):
        return None


class PointerCheck(QObject):
    finished = pyqtSignal(object)

    def __init__(self, parent, callback):
        super().__init__(parent)
        self.done = False
        self.payload = bytearray()
        self.socket = QLocalSocket(self)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda: self.finish(False))
        self.socket.connected.connect(lambda: self.socket.write(b'[[BATCH]]j/cursorpos;j/clients'))
        self.socket.readyRead.connect(lambda: self.payload.extend(bytes(self.socket.readAll())))
        self.socket.disconnected.connect(self.finish)
        self.socket.errorOccurred.connect(self.error)
        self.finished.connect(callback)

    def start(self):
        runtime = os.environ.get('XDG_RUNTIME_DIR')
        signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
        if not runtime or not signature:
            self.finish(False)
            return
        self.timeout.start(1000)
        self.socket.connectToServer(str(Path(runtime) / 'hypr' / signature / '.socket.sock'))

    def error(self, error):
        if error != QLocalSocket.LocalSocketError.PeerClosedError:
            self.finish(False)

    def finish(self, valid=True):
        if self.done:
            return
        self.done = True
        self.payload.extend(bytes(self.socket.readAll()))
        self.timeout.stop()
        self.socket.abort()
        self.finished.emit(outside_menu(bytes(self.payload), os.getpid()) if valid else None)
        self.deleteLater()


def check_pointer(parent, callback):
    # No process or polling loop: the existing compositor connection supplies
    # click events, and this short-lived socket reads geometry only on a click.
    PointerCheck(parent, callback).start()
