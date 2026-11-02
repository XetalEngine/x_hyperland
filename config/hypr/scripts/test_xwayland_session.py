"""Socket recovery uses private fixtures; never touch the desktop's X11 sockets."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('xwayland-session.py')
spec = importlib.util.spec_from_file_location('xwayland_guard', SOURCE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class XWaylandSessionTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory(prefix='fusion-x11-test-')
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.sockets = self.root/'sockets'; self.sockets.mkdir()
        self.instance = self.root/'hypr/session'; self.instance.mkdir(parents=True)
        self.number = 42
        self.public = self.sockets/'X42'
        self.alternate = self.sockets/'X42_'
        self.lock = self.root/'.X42-lock'; self.lock.write_text(f'{os.getpid():010d}\n')
        self.identity = (os.getpid(), os.getuid())
        self.stop = threading.Event()
        self.addCleanup(self.stop.set)

    def listener(self, path, drain=True):
        server = socket.socket(socket.AF_UNIX)
        self.addCleanup(server.close)
        server.bind(str(path)); server.listen(8); server.settimeout(.05)
        if drain:
            def accept():
                while not self.stop.is_set():
                    try:
                        connection, _ = server.accept(); connection.close()
                    except socket.timeout:
                        pass
                    except OSError:
                        return
            thread = threading.Thread(target=accept, daemon=True); thread.start()
        return server

    def recover(self, repair=True):
        return guard.recover(self.number, self.identity, repair=repair,
                             socket_dir=self.sockets, lock_dir=self.root)

    def test_missing_path_is_repaired_and_new_clients_reach_same_listener(self):
        self.listener(self.alternate)
        self.assertEqual(self.recover()[0], 'recovered')
        self.assertEqual(os.readlink(self.public), 'X42_')
        self.assertTrue(guard.same_listener(self.public, self.identity))
        self.assertEqual(self.recover()[0], 'healthy')

    def test_check_diagnoses_recoverable_path_without_writing(self):
        self.listener(self.alternate)
        self.assertEqual(self.recover(repair=False)[0], 'recoverable')
        self.assertFalse(self.public.exists())

    def test_healthy_primary_is_preserved_without_needing_backup(self):
        self.listener(self.public)
        inode = self.public.stat().st_ino
        self.assertEqual(self.recover()[0], 'healthy')
        self.assertEqual(self.public.stat().st_ino, inode)
        self.assertFalse(self.public.is_symlink())

    def test_wrong_display_lock_cannot_authorize_repair(self):
        self.listener(self.alternate)
        self.lock.write_text('9999999999\n')
        self.assertEqual(self.recover()[0], 'unavailable')
        self.assertFalse(self.public.exists())

    def test_backup_from_another_process_cannot_authorize_repair(self):
        self.listener(self.alternate)
        self.identity = (os.getpid()+1, os.getuid())
        self.lock.write_text(str(self.identity[0]))
        self.assertEqual(self.recover()[0], 'unavailable')
        self.assertFalse(self.public.exists())

    def test_stale_backup_cannot_authorize_repair(self):
        server = self.listener(self.alternate, drain=False); server.close()
        self.assertEqual(self.recover()[0], 'unavailable')
        self.assertFalse(self.public.exists())

    def test_existing_files_fifo_and_dangling_symlink_are_never_overwritten(self):
        self.listener(self.alternate)
        for kind in ('file', 'fifo', 'symlink'):
            with self.subTest(kind=kind):
                if kind == 'file': self.public.write_text('keep me')
                elif kind == 'fifo': os.mkfifo(self.public)
                else: self.public.symlink_to('missing')
                inode = self.public.lstat().st_ino
                self.assertEqual(self.recover()[0], 'unavailable')
                self.assertEqual(self.public.lstat().st_ino, inode)
                if kind == 'file': self.assertEqual(self.public.read_text(), 'keep me')
                self.public.unlink()

    def test_symlinked_backup_and_lock_are_not_followed_for_repair(self):
        other = self.sockets/'other'; self.listener(other)
        self.alternate.symlink_to(other)
        self.assertEqual(self.recover()[0], 'unavailable')
        self.alternate.unlink(); self.listener(self.alternate)
        saved = self.root/'saved-lock'; self.lock.rename(saved); self.lock.symlink_to(saved)
        self.assertEqual(self.recover()[0], 'unavailable')
        self.assertFalse(self.public.exists())

    def test_changed_backup_during_inspection_is_rejected(self):
        self.listener(self.alternate)
        replacement = self.sockets/'replacement'; self.listener(replacement)
        probe = guard.same_listener
        def change(path, identity):
            result = probe(path, identity)
            replacement.replace(self.alternate)
            return result
        with patch.object(guard, 'same_listener', side_effect=change):
            self.assertEqual(self.recover()[0], 'unavailable')
        self.assertFalse(self.public.exists())

    def test_concurrent_path_creation_is_never_clobbered(self):
        self.listener(self.alternate)
        def create(*args, **kwargs):
            self.public.write_text('another owner won')
            raise FileExistsError()
        with patch.object(guard.os, 'symlink', side_effect=create):
            self.assertEqual(self.recover()[0], 'unavailable')
        self.assertEqual(self.public.read_text(), 'another owner won')

    def test_world_writable_nonsticky_socket_directory_is_rejected(self):
        self.listener(self.alternate)
        self.sockets.chmod(0o777)
        self.assertEqual(self.recover()[0], 'unavailable')
        self.assertFalse(self.public.exists())

    def test_only_local_display_numbers_are_accepted(self):
        self.assertEqual(guard.display_number(':42.0'), 42)
        for value in ('', 'host:42', '../../X1', ':1;echo bad', '-1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                guard.display_number(value)

    def test_session_recovers_once_and_stops_on_ipc_disconnect(self):
        self.listener(self.alternate)
        compositor = self.listener(self.instance/'.socket2.sock', drain=False)
        compositor.settimeout(3)
        script = (f'import runpy\nfrom pathlib import Path\nm=runpy.run_path({str(SOURCE)!r})\n'
                  f'm["serve"](Path({str(self.instance)!r}),42,interval=.03,'
                  f'socket_dir=Path({str(self.sockets)!r}),lock_dir=Path({str(self.root)!r}))\n')
        child = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def stop_child():
            if child.poll() is None: child.kill()
            child.communicate(timeout=3)
        self.addCleanup(stop_child)
        connection, _ = compositor.accept(); self.addCleanup(connection.close)
        deadline = time.monotonic()+3
        while not self.public.is_symlink() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(self.public.is_symlink())
        connection.close()
        output, error = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, error.decode())
        self.assertEqual(output.count(b'XWayland recovered:'), 1)
        self.assertTrue((self.instance/'.socket2.sock').exists())


if __name__ == '__main__':
    unittest.main()
