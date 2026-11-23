"""Old installations hand new package requirements to foreground Setup."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'installer'))
import update

OLD, NEW = '1'*40, '2'*40
MISSING = ['Missing command: '+name for name in (
    'wayvnc', 'vncviewer', 'kdeconnect-cli', 'mpv', 'hypridle',
    'meson', 'ninja', 'cargo', 'rustc')]


@unittest.skipIf(os.geteuid() == 0, 'Updates run as the desktop user')
class DependencyUpdates(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='fusion-dependency-update-')
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.live = self.home/'.config/hypr'; self.live.mkdir(parents=True)
        (self.live/'code.py').write_text('old desktop\n')
        update.engine.write_json(self.live/update.engine.META, update.engine.metadata(self.live, OLD))
        self.before = {p.name: p.read_bytes() for p in self.live.iterdir()}
        self.state = self.home/'.local/state/xetal-hyprland/updates'
        self.mocks = {}
        for owner, name, value in (
            (update.install, 'source_revision', NEW),
            (update.install.runtime_install.policy, 'problem', None),
            (update.install.runtime_install, 'ensure', False),
            (update.install.runtime_install, 'restart_after_python_upgrade', None),
            (update.dependencies, 'prepare_repositories', None),
            (update.dependencies, 'preflight', None),
            (update.dependencies, 'install', None),
            (update.dependencies, 'repair_toolchain', None),
            (update.dependencies, 'prepare_account', None),
            (update.dependencies, 'check', MISSING),
            (update.install, 'connected_monitors', []),
            (update.install, 'validate_config', None),
            (update.install, 'build', None),
            (update.install, 'validate', None),
            (update, 'repair_user_directories', True),
        ):
            self.mocks[name] = self.enterContext(patch.object(owner, name, return_value=value))
        self.render = self.enterContext(patch.object(update.install, 'render', side_effect=self.render_fixture))

    def render_fixture(self, destination, *args, **kwargs):
        (destination/'theme').mkdir(parents=True)
        (destination/'code.py').write_text('new desktop\n')
        (destination/'theme/update_widget.py').write_text('# No native build in this fixture.\n')

    def assert_live_unchanged(self):
        self.assertEqual({p.name: p.read_bytes() for p in self.live.iterdir()}, self.before)

    def request_packages(self, automatic=False):
        with self.assertRaisesRegex(update.SetupRequired, 'Setup is required') as error:
            update.prepare(self.home, NEW, automatic=automatic)
        self.assertTrue(all(problem in str(error.exception) for problem in MISSING))
        return update.engine.json_file(self.state/'runtime-required.json')

    def test_missing_packages_offer_setup_in_both_manual_and_background_preparation(self):
        for automatic in (True, False):
            with self.subTest(automatic=automatic):
                update.engine.write_json(self.state/'pending.json', {'revision': OLD})
                marker = self.request_packages(automatic=automatic)
                self.assertEqual(marker['revision'], NEW)
                self.assertEqual(marker['reason'], 'dependencies')
                self.assertEqual(marker['problems'], MISSING)
                self.assertFalse((self.state/'pending.json').exists())
                self.assert_live_unchanged()
        self.render.assert_not_called()
        for name in ('ensure', 'install', 'prepare_repositories', 'preflight', 'prepare_account', 'build'):
            self.mocks[name].assert_not_called()

    def test_foreground_setup_installs_and_rechecks_even_when_compositor_matches(self):
        self.request_packages()
        self.mocks['check'].side_effect = [MISSING, []]
        update.prepare(self.home, NEW, automatic=False, allow_runtime=True)
        self.mocks['install'].assert_called_once_with(yes=True)
        self.mocks['repair_toolchain'].assert_called_once_with(yes=True)
        self.mocks['prepare_account'].assert_called_once_with()
        pending = update.engine.json_file(self.state/'pending.json')
        self.assertFalse(pending['automatic'])
        self.assertTrue(pending['runtime_setup'])
        self.assertEqual((Path(pending['stage'])/'code.py').read_text(), 'new desktop\n')
        self.assertFalse((self.state/'runtime-required.json').exists())
        self.assert_live_unchanged()

    def test_cancelled_package_install_keeps_desktop_and_setup_retry(self):
        self.request_packages()
        self.mocks['install'].side_effect = RuntimeError('Administrator authentication cancelled')
        with self.assertRaisesRegex(RuntimeError, 'authentication cancelled'):
            update.prepare(self.home, NEW, automatic=False, allow_runtime=True)
        self.render.assert_not_called()
        self.assertFalse((self.state/'pending.json').exists())
        self.assertTrue((self.state/'runtime-required.json').exists())
        self.assert_live_unchanged()

    def test_incomplete_package_install_does_not_prepare_a_broken_desktop(self):
        self.mocks['check'].side_effect = [MISSING, ['Missing command: rustc']]
        with self.assertRaisesRegex(RuntimeError, 'Missing command: rustc'):
            update.prepare(self.home, NEW, automatic=False, allow_runtime=True)
        self.mocks['install'].assert_called_once_with(yes=True)
        self.render.assert_not_called()
        self.assertFalse((self.state/'pending.json').exists())
        self.assert_live_unchanged()

    def test_requirements_already_resolved_prepare_without_package_changes(self):
        self.request_packages()
        self.mocks['check'].return_value = []
        update.prepare(self.home, NEW, automatic=False)
        self.mocks['install'].assert_not_called()
        self.mocks['ensure'].assert_not_called()
        self.assertFalse((self.state/'runtime-required.json').exists())
        pending = update.engine.json_file(self.state/'pending.json')
        self.assertFalse(pending['runtime_setup'])
        self.assertEqual(pending['revision'], NEW)
        self.assert_live_unchanged()

    def test_manual_update_opens_setup_in_the_same_worker_and_propagates_its_result(self):
        for code in (0, 1):
            with self.subTest(code=code), patch.object(update.Path, 'home', return_value=self.home), \
                 patch.object(update.subprocess, 'run', return_value=subprocess.CompletedProcess([], code)) as run:
                self.assertEqual(update.main(['--manual', '--revision', NEW]), code)
            self.assertEqual(run.call_args.args[0], [sys.executable,
                str(REPO/'installer/launcher.py'), '--gui', '--update'])
            self.mocks['install'].assert_not_called()
            self.assert_live_unchanged()

    def test_background_preparation_never_opens_setup_or_installs_packages(self):
        with patch.object(update.Path, 'home', return_value=self.home), \
             patch.object(update.subprocess, 'run') as run:
            self.assertEqual(update.main(['--revision', NEW]), 1)
        run.assert_not_called()
        self.mocks['install'].assert_not_called()
        self.assert_live_unchanged()

    def test_compiler_error_does_not_open_setup_again(self):
        with patch.object(update, 'prepare', side_effect=RuntimeError('Compiler failure')), \
             patch.object(update.install.runtime_install, 'rollback') as rollback, \
             patch.object(update.subprocess, 'run') as run:
            self.assertEqual(update.main(['--manual', '--revision', NEW]), 1)
        run.assert_not_called(); rollback.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
