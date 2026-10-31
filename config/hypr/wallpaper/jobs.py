"""Small Qt worker pool; image decoding and filesystem scans never block paint."""
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class Signals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.signals = Signals(); self.value = None; self.completed = False

    def run(self):
        try:
            self.value = self.fn(); self.completed = True; self.signals.done.emit(self.value)
        except Exception as error: self.signals.failed.emit(str(error))


class Jobs(QObject):
    def __init__(self, parent=None, threads=2):
        super().__init__(parent); self.pool = QThreadPool(self); self.pool.setMaxThreadCount(threads); self.active = set(); self.stopped = False

    def run(self, fn, done, failed, discard=None):
        if self.stopped: return
        job = Job(fn); job.discard = discard; self.active.add(job)
        def success(value):
            if self.stopped: return
            self.active.discard(job); done(value)
        def failure(message):
            if self.stopped: return
            self.active.discard(job); failed(message)
        job.signals.done.connect(success); job.signals.failed.connect(failure); self.pool.start(job)

    def shutdown(self, cancel_queued=False):
        """Keep Python/Qt objects alive until every worker has left its run method."""
        if self.stopped: return
        self.stopped = True
        if cancel_queued: self.pool.clear()
        self.pool.waitForDone()
        for job in self.active:
            job.signals.done.disconnect(); job.signals.failed.disconnect()
            if job.completed and job.discard: job.discard(job.value)
        self.active.clear()
