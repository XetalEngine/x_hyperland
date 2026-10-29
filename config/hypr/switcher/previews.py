"""Bounded, asynchronous, memory-only window previews while the switcher is open."""
from collections import OrderedDict
from pathlib import Path
import re
import time

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

HELPER = Path(__file__).resolve().parents[1]/'share-picker/window-preview'


class PreviewQueue(QObject):
    changed = pyqtSignal(str)

    def __init__(self, parent=None, helper=HELPER):
        super().__init__(parent)
        self.helper = helper; self.running = {}; self.cache = OrderedDict()
        self.attempts = {}; self.wanted = []; self.active = False
        self.timer = QTimer(self); self.timer.setInterval(120); self.timer.timeout.connect(self.tick)

    def start(self):
        self.active = self.helper.is_file()
        if self.active: self.timer.start()

    def request(self, addresses):
        self.wanted = list(dict.fromkeys(a for a in addresses if re.fullmatch(r'0x[0-9a-fA-F]+', a)))[:24]
        keep = set(self.wanted)
        for address in list(self.cache):
            if address not in keep: del self.cache[address]
        self.attempts = {k: v for k, v in self.attempts.items() if k in keep}

    def tick(self):
        if not self.active: return
        now = time.monotonic()
        # Cold entries first, then refresh the selected window faster than others.
        wanted = sorted(enumerate(self.wanted), key=lambda pair: (pair[1] in self.cache, pair[0]))
        for index, address in wanted:
            if len(self.running) >= 2: break
            if address in self.running or now-self.attempts.get(address, -100) < (.6 if index == 0 else 2.): continue
            self.attempts[address] = now
            process = QProcess(self); self.running[address] = process
            process.finished.connect(lambda code, status, a=address, p=process: self.finished(a, p, code))
            process.errorOccurred.connect(lambda error, a=address, p=process: self.finished(a, p, 1)
                                          if error == QProcess.ProcessError.FailedToStart else None)
            # A process-owned timer cannot outlive the process when the UI closes.
            timeout = QTimer(process); timeout.setSingleShot(True); timeout.timeout.connect(process.kill)
            process.start(str(self.helper), [address]); timeout.start(2200)

    def finished(self, address, process, code):
        if self.running.get(address) is not process: return
        del self.running[address]
        data = process.readAllStandardOutput(); process.deleteLater()
        if not self.active or address not in self.wanted: return
        picture = QPixmap()
        if code == 0 and len(data) < 4*1024*1024 and picture.loadFromData(data):
            self.cache[address] = picture; self.cache.move_to_end(address)
            while len(self.cache) > 24: self.cache.popitem(last=False)
            self.changed.emit(address)

    def stop(self):
        self.active = False; self.timer.stop(); self.wanted = []
        # Do not block a fast Super release on a capture. The event loop reaps
        # these two bounded children asynchronously, even while the UI is hidden.
        for process in tuple(self.running.values()): process.kill()
        self.cache.clear(); self.attempts.clear()

    def shutdown(self):
        self.stop()
        for process in tuple(self.running.values()): process.waitForFinished(300)
