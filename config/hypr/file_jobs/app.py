#!/usr/bin/env python3
"""File-job progress service owned by this Hyprland session."""
import os
from pathlib import Path
import signal
import socket
import sys

from PyQt6.QtCore import QSocketNotifier, QTimer
from PyQt6.QtWidgets import QApplication
from service import Service
from window import ProgressWindow

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'theme'))
import runtime as theme_runtime


class Windows:
    def __init__(self, service):
        self.service, self.windows = service, {}
        service.created.connect(self.create)

    def create(self, job):
        window = ProgressWindow(job)
        self.windows[job.path] = window
        window.dismissed.connect(lambda: self.release(job))
        if job.result is not None:
            window.completed()
        else:
            QTimer.singleShot(0 if job.data.get('immediate') else 500,
                lambda: window.show() if job.path in self.windows and job.result is None else None)

    def release(self, job):
        self.windows.pop(job.path, None)
        self.service.release(job)


def main():
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not runtime:
        return 1
    endpoint = Path(runtime)/'hypr'/signature/'.socket2.sock'
    connection = socket.socket(socket.AF_UNIX)
    try:
        connection.connect(str(endpoint))
    except OSError:
        connection.close(); return 1
    app = QApplication([sys.argv[0]])
    app.setApplicationName('Xetal Files'); app.setDesktopFileName('xetal-file-progress')
    app.setQuitOnLastWindowClosed(False)
    theme_runtime.install(app)
    service = Service(parent=app)
    try:
        service.start()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        connection.close(); return 0
    windows = Windows(service)
    app.file_job_windows = windows
    app.aboutToQuit.connect(service.stop)
    connection.setblocking(False)
    notifier = QSocketNotifier(connection.fileno(), QSocketNotifier.Type.Read, app)
    def compositor_event(*_):
        try:
            if connection.recv(65536): return
        except BlockingIOError: return
        except OSError: pass
        notifier.setEnabled(False); app.quit()
    notifier.activated.connect(compositor_event)
    heartbeat = QTimer(app); heartbeat.start(250); heartbeat.timeout.connect(lambda: None)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, lambda *_: app.quit())
    try: return app.exec()
    finally: service.stop(); connection.close()


if __name__ == '__main__': raise SystemExit(main())
