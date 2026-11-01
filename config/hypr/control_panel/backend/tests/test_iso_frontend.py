"""Run the real curses frontend on a PTY. No block devices are opened."""
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest


REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / 'iso/installer-ui.py'
spec = importlib.util.spec_from_file_location('installer_ui', FRONTEND)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
HOME = ['home', '--uefi', '--dummy', '--', 'wipe', 'Restore', 'verify', 'Check',
        'free', 'Free space', 'parts', 'Partitions']
MENU = ['menu', '--uefi', '--title', 'Select disk to ERASE', '--text', 'Choose a target.',
        '--', '/dev/test-a', '100 GiB Test SSD', '/dev/test-b', '200 GiB Test SSD']


class Terminal:
    def __init__(self, args, size, term, locale, command=None):
        self.master, slave = os.openpty()
        self.resize(*size)
        self.process = subprocess.Popen(
            command or [sys.executable, str(FRONTEND)] + args, stdin=slave,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, TERM=term, LC_ALL=locale, PYTHONCOERCECLOCALE='0'))
        os.close(slave)
        self.output = bytearray()
        self.drain()

    def resize(self, rows, cols):
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        if hasattr(self, 'process'):
            self.process.send_signal(signal.SIGWINCH)

    def drain(self):
        deadline = time.monotonic() + 3
        received = False
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.master], [], [], .05 if received else .1)
            if ready:
                try:
                    block = os.read(self.master, 65536)
                except OSError:
                    break
                if not block:
                    break
                self.output.extend(block)
                received = True
            elif received or self.process.poll() is not None:
                break

    def send(self, keys):
        os.write(self.master, keys)
        self.drain()

    def finish(self):
        stdout, stderr = self.process.communicate(timeout=5)
        return self.process.returncode, stdout.decode(), stderr.decode()

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.communicate()
        os.close(self.master)


@contextmanager
def terminal(args, size=(30, 100), term='xterm-256color', locale='C.UTF-8', command=None):
    session = Terminal(args, size, term, locale, command)
    try:
        yield session
    finally:
        session.close()


