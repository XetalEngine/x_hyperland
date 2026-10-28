"""Image picker using the common right-side preview pane."""
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from file_preview import attach, readable_size


# The image viewer also uses this asynchronous loader; keep its public API.
JOBS = set()


class Signals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)


class InspectJob(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.signals = Signals()

    def run(self):
        try: self.signals.done.emit(self.fn())
        except Exception as error: self.signals.failed.emit(str(error))


def background(fn, done, failed):
    job = InspectJob(fn); JOBS.add(job)
    def success(data): JOBS.discard(job); done(data)
    def failure(message): JOBS.discard(job); failed(message)
    job.signals.done.connect(success); job.signals.failed.connect(failure)
    QThreadPool.globalInstance().start(job)


class ImagePicker(QFileDialog):
    def __init__(self, parent, title, directory, filters, async_run=None):
        super().__init__(parent, title, directory, filters)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setFileMode(QFileDialog.FileMode.ExistingFile)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        attach(self)

    @classmethod
    def choose(cls, parent, title, directory, filters, async_run=None):
        dialog = cls(parent, title, directory, filters, async_run)
        result = dialog.exec(); files = dialog.selectedFiles() if result else []
        dialog.deleteLater()
        return files[0] if files else ''
