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
        result = subprocess.run([str(self.destination), '--json'], env=dict(os.environ, HOME=str(home)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, "recipient ['--json']\n")
        script.unlink()
        result = subprocess.run([str(self.destination)], env=dict(os.environ, HOME=str(home)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2); self.assertIn('not installed', result.stderr)

    def test_existing_global_command_does_not_request_administrator_again(self):
        import runtime_install
        with patch.object(commands, 'current', return_value=True), \
             patch.object(runtime_install, 'administrator', side_effect=AssertionError('unexpected elevation')):
            commands.install()


if __name__ == '__main__': unittest.main()
