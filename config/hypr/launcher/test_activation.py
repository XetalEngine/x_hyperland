"""A bar launch activates its own mapped menu without retaining focus later."""
import os
import json
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QObject,QEvent,QProcess,Qt,pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QWidget

import activation

QT=QApplication.instance() or QApplication([])


class Process(QObject):
    finished=pyqtSignal(int,QProcess.ExitStatus)
    errorOccurred=pyqtSignal(QProcess.ProcessError)
    ProcessState=QProcess.ProcessState
    def __init__(self,parent):
        super().__init__(parent);self.calls=[];self.running=False;self.reply=b'';self.killed=False
    def start(self,*args):self.calls.append(args);self.running=True
    def state(self):return self.ProcessState.Running if self.running else self.ProcessState.NotRunning
    def readAllStandardOutput(self):return self.reply
    def complete(self,reply):
        self.reply=reply;self.running=False;self.finished.emit(0,QProcess.ExitStatus.NormalExit)
    def kill(self):self.killed=True;self.running=False;self.finished.emit(0,QProcess.ExitStatus.CrashExit)


class Window(QWidget):
    protected=False
    def dismissal_protected(self):return self.protected


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.patch=patch.object(activation,'QProcess',Process);self.patch.start()
        self.window=Window();self.window.setWindowTitle('Fusion Settings');self.window.show();QT.processEvents()
        self.job=activation.BarActivation(self.window)
    def tearDown(self):
        self.job.cancel();self.window.close();self.window.deleteLater()
        QT.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.patch.stop()
    def start(self):self.job.start();QT.processEvents()

    def found(self,**changes):
        client=dict(pid=os.getpid(),title='Fusion Settings',address='0xabc',mapped=True)
        client.update(changes);self.job.process.complete(json.dumps([client]).encode())

    def test_bar_focuses_and_raises_exact_own_window_once(self):
        self.start()
        self.assertEqual(self.job.process.calls,[('hyprctl',['-j','clients'])])
        self.found();self.job.process.complete(b'ok\n')
        self.assertEqual(self.job.process.calls[1:],[
            ('hyprctl',['dispatch','focuswindow','address:0xabc']),
            ('hyprctl',['dispatch','alterzorder','top,address:0xabc'])])
        self.job.process.complete(b'ok\n');QTest.qWait(60)
        self.assertTrue(self.job.done);self.assertEqual(len(self.job.process.calls),3)
        self.assertFalse(self.job.process.killed)

    def test_unmapped_first_frame_retries_then_stops_on_success(self):
        self.start();self.job.process.complete(b'[]')
        QTest.qWait(40);self.assertEqual(len(self.job.process.calls),2)
        self.found();self.job.process.complete(b'ok\n')
        self.job.process.complete(b'ok\n');QTest.qWait(40)
        self.assertEqual(len(self.job.process.calls),4);self.assertTrue(self.job.done)

    def test_unavailable_compositor_does_not_keep_retrying(self):
        self.start();self.job.process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        QTest.qWait(40);self.assertTrue(self.job.done);self.assertEqual(len(self.job.process.calls),1)

    def test_outside_click_cancels_pending_handoff_before_retry(self):
        self.start();self.job.process.complete(b'[]')
        self.job.cancel();QTest.qWait(40)
        self.assertEqual(len(self.job.process.calls),1)

    def test_typing_or_clicking_in_the_menu_cancels_inflight_handoff(self):
        self.start();QTest.keyClick(self.window,Qt.Key.Key_Down)
        self.assertTrue(self.job.done);self.assertTrue(self.job.process.killed)

    def test_editor_or_screenshot_prevents_focus_handoff(self):
        self.window.protected=True;self.start()
        self.assertTrue(self.job.done);self.assertFalse(self.job.process.calls)

    def test_closing_before_mapping_cancels_handoff(self):
        self.job.start();self.window.hide();QT.processEvents()
        self.assertTrue(self.job.done);self.assertFalse(self.job.process.calls)

    def test_hung_focus_request_is_bounded(self):
        self.start();QTest.qWait(800)
        self.assertTrue(self.job.done);self.assertTrue(self.job.process.killed)

    def test_other_process_and_another_window_in_this_process_are_not_activated(self):
        self.start()
        clients=[dict(pid=os.getpid()+1,title='Fusion Settings',address='0x111',mapped=True),
                 dict(pid=os.getpid(),title='Window shortcuts',address='0x222',mapped=True),
                 dict(pid=os.getpid(),title='Fusion Settings',address='0x333',mapped=True)]
        self.job.process.complete(json.dumps(clients).encode())
        self.assertEqual(self.job.process.calls[-1],('hyprctl',['dispatch','focuswindow','address:0x333']))

    def test_failed_focus_does_not_raise(self):
        self.start();self.found();self.job.process.complete(b'Cannot focus window\n')
        self.assertTrue(self.job.done);self.assertEqual(len(self.job.process.calls),2)

    def test_malformed_reply_does_not_focus_any_window(self):
        self.start();self.job.process.complete(b'not json')
        self.assertTrue(self.job.done);self.assertEqual(len(self.job.process.calls),1)

    def test_user_input_cancels_between_discovery_and_focus(self):
        self.start();self.found();QTest.keyClick(self.window,Qt.Key.Key_Down)
        self.job.process.complete(b'ok\n')
        self.assertTrue(self.job.done);self.assertEqual(len(self.job.process.calls),2)


if __name__=='__main__':unittest.main()
