"""Exercise a native folder copy through Fusion's themed JobView service.

Invoked by test.py only, inside its disposable config and private session bus.
"""
import os
from pathlib import Path
import sys

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from file_jobs.app import Windows
from file_jobs.service import Service
from file_jobs import preferences


def main():
    if os.environ.get('FUSION_FILES_ISOLATED') != '1':
        raise SystemExit('Run this check through file_manager/test.py.')
    os.environ['FUSION_FILES_PROGRESS_CHECK'] = '1'
    cancel = '--cancel' in sys.argv[2:]
    if cancel:
        os.environ['FUSION_FILES_PROGRESS_CANCEL'] = '1'
    os.environ['QT_LOGGING_RULES'] = 'kf.kio.workers.file.debug=false'
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    service = Service(parent=app)
    service.start()
    windows = Windows(service)
    windows.options = preferences.normalize({'style':'binaryknife',
        'behavior':{'show_delay':0, 'auto_close':False}})
    observations = dict(created=False, paused=False, completed=False,
                        bytes=False, themed=False, files=False, current=False)
    if not cancel:
        observations['resumed'] = False

    def created(job):
        observations['created'] = True
        window = windows.windows[job.path]
        observations['themed'] = window.options['style'] == 'binaryknife'
        pause_scheduled = [False]

        def changed():
            observations['bytes'] |= job.data.get('totalBytes', 0) >= 64*1024*1024
            observations['files'] |= job.data.get('totalFiles', 0) >= 1024
            observations['current'] |= bool(job.data.get('currentFile'))
            if observations['bytes'] and not pause_scheduled[0]:
                pause_scheduled[0] = True
                QTimer.singleShot(150, lambda: job.request('suspend'))
            if job.data.get('suspended') and not observations['paused']:
                observations['paused'] = True
                capture = os.environ.get('FUSION_FILES_CAPTURE')
                if capture:
                    window.grab().save(capture+'-transfer.png')
                QTimer.singleShot(200, lambda: job.request('cancel' if cancel else 'resume'))
            elif not cancel and observations['paused'] and not job.data.get('suspended'):
                observations['resumed'] = True
        job.changed.connect(changed)
        job.finished.connect(lambda: observations.update(completed=job.result == ('canceled' if cancel else 'done')))
        # Wait for the client to receive requestView's reply and subscribe to
        # control signals, as a real click after the popup appears would.
        # The card exists before counting finishes. Exercise cancellation
        # during an actual, measurable copy, not just during discovery.

    service.created.connect(created)
    process = QProcess(app)
    process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
    result = [1]

    def finished(code, status):
        def conclude():
            result[0] = int(code != 0 or not all(observations.values()))
            print('Fusion transfer integration ('+('cancel' if cancel else 'complete')+'):', observations, flush=True)
            app.exit(result[0])
        QTimer.singleShot(150, conclude)
    process.finished.connect(finished)
    process.start(sys.argv[1], ['transferProgress'])
    QTimer.singleShot(45000, lambda: (process.kill(), app.exit(1)))
    app.exec()
    service.stop()
    return result[0]


if __name__ == '__main__':
    raise SystemExit(main())
