#!/usr/bin/env python3
"""File-job progress service owned by this Hyprland session."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import sys

from PyQt6.QtCore import QFileSystemWatcher, QSocketNotifier, QTimer
from PyQt6.QtWidgets import QApplication
try:
    from .service import Service
    from .window import ProgressWindow
    from . import preferences
except ImportError:
    from service import Service
    from window import ProgressWindow
    import preferences

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'theme'))
import runtime as theme_runtime


class Windows:
    def __init__(self, service):
        self.service, self.windows = service, {}
        self.options = preferences.current()
        self.watcher = QFileSystemWatcher([str(preferences.PATH.parent)], service)
        if preferences.PATH.is_file(): self.watcher.addPath(str(preferences.PATH))
        self.reload_timer = QTimer(service); self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(80); self.reload_timer.timeout.connect(self.reload)
        self.watcher.directoryChanged.connect(lambda *_: self.reload_timer.start())
        self.watcher.fileChanged.connect(lambda *_: self.reload_timer.start())
        service.created.connect(self.create)

    def reload(self):
        if preferences.PATH.is_file() and str(preferences.PATH) not in self.watcher.files():
            self.watcher.addPath(str(preferences.PATH))
        try:
            self.options = preferences.load()[0]
        except (OSError, ValueError) as error:
            print(f'Keeping current File Transfer settings: {error}', file=sys.stderr)
            return
        for window in list(self.windows.values()): window.set_options(self.options)

    def create(self, job):
        window = ProgressWindow(job, options=self.options)
        self.windows[job.path] = window
        window.dismissed.connect(lambda: self.release(job))
        if job.result is not None:
            window.completed()
        else:
            QTimer.singleShot(0 if job.data.get('immediate') else self.options['behavior']['show_delay'],
                lambda: window.show() if job.path in self.windows and job.result is None else None)

    def release(self, job):
        self.windows.pop(job.path, None)
        self.service.release(job)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', help='JSON preferences for a simulated file-operation popup')
    parser.add_argument('--operation', choices=['copy', 'move', 'compress', 'extract'], default='copy')
    parser.add_argument('--state', choices=['running', 'unknown', 'paused', 'completed', 'error', 'conflicts', 'file', 'duplicate'], default='running')
    args = parser.parse_args()
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
    service = None
    if args.preview is not None:
        try:
            from .samples import sample
        except ImportError:
            from samples import sample
        options = preferences.normalize(json.loads(args.preview))
        job = sample(args.operation, args.state)
        job.data['title'] = 'Preview · '+job.title
        window = ProgressWindow(job, options=options, preview=True)
        window.dismissed.connect(app.quit)
        job.requested.connect(lambda action: job.update({'suspended': action == 'suspend'}))
        window.show()
        preview_timer = QTimer(app); preview_timer.setInterval(180)
        def advance():
            if job.running and job.percent is not None and 'totalBytes' in job.data:
                percent = (job.percent+1) % 96
                job.update({'percent': percent, 'processedBytes': int(job.data['totalBytes']*percent/100)})
        preview_timer.timeout.connect(advance); preview_timer.start()
        app.preview_window = window
    else:
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
    finally:
        if service: service.stop()
        connection.close()


if __name__ == '__main__': raise SystemExit(main())
