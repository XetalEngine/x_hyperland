"""Missing rollback downloads require a real decision before live packages change."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import arch_runtime as arch
import recovery_choice as choice
import runtime_install as runtime
import system_arch_runtime as system

MISSING = [dict(name='appstream', version='1.2.2-1', error='The read operation timed out')]


class ChoiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.object(runtime, 'TRANSACTION', None))
        self.enterContext(patch.object(runtime, 'TRANSACTION_BACKEND', 'arch'))
        self.enterContext(patch.object(runtime, 'TRANSACTION_ROLLBACK_AVAILABLE', True))
        self.enterContext(patch.object(runtime, 'PACKAGE_ROLLBACK_ENABLED', True))
        self.enterContext(patch.object(runtime, 'REQUIRE_RECOVERY', False))
        self.enterContext(patch.dict(os.environ, {'XETAL_SETUP_GUI':'0', 'XETAL_SETUP_CANCEL_FILE':''}))

    def test_noninteractive_and_empty_or_invalid_terminal_answers_cancel(self):
        with patch.object(sys.stdin, 'isatty', return_value=False), patch('builtins.input') as answer:
            self.assertEqual(choice.ask(MISSING), 'cancel')
        answer.assert_not_called()
        for value, expected in (('', 'cancel'), ('yes', 'cancel'), ('r', 'retry'), ('continue', choice.CONTINUE)):
            with self.subTest(value=value), patch.object(sys.stdin, 'isatty', return_value=True), \
                 patch('builtins.input', return_value=value):
                self.assertEqual(choice.ask(MISSING), expected)

    def test_missing_gui_close_or_invalid_response_never_grants_waiver(self):
        with patch.dict(os.environ, {'XETAL_SETUP_GUI':'1'}):
            for code, answer in ((0, 'cancel'), (0, ''), (0, 'yes'), (1, choice.CONTINUE)):
                with self.subTest(code=code, answer=answer), patch.object(choice.subprocess, 'run',
                        return_value=subprocess.CompletedProcess([], code, answer, '')):
                    self.assertEqual(choice.ask(MISSING), 'cancel')
            with patch.object(choice.subprocess, 'run', side_effect=OSError('cannot open dialog')):
                self.assertEqual(choice.ask(MISSING), 'cancel')

    def test_stop_after_step_overrides_a_dialog_continue_response(self):
        cancel = self.root/'cancel'
        def answer(*args, **kwargs):
            cancel.touch()
            return subprocess.CompletedProcess([], 0, choice.CONTINUE, '')
        with patch.dict(os.environ, {'XETAL_SETUP_GUI':'1', 'XETAL_SETUP_CANCEL_FILE':str(cancel)}), \
             patch.object(choice.subprocess, 'run', side_effect=answer):
            self.assertEqual(choice.ask(MISSING), 'cancel')

    def exercise_helper(self, replies, decisions, *, required=False):
        calls = []
        original_popen = subprocess.Popen
        def child(args, **kwargs):
            calls.append(args)
            output, code = replies[len(calls)-1]
            return original_popen([sys.executable, '-c', 'import sys;print('+repr(output)+');sys.exit('+str(code)+')'], **kwargs)
        self.enterContext(patch.object(arch, 'packages'))
        self.enterContext(patch.object(arch, 'pinned', return_value=True))
        self.enterContext(patch.object(runtime, 'administrator', return_value=[]))
        self.enterContext(patch.object(runtime.policy, 'require'))
        self.enterContext(patch.object(runtime.policy, 'arch_versions', return_value=arch.expected()))
        self.enterContext(patch.object(arch.subprocess, 'Popen', side_effect=child))
        self.enterContext(patch.object(runtime, 'REQUIRE_RECOVERY', required))
        ask = self.enterContext(patch.object(choice, 'ask', side_effect=decisions))
        return calls, ask

    def test_continue_transmits_only_reviewed_identities_and_keeps_waiver_state(self):
        record = self.root/'record'
        first = (choice.MARKER+json.dumps(MISSING), choice.EXIT_REQUIRED)
        last = ('XETAL_RUNTIME_TRANSACTION '+str(record)+'\nXETAL_RUNTIME_ROLLBACK_UNAVAILABLE '+str(record), 0)
        calls, ask = self.exercise_helper([first, last], [choice.CONTINUE])
        self.assertTrue(arch.ensure(yes=True, force=True))
        ask.assert_called_once_with(MISSING)
        self.assertNotIn('--without-package-rollback', calls[0])
        self.assertEqual(json.loads(calls[1][-1]), MISSING)
        self.assertEqual(calls[1][-2], '--without-package-rollback')
        self.assertFalse(runtime.rollback_available())

    def test_default_does_not_enable_rollback_downloads_in_root_helper(self):
        record = self.root/'record'
        calls, ask = self.exercise_helper([('XETAL_RUNTIME_TRANSACTION '+str(record)+
                                           '\nXETAL_RUNTIME_ROLLBACK_UNAVAILABLE '+str(record), 0)], [])
        with patch.object(runtime, 'PACKAGE_ROLLBACK_ENABLED', False):
            arch.ensure(yes=True, force=True)
        self.assertNotIn('--package-rollback', calls[0])
        ask.assert_not_called(); self.assertFalse(runtime.rollback_available())

    def test_retry_rechecks_with_complete_rollback_required(self):
        first = (choice.MARKER+json.dumps(MISSING), choice.EXIT_REQUIRED)
        calls, _ = self.exercise_helper([first, ('XETAL_RUNTIME_TRANSACTION '+str(self.root/'record'), 0)], ['retry'])
        arch.ensure(yes=True, force=True)
        self.assertEqual(calls[0], calls[1])
        self.assertIn('--package-rollback', calls[0])
        self.assertTrue(runtime.rollback_available())

    def test_yes_does_not_accept_waiver_and_cancel_does_not_start_second_helper(self):
        calls, ask = self.exercise_helper([(choice.MARKER+json.dumps(MISSING), choice.EXIT_REQUIRED)], ['cancel'])
        with self.assertRaisesRegex(RuntimeError, 'cancelled before the package upgrade'):
            arch.ensure(yes=True, force=True)
        self.assertEqual(len(calls), 1); ask.assert_called_once()
        self.assertIsNone(runtime.TRANSACTION)

    def test_review_copy_never_offers_incomplete_rollback(self):
        calls, ask = self.exercise_helper([(choice.MARKER+json.dumps(MISSING), choice.EXIT_REQUIRED)], [], required=True)
        with self.assertRaisesRegex(RuntimeError, 'review copy requires complete package rollback'):
            arch.ensure(yes=True, force=True)
        ask.assert_not_called(); self.assertEqual(len(calls), 1)

    def test_unrelated_helper_failure_does_not_offer_waiver(self):
        calls, ask = self.exercise_helper([('signature rejected', 1)], [])
        with self.assertRaisesRegex(RuntimeError, 'installation failed'):
            arch.ensure(yes=True, force=True)
        ask.assert_not_called(); self.assertEqual(len(calls), 1)

    def test_waiver_survives_python_upgrade_and_disables_automatic_rollback(self):
        runtime.TRANSACTION = Path('/var/lib/xetal-hyprland/arch-runtime/test-waiver')
        runtime.TRANSACTION_ROLLBACK_AVAILABLE = False
        with patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '99.1\n', '')), \
             patch.object(runtime.os, 'execve') as restart:
            runtime.restart_after_python_upgrade()
        self.assertFalse(json.loads(restart.call_args.args[2]['XETAL_SETUP_PACKAGE_RECOVERY'])['rollback_available'])
        with patch.object(runtime.subprocess, 'run') as execute, redirect_stdout(io.StringIO()) as log:
            runtime.rollback()
        execute.assert_not_called(); self.assertIn('No partial downgrade', log.getvalue())


class PackageChoiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.backup = self.root/'backup'; self.backup.mkdir()

    def test_all_missing_downloads_are_collected_but_other_archives_are_verified(self):
        def previous(directory, name, **kwargs):
            if name != 'saved': raise runtime.RecoveryDownloadError('timeout')
            path = directory/'saved.pkg.tar.zst'; path.write_bytes(b'archive')
            Path(str(path)+'.sig').write_bytes(b'sig')
            return path
        with patch.object(runtime, 'previous_package', side_effect=previous), patch.object(system, 'verify') as verify:
            with self.assertRaises(system.MissingRecoveryPackages) as caught:
                system.save_previous(self.backup, {'appstream':'1.2.2-1', 'saved':'1-1', 'other':'2-1'}, {})
        self.assertEqual([p['name'] for p in caught.exception.packages], ['appstream', 'other'])
        verify.assert_called_once_with(self.backup/'previous/saved.pkg.tar.zst', 'saved 1-1')

    def test_storage_and_signature_errors_cannot_be_waived_as_download_failures(self):
        for number, error in enumerate((OSError('disk full'), subprocess.CalledProcessError(1, ['verify']))):
            backup = self.root/str(number); backup.mkdir()
            with patch.object(runtime, 'previous_package', side_effect=error):
                with self.assertRaises(type(error)):
                    system.save_previous(backup, {'appstream':'1.2.2-1'}, {})

    def test_new_missing_version_requires_another_choice(self):
        with patch.object(runtime, 'previous_package', side_effect=runtime.RecoveryDownloadError('timeout')):
            with self.assertRaises(system.MissingRecoveryPackages) as caught:
                system.save_previous(self.backup, {'appstream':'1.2.3-1'}, {}, waived=MISSING)
        self.assertEqual(caught.exception.packages[0]['version'], '1.2.3-1')

    def test_additional_missing_package_is_reported_with_previous_waiver(self):
        with patch.object(runtime, 'previous_package', side_effect=runtime.RecoveryDownloadError('timeout')):
            with self.assertRaises(system.MissingRecoveryPackages) as caught:
                system.save_previous(self.backup, {'appstream':'1.2.2-1', 'other':'1-1'}, {}, waived=MISSING)
        self.assertEqual([p['name'] for p in caught.exception.packages], ['appstream', 'other'])

    def test_waiver_still_checks_forward_dependencies_and_records_incomplete_recovery(self):
        database = self.root/'db'
        for name in ('local', 'sync'):
            (database/name).mkdir(parents=True)
            (database/name/'sentinel').write_text('unchanged')
        before, after = {'appstream':'1.2.2-1'}, {'appstream':'1.2.3-1'}
        with patch.object(system, 'inventory', side_effect=[before, after, before]), \
             patch.object(runtime, 'previous_package') as download, \
             patch.object(system, 'run') as run, patch.object(system.recovery, 'replay') as replay:
            self.assertEqual(system.prepare_recovery(self.backup, ['pacman'], [], database, '[options]\n', waived=MISSING),
                             (before, after, {}))
        download.assert_not_called(); replay.assert_not_called()
        args = run.call_args.args[0]
        self.assertIn('--dbonly', args); self.assertNotIn('--nodeps', args)
        self.assertEqual((database/'local/sentinel').read_text(), 'unchanged')
        status = json.loads((self.backup/'package-recovery.json').read_text())
        self.assertFalse(status['available']); self.assertEqual(status['choice'], choice.CONTINUE)
        self.assertEqual(status['missing'], MISSING)

    def test_disabled_root_recovery_never_attempts_partial_downgrade_or_replaces_holds(self):
        (self.root/'setup.lock').touch()
        (self.backup/'record.json').write_text(json.dumps({'rollback_available':False}))
        with patch.object(system, 'run') as run, patch.object(system, 'restore_configuration') as restore:
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                system.restore(self.backup, state=self.root)
        run.assert_not_called(); restore.assert_not_called()


class LiveTransactionTests(unittest.TestCase):
    """Run the root transaction orchestration with a disposable package backend."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root/'state'
        self.database = self.root/'db'
        for name in ('local', 'sync'): (self.database/name).mkdir(parents=True)
        self.conf = self.root/'pacman.conf'; self.conf.write_text('[options]\n')
        self.pin = self.root/'pin'; self.pin.write_text('old holds\n')
        self.before = {'appstream':'1.2.2-1'}
        self.after = {**arch.expected(), 'appstream':'1.2.3-1'}
        self.current = dict(self.before)
        self.projected = dict(self.before)
        self.fail_live = False
        self.live_calls = []
        def repository(directory, *args, **kwargs):
            self.assertTrue(kwargs['verify'])
            directory.mkdir(parents=True)
            path = directory/(arch.REPOSITORY+'.db'); path.write_bytes(b'private index')
            return path
        def run(args, **kwargs):
            if '-Su' in args:
                if '--dbonly' in args:
                    self.projected = dict(self.after)
                else:
                    self.live_calls.append(args)
                    self.assertTrue(list(self.state.glob('*/record.json')))
                    self.assertNotIn('--nodeps', args)
                    if self.fail_live:
                        raise subprocess.CalledProcessError(1, args)
                    self.current = dict(self.after)
            return subprocess.CompletedProcess(args, 0, '[options]\n', '')
        self.enterContext(patch.object(system, 'refresh_keyrings'))
        self.enterContext(patch.object(arch, 'repository', side_effect=repository))
        self.enterContext(patch.object(arch, 'resolve', return_value=self.after))
        self.enterContext(patch.object(system, 'run', side_effect=run))
        self.enterContext(patch.object(system, 'inventory', side_effect=lambda db=None:
                         dict(self.current) if db is None or db == self.database else dict(self.projected)))
        self.enterContext(patch.object(runtime, 'pacman_config', side_effect=lambda key:
                         [str(self.database)] if key == 'DBPath' else []))
        self.enterContext(patch.object(runtime, 'previous_package', side_effect=runtime.RecoveryDownloadError('timeout')))
        self.enterContext(patch.object(runtime.policy, 'arch_versions', side_effect=lambda names:
                         {name:self.current[name] for name in names if name in self.current}))
        self.enterContext(patch.object(runtime.policy, 'require'))
        self.replay = self.enterContext(patch.object(system.recovery, 'replay'))
        self.restore = self.enterContext(patch.object(system, 'restore'))

    def test_missing_recovery_stops_live_install_and_preserves_holds(self):
        with self.assertRaises(system.MissingRecoveryPackages):
            system.install(self.state, self.conf, self.pin, rollback=True)
        self.assertEqual(self.live_calls, [])
        self.assertEqual(self.current, self.before)
        self.assertEqual(self.pin.read_text(), 'old holds\n')
        self.assertFalse(list(self.state.glob('*/record.json')))

    def test_explicit_waiver_installs_complete_runtime_and_matching_holds(self):
        system.install(self.state, self.conf, self.pin, waived=MISSING, rollback=True)
        self.assertEqual(len(self.live_calls), 1)
        self.assertEqual(self.current, self.after)
        self.assertEqual(self.pin.read_text(), arch.hold_text())
        self.assertIn('Include = '+str(self.pin), self.conf.read_text())
        record = json.loads(next(self.state.glob('*/record.json')).read_text())
        self.assertFalse(record['rollback_available'])
        self.assertEqual(record['package_recovery']['missing'], MISSING)
        self.replay.assert_not_called(); self.restore.assert_not_called()

    def test_default_installs_without_any_historical_package_download(self):
        with patch.object(runtime, 'previous_package', side_effect=AssertionError('Historical download attempted')) as download:
            system.install(self.state, self.conf, self.pin)
        download.assert_not_called()
        self.assertEqual(self.current, self.after)
        self.assertEqual(self.pin.read_text(), arch.hold_text())
        record = json.loads(next(self.state.glob('*/record.json')).read_text())
        self.assertFalse(record['rollback_available'])
        self.assertEqual(record['package_recovery']['choice'], 'disabled')
        self.assertEqual(record['previous'], {})

    def test_live_failure_after_waiver_does_not_attempt_partial_rollback(self):
        self.fail_live = True
        with self.assertRaises(subprocess.CalledProcessError):
            system.install(self.state, self.conf, self.pin)
        self.assertEqual(len(self.live_calls), 1)
        self.restore.assert_not_called()


if __name__ == '__main__': unittest.main()
