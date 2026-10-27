import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QEvent,QProcess
from PyQt6.QtWidgets import QApplication,QMessageBox
import app

QT=QApplication.instance() or QApplication([])


def wait(check):
    until=time.monotonic()+4
    while time.monotonic()<until:
        QT.processEvents()
        if check():return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for the worker')


class PopupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.worker=self.root/'worker.py'
        self.worker.write_text('import json\nprint(json.dumps({"type":"success","text":"Finished"}),flush=True)\n')
        self.window=app.Window(preview=True,state=self.root,worker=self.worker);self.window.show();QT.processEvents()

    def tearDown(self):
        self.window.shutdown();self.window.close();self.window.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.temp.cleanup()

    def test_invalid_input_never_starts_a_job(self):
        self.window.url.setText('not a youtube link');self.window.download()
        self.assertFalse(self.window.busy);self.assertEqual(self.window.process.state(),QProcess.ProcessState.NotRunning)
        self.assertIn('YouTube',self.window.status.text())

    def test_format_and_destination_and_paste(self):
        self.window.choose('mp4');self.assertTrue(self.window.formats['mp4'].isChecked());self.assertFalse(self.window.formats['mp3'].isChecked())
        self.assertEqual(self.window.folder,app.backend.destination('mp4'));self.assertEqual(self.window.download_button.text(),'Download MP4')
        QT.clipboard().setText('https://youtu.be/BaW_jenozKc');self.window.paste_url()
        self.assertEqual(self.window.url.text(),'https://www.youtube.com/watch?v=BaW_jenozKc')

    def test_worker_success_and_no_automatic_download_from_selection(self):
        self.window.present('https://youtu.be/BaW_jenozKc');self.assertFalse(self.window.busy)
        self.window.download();self.assertTrue(self.window.busy)
        wait(lambda:not self.window.busy)
        self.assertEqual(self.window.status.text(),'Finished');self.assertIn('Finished',self.window.log.toPlainText())

    def test_active_download_keeps_current_link_and_queues_next_selection(self):
        self.worker.write_text('import time\ntime.sleep(30)\n')
        self.window.url.setText('https://youtu.be/BaW_jenozKc');self.window.download()
        self.window.present('https://youtu.be/abcdefghijk')
        self.assertIn('BaW_jenozKc',self.window.url.text());self.assertTrue(self.window.pending_url)
        self.window.cancel();wait(lambda:not self.window.busy)
        self.assertIn('abcdefghijk',self.window.url.text());self.assertIn('Cancelled',self.window.status.text())

    def test_cancel_terminates_worker_and_its_child(self):
        child_pid=self.root/'child.pid'
        self.worker.write_text('import sys,subprocess,time\nsys.path.insert(0,'+repr(str(app.backend.ROOT/'media'))+')\nfrom worker import own_process_group\nown_process_group()\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\nopen('+repr(str(child_pid))+',"w").write(str(p.pid))\ntime.sleep(60)\n')
        self.window.start_job('download');wait(child_pid.exists)
        pid=int(child_pid.read_text());self.window.cancel();wait(lambda:not self.window.busy)
        def stopped():
            path=Path('/proc')/str(pid)/'stat'
            return not path.exists() or path.read_text().split()[2]=='Z'
        wait(stopped)

    def test_close_confirmation_keeps_running_job_until_accepted(self):
        self.worker.write_text('import time\ntime.sleep(30)\n');self.window.start_job('download')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):self.window.close()
        self.assertTrue(self.window.isVisible());self.assertTrue(self.window.busy)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):self.window.close()
        wait(lambda:not self.window.isVisible())


if __name__=='__main__':unittest.main()
