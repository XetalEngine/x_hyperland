"""System-command installation stays inside a disposable directory."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import commands


class CommandTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.destination = self.root/'usr/local/bin/fusion-check'

    def test_installs_idempotently_and_preserves_unrelated_commands(self):
        commands.write(self.destination); self.assertTrue(commands.current(self.destination))
        inode = self.destination.stat().st_ino
        commands.write(self.destination); self.assertEqual(inode, self.destination.stat().st_ino)
        self.destination.write_text('unrelated tool')
        with self.assertRaisesRegex(RuntimeError, 'another program'): commands.write(self.destination)
        self.assertEqual(self.destination.read_text(), 'unrelated tool')
        self.destination.unlink(); self.destination.symlink_to(self.root/'elsewhere')
        with self.assertRaisesRegex(RuntimeError, 'symlink'): commands.write(self.destination)

    def test_command_uses_calling_users_profile_and_forwards_arguments(self):
        commands.write(self.destination)
        home = self.root/'recipient'; script = home/'.config/hypr/runtime/plugin_health.py'
        script.parent.mkdir(parents=True)
        script.write_text('import sys\nprint("recipient",repr(sys.argv[1:]))\nraise SystemExit(1)\n')
        env = dict(os.environ, HOME=str(home), PATH=str(self.destination.parent)+':/usr/bin:/bin')
        result = subprocess.run(['fusion-check', '--json'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, "recipient ['--json']\n")
        script.unlink()
        result = subprocess.run([str(self.destination)], env=dict(os.environ, HOME=str(home)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2); self.assertIn('not installed', result.stderr)

    def test_existing_global_command_does_not_request_administrator_again(self):
        import runtime_install
        with patch.object(commands, 'current', return_value=True), \
             patch.object(runtime_install, 'administrator', side_effect=AssertionError('unexpected elevation')):
            commands.install()

    def test_environment_repair_is_delivered_without_losing_personal_settings(self):
        sys.path.insert(0, str(ROOT/'config/hypr/updates'))
        import update_engine
        remote = (ROOT/'config/hypr/desktop/environment.conf').read_bytes()
        bad = b'# The profile also supplies fusion-check for updates prepared without root access.\nenv = PATH,/home/recipient/.config/hypr/bin:$PATH\n'
        old = remote+bad
        base = {'sha256':update_engine.sha(old), 'text':old.decode()}
        for local, wanted in ((old, remote), (b'env = MY_PERSONAL_OPTION,yes\n'+old, b'env = MY_PERSONAL_OPTION,yes\n'+remote),
                              (remote, remote)):
            with self.subTest(local=local):
                self.assertEqual(update_engine.merge_file('desktop/environment.conf', base, local, remote), wanted)


if __name__ == '__main__': unittest.main()
