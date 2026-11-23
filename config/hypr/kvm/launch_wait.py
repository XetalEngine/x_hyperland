"""Keep the desktop responsive while launch authentication waits externally."""
from PyQt6.QtCore import QEventLoop, QThread
from PyQt6.QtWidgets import QApplication


class _Operation(QThread):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.function()
        except BaseException as error:
            self.error = error


def run(function, window=None):
    """Wait for one operation, keeping Qt pings/painting and timers alive.

    sudo still has the GUI process as its parent, preserving its normal cached
    authentication scope. No password is received or retained by this helper.
    Editing and repeated launches are disabled while the validated setup waits.
    """
    application = QApplication.instance()
    if application is None or QThread.currentThread() != application.thread():
        return function()
    if window is not None and getattr(window, '_launch_waiting', False):
        raise RuntimeError('A launch authorization is already in progress.')
    enabled = window.isEnabled() if window is not None else False
    worker = _Operation(function)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    if window is not None:
        window._launch_waiting = True
        window.setEnabled(False)
    try:
        worker.start()
        loop.exec()
        worker.wait()
        if worker.error is not None:
            raise worker.error
        return worker.result
    finally:
        if window is not None:
            window._launch_waiting = False
            window.setEnabled(enabled)
        worker.deleteLater()
