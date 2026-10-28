"""A bar launch activates its own mapped menu without retaining focus later."""
import os
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
        self.window=Window();self.window.show();QT.processEvents()
        self.job=activation.BarActivation(self.window)
    def tearDown(self):
        self.job.cancel();self.window.close();self.window.deleteLater()
        QT.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.patch.stop()
    def start(self):self.job.start();QT.processEvents()

    def test_bar_requests_compositor_focus_for_only_its_own_process_once(self):
        self.start()
        self.assertEqual(self.job.process.calls,[('hyprctl',['dispatch','focuswindow',f'pid:{os.getpid()}'])])
        self.job.process.complete(b'ok\n');QTest.qWait(60)
        self.assertTrue(self.job.done);self.assertEqual(len(self.job.process.calls),1)
        self.assertFalse(self.job.process.killed)

    def test_unmapped_first_frame_retries_then_stops_on_success(self):
        self.start();self.job.process.complete(b'No such window found\n')
        QTest.qWait(40);self.assertEqual(len(self.job.process.calls),2)
        self.job.process.complete(b'ok\n');QTest.qWait(40)
        self.assertEqual(len(self.job.process.calls),2);self.assertTrue(self.job.done)

    def test_unavailable_compositor_does_not_keep_retrying(self):
        self.start();self.job.process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
        QTest.qWait(40);self.assertTrue(self.job.done);self.assertEqual(len(self.job.process.calls),1)

    def test_outside_click_cancels_pending_handoff_before_retry(self):
        self.start();self.job.process.complete(b'No such window found\n')
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


if __name__=='__main__':unittest.main()
