"""Exercise interactive editing and history in real, isolated Bash PTYs."""
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terminal_fetch import preferences

SOURCE = Path(__file__).resolve().parent
ANSI = re.compile(rb'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b\([A-Z]')


class Shell:
    def __init__(self, home, profile):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 140, 0, 0))
        env = dict(os.environ, HOME=str(home), XDG_STATE_HOME=str(home/'state'),
                   XDG_CACHE_HOME=str(home/'cache'), TERM='xterm-256color',
                   LC_ALL='C.UTF-8', SHELL='/bin/bash')
        for key in ('KITTY_INSTALLATION_DIR', 'KITTY_SHELL_INTEGRATION', 'HISTFILE', 'BASH_ENV'):
            env.pop(key, None)
        self.process = subprocess.Popen(['/bin/bash', '--rcfile', str(profile/'bashrc'), '-i'],
            stdin=slave, stdout=slave, stderr=slave, env=env, cwd=home, start_new_session=True)
        os.close(slave)
        self.output = bytearray()
        self.until(b'HF_TEST> ', 8)
        self.read(.25)

    def read(self, seconds=.25):
        end = time.monotonic() + seconds; output = bytearray()
        while time.monotonic() < end:
            if select.select([self.master], [], [], min(.025, max(0, end-time.monotonic())))[0]:
                try: data = os.read(self.master, 65536)
                except OSError: break
                output.extend(data)
                # Reply to terminal capability probes without running a compositor.
                for _ in range(data.count(b'\x1b[6n')): os.write(self.master, b'\x1b[1;1R')
                if b'\x1b[>c' in data or b'\x1b[>0c' in data: os.write(self.master, b'\x1b[>1;4000;0c')
                if b'\x1b[c' in data: os.write(self.master, b'\x1b[?62;22c')
        self.output.extend(output)
        return bytes(output)

    def until(self, text, timeout=5):
        output = bytearray(); end = time.monotonic() + timeout
        while time.monotonic() < end:
            output.extend(self.read(.05))
            if text in ANSI.sub(b'', bytes(output)): return bytes(output)
        raise AssertionError('Interactive shell did not produce ' + repr(text) + ': ' + repr(bytes(output)[-1800:]))

    def send(self, text): os.write(self.master, text.encode() if isinstance(text, str) else text)

    def command(self, text):
        self.send(text + '\r')
        return self.until(b'HF_TEST> ')

    def close(self):
        if self.process.poll() is None:
            self.send(b'\x03'); self.read(.05); self.send('exit\r'); self.read(.2)
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate(); self.process.wait(timeout=2)
        os.close(self.master)


class BashIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion bash test ')
        self.addCleanup(temporary.cleanup); self.home = Path(temporary.name)
        self.profile = self.home/'profile'; self.profile.mkdir()
        for name in ('bashrc', 'bash-enhancements.sh', 'blerc', 'preferences.py', 'commands.sh'):
            shutil.copy2(SOURCE/name, self.profile/name)
        (self.profile/'vendor').symlink_to(SOURCE/'vendor', target_is_directory=True)
        (self.profile/'model.py').write_text('')
        (self.home/'.bashrc').write_text("PS1='HF_TEST> '\nalias fusion-test-alias='echo HF_ALIAS_OK'\n")
        (self.home/'.bash_history').write_text('echo HF_ORIGINAL_HISTORY\n')
        self.settings = dict(preferences.DEFAULTS)

    def shell(self):
        (self.profile/'preferences.json').write_text(json.dumps(self.settings))
        shell = Shell(self.home, self.profile); self.addCleanup(shell.close)
        return shell

    def state(self): return self.home/'state/hyperfusion/terminal'

    def test_live_colors_aliases_exit_status_and_completion_after_sudo(self):
        shell = self.shell()
        before = (self.home/'.bashrc').read_bytes()
        self.assertIn(b'HF_ALIAS_OK', shell.command('fusion-test-alias'))
        shell.command('false')
        self.assertIn(b'STATUS=1', shell.command('printf "STATUS=%s\\n" "$?"'))
        shell.send('sudo printf --help "sample" ${USER}')
        output = shell.read(.3)
        for color in (b'32m', b'36m', b'33m', b'35m'):
            self.assertIn(color, output)
        shell.send(b'\x03'); shell.until(b'HF_TEST> ')
        (self.home/'hf-complete-file').write_text('')
        shell.send('sudo cat hf-complete-\t'); output = shell.read(.8)
        self.assertIn(b'hf-complete-file', ANSI.sub(b'', output))
        shell.send(b'\x03'); shell.until(b'HF_TEST> ')
        self.assertEqual((self.home/'.bashrc').read_bytes(), before)
        self.assertNotIn(b'unrecognized', shell.output)
        self.assertNotIn(b'unknown bleopt', shell.output)

    def test_history_suggestions_prefix_search_and_private_commands(self):
        shell = self.shell()
        shell.command('echo HF_SUGGESTION_UNIQUE')
        shell.send('echo HF_SUGG'); output = shell.read(.45)
        self.assertIn(b'ESTION_UNIQUE', ANSI.sub(b'', output))
        shell.send(b'\x03'); shell.until(b'HF_TEST> ')
        shell.command(' echo HF_DO_NOT_SAVE')
        shell.command('history > saved-history.txt')
        history = (self.home/'saved-history.txt').read_text()
        self.assertIn('HF_SUGGESTION_UNIQUE', history)
        self.assertNotIn('HF_DO_NOT_SAVE', history)
        shell.send('echo HF_SU\x1b[A'); output = shell.read(.35)
        self.assertIn(b'GGESTION_UNIQUE', ANSI.sub(b'', output))
        shell.send(b'\x03'); shell.until(b'HF_TEST> ')

    def test_clear_history_with_two_open_sessions_and_share_new_commands(self):
        first, second = self.shell(), self.shell()
        first.command('echo HF_SHARED_OLD')
        second.command(':')  # receive shared history at the next prompt
        second.command('history > before-clear.txt')
        self.assertIn('HF_SHARED_OLD', (self.home/'before-clear.txt').read_text())
        old_generation = preferences.generation(self.state())
        preferences.clear_history(self.state())
        first.command('echo HF_NEW_AFTER_CLEAR')
        second.command(':')
        second.command('history > after-clear.txt')
        history = (self.home/'after-clear.txt').read_text()
        self.assertNotIn('HF_SHARED_OLD', history)
        self.assertNotIn('HF_ORIGINAL_HISTORY', history)
        self.assertIn('HF_NEW_AFTER_CLEAR', history)
        self.assertFalse((self.state()/old_generation).exists())
        self.assertEqual((self.home/'.bash_history').read_text(), 'echo HF_ORIGINAL_HISTORY\n')

    def test_disabled_history_does_not_create_files_or_keep_commands(self):
        self.settings['history_enabled'] = False
        shell = self.shell(); shell.command('echo HF_FORGET_ME')
        shell.command('history > disabled-history.txt')
        self.assertNotIn('HF_FORGET_ME', (self.home/'disabled-history.txt').read_text())
        self.assertFalse(self.state().exists())

    def test_history_capacity_and_plain_bash_mode(self):
        self.settings.update(history_size=100, enhanced=False)
        shell = self.shell()
        self.assertIn(b'BLE=none', shell.command('printf "BLE=%s\\n" "${BLE_VERSION-none}"'))
        shell.command('for i in {001..120}; do history -s "echo HF_CAPACITY_$i"; done')
        shell.command('history > capacity.txt')
        content = (self.home/'capacity.txt').read_text()
        self.assertNotIn('HF_CAPACITY_001', content)
        self.assertIn('HF_CAPACITY_120', content)
        self.assertLessEqual(len(content.splitlines()), 100)


if __name__ == '__main__': unittest.main()
