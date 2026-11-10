"""Real D-Bus progress / attention queue contract; run on a private bus."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import json
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'archive_manager'))
from file_jobs.service import Service
from ui import JobController
APP=QApplication.instance() or QApplication([])


def until(condition):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        APP.processEvents()
        if condition():return True
        QTest.qWait(10)
    return False


class Remote(unittest.TestCase):
    def test_separate_service_process_handles_nested_decisions(self):
        with tempfile.TemporaryDirectory(prefix='fusion-archive-dbus-child-') as temporary,patch.dict(os.environ,{'XDG_STATE_HOME':temporary+'/state'}):
            base=Path(temporary)
            child=subprocess.Popen([sys.executable,__file__,'--service',temporary],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            controller=None
            denied=base/'denied';denied.write_text('private');denied.chmod(0)
            (base/'readable').write_text('archive this')
            try:
                self.assertTrue(until(lambda:(base/'ready').exists() or child.poll() is not None))
                self.assertIsNone(child.poll())
                controller=JobController(dict(operation='compress',sources=[str(denied),str(base/'readable')],output=str(base/'output.7z'),options={'format':'7z','threads':2}))
                self.assertTrue(until(lambda:(base/'result.json').exists()))
                result=json.loads((base/'result.json').read_text())
                self.assertEqual(result['result'],'done',result)
                self.assertEqual(result['rows'][0]['status'],'skipped')
                self.assertTrue(result['rows'][0]['id']<0)
                self.assertIsNone(controller.window)
                self.assertTrue((base/'output.7z').is_file());controller.task.wait()
                # Exercise the real launcher/controller shutdown, not only the
                # in-process controller. Very short jobs can finish during IPC.
                launched=subprocess.run([sys.executable,str(ROOT/'archive_manager/app.py'),'quick-zip','--directory',str(base),'--',str(base/'readable')],
                    capture_output=True,text=True,timeout=15)
                self.assertEqual(launched.returncode,0,launched.stderr)
                self.assertTrue((base/'readable.zip').is_file())
            finally:
                if controller and controller.task.isRunning():controller.task.command({'command':'cancel'});controller.task.wait(5000)
                denied.chmod(0o600)
                child.terminate();child.communicate(timeout=5)

    def test_native_service_receives_completion_and_queue_decisions(self):
        service=Service();service.start()
        with tempfile.TemporaryDirectory(prefix='fusion-archive-dbus-') as temporary,patch.dict(os.environ,{'XDG_STATE_HOME':temporary+'/state'}):
            base=Path(temporary);source=base/'source';source.mkdir();(source/'readable').write_text('archived')
            denied=source/'denied';denied.write_text('permission test');denied.chmod(0)
            controller=JobController(dict(operation='compress',sources=[str(source)],output=str(base/'output.7z'),options={'format':'7z','threads':2}))
            try:
                self.assertTrue(until(lambda:bool(service.jobs) and bool(next(iter(service.jobs.values())).queue_rows)))
                remote=next(iter(service.jobs.values()))
                self.assertIsNone(controller.window)
                self.assertEqual(remote.data['operation'],'compress')
                row=next(iter(remote.queue_rows.values()))
                self.assertTrue(remote.decide_queue([row['id']],'skip',False,{str(row['id']):row['version']}))
                self.assertTrue(until(lambda:remote.result is not None))
                self.assertEqual(remote.result,'done',remote.data)
                self.assertEqual(remote.queue_rows[row['id']]['status'],'skipped')
                self.assertTrue(remote.data.get('warningMessage'))
                self.assertTrue((base/'output.7z').is_file())
                controller.task.wait()
            finally:
                if controller.task.isRunning():controller.task.command({'command':'cancel'});controller.task.wait(5000)
                denied.chmod(0o600);service.stop()


if __name__=='__main__':
    if os.environ.get('FUSION_ARCHIVE_PRIVATE_BUS')!='1':raise SystemExit('Run under dbus-run-session with FUSION_ARCHIVE_PRIVATE_BUS=1.')
    if '--service' in sys.argv:
        base=Path(sys.argv[-1]);service=Service();service.start()
        def check():
            for job in service.jobs.values():
                for row in list(job.queue_rows.values()):
                    if row['status']=='pending':job.decide_queue([row['id']],'skip',False,{str(row['id']):row['version']})
                if job.result is not None and not (base/'result.json').exists():
                    (base/'result.json').write_text(json.dumps(dict(result=job.result,rows=list(job.queue_rows.values()),data=job.data)))
        timer=QTimer();timer.setInterval(10);timer.timeout.connect(check);timer.start()
        (base/'ready').touch();APP.exec()
    else:unittest.main()
