"""Exercise recovery with real disposable processes and a private session socket."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest


MODULE = Path(__file__).with_name('waybar-session.py')


class WaybarSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='xetal-bar-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(self.root/'.socket2.sock'))
        self.server.listen()
        self.server.settimeout(3)
        self.addCleanup(self.server.close)
        self.connections = []
        self.processes = []
        self.addCleanup(self.cleanup_processes)
        self.child_script = self.root/'bar.py'
        self.child_script.write_text('''import json,os,signal,time
from pathlib import Path
root=Path(__file__).parent
with (root/'starts.jsonl').open('a') as f:
 f.write(json.dumps({'pid':os.getpid(),'time':time.monotonic()})+'\\n')
if (root/'stubborn').exists():signal.signal(signal.SIGTERM,signal.SIG_IGN)
if (root/'crash').exists():raise SystemExit(17)
while True:time.sleep(.05)
''')
        self.wrapper = self.root/'supervisor.py'
        self.wrapper.write_text(
            'import runpy,sys\nfrom pathlib import Path\n'
            f"module=runpy.run_path({str(MODULE)!r})\n"
            "root=Path(__file__).parent\n"
            "raise SystemExit(module['supervise'](root,[sys.executable,str(root/'bar.py')],"
            "interval=.02,delays=(.08,.16,.32),stable_after=1))\n")

    def cleanup_processes(self):
        for connection in self.connections:
            connection.close()
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        # A failed assertion must not leave any fixture child running.
        for record in self.starts():
            try:
                pid = record['pid']
                if str(self.child_script).encode() in (Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0'):
                    os.kill(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass

    def starts(self):
        path = self.root/'starts.jsonl'
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.endswith('}')]

    def until(self, predicate, timeout=4):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail('Timed out waiting for fixture state')

    def start(self):
        process = subprocess.Popen([sys.executable, str(self.wrapper)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        connection, _ = self.server.accept()
        self.connections.append(connection)
        return process, connection

    def assert_stopped(self, pid):
        stat = Path('/proc')/str(pid)/'stat'
        self.assertTrue(not stat.exists() or stat.read_text().split(') ')[1][0]=='Z', 'Owned bar survived logout')

    def test_crash_restarts_bar_then_logout_stops_it_with_stale_socket_present(self):
        process, connection = self.start()
        self.until(lambda: len(self.starts())==1)
        first = self.starts()[0]['pid']
        os.kill(first, signal.SIGKILL)
        self.until(lambda: len(self.starts())==2)
        second = self.starts()[1]['pid']
        self.assertNotEqual(first, second)
        connection.close()
        _, error = process.communicate(timeout=4)
        self.assertEqual(process.returncode, 0, error.decode())
        self.assertTrue((self.root/'.socket2.sock').exists())
        self.assert_stopped(second)
        self.assertEqual(len(self.starts()), 2)

    def test_duplicate_supervisor_exits_without_spawning_another_bar(self):
        process, _ = self.start()
        self.until(lambda: len(self.starts())==1)
        duplicate = subprocess.run([sys.executable, str(self.wrapper)], capture_output=True, timeout=3)
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr.decode())
        self.assertEqual(len(self.starts()), 1)
        self.assertIsNone(process.poll())

    def test_repeated_crashes_back_off_and_logout_cancels_pending_restart(self):
        (self.root/'crash').touch()
        process, connection = self.start()
        self.until(lambda: len(self.starts())>=4)
        times = [row['time'] for row in self.starts()[:4]]
        self.assertGreaterEqual(times[1]-times[0], .075)
        self.assertGreaterEqual(times[2]-times[1], .155)
        self.assertGreaterEqual(times[3]-times[2], .315)
        connection.close()
        process.communicate(timeout=4)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(len(self.starts()), 4)

    def test_termination_kills_only_owned_stubborn_bar(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(120)'])
        self.processes.append(unrelated)
        (self.root/'stubborn').touch()
        process, _ = self.start()
        self.until(lambda: len(self.starts())==1)
        pid = self.starts()[0]['pid']
        # The fixture writes its PID just before installing the handler.
        time.sleep(.05)
        process.terminate()
        process.communicate(timeout=4)
        self.assertEqual(process.returncode, 0)
        self.assert_stopped(pid)
        self.assertIsNone(unrelated.poll())

    def test_disconnected_session_does_not_launch_a_bar(self):
        process, connection = self.start()
        connection.close()
        process.communicate(timeout=4)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(self.starts(), [])


if __name__ == '__main__':
    unittest.main()
