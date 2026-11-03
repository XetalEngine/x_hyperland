"""Real KIO transfers pause for choices inside the same themed JobView window."""
import os
from pathlib import Path
import sys
from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from file_jobs.app import Windows
from file_jobs.service import Service
from file_jobs.questions import ChoiceButton
from file_jobs import preferences


def check_question_ownership(service):
    clients = [QDBusConnection.connectToBus(os.environ['DBUS_SESSION_BUS_ADDRESS'], name)
               for name in ('question-owner', 'question-other')]
    def ask(client, path):
        message = QDBusMessage.createMethodCall(service.bus.baseService(), path, 'org.xetal.FileTransfer1', 'ask')
        message.setArguments([{'kind': 'file', 'destination': '/fixture/only', 'replace_allowed': True}])
        return QDBusPendingCallWatcher(client.asyncCall(message, 2000))
    def wait(predicate):
        for _ in range(200):
            if predicate(): return
            QTest.qWait(5)
        raise AssertionError('Private question protocol did not respond')
    paths = [service.create(client.baseService(), 'Protocol fixture', 3, {}, 'org.kde.JobViewV3').path()
             for client in clients]
    first, second = [service.jobs[path] for path in paths]
    pending = [ask(client, path) for client, path in zip(clients, paths)]
    wait(lambda: first.question is not None and second.question is not None)
    wrong = ask(clients[1], paths[0]); wait(wrong.isFinished)
    assert QDBusPendingReply(wrong).error().name() == 'org.freedesktop.DBus.Error.AccessDenied'
    assert first.question is not None and second.question is not None
    first.answer('skip'); wait(pending[0].isFinished)
    assert not QDBusPendingReply(pending[0]).isError()
    assert not pending[1].isFinished(), 'One transfer answered the other transfer'
    second.disconnected(); wait(pending[1].isFinished)
    assert second.question is None and second.result == 'failed'
    for job in (first, second): service.release(job)
    for name in ('question-owner', 'question-other'): QDBusConnection.disconnectFromBus(name)
    print('Question ownership, concurrent replies and client loss passed', flush=True)


def main():
    if os.environ.get('FUSION_FILES_ISOLATED') != '1':
        raise SystemExit('Run through the isolated file_manager test launcher.')
    os.environ['FUSION_FILES_QUESTIONS_CHECK'] = '1'
    app = QApplication([]); app.setQuitOnLastWindowClosed(False)
    service = Service(parent=app); service.start()
    check_question_ownership(service)
    windows = Windows(service)
    windows.options = preferences.normalize({'style': 'breakpoint', 'behavior': {'show_delay': 3000, 'auto_close': False}})
    observed = []; failures = []; pending = set()

    def created(job):
        window = windows.windows[job.path]
        original_window = id(window)
        def question():
            if not job.question or job.path in pending: return
            pending.add(job.path)
            # Click only after the expansion has finished, like a person does.
            def answer():
                pending.discard(job.path)
                try:
                    assert job.question, 'Question disappeared before an answer'
                    assert window.isVisible(), 'Question must bypass the normal progress delay'
                    assert window.height() > window.base_height
                    assert id(windows.windows[job.path]) == original_window
                    assert window.design == 'breakpoint'
                    assert not window.pause.isEnabled()
                    kind = job.question['kind']; destination = job.question['destination']
                    choice = ('copy' if kind == 'duplicate' else
                              'cancel' if 'questions-cancel' in destination else
                              'skip' if 'questions-skip' in destination else
                              'individual' if 'questions-individual' in destination and kind == 'conflicts' else
                              'skip' if 'questions-individual' in destination and not destination.endswith('/a.txt') else 'replace')
                    observed.append((kind, choice))
                    capture = os.environ.get('FUSION_FILES_CAPTURE')
                    if capture: window.grab().save(capture+'-'+kind+'.png')
                    if choice == 'cancel': QTest.mouseClick(window.close_button, Qt.MouseButton.LeftButton)
                    else:
                        button = next(b for b in window.question_panel.findChildren(ChoiceButton) if b.property('choice') == choice)
                        window.question_scroll.ensureWidgetVisible(button)
                        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                except Exception as error:
                    failures.append(str(error)); job.answer('cancel')
            QTimer.singleShot(260, answer)
        job.question_changed.connect(question)
        question()
    service.created.connect(created)
    process = QProcess(app); process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
    result = [1]
    def finished(code, status):
        expected = {('conflicts', 'replace'), ('conflicts', 'skip'), ('conflicts', 'individual'),
                    ('file', 'replace'), ('file', 'skip'), ('conflicts', 'cancel'), ('duplicate', 'copy')}
        result[0] = int(code != 0 or failures or not expected.issubset(set(observed)))
        print('Expanding transfer questions:', observed, 'failures:', failures, flush=True)
        app.quit()
    process.finished.connect(finished)
    process.start(sys.argv[1], ['transferQuestions'])
    QTimer.singleShot(90000, lambda: (process.kill(), app.quit()))
    app.exec(); service.stop()
    return result[0]


if __name__ == '__main__': raise SystemExit(main())
