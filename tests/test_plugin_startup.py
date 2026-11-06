"""Startup recovery uses disposable IPC sockets, never the desktop compositor."""
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'config/hypr'))
from effects import session


class StartupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='fusion-startup-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.stopped = threading.Event()

    def state(self, name='minimize'):
        return json.loads((self.root/('plugin-startup-'+name+'.json')).read_text())

    def test_failed_first_login_attempt_recovers_without_changing_settings(self):
        preferences = self.root/'settings.conf'; preferences.write_text('enabled=1\n')
        start = Mock(side_effect=[RuntimeError('Compositor is busy at login'), None])
        self.assertTrue(session.initialize('minimize', start, self.root, self.stopped, delays=(0, 0), probe=lambda:None))
        self.assertEqual(start.call_count, 2)
        self.assertEqual(self.state()['state'], 'ready')
        self.assertEqual(self.state()['attempt'], 2)
        self.assertIn('busy at login', self.state()['previous_error'])
        self.assertEqual(preferences.read_text(), 'enabled=1\n')

    def test_waits_for_renderer_before_loading(self):
        probe = Mock(side_effect=[RuntimeError('No monitor yet'), None]); start = Mock()
        self.assertTrue(session.initialize('minimize', start, self.root, self.stopped, delays=(0, 0), probe=probe))
        start.assert_called_once(); self.assertEqual(probe.call_count, 2)

    def test_persistent_failure_is_bounded_and_has_a_diagnostic(self):
        start = Mock(side_effect=RuntimeError('Missing compositor headers'))
        self.assertFalse(session.initialize('minimize', start, self.root, self.stopped, delays=(0, 0, 0), probe=lambda:None))
        self.assertEqual(start.call_count, 3)
        self.assertEqual(self.state()['state'], 'failed')
        self.assertEqual(self.state()['error'], 'Missing compositor headers')

    def test_logout_prevents_retries_and_waiting_loads(self):
        def start():
            self.stopped.set(); raise RuntimeError('Session ended')
        work = Mock(side_effect=start)
        self.assertFalse(session.initialize('minimize', work, self.root, self.stopped, delays=(0, 0), probe=lambda:None))
        work.assert_called_once()
        with (self.root/'plugin-startup.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.stopped.clear()
            timer = threading.Timer(.03, self.stopped.set); timer.start()
            try:
                never = Mock()
                self.assertFalse(session.initialize('cube', never, self.root, self.stopped, delays=(0,), probe=lambda:None))
                never.assert_not_called()
            finally: timer.join()

    def test_parallel_effects_do_not_build_or_load_at_the_same_time(self):
        entered = threading.Event(); release = threading.Event(); second = Mock()
        def first(): entered.set(); release.wait(3)
        a = threading.Thread(target=lambda:session.initialize('cube', first, self.root, self.stopped, delays=(0,), probe=lambda:None))
        b = threading.Thread(target=lambda:session.initialize('minimize', second, self.root, self.stopped, delays=(0,), probe=lambda:None))
        a.start(); self.assertTrue(entered.wait(3)); b.start()
        try: time.sleep(.05); second.assert_not_called()
        finally: release.set(); a.join(3); b.join(3)
        second.assert_called_once(); self.assertFalse(a.is_alive() or b.is_alive())

    def test_delayed_event_socket_and_logout_own_the_loader_lifetime(self):
        self.exercise_loader()

    def test_empty_login_interpreter_still_loads_minimize_and_dock_icons(self):
        self.exercise_loader('normal')

    def test_icon_helper_failure_leaves_minimize_loaded_and_owned(self):
        self.exercise_loader('failed')

    def test_icon_helper_crash_is_reported_without_stopping_minimize(self):
        self.exercise_loader('crash')

    def exercise_loader(self, helper='none'):
        runtime = self.root/'runtime'; instance = runtime/'hypr'/'fixture'; instance.mkdir(parents=True)
        helper_file = instance/'icons.py'
        helper_file.write_text('import os, time\nfrom pathlib import Path\n'
                              'folder=Path(__file__).parent\n'
                              'assert (folder/"loaded").exists(), "icons ran before native load"\n'
                              '(folder/"icons-started").write_text(str(os.getpid()))\n'+
                              ('raise SystemExit(7)\n' if helper == 'crash' else 'time.sleep(60)\n'))
        program = '''from pathlib import Path
from effects import session
session.sys.executable = ''
session.ready = lambda:None
original = session.initialize
session.initialize = lambda *args:original(*args, delays=(0, .02), probe=lambda:None)
folder = session.instance_path()
def start():
 marker = folder/'attempted'
 if not marker.exists():
  marker.touch(); raise RuntimeError('cold-start fixture')
 (folder/'loaded').touch()
'''
        if helper == 'failed':
            program += 'def fail(): raise PermissionError("icon-helper fixture")\nsession.python_executable=fail\n'
        program += 'session.run("minimize", start, auxiliary='+('None' if helper == 'none' else repr(str(helper_file)))+')\n'
        env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), HYPRLAND_INSTANCE_SIGNATURE='fixture',
                   PYTHONPATH=str(ROOT/'config/hypr'))
        with (self.root/'loader.log').open('w') as output:
            child = subprocess.Popen([sys.executable, '-c', program], env=env, stdout=output, stderr=output)
            try:
                # Reproduce starting the helper before socket2 accepts clients.
                time.sleep(.15)
                with socket.socket(socket.AF_UNIX) as server:
                    server.bind(str(instance/'.socket2.sock')); server.listen(); server.settimeout(4)
                    self.assertIsNone(child.poll(), (self.root/'loader.log').read_text())
                    connection, _ = server.accept()
                    with connection:
                        deadline = time.monotonic()+4
                        while not (instance/'loaded').exists() and time.monotonic() < deadline:
                            self.assertIsNone(child.poll()); time.sleep(.02)
                        self.assertTrue((instance/'loaded').exists(), (self.root/'loader.log').read_text())
                        self.assertIsNone(child.poll())
                        if helper != 'none':
                            expected = 'failed' if helper in ('failed', 'crash') else 'ready'
                            state = {}; deadline = time.monotonic()+4
                            while time.monotonic() < deadline:
                                try: state=json.loads((instance/'plugin-startup-minimize-icons.json').read_text())
                                except FileNotFoundError: pass
                                if state.get('state') == expected and (helper == 'failed' or (instance/'icons-started').exists()): break
                                time.sleep(.02)
                            self.assertEqual(state.get('state'), expected, (self.root/'loader.log').read_text())
                            if helper == 'crash': self.assertIn('status 7', state['error'])
                            self.assertIsNone(child.poll())
                    self.assertEqual(child.wait(timeout=4), 0)
            finally:
                if child.poll() is None: child.terminate(); child.wait(timeout=4)
        self.assertEqual(json.loads((instance/'plugin-startup-minimize.json').read_text())['state'], 'ready')
        if helper == 'normal':
            pid = int((instance/'icons-started').read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)


if __name__ == '__main__': unittest.main()