class FrontendTests(unittest.TestCase):
    def click(self, tty, x, y):
        tty.send(f'\x1b[<0;{x};{y}M'.encode())
        tty.send(f'\x1b[<0;{x};{y}m'.encode())

    def test_mouse_selects_drive_and_next_returns_only_that_drive(self):
        with terminal(MENU) as tty:
            self.click(tty,10,13)
            self.assertIsNone(tty.process.poll())
            self.click(tty,94,28)
            self.assertEqual(tty.finish(),(0,'/dev/test-b\n',''))

    def test_mouse_confirmation_requires_a_click_on_the_confirm_button(self):
        with terminal(['confirm','--text','Erase the selected sample disk?','--accept','Confirm install']) as tty:
            tty.send(b'\x1b[<0;4;28M')
            tty.send(b'\x1b[<0;90;28m')
            self.assertIsNone(tty.process.poll())
            self.click(tty,90,28)
            self.assertEqual(tty.finish(),(0,'',''))

    def test_account_fields_mask_password_and_return_only_a_hash(self):
        with terminal(['account','--dummy']) as tty:
            tty.send(b'charlie\tPrivate password!\tPrivate password!\t\t\r')
            code,out,err=tty.finish();self.assertEqual((code,err),(0,''))
            plan=json.loads(out)
            self.assertEqual((plan['original'],plan['username']),('fusion','charlie'))
            self.assertTrue(plan['password_hash'].startswith('$6$'))
            self.assertNotIn('Private password!',out)
            self.assertNotIn(b'Private password!',tty.output)

    def test_required_account_and_validation_can_be_navigated_by_mouse(self):
        with terminal(['account','--dummy']) as tty:
            self.click(tty,94,28)
            self.assertIsNone(tty.process.poll())
            tty.send(b'charlie\tx\tx')
            self.click(tty,94,28)
            self.assertEqual(json.loads(tty.finish()[1])['username'],'charlie')
        with terminal(['account','--dummy']) as tty:
            tty.send(b'-invalid\r')
            self.assertIsNone(tty.process.poll())
            self.assertIn(b'lowercase',tty.output)
            tty.send(b'\x1b');self.assertEqual(tty.finish()[0],ui.BACK)

    def test_progress_cannot_be_dismissed_until_backend_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'progress';path.write_text('2\nRestoring your files')
            with terminal(['progress','--progress-file',str(path)]) as tty:
                tty.send(b'\x1b\r');self.assertIsNone(tty.process.poll())
                path.write_text('done\nYour workspace is ready.');time.sleep(.2);tty.drain()
                self.assertIn(b'Welcome home.',tty.output)
                self.click(tty,94,28)
                self.assertEqual(tty.finish(),(0,'',''))

    def test_navigation_returns_only_the_selected_tag(self):
        with terminal(HOME) as tty:
            self.assertIn(b'ACTIONS', tty.output)
            tty.send(b'jj\r')
            self.assertEqual(tty.finish(), (0, 'free\n', ''))
        with terminal(MENU) as tty:
            self.assertIn(b'/dev/test-a', tty.output)
            tty.send(b'j\r')
            self.assertEqual(tty.finish(), (0, '/dev/test-b\n', ''))

    def test_right_arrow_opens_action_and_back_navigation(self):
        with terminal(HOME) as tty:
            tty.send(b'\x1bOC')
            self.assertEqual(tty.finish()[:2], (0, 'wipe\n'))
        for key in (b'\x1bOD', b'\t\r', b'\x1b'):
            with self.subTest(key=key), terminal(MENU) as tty:
                tty.send(key)
                self.assertEqual(tty.finish()[:2], (ui.BACK, ''))

    def test_confirm_defaults_to_back_and_requires_explicit_button_change(self):
        args = ['confirm', '--title', 'FINAL WARNING', '--text', 'Erase /dev/test-a?', '--accept', 'Confirm install']
        with terminal(args) as tty:
            tty.send(b'\r')
            self.assertEqual(tty.finish()[:2], (ui.BACK, ''))
        with terminal(args) as tty:
            tty.send(b'\t')
            tty.send(b'\r')
            self.assertEqual(tty.finish(), (0, '', ''))

    def test_piped_input_cannot_select_or_confirm(self):
        for args in (HOME, ['confirm', '--text', 'Erase?']):
            result = subprocess.run([sys.executable, str(FRONTEND)] + args,
                                    input='yes\n\t\n', capture_output=True, text=True)
            self.assertEqual(result.returncode, ui.UNAVAILABLE)
            self.assertEqual(result.stdout, '')

    def test_linux_monochrome_ascii_and_compact_terminals(self):
        for term, size, loc in [('linux', (25, 80), 'C.UTF-8'),
                                ('vt100', (24, 80), 'C'),
                                ('xterm-256color', (20, 60), 'C.UTF-8')]:
            with self.subTest(term=term, size=size), terminal(HOME, size, term, loc) as tty:
                self.assertIn(b'ACTIONS', tty.output)
                tty.send(b'jjj\r')
                self.assertEqual(tty.finish(), (0, 'parts\n', ''))

    def test_resize_does_not_change_selection(self):
        with terminal(MENU, size=(42, 150)) as tty:
            tty.send(b'j')
            tty.resize(24, 80)
            tty.drain()
            tty.send(b'\r')
            self.assertEqual(tty.finish(), (0, '/dev/test-b\n', ''))

    def test_tiny_terminal_cannot_confirm_hidden_warning(self):
        with terminal(['confirm', '--text', 'Erase?'], size=(10, 30)) as tty:
            tty.send(b'\t\r')
            self.assertIsNone(tty.process.poll())
            tty.send(b'\x1b')
            self.assertEqual(tty.finish()[:2], (ui.BACK, ''))

    def test_long_target_lists_scroll_to_the_last_item(self):
        args = ['menu', '--title', 'Choose target', '--']
        for i in range(40):
            args += [f'/dev/test-{i}', f'Disk number {i}']
        with terminal(args, size=(24, 80)) as tty:
            tty.send(b'j' * 39)
            tty.send(b'\r')
            self.assertEqual(tty.finish()[:2], (0, '/dev/test-39\n'))

    def test_actual_checksum_success_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / 'rootfs-snapshot.tar.zst'
            snapshot.write_bytes(b'small test archive')
            digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            (root / 'snapshot.sha256').write_text(f'{digest}  {snapshot.name}\n')
            for expected in ('passed', 'failed'):
                with terminal(['verify', '--clone-dir', tmp]) as tty:
                    tty.drain()
                    tty.send(b'\r')
                    self.assertEqual(tty.finish(), (0, expected + '\n', ''))
                snapshot.write_bytes(b'corrupt')

    def test_metadata_controls_are_not_executed(self):
        self.assertEqual(ui.clean('SSD\x1b[2J\x00\\Z1 danger\u202e'), 'SSD danger')

    def test_shell_frontend_contract_on_a_real_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'installer-ui.py').write_bytes(FRONTEND.read_bytes())
            (root/'installer_account.py').write_bytes((FRONTEND.parent/'installer_account.py').read_bytes())
            (root/'installer_mouse.py').write_bytes((FRONTEND.parent/'installer_mouse.py').read_bytes())
            installer = root/'installer.sh'
            installer.write_text((REPO/'iso/installer.sh').read_text().replace('/opt/clone', tmp))
            code = '''source "$1"
SNAPSHOT_CHECK=passed
INSTALL_MODE=wipe
installer_menu 'Select disk to ERASE' 'Choose a target' /dev/test-a '100G SSD A' /dev/test-b '200G SSD B'
'''
            with terminal([], command=['bash', '-c', code, 'test', str(installer)]) as tty:
                self.assertIn(b'passed', tty.output)
                tty.send(b'j\r')
                self.assertEqual(tty.finish(), (0, '/dev/test-b\n', ''))


if __name__ == '__main__':
    unittest.main()
