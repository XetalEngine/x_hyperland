"""Bounded live streams, kept in memory only while the switcher is visible."""
from collections import OrderedDict
from pathlib import Path
import re
import struct
import time

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

HELPER = Path(__file__).resolve().parents[1]/'share-picker/window-preview'
HEADER = struct.Struct('<4sQIII')
MAX_FRAME = 640*400*4


class PreviewQueue(QObject):
    changed = pyqtSignal(str)

    def __init__(self, parent=None, helper=HELPER):
        super().__init__(parent)
        self.helper = helper; self.cache = OrderedDict(); self.wanted = []
        self.active = False; self.fps = 60; self.process = None; self.workers = set()
        self.buffer = bytearray(); self.last_start = 0.
        self.timer = QTimer(self); self.timer.setInterval(500); self.timer.timeout.connect(self.tick)

    def start(self, fps=60):
        self.fps = max(1, min(144, int(fps)))
        self.active = self.helper.is_file()
        if self.active: self.timer.start(); self.tick()

    def request(self, addresses):
        wanted = list(dict.fromkeys(f'0x{int(a, 16):x}' for a in addresses if re.fullmatch(r'0x[0-9a-fA-F]+', a) and 0 < int(a, 16) < 2**64))[:24]
        keep = set(wanted)
        for address in list(self.cache):
            if address not in keep: del self.cache[address]
        changed = self.wanted != wanted; self.wanted = wanted
        if changed: self.configure()

    def configure(self):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.write((str(self.fps)+' '+' '.join(self.wanted)+'\n').encode('ascii'))

    def tick(self):
        if not self.active or self.process or time.monotonic()-self.last_start < 2.: return
        self.last_start = time.monotonic()
        process = QProcess(self); self.process = process; self.workers.add(process)
        self.buffer.clear()
        process.started.connect(self.configure)
        process.readyReadStandardOutput.connect(lambda: self.read(process))
        process.finished.connect(lambda *_: self.finished(process))
        process.errorOccurred.connect(lambda error: self.finished(process)
                                      if error == QProcess.ProcessError.FailedToStart else None)
        process.start(str(self.helper), ['--stream'])

    def read(self, process):
        data = process.readAllStandardOutput()
        if process is not self.process or not self.active: return
        self.buffer.extend(data)
        if len(self.buffer) > 12*1024*1024:
            process.kill(); self.buffer.clear(); return
        latest = {}; consumed = 0
        while len(self.buffer)-consumed >= HEADER.size:
            magic, handle, width, height, length = HEADER.unpack_from(self.buffer, consumed)
            if magic != b'XTPF' or not 0 < width <= 640 or not 0 < height <= 400 or length != width*height*4 or length > MAX_FRAME:
                process.kill(); self.buffer.clear(); return
            end = consumed+HEADER.size+length
            if end > len(self.buffer): break
            address = f'0x{handle:x}'
            if address in self.wanted:
                latest[address] = (width, height, bytes(self.buffer[consumed+HEADER.size:end]))
            consumed = end
        if consumed: del self.buffer[:consumed]
        for address, (width, height, pixels) in latest.items():
            image = QImage(pixels,width,height,width*4,QImage.Format.Format_ARGB32_Premultiplied)
            self.cache[address] = QPixmap.fromImage(image.copy())
            self.cache.move_to_end(address)
            while len(self.cache) > 24: self.cache.popitem(last=False)
            self.changed.emit(address)

    def finished(self, process):
        if process not in self.workers: return
        self.workers.discard(process)
        if process is self.process: self.process = None; self.buffer.clear()
        process.deleteLater()

    def stop(self):
        self.active = False; self.timer.stop(); self.wanted = []; self.last_start = 0.
        self.process = None
        for process in tuple(self.workers):
            process.closeWriteChannel(); process.terminate()
        self.cache.clear(); self.buffer.clear()

    def shutdown(self):
        self.stop()
        for process in tuple(self.workers):
            if not process.waitForFinished(300): process.kill(); process.waitForFinished(300)
