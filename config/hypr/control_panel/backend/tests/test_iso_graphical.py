"""Graphical navigation and worker lifecycle with sample data, never real disks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1]/'iso'
sys.path.insert(0,str(ROOT))


def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/filename)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


session=module('iso_session','installer-session.py')
try:
    gui=module('iso_graphical','installer-graphical.py')
    from PyQt6.QtTest import QTest
except ImportError:gui=None


@unittest.skipIf(gui is None,'PyQt6 is needed for graphical checks')
class GraphicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=gui.QApplication.instance() or gui.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.window=gui.Wizard(True);self.window.show();self.app.processEvents()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.app.processEvents)

    def click(self,widget):
        from PyQt6.QtCore import QPoint
        if isinstance(widget,gui.QCheckBox):QTest.mouseClick(widget,gui.Qt.MouseButton.LeftButton,pos=QPoint(12,widget.height()//2))
        else:QTest.mouseClick(widget,gui.Qt.MouseButton.LeftButton)
        self.app.processEvents()

    def wait_for(self,condition):
        deadline=time.monotonic()+5
        while not condition() and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.01)
        self.assertTrue(condition())

    def test_preview_drive_requires_selection_then_accepts_simple_password(self):
        w=self.window
        self.assertIn('Install ISO',w.cards[0][1].accessibleName())
        self.click(w.next)
        self.assertEqual(w.current['kind'],'menu');self.assertFalse(w.next.isEnabled())
        self.click(w.cards[1][1]);self.click(w.next)
        self.assertEqual(w.current['kind'],'account')
        QTest.keyClicks(w.username,'Valdemar')
        self.assertEqual(w.username.text(),'valdemar')
        QTest.keyClicks(w.password,'phphph');QTest.keyClicks(w.confirm,'phphph')
        self.click(w.next)
        self.assertEqual(w.current['kind'],'confirm')
        self.assertIn('valdemar',w.current['text']);self.assertNotIn('phphph',w.current['text'])
        self.assertIn('Portable SSD',w.current['text'])
        self.assertIs(w.focusWidget(),w.back)
        self.click(w.next);self.assertEqual(w.next.text(),'Confirm preview')
        self.assertIs(w.focusWidget(),w.back)
        self.click(w.next);self.assertEqual(w.current['kind'],'confirm')
        self.wait_for(w.next.isEnabled)
        self.click(w.next);self.assertTrue(w.busy);self.assertFalse(w.next.isEnabled())
        w.close();self.assertTrue(w.isVisible())
        w.progress_started-=5;w.tick();self.assertFalse(w.busy)
        self.assertEqual(w.next.text(),'Done');self.click(w.next)
        self.assertFalse(w.isVisible())

    def test_fresh_account_is_required_and_password_confirmation_matches(self):
        w=self.window;w.preview_index=2;w.show_preview()
        self.click(w.next);self.assertEqual(w.current['kind'],'account')
        w.username.setText('fusion');w.password.setText('x');w.confirm.setText('x')
        self.click(w.next);self.assertIn('new username',w.error.text())
        w.username.setText('charlie');w.password.clear();w.confirm.clear()
        self.click(w.next);self.assertIn('Enter a password',w.error.text())
        w.password.setText('x');w.confirm.setText('y');self.click(w.next)
        self.assertEqual(w.current['kind'],'account');self.assertIn('do not match',w.error.text())

    def test_failed_progress_keeps_last_completed_stage_and_shows_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress';path.write_text('3\nApplying account preferences')
            w=self.window;w.preview=False
            w.show_page(dict(kind='progress',progress_file=str(path),uefi=True));w.tick()
            self.assertEqual(w.badge.text(),'UEFI');self.assertEqual(w.progress.value(),50)
            path.write_text('failed\nThe account update failed');w.tick()
            self.assertEqual(w.progress.value(),50);self.assertEqual(w.percentage.text(),'Stopped')
            self.assertTrue(w.details_button.isChecked());self.assertTrue(w.next.isEnabled())

    def test_shell_client_receives_only_selected_tag_without_a_terminal(self):
        with tempfile.TemporaryDirectory(prefix='iso-gui-protocol-') as tmp:
            endpoint=Path(tmp)/'ui.sock';w=self.window;w.preview=False
            server=gui.Server(w,endpoint)
            child=subprocess.Popen([sys.executable,str(ROOT/'installer-ui.py'),'menu','--','/dev/sample-a','SSD 1','/dev/sample-b','SSD 2'],
                env=dict(os.environ,XETAL_INSTALLER_SOCKET=str(endpoint)),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                self.wait_for(lambda:w.peer is not None)
                self.assertFalse(w.next.isEnabled());self.click(w.cards[1][1]);self.click(w.next)
                self.wait_for(lambda:child.poll() is not None)
                output,error=child.communicate()
                self.assertEqual((child.returncode,output,error),(0,b'/dev/sample-b\n',b''))
            finally:
                if child.poll() is None:child.kill();child.communicate()
                server.server.close()

    def test_disconnected_confirmation_is_not_approval_or_console_fallback(self):
        with tempfile.TemporaryDirectory(prefix='iso-gui-disconnect-') as tmp:
            endpoint=Path(tmp)/'ui.sock';w=self.window;w.preview=False
            server=gui.Server(w,endpoint)
            child=subprocess.Popen([sys.executable,str(ROOT/'installer-ui.py'),'confirm','--text','Erase sample disk?'],
                env=dict(os.environ,XETAL_INSTALLER_SOCKET=str(endpoint)),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                self.wait_for(lambda:w.peer is not None)
                w.peer.abort();self.wait_for(lambda:child.poll() is not None)
                output,error=child.communicate();self.assertEqual(child.returncode,1);self.assertEqual(output,b'')
                self.assertIn(b'disconnected',error)
            finally:
                if child.poll() is None:child.kill();child.communicate()
                server.server.close()

    def test_small_screen_keeps_navigation_inside_window(self):
        w=self.window;w.resize(800,600);self.app.processEvents()
        for index in range(6):
            w.preview_index=index;w.show_preview();self.app.processEvents()
            for button in (w.back,w.next):
                if button.isVisible():
                    point=button.mapTo(w,button.rect().bottomRight())
                    self.assertLess(point.x(),w.width());self.assertLess(point.y(),w.height())


class SessionTests(unittest.TestCase):
    def test_software_platforms_only_take_over_a_real_console(self):
        self.assertEqual(session.platforms({},'/dev/pts/3',True,True),[])
        self.assertEqual(session.platforms({},'/dev/ttyS0',True,True),[])
        self.assertEqual(session.platforms({},'/dev/tty1',True,True),[('linuxfb',{'QT_QPA_FB_DRM':'1'}),('linuxfb:fb=/dev/fb0',{'QT_QPA_FB_DRM':'0'})])
        self.assertEqual(session.platforms({'DISPLAY':':99'},'/dev/pts/3',True,True),[('xcb',{})])

    def exercise(self,graphics):
        with tempfile.TemporaryDirectory(prefix='iso-session-test-') as tmp:
            root=Path(tmp);calls=root/'calls'
            backend=root/'backend.sh';backend.write_text('printf "worker\\n" >> "$ISO_TEST_CALLS"\nsleep .4\nprintf "finished\\n" >> "$ISO_TEST_CALLS"\n')
            (root/'installer-graphical.py').write_text(graphics)
            with patch.object(session,'ROOT',root),patch.object(session,'BACKEND',backend),patch.dict(os.environ,dict(DISPLAY=':test',ISO_TEST_CALLS=str(calls)),clear=True),patch.object(session.os,'geteuid',return_value=1000):
                status=session.run([])
            self.assertEqual(status,0)
            self.assertEqual(calls.read_text(),'worker\nfinished\n')

    def test_graphics_start_failure_runs_console_backend_once(self):
        self.exercise('raise SystemExit(2)\n')

    def test_graphics_crash_does_not_restart_or_kill_existing_worker(self):
        self.exercise('import sys,time\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index("--ready")+1]).write_text("ready")\ntime.sleep(.2)\nraise SystemExit(3)\n')


if __name__=='__main__':unittest.main()
