"""Fedora installer safety checks; never invoke a host package operation."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import dependencies
import fedora_runtime as fedora
import runtime_install as runtime
import system_fedora_runtime as system


class FedoraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xetal-fedora-unit-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.pin = self.root/'versionlock.toml'
        self.required = fedora.target()

    def test_bundle_is_real_verified_data_under_github_file_limit(self):
        paths = fedora.bundled()
        self.assertEqual(len(paths), len(self.required['packages'])+1)
        self.assertLess(sum(p.stat().st_size for p in paths), 100_000_000)
        for source in self.required.get('sources', []):
            p = fedora.BUNDLE/source['file']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), source['sha256'])
            self.assertLess(p.stat().st_size, 100_000_000)

    def test_locks_preserve_unrelated_rules_and_hold_exact_evr_and_arch(self):
        user = 'version = "1.0"\n\n[[packages]]\nname = "example"\ncomment = "mine"\n'
        text = fedora.with_hold(user, self.required)
        self.assertIn(user.strip(), text)
        self.assertEqual(fedora.with_hold(text, self.required), text)
        parsed = tomllib.loads(text)
        compositor = next(p for p in parsed['packages'] if p['name']=='hyprland')
        self.assertEqual(compositor['conditions'], [dict(key='evr',comparator='=',value='0:0.56.2-6.fc44'),
                                                   dict(key='arch',comparator='=',value='x86_64')])

    def test_user_compositor_locks_and_broken_markers_are_never_overwritten(self):
        for text in ['version = "1.0"\n[[packages]]\nname = "hyprland"\n', fedora.BEGIN]:
            with self.assertRaises(RuntimeError): fedora.with_hold(text, self.required)

    def test_dnf_rewriting_toml_preserves_ownership_and_package_hold(self):
        text=fedora.with_hold('',self.required).replace(fedora.BEGIN,'').replace(fedora.END,'')
        text=text.replace(' = ', ' =  ')+'\n[[packages]]\nname = "later"\ncomment = "Added by versionlock"\n'
        self.pin.write_text(text)
        with patch.object(fedora,'PIN',self.pin):self.assertTrue(fedora.pinned())
        rewritten=fedora.with_hold(text,self.required)
        self.assertEqual(len(tomllib.loads(rewritten)['packages']),len(self.required['packages'])+1)
        system.restore_hold(dict(old_hold='',new_hold=fedora.hold_block(self.required),had_pin=False),self.pin)
        self.assertEqual([p['name'] for p in tomllib.loads(self.pin.read_text())['packages']],['later'])

    def test_recovery_keeps_later_unrelated_locks(self):
        self.pin.write_text(fedora.with_hold('', self.required)+'\n[[packages]]\nname = "later"\n')
        record = dict(old_hold='', new_hold=fedora.hold_block(self.required), had_pin=False)
        system.restore_hold(record, self.pin)
        self.assertEqual([p['name'] for p in tomllib.loads(self.pin.read_text())['packages']], ['later'])

    def test_recovery_refuses_externally_edited_runtime_hold(self):
        self.pin.write_text(fedora.with_hold('', self.required).replace('0:0.56.2-6.fc44','0:0.57.0-1.fc44'))
        with self.assertRaisesRegex(RuntimeError, 'edited externally'):
            system.restore_hold(dict(old_hold='', new_hold=fedora.hold_block(self.required), had_pin=False), self.pin)

    def test_release_guard_excludes_other_fedora_releases_and_derived_distributions(self):
        self.assertTrue(runtime.policy.fedora_host({'ID':'fedora','VERSION_ID':'44'}))
        for data in [dict(ID='fedora',VERSION_ID='43'),dict(ID='rhel',ID_LIKE='fedora',VERSION_ID='44'),
                     dict(ID='fedora',VERSION_ID='45')]:
            self.assertFalse(runtime.policy.fedora_host(data))

    def test_fedora_preflight_accepts_only_a_successful_resolution_declined_by_assumeno(self):
        version = subprocess.CompletedProcess([], 0, 'dnf5 version 5.4.1.0', '')
        versions = subprocess.CompletedProcess([], 0, 'waybar 0.15.0\nkitty 0.49.0\n', '')
        ok = subprocess.CompletedProcess([], 1, 'Transaction Summary:\n Installing: 1 package\n', 'Operation aborted by the user.\n')
        failure = subprocess.CompletedProcess([], 1, '', 'Problem: conflicting requests\n')
        with patch.object(fedora, 'bundled', return_value=[Path('/key'),Path('/hyprland.rpm')]), \
             patch.object(fedora, 'PIN', self.pin), patch.object(fedora.subprocess, 'run', side_effect=[version,versions,ok]) as run:
            fedora.preflight(['kitty'])
            command = run.call_args.args[0]
            self.assertIn('--assumeno', command); self.assertNotIn('sudo', command)
        with patch.object(fedora, 'bundled', return_value=[Path('/key'),Path('/hyprland.rpm')]), \
             patch.object(fedora, 'PIN', self.pin), patch.object(fedora.subprocess, 'run', side_effect=[version,versions,failure]):
            with self.assertRaisesRegex(RuntimeError, 'No packages have been changed'): fedora.preflight(['kitty'])

    def test_fedora_44_routes_to_native_rpm_preflight(self):
        with patch.object(dependencies,'distribution',return_value=dict(ID='fedora',VERSION_ID='44')), \
             patch.object(dependencies,'platform_problems',return_value=[]), \
             patch.object(fedora,'preflight') as preflight:
            dependencies.preflight()
            preflight.assert_called_once_with(dependencies.PACKAGES['fedora'])

    def test_missing_sdl3_is_reported_even_when_other_desktop_tools_exist(self):
        with patch.object(dependencies, 'distribution', return_value=dict(ID='fedora', VERSION_ID='44')), \
             patch.object(dependencies, 'find_library', return_value=None), \
             patch.object(dependencies.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            self.assertIn('QEMU needs the SDL3 runtime: install SDL3.', dependencies.check(runtime=False))
        with patch.object(dependencies, 'distribution', return_value=dict(ID='fedora', VERSION_ID='44')), \
             patch.object(dependencies, 'find_library', return_value='libSDL3.so.0'), \
             patch.object(dependencies.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            self.assertNotIn('QEMU needs the SDL3 runtime: install SDL3.', dependencies.check(runtime=False))

    def test_dnf_plan_cannot_erase_unrelated_apps_or_expand_recovery(self):
        plan = self.root/'plan'; plan.mkdir()
        for action in ['Remove','Install','Upgrade']:
            (plan/'transaction.json').write_text(json.dumps(dict(version='1.0',rpms=[dict(nevra='dolphin-1.0-1.fc44.x86_64',action=action)])))
            with self.assertRaisesRegex(RuntimeError,'unrelated package'): system.check_plan(plan, {'hyprland'}, recovery=True)
        (plan/'transaction.json').write_text(json.dumps(dict(version='1.0',rpms=[dict(nevra='dolphin-1.0-1.fc44.x86_64',action='Remove')])))
        with self.assertRaises(RuntimeError): system.check_plan(plan, {'hyprland'})

    def test_saved_transaction_copies_local_rpms_and_rejects_external_paths(self):
        plan=self.root/'plan'; plan.mkdir(); package=self.root/'example-1-1.x86_64.rpm';package.write_bytes(b'verified RPM')
        item=dict(nevra='example-1-1.x86_64',action='Install',package_path='./packages/'+package.name)
        manifest=plan/'transaction.json';manifest.write_text(json.dumps(dict(version='1.0',rpms=[item])))
        system.complete_plan(plan,[package])
        self.assertEqual((plan/'packages'/package.name).read_bytes(),b'verified RPM')
        item['package_path']='../../outside.rpm';manifest.write_text(json.dumps(dict(version='1.0',rpms=[item])))
        with self.assertRaisesRegex(RuntimeError,'outside'):system.complete_plan(plan,[package])

    def test_fedora_library_change_requires_setup_even_when_hyprland_commit_matches(self):
        target = runtime.policy.manifest()
        actual = dict(version=target['hyprland'],commit=target['commit'])
        packages = {p['name']:p['evr']+'.'+p['architecture'] for p in self.required['packages']}
        with patch.object(runtime.policy,'installed',return_value=actual), \
             patch.object(runtime.policy,'fedora_host',return_value=True), \
             patch.object(runtime.policy,'rpm_versions',return_value=packages):
            self.assertEqual(runtime.policy.problem(), '')
            self.assertTrue(runtime.policy.matches_requirement(dict(target,fedora_packages=packages)))
        with patch.object(runtime.policy,'installed',return_value=actual), \
             patch.object(runtime.policy,'fedora_host',return_value=True), \
             patch.object(runtime.policy,'rpm_versions',return_value={}):
            self.assertIn('Fedora',runtime.policy.problem())
            self.assertFalse(runtime.policy.matches_requirement(dict(target,fedora_packages=packages)))

    def test_rollback_routes_to_the_fedora_helper(self):
        with patch.object(runtime,'TRANSACTION',self.root/'record'), \
             patch.object(runtime,'TRANSACTION_BACKEND','fedora'), \
             patch.object(runtime,'administrator',return_value=['sudo']), patch.object(runtime.subprocess,'run') as run:
            runtime.rollback()
            self.assertIn(str(ROOT/'installer/system_fedora_runtime.py'),run.call_args.args[0])

    def test_corrupt_bundle_is_rejected_before_a_package_manager_is_called(self):
        with patch.object(fedora,'BUNDLE',self.root),patch.object(fedora.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'missing or damaged'):fedora.bundled()
            run.assert_not_called()

    def test_external_package_change_blocks_recovery_before_locks_or_packages(self):
        state=self.root/'state'; state.mkdir(); backup=state/'record';backup.mkdir()
        (backup/'record.json').write_text(json.dumps(dict(before={}, expected={'hyprland':'0:0.56.2-6.fc44.x86_64'})))
        with patch.object(runtime.policy,'rpm_versions',return_value={'hyprland':'0:0.57.0-1.fc44.x86_64'}), \
             patch.object(system,'run') as run,patch.object(system,'restore_hold') as hold:
            with self.assertRaisesRegex(RuntimeError,'changed externally'):system.restore(backup,state)
            run.assert_not_called();hold.assert_not_called()


if __name__=='__main__': unittest.main()
