"""Debian runtime checks never invoke a host package mutation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import debian_runtime as debian
import dependencies
import runtime_install as runtime
import system_debian_runtime as system


class DebianTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='xetal-debian-unit-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.pin = self.root/'preferences'

    def test_native_bundle_is_complete_verified_and_below_100_mb(self):
        required = debian.target()
        paths = debian.extract(self.root, required)
        self.assertLess(required['bytes'], 100_000_000)
        self.assertEqual(len(paths), len(required['packages']))
        self.assertTrue(all(p.read_bytes().startswith(b'!<arch>\n') for p in paths))

    def test_corrupt_archive_stops_before_extraction_or_apt(self):
        with patch.object(debian, 'BUNDLE', self.root), patch.object(debian.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'missing or damaged'):
                debian.extract(self.root)
            run.assert_not_called()

    def test_archive_member_paths_and_duplicate_entries_cannot_escape_manifest(self):
        for names in (['../escape.deb'], ['safe.deb', 'safe.deb']):
            archive = self.root/'debian-13-runtime.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                for name in names: output.writestr(name, b'deb')
            required = dict(file=archive.name, bytes=archive.stat().st_size,
                            sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                            packages=[dict(file='safe.deb', bytes=3, sha256=hashlib.sha256(b'deb').hexdigest())])
            with patch.object(debian, 'BUNDLE', self.root):
                with self.assertRaisesRegex(RuntimeError, 'does not match'):
                    debian.extract(self.root, required)
            self.assertFalse((self.root/'safe.deb').exists())

    def test_release_guard_rejects_ubuntu_derivatives_and_other_debian_versions(self):
        self.assertTrue(runtime.policy.debian_host(dict(ID='debian', VERSION_ID='13')))
        for data in [dict(ID='ubuntu', ID_LIKE='debian', VERSION_ID='26.04'), dict(ID='debian', VERSION_ID='12'),
                     dict(ID='debian', VERSION_ID='14'), dict(ID='kali', ID_LIKE='debian', VERSION_ID='13')]:
            self.assertFalse(runtime.policy.debian_host(data))

    def test_preflight_routes_to_native_debian_without_pacman(self):
        with patch.object(dependencies, 'distribution', return_value=dict(ID='debian', VERSION_ID='13')), \
             patch.object(dependencies, 'platform_problems', return_value=[]), patch.object(debian, 'preflight') as check:
            dependencies.preflight()
            check.assert_called_once_with(dependencies.PACKAGES['debian'])

    def test_apt_plan_retains_exact_versions_and_detects_removals(self):
        plan, removed = debian.parse_plan('Inst hyprland (0.56.2+ds-3~xetal13.1 local-deb [amd64])\n'
                                         'Inst libwayland-client0:amd64 [1.23.1-3] (1.26.0-1~xetal13.1 local-deb [amd64])\n'
                                         'Remv dolphin [4:24.12.3-1]\n')
        self.assertEqual(plan['hyprland'], '0.56.2+ds-3~xetal13.1')
        self.assertEqual(plan['libwayland-client0:amd64'], '1.26.0-1~xetal13.1')
        self.assertEqual(removed, {'dolphin'})
        with self.assertRaises(RuntimeError): debian.parse_plan('Inst unknown output\n')

    def test_apt_simulation_never_accepts_unrelated_app_removal(self):
        result = subprocess.CompletedProcess([], 0, 'Remv dolphin [1]\n', '')
        with patch.object(debian.subprocess, 'run', return_value=result) as run:
            with self.assertRaises(RuntimeError): debian.simulate(['/package.deb'])
            self.assertIn('-s', run.call_args.args[0])
            self.assertIn('--no-remove', run.call_args.args[0])
            with self.assertRaises(RuntimeError): debian.simulate(['hyprland-'], allow_remove={'hyprland'})

    def test_user_pin_is_not_overwritten_and_recovery_preserves_external_edits(self):
        with self.assertRaises(RuntimeError): debian.check_hold('Package: *\nPin-Priority: 1001\n')
        self.pin.write_text('user edited')
        with self.assertRaisesRegex(RuntimeError, 'externally'):
            system.restore_pin(dict(old_pin=None, new_pin='ours'), self.pin)
        self.assertEqual(self.pin.read_text(), 'user edited')
        self.pin.write_text('ours')
        system.restore_pin(dict(old_pin=None, new_pin='ours'), self.pin)
        self.assertFalse(self.pin.exists())

    def test_external_package_update_blocks_recovery_before_any_changes(self):
        state = self.root/'state'; state.mkdir(); backup = state/'record'; backup.mkdir()
        (backup/'record.json').write_text(json.dumps(dict(before={}, expected={'hyprland:amd64':'0.56.2'})))
        with patch.object(system, 'versions', return_value={'hyprland:amd64':'0.57.0'}), \
             patch.object(system, 'run') as run, patch.object(system, 'restore_pin') as pin:
            with self.assertRaisesRegex(RuntimeError, 'changed externally'): system.restore(backup, state)
            run.assert_not_called(); pin.assert_not_called()

    def test_recovery_routes_to_debian_helper(self):
        with patch.object(runtime, 'TRANSACTION', self.root/'record'), patch.object(runtime, 'TRANSACTION_BACKEND', 'debian'), \
             patch.object(runtime, 'administrator', return_value=['sudo']), patch.object(runtime.subprocess, 'run') as run:
            runtime.rollback()
            self.assertIn(str(ROOT/'installer/system_debian_runtime.py'), run.call_args.args[0])

    def test_recovery_keeps_new_ordinary_system_services(self):
        state = self.root/'state'; state.mkdir(); backup = state/'record'; backup.mkdir()
        expected = {'hyprland:amd64':'0.56.2', 'systemd:amd64':'257'}
        record = dict(before={}, expected=expected, bundled=['hyprland:amd64'], previous={}, old_pin=None, new_pin='ours')
        (backup/'record.json').write_text(json.dumps(record)); self.pin.write_text('ours')
        with patch.object(debian, 'PIN', self.pin), \
             patch.object(system, 'versions', side_effect=[expected, {'systemd:amd64':'257'}]), \
             patch.object(debian, 'simulate', return_value=({}, {'hyprland:amd64'})) as simulate, \
             patch.object(system, 'run') as run:
            system.restore(backup, state)
            self.assertEqual(simulate.call_args.args[0], ['hyprland:amd64-'])
            self.assertNotIn('systemd:amd64-', run.call_args.args[0])
        self.assertTrue(json.loads((backup/'record.json').read_text())['restored'])

    def test_matching_commit_still_requires_matching_debian_libraries(self):
        target = runtime.policy.manifest()
        actual = dict(version=target['hyprland'], commit=target['commit'])
        expected = {p['name']+':'+p['architecture']: p['version'] for p in debian.target()['packages']}
        with patch.object(runtime.policy, 'installed', return_value=actual), patch.object(runtime.policy, 'debian_host', return_value=True), \
             patch.object(runtime.policy, 'fedora_host', return_value=False), patch.object(runtime.policy, 'deb_versions', return_value={}):
            self.assertIn('Debian', runtime.policy.problem())
            self.assertFalse(runtime.policy.matches_requirement(dict(target, debian_packages=expected)))


if __name__ == '__main__': unittest.main()
