"""Real KIO transfers pause for choices inside the same themed JobView window."""
import os
from pathlib import Path
import sys
from PyQt6.QtCore import QObject, QProcess, QTimer, Qt, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

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
    def queue(client, path, values):
        message = QDBusMessage.createMethodCall(service.bus.baseService(), path, 'org.xetal.FileTransfer1', 'updateQueue')
        message.setArguments([values])
        return QDBusPendingCallWatcher(client.asyncCall(message, 2000))
    def wait(predicate):
        for _ in range(200):
            if predicate(): return
            QTest.qWait(5)
        raise AssertionError('Private question protocol did not respond')
    paths = [service.create(client.baseService(), 'Protocol fixture', 3, {}, 'org.kde.JobViewV3').path()
             for client in clients]
    first, second = [service.jobs[path] for path in paths]
    class QueueReceiver(QObject):
        def __init__(self): super().__init__(); self.decisions = []
        @pyqtSlot('QVariantMap')
        def decision(self, values): self.decisions.append(values)
    receivers = [QueueReceiver(), QueueReceiver()]
    for client, path, receiver in zip(clients, paths, receivers):
        assert client.connect(service.bus.baseService(), path, 'org.xetal.FileTransfer1', 'queueDecision', receiver.decision)
    values = {'rows': [{'id': 1, 'version': 3, 'status': 'pending', 'category': 'copy:permission'}],
              'state': {'journal': '/fixture/owned-only.sqlite'}}
    accepted = queue(clients[0], paths[0], values); wait(accepted.isFinished)
    assert not QDBusPendingReply(accepted).isError() and first.queue_rows[1]['version'] == 3
    rejected = queue(clients[1], paths[0], {'state': {'journal': '/wrong'}}); wait(rejected.isFinished)
    assert QDBusPendingReply(rejected).error().name() == 'org.freedesktop.DBus.Error.AccessDenied'
    assert first.queue_state['journal'] == '/fixture/owned-only.sqlite'
    assert first.decide_queue([1], 'authorize')
    wait(lambda: bool(receivers[0].decisions))
    assert receivers[0].decisions[0]['choice'] == 'authorize' and not receivers[1].decisions
    class ReviewReceiver(QObject):
        called = False
        @pyqtSlot()
        def review(self): self.called = True
    receiver = ReviewReceiver()
    assert clients[0].connect(service.bus.baseService(), paths[0], 'org.xetal.FileTransfer1', 'reviewRequested', receiver.review)
    first.update({'pendingIssues': 2})
    assert first.request('review')
    wait(lambda: receiver.called)
    assert first.pending == '' and first.running
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
    print('Question and queue ownership, targeted decisions, concurrent replies and client loss passed', flush=True)


def main():
    if os.environ.get('FUSION_FILES_ISOLATED') != '1':
        raise SystemExit('Run through the isolated file_manager test launcher.')
    os.environ['FUSION_FILES_QUESTIONS_CHECK'] = '1'
    os.environ['FUSION_FILES_EMBEDDED_QUEUE_CHECK'] = '1'
    app = QApplication([]); app.setQuitOnLastWindowClosed(False)
    service = Service(parent=app); service.start()
    check_question_ownership(service)
    windows = Windows(service)
    windows.options = preferences.normalize({'style': 'breakpoint', 'behavior': {'show_delay': 3000, 'auto_close': False}})
    observed = []; failures = []; pending = set(); reports = []

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
        def queue_changed(_rows):
            if not job.queue_rows or job.path in pending or job.result is not None: return
            rows = [r for r in job.queue_rows.values() if r.get('status') == 'pending']
            if not rows: return
            pending.add(job.path)
            def decide():
                pending.discard(job.path)
                if job.result is not None: return
                try:
                    panel = window.queue_panel
                    assert panel is not None and panel.window() is window
                    assert window.isVisible() and window.height() > window.base_height
                    assert window.width() == window.appearance['width']
                    assert panel.model.columnCount() == 3
                    assert id(windows.windows[job.path]) == original_window
                    rows = [r for r in job.queue_rows.values() if r.get('status') == 'pending']
                    if not rows: return
                    destination = rows[0]['destination']
                    mode = ('retry' if 'questions-retry' in destination else
                            'individual' if 'questions-individual' in destination else
                            'cancel' if 'questions-cancel' in destination else
                            'skip' if 'questions-skip' in destination else 'replace')
                    if mode == 'cancel':
                        observed.append(('queue', 'cancel')); panel.cancel.click(); return
                    panel.table.clearSelection()
                    if mode == 'individual':
                        identifier = rows[0]['id']
                        for n in range(panel.proxy.rowCount()):
                            if panel.proxy.index(n, 0).data(Qt.ItemDataRole.UserRole) == identifier: panel.table.selectRow(n); break
                        choice = 'replace' if rows[0]['source'].endswith('/a.txt') else 'skip'
                        panel.similar.setChecked(False)
                    else:
                        panel.table.selectAll(); panel.similar.setChecked(True); choice = mode
                    if choice == 'retry':
                        for row in rows:
                            assert 'questions-retry' in row['source']
                            assert (Path(row['destination']).parent/'ordinary.txt').is_file(), 'Other files stopped for the queue'
                            Path(row['source']).chmod(0o600)
                    observed.append(('queue', choice))
                    if choice == 'replace':
                        QTimer.singleShot(0, lambda: [d.button(QMessageBox.StandardButton.Yes).click()
                            for d in panel.findChildren(QMessageBox)])
                    panel.buttons[choice].click()
                except Exception as error:
                    failures.append(str(error)); job.request('cancel')
            QTimer.singleShot(270, decide)
        job.queue_changed.connect(queue_changed)
        queue_changed([])
        def completed():
            rows = list(job.queue_rows.values())
            if not any('questions-retry' in r.get('source', '') for r in rows): return
            try:
                assert rows[0]['statusText'] == 'Copied successfully'
                assert rows[0]['resultText'] == 'Completed after retry'
                assert job.queue_state.get('done') is True
                assert not window.queue_panel.buttons['retry'].isEnabled()
                assert window.review.isVisible()
                report = Path(os.environ['TMPDIR'])/'completed-transfer-report.txt'
                window.queue_panel.save_report(str(report))
                process = window.queue_panel.report_process
                assert process is not None
                def saved(*_):
                    try:
                        text = report.read_text()
                        assert 'Copied successfully' in text and 'Original issue:' in text
                        assert 'From:' in text and 'To:' in text
                        reports.append(True)
                    except Exception as error: failures.append('Report: '+str(error))
                process.finished.connect(saved)
            except Exception as error: failures.append('Completed queue: '+str(error))
        job.finished.connect(completed)
    service.created.connect(created)
    process = QProcess(app); process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
    result = [1]
    def finished(code, status):
        expected = {('duplicate', 'copy'), ('queue', 'replace'), ('queue', 'skip'), ('queue', 'cancel'), ('queue', 'retry')}
        result[0] = int(code != 0 or failures or not reports or not expected.issubset(set(observed)))
        print('Expanding transfer questions:', observed, 'failures:', failures, flush=True)
        # The fixture's completed progress cards intentionally ignore Close.
        # Exit the test loop directly once the child and assertions finish.
        app.exit(result[0])
    process.finished.connect(finished)
    process.start(sys.argv[1], ['transferQuestions'])
    QTimer.singleShot(90000, lambda: (process.kill(), app.exit(1)))
    app.exec(); service.stop()
    return result[0]


if __name__ == '__main__': raise SystemExit(main())
