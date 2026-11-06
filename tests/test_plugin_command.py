"""System-command installation stays inside a disposable directory."""
import os
from pathlib import Path
import json
import shutil
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

    def test_installer_checks_the_result_after_authentication(self):
        import runtime_install
        original_current = commands.current
        def run_command(*args, **kwargs):
            commands.write(self.destination)
            return subprocess.CompletedProcess(args[0], 0, '', '')
        with patch.object(commands, 'current', side_effect=lambda destination=self.destination: original_current(destination)), \
             patch.object(runtime_install, 'administrator', return_value=['sudo']), \
             patch.object(commands.subprocess, 'run', side_effect=run_command):
            commands.install()
        self.assertTrue(original_current(self.destination))
        self.destination.unlink()
        with patch.object(commands, 'current', side_effect=lambda destination=self.destination: original_current(destination)), \
             patch.object(runtime_install, 'administrator', return_value=['sudo']), \
             patch.object(commands.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
             self.assertRaisesRegex(RuntimeError, 'did not produce the expected executable'):
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


class TerminalCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion terminal ')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.profile = self.home/'.config/hypr'
        for relative in ('scripts/terminal-shell.sh', 'terminal_fetch/bashrc', 'terminal_fetch/commands.sh',
                         'terminal_fetch/commands.fish', 'terminal_fetch/zsh/.zshenv',
                         'terminal_fetch/zsh/.zshrc', 'bin/fusion-check'):
            target = self.profile/relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/'config/hypr'/relative, target)
        # The welcome and health data are fixtures; the real terminal startup and
        # command wrapper still run in an interactive shell, including user rc.
        (self.profile/'terminal_fetch/model.py').write_text('')
        runtime = self.profile/'runtime'; runtime.mkdir()
        (runtime/'plugin_health.py').write_text(
            'import json,os,sys\nprint(json.dumps(dict(args=sys.argv[1:],path=os.environ["PATH"],'
            'rc=os.environ.get("FUSION_TEST_RC"))))\nraise SystemExit(17)\n')
        self.local_bin = self.home/'global-bin'; self.local_bin.mkdir()

    def run_shell(self, shell, command, rc='', command_path='/usr/bin:/bin'):
        executable = shutil.which(shell)
        if not executable: self.skipTest(shell+' is not installed')
        if shell == 'fish':
            startup = self.home/'.config/fish/config.fish'
            startup.parent.mkdir(parents=True, exist_ok=True)
            startup.write_text('set -gx FUSION_TEST_RC loaded\n'+rc)
        else:
            startup = self.home/('.'+shell+'rc')
            startup.write_text('export FUSION_TEST_RC=loaded\n'+rc)
        original = startup.read_bytes()
        env = dict(HOME=str(self.home), SHELL=executable, PATH=command_path, TERM='xterm',
                   XDG_CONFIG_HOME=str(self.home/'.config'), LC_ALL='C.UTF-8')
        result = subprocess.run(['/bin/sh', str(self.profile/'scripts/terminal-shell.sh'), '-c', command],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(startup.read_bytes(), original)
        return result

    def check_shell(self, shell):
        if not shutil.which(shell): self.skipTest(shell+' is not installed')
        # Profile-only update: the user has no global wrapper at all.
        for installed in (False, True):
            with self.subTest(installed_outside_path=installed):
                if installed: commands.write(self.local_bin/'fusion-check')
                result = self.run_shell(shell, 'fusion-check --json "literal # file.zip"')
                self.assertEqual(result.returncode, 17, result.stderr)
                self.assertEqual(json.loads(result.stdout),
                                 dict(args=['--json', 'literal # file.zip'], path='/usr/bin:/bin', rc='loaded'))
        # A global command or user alias still wins; the fallback never replaces it.
        (self.local_bin/'fusion-check').write_text('#!/bin/sh\nprintf "%s\\n" global-command\n')
        result = self.run_shell(shell, 'fusion-check', command_path=str(self.local_bin)+':/usr/bin:/bin')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'global-command')
        result = self.run_shell(shell, 'fusion-check', rc="alias fusion-check='printf \"%s\\n\" user-alias'\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'user-alias')

    def test_bash_terminal_command(self): self.check_shell('bash')
    def test_zsh_terminal_command(self): self.check_shell('zsh')
    def test_fish_terminal_command(self): self.check_shell('fish')


if __name__ == '__main__': unittest.main()
