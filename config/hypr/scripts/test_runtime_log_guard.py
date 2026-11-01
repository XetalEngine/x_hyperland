"""Real log descriptors and disposable compositor sockets; no desktop cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('runtime-log-guard.py')
spec = importlib.util.spec_from_file_location('log_guard', SOURCE)
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)


class LogGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fusion-log-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.instance = self.root/'hypr/session'; self.instance.mkdir(parents=True)
        self.profile = self.root/'profile'; (self.profile/'scripts').mkdir(parents=True)
        shutil.copy2(SOURCE, self.profile/'scripts/runtime-log-guard.py')
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(self.instance/'.socket2.sock')); self.server.listen(); self.server.settimeout(3)
        self.addCleanup(self.server.close)
        self.processes, self.connections = [], []
        self.addCleanup(self.close_processes)
        self.env = {**os.environ, 'XDG_RUNTIME_DIR': str(self.root), 'HYPRLAND_INSTANCE_SIGNATURE': 'session'}

    def close_processes(self):
        for connection in self.connections: connection.close()
        for process in self.processes:
            if process.poll() is None: process.terminate()
            try: process.communicate(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.communicate()

    def launch(self):
        script = ('import runpy\nfrom pathlib import Path\n'
                  f'm=runpy.run_path({str(SOURCE)!r})\n'
                  f'm["serve"](Path({str(self.instance)!r}),Path({str(self.profile)!r}),interval=.03,limit=1024)\n')
        process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        connection, _ = self.server.accept(); self.connections.append(connection)
        return process, connection

    def until(self, predicate):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(.01)
        self.fail('Timed out waiting for the fixture guard')

    def test_in_place_cleanup_preserves_active_writer_and_leaves_other_files_alone(self):
        path = self.instance/'hyprland.log'
        other = self.instance/'someone-elses.log'; other.write_bytes(b'x'*8192)
        small = self.instance/'cached-apps.log'; small.write_bytes(b'x'*1024)
        with path.open('ab') as writer:
            writer.write(b'x'*8192); writer.flush(); original = path.stat().st_ino
            with guard.session(self.instance) as (directory, _):
                result = guard.check(directory, self.profile, limit=4096)
            self.assertEqual(result['cleared'], ['hyprland.log'])
            self.assertEqual(path.stat().st_size, 0); self.assertEqual(path.stat().st_ino, original)
            writer.write(b'logging continues\n'); writer.flush()
            self.assertEqual(path.read_bytes(), b'logging continues\n')
        self.assertEqual(other.stat().st_size, 8192); self.assertEqual(small.stat().st_size, 1024)

    def test_symlink_hardlink_and_fifo_are_never_truncated(self):
        target = self.root/'keep'; target.write_bytes(b'x'*4096)
        (self.instance/'hyprland.log').symlink_to(target)
        os.link(target, self.instance/'cached-panel.log')
        os.mkfifo(self.instance/'cached-apps.log')
        with guard.session(self.instance) as (directory, _): result = guard.check(directory, self.profile, limit=1024)
        self.assertEqual(target.stat().st_size, 4096)
        self.assertFalse(result['cleared']); self.assertEqual(len(result['errors']), 3)

    def test_daemon_trims_new_growth_and_exits_on_logout_even_with_stale_socket(self):
        process, connection = self.launch()
        log = self.instance/'hyprland.log'; log.write_bytes(b'x'*4096)
        self.until(lambda: log.stat().st_size == 0)
        log.write_bytes(b'x'*8192); self.until(lambda: log.stat().st_size == 0)
        connection.close(); _, error = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 0, error.decode())
        self.assertTrue((self.instance/'.socket2.sock').exists())
        log.write_bytes(b'x'*8192); time.sleep(.05); self.assertEqual(log.stat().st_size, 8192)

    def test_disable_persists_and_resume_is_observed_without_a_service(self):
        guard.write_json(guard.setting_path(self.profile), {'version': 1, 'enabled': False})
        log = self.instance/'hyprland.log'; log.write_bytes(b'x'*4096)
        process, _ = self.launch(); time.sleep(.1)
        self.assertEqual(log.stat().st_size, 4096); self.assertIsNone(process.poll())
        guard.write_json(guard.setting_path(self.profile), {'version': 1, 'enabled': True})
        self.until(lambda: log.stat().st_size == 0)

    def test_duplicate_daemon_exits_without_replacing_owner(self):
        first, _ = self.launch()
        with guard.session(self.instance) as (directory, _): self.until(lambda: guard.running(directory))
        duplicate, _ = self.launch(); _, error = duplicate.communicate(timeout=3)
        self.assertEqual(duplicate.returncode, 0, error.decode()); self.assertIsNone(first.poll())

    def test_invalid_session_and_symlinked_directory_are_rejected(self):
        for signature in ('', '../session', 'session/../../elsewhere'):
            with self.assertRaises(RuntimeError): guard.instance_path({**self.env,'HYPRLAND_INSTANCE_SIGNATURE':signature})
        (self.root/'hypr/alias').symlink_to(self.instance)
        with self.assertRaises(RuntimeError): guard.instance_path({**self.env,'HYPRLAND_INSTANCE_SIGNATURE':'alias'})

    def test_history_write_failure_does_not_stop_cleanup(self):
        log = self.instance/'hyprland.log'; log.write_bytes(b'x'*4096)
        with guard.session(self.instance) as (directory, _), patch.object(guard,'write_json',side_effect=OSError('full')):
            result = guard.check(directory, self.profile, limit=1024)
        self.assertEqual(log.stat().st_size,0); self.assertTrue(result['errors'])

    def test_status_is_read_only_and_default_is_enabled(self):
        log = self.instance/'hyprland.log'; log.write_bytes(b'x'*4096)
        with patch.dict(os.environ,self.env): result = guard.status(self.profile)
        self.assertTrue(result['enabled']); self.assertTrue(result['active']); self.assertFalse(result['running'])
        self.assertEqual(log.stat().st_size,4096); self.assertFalse(guard.setting_path(self.profile).exists())


if __name__ == '__main__': unittest.main()
