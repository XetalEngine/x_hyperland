"""Native dialog and real background-job interaction checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['DBUS_SESSION_BUS_ADDRESS']='unix:path=/nonexistent/fusion-archive-ui-tests'
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QInputDialog, QTabWidget
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'archive_manager'))
from ui import CompressDialog, JobController, MemberModel
from engine import Index, Runner

APP=QApplication.instance() or QApplication([])


def until(condition,seconds=12):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        APP.processEvents()
        if condition():return True
        QTest.qWait(10)
    return False


class Interface(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fusion-archive-ui-');self.base=Path(self.temp.name)
        self.environment=patch.dict(os.environ,{'XDG_STATE_HOME':str(self.base/'state')});self.environment.start()
        self.source=self.base/'source';self.source.mkdir();(self.source/'file.txt').write_text('Fusion archive UI\n'*40)
    def tearDown(self):self.environment.stop();self.temp.cleanup()

    def test_compact_tabs_and_supported_encryption(self):
        dialog=CompressDialog([str(self.source)],str(self.base));dialog.show();APP.processEvents()
        self.assertLess(dialog.height(),720);self.assertEqual(dialog.findChild(QTabWidget).count(),3)
        dialog.encrypt.setChecked(True);dialog.password.setText('secret');dialog.confirm.setText('secret')
        self.assertEqual(dialog.request()['password'],'secret');self.assertTrue(dialog.names.isEnabled())
        dialog.format.setCurrentText('zip');self.assertFalse(dialog.names.isEnabled());self.assertTrue(dialog.encryption.isEnabled())
        dialog.format.setCurrentText('tar.xz');self.assertFalse(dialog.encrypt.isEnabled());self.assertNotIn('password',dialog.request())
        dialog.close()
        dialog=CompressDialog([str(self.source)],str(self.base),self.base/'chosen.zip')
        self.assertEqual(dialog.request()['options']['format'],'zip')
        self.assertEqual(dialog.request()['output'],str(self.base/'chosen.zip'));dialog.close()

    def test_password_job_and_prompted_extraction(self):
        archive=self.base/'secret.7z'
        controller=JobController(dict(operation='compress',sources=[str(self.source)],output=str(archive),options={'format':'7z','threads':2},password='Correct password'))
        self.assertTrue(until(lambda:controller.job.result is not None));self.assertEqual(controller.job.result,'done',controller.job.data)
        controller.task.wait();controller.window.dismiss()
        dest=self.base/'unpacked'
        with patch.object(QInputDialog,'getText',side_effect=[('Wrong password',True),('Correct password',True)]) as prompt:
            controller=JobController(dict(operation='extract',sources=[str(archive)],destination=str(dest)))
            self.assertTrue(until(lambda:controller.job.result is not None));self.assertEqual(controller.job.result,'done',controller.job.data)
            self.assertEqual(prompt.call_count,2)
            self.assertFalse(controller.job.queue_rows)
        controller.task.wait();controller.window.dismiss();self.assertTrue((dest/'source/file.txt').exists())

    def test_issue_drawer_skip_and_report(self):
        if os.getuid()==0:self.skipTest('Requires unprivileged permissions')
        source=self.source/'denied';source.write_text('private');source.chmod(0)
        controller=JobController(dict(operation='compress',sources=[str(self.source)],output=str(self.base/'partial.7z'),options={'format':'7z','threads':2}))
        try:
            self.assertTrue(until(lambda:bool(controller.job.queue_rows)))
            panel=controller.window.queue_panel;self.assertIsNotNone(panel);self.assertEqual(panel.window(),controller.window)
            self.assertTrue(panel.buttons['skip'].isEnabled());panel.buttons['skip'].click()
            self.assertTrue(until(lambda:controller.job.result is not None));self.assertEqual(controller.job.result,'done',controller.job.data)
            self.assertTrue(controller.job.data.get('warningMessage'));controller.task.wait()
            report=self.base/'report.txt';panel.save_report(str(report));self.assertTrue(until(report.is_file))
            self.assertIn('denied',report.read_text());self.assertIn('Completed',report.read_text())
        finally:
            source.chmod(0o600)
            if controller.task.isRunning():controller.task.command({'command':'cancel'});controller.task.wait(5000)
            controller.window.dismiss()

    def test_member_index_pages_and_filters(self):
        index=Index(self.base/'index.sqlite')
        for number in range(1025):index.add(dict(path=f'Folder/{number:04}.txt',directory=False,size=number,packed=number//2))
        index.build_tree();index.close()
        model=MemberModel();model.open(self.base/'index.sqlite')
        self.assertEqual(model.rowCount(),1)
        folder=model.index(0,0)
        self.assertEqual(model.rowCount(folder),1025);self.assertEqual(model.entry(1000,folder)['size'],1000)
        model.filter('1000');self.assertEqual(model.rowCount(),1)
        folder=model.index(0,0)
        self.assertEqual(model.rowCount(folder),1);self.assertEqual(model.entry(0,folder)['path'],'Folder/1000.txt')
        model.close()

    def test_skip_feedback_arrives_while_the_archive_pass_is_busy_and_paused(self):
        if os.getuid()==0:self.skipTest('Requires unprivileged permissions')
        denied=self.source/'denied';denied.write_text('private');denied.chmod(0)
        hold=threading.Event();waiting=threading.Event();original=Runner.run
        def busy_pass(runner,arguments,**kwargs):
            result=original(runner,arguments,**kwargs)
            if arguments[0]=='a':
                waiting.set()
                if not hold.wait(5):raise AssertionError('Test did not release compression pass')
            return result
        with patch.object(Runner,'run',busy_pass):
            controller=JobController(dict(operation='compress',sources=[str(self.source)],output=str(self.base/'paused.7z'),options={'format':'7z','threads':2}))
            try:
                self.assertTrue(until(lambda:waiting.is_set() and bool(controller.job.queue_rows)))
                controller.job.request('suspend');self.assertTrue(controller.job.data['suspended'])
                panel=controller.window.queue_panel;panel.similar.setChecked(True);panel.buttons['skip'].click()
                self.assertTrue(until(lambda:panel.model.index(0,1).data()=='Skipped',seconds=1))
                self.assertIsNone(controller.job.result);self.assertFalse(hold.is_set())
                self.assertIn('later matching',panel.detail.toPlainText())
                self.assertIn('1 skipped',panel.summary.text())
                self.assertFalse(panel.buttons['skip'].isEnabled())
                self.assertTrue(controller.job.data['suspended'])
                controller.job.request('resume');hold.set()
                self.assertTrue(until(lambda:controller.job.result is not None));self.assertEqual(controller.job.result,'done')
                self.assertEqual(panel.model.index(0,1).data(),'Skipped')
            finally:
                hold.set();denied.chmod(0o600)
                if controller.task.isRunning():controller.task.command({'command':'cancel'});controller.task.wait(5000)
                if controller.window:controller.window.dismiss()


if __name__=='__main__':unittest.main()
