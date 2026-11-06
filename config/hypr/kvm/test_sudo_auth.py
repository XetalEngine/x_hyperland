"""KVM authentication regressions. No real sudo or package operations run."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import kernel_install as kernel

sys.path.insert(0, str(kernel.ROOT/'backend/lib'))
import uiutil
sys.path.pop(0)


class SudoCommandTests(unittest.TestCase):
    def test_graphical_fallback_does_not_trust_a_separate_probe(self):
        command = ['pacman-key', '--verify', '/fixture with spaces/pkg.sig', '/fixture with spaces/pkg']
        with patch.object(uiutil, '_find_askpass', return_value='/fixture/askpass'), \
             patch.object(uiutil, '_passwordless_sudo') as probe:
            argv, env, available = uiutil.sudo_command(command)
        self.assertTrue(available)
        self.assertEqual(argv, ['sudo', '-A', *command])
        self.assertEqual(env['SUDO_ASKPASS'], '/fixture/askpass')
        probe.assert_not_called()

    def test_no_graphical_helper_keeps_noninteractive_sudo_available(self):
        with patch.object(uiutil, '_find_askpass', return_value=None), \
             patch.object(uiutil, '_passwordless_sudo', return_value=True):
            argv, _, available = uiutil.sudo_command(['true'])
        self.assertTrue(available)
        self.assertEqual(argv, ['sudo', '-n', 'true'])

    def test_no_authentication_route_reports_unavailable(self):
        with patch.object(uiutil, '_find_askpass', return_value=None), \
             patch.object(uiutil, '_passwordless_sudo', return_value=False):
            argv, _, available = uiutil.sudo_command(['true'])
        self.assertFalse(available)
        self.assertIsNone(argv)


class KernelAuthenticationTests(unittest.TestCase):
    command = ['pacman-key', '--verify', 'fixture.sig', 'fixture.pkg']

    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Isolate PATH entirely: even a broken test cannot reach real sudo or
        # pacman. The stub only records the expected command; it never runs it.
        self.enterContext(patch.dict(os.environ, {'PATH':str(self.root)}))
        sudo = self.root/'sudo'
        sudo.write_text('''#!/usr/bin/python3
import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parent
args = sys.argv[1:]
with (root/'calls.jsonl').open('a') as stream:
    stream.write(json.dumps(dict(args=args, pid=os.getpid(), sid=os.getsid(0)))+'\\n')
if args == ['-n', 'true']:
    sys.exit(0)  # Cached or command-specific access does not cover verification.
if args == ['-n', 'pacman-key', '--verify', 'fixture.sig', 'fixture.pkg']:
    sys.exit('sudo: a password is required')
if args != ['-A', 'pacman-key', '--verify', 'fixture.sig', 'fixture.pkg']:
    sys.exit('Unexpected fixture command')
if not (root/'authorized').exists():
    reply = subprocess.run([os.environ['SUDO_ASKPASS']], capture_output=True, text=True)
    if reply.returncode or reply.stdout.strip() != 'fixture-response-only':
        sys.exit('sudo: no password was provided')
(root/'verified').touch()
print('Signature verified (fixture only)')
''')
        sudo.chmod(0o700)
        askpass = self.root/'askpass'
        askpass.write_text('''#!/usr/bin/python3
from pathlib import Path
root = Path(__file__).resolve().parent
(root/'prompted').touch()
if (root/'cancel').exists():
    raise SystemExit(1)
print('fixture-response-only')
''')
        askpass.chmod(0o700)
        self.enterContext(patch.object(uiutil, '_find_askpass', return_value=str(askpass)))
        # Installer.run temporarily adds its backend import directory.
        self.enterContext(patch.object(sys, 'path', list(sys.path)))
        self.messages = []
        self.runner = kernel.Installer(kernel.Target.parse('7.2.11-arch1-1'),
                                       state=self.root/'state', log=self.messages.append)

    def calls(self):
        return [json.loads(line) for line in (self.root/'calls.jsonl').read_text().splitlines()]

    def test_detached_verification_can_prompt_after_successful_sudo_probe(self):
        self.assertTrue(uiutil._passwordless_sudo())
        denied = subprocess.run(['sudo', '-n', *self.command], capture_output=True, text=True)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn('a password is required', denied.stderr)
        output = self.runner.run(self.command, admin=True)
        self.assertIn('Signature verified', output)
        self.assertTrue((self.root/'prompted').exists())
        self.assertTrue((self.root/'verified').exists())
        actual = self.calls()[-1]
        self.assertEqual(actual['pid'], actual['sid'])  # Real detached worker.
        self.assertEqual(actual['args'], ['-A', *self.command])
        self.assertNotIn('fixture-response-only', output+'\n'.join(self.messages))

    def test_existing_authorization_does_not_require_another_password(self):
        (self.root/'authorized').touch()
        self.assertIn('Signature verified', self.runner.run(self.command, admin=True))
        self.assertTrue((self.root/'verified').exists())
        self.assertFalse((self.root/'prompted').exists())

    def test_cancelled_authentication_does_not_execute_or_retry_command(self):
        (self.root/'cancel').touch()
        with self.assertRaisesRegex(RuntimeError, 'no password was provided'):
            self.runner.run(self.command, admin=True)
        self.assertTrue((self.root/'prompted').exists())
        self.assertFalse((self.root/'verified').exists())
        self.assertFalse(self.runner.changed)
        self.assertEqual(len(self.calls()), 1)


if __name__ == '__main__':unittest.main()
