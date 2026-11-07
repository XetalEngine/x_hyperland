"""Automatic optional-module fallback; no module loading or VM operations."""
from contextlib import ExitStack, nullcontext
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import editions
import module_policy
import module_tool
import packages
import portable
import vm_session


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'XETAL_KVM_DATA': str(self.root), 'XETAL_KVM_EDITION': 'xetallic'})
        env.start(); self.addCleanup(env.stop)
        self.cfg = portable.configuration('windows')
        for name, value in (('cpu_vendor', 'amd'),):
            patcher = patch.object(packages, name, return_value=value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.read_busy = module_policy.busy_reason
        patcher = patch.object(module_policy, 'busy_reason', return_value='')
        patcher.start(); self.addCleanup(patcher.stop)

    def package(self, kernel='test-kernel'):
        directory = portable.component_path('kvm-amd'); directory.mkdir(parents=True, exist_ok=True)
        entry = {'version': '1.0.3', 'sha256': 'a'*64, 'cpu': 'amd', 'kernel': kernel}
        packages.atomic_json(directory/'.component.json', entry)
        for name in ('kvm.ko', 'kvm-amd.ko', 'load-kvm.sh'):
            (directory/name).write_text('fixture, never executed')
        return directory

    def test_missing_and_mismatched_then_compatible_kernel_keep_preference(self):
        original = copy.deepcopy(self.cfg)
        self.assertTrue(module_policy.requested(self.cfg))
        self.assertIn('No custom', module_policy.unavailable())
        self.package()
        with patch.object(module_policy.platform, 'release', return_value='newer-kernel'):
            self.assertEqual(module_policy.unavailable(), 'Requires kernel test-kernel')
            self.assertIn('standard KVM', module_policy.warning(self.cfg)[0])
        with patch.object(module_policy.platform, 'release', return_value='test-kernel'):
            self.assertEqual(module_policy.unavailable(), '')
            self.assertEqual(module_policy.warning(self.cfg), ('', ''))
        self.assertEqual(self.cfg, original)

    def test_explicit_opt_out_and_custom_build_script_are_retained(self):
        self.cfg['tools']['kvm_build_enabled'] = False
        self.assertFalse(module_policy.requested(self.cfg))
        self.assertEqual(module_policy.warning(self.cfg), ('', ''))
        self.cfg['tools'].update(kvm_build_enabled=True, kvm_build='/my/build-kvm.sh')
        self.assertFalse(module_policy.managed(self.cfg))

    def test_non_amd_and_incomplete_build_fall_back(self):
        directory = self.package()
        with patch.object(module_policy.platform, 'release', return_value='test-kernel'):
            with patch.object(packages, 'cpu_vendor', return_value='intel'):
                self.assertIn('AMD', module_policy.unavailable())
            (directory/'kvm.ko').unlink()
            self.assertIn('incomplete', module_policy.unavailable())

    def test_auto_loader_does_not_touch_incompatible_module(self):
        with patch.object(sys, 'argv', ['module-tool', '--auto']), \
             patch.object(module_tool, 'check', side_effect=AssertionError('Must not load')), \
             patch.object(module_tool.os, 'execv', side_effect=AssertionError('Must not execute')):
            module_tool.main()
        with self.assertRaises(RuntimeError): module_tool.check(self.root)

    def test_normal_kvm_dependency_is_not_a_vm(self):
        # Use the real busy check, not setUp's idle patch.
        for text, busy in [('kvm 1 1 kvm_amd, Live 0\nkvm_amd 1 0 - Live 0\n', False),
                           ('kvm 1 2 kvm_amd, Live 0\nkvm_amd 1 1 - Live 0\n', True),
                           ('kvm 1 1 - Live 0\n', True),
                           ('kvm 1 2 kvm_amd,vboxdrv, Live 0\n', True)]:
            with patch.object(Path, 'read_text', return_value=text):
                self.assertEqual(bool(self.read_busy()), busy)

    def test_single_script_uses_auto_guard_and_skips_manual_rebuild_blocker(self):
        sys.path.insert(0, str(portable.ROOT/'backend/lib')); self.addCleanup(sys.path.pop, 0)
        import launcher
        from model import VMConfig
        cfg = VMConfig(self.cfg)
        script = launcher.build_start(cfg, {})
        self.assertIn('module-tool.sh --auto', script)
        self.assertNotIn('untick the module build', script)
        subprocess.run(['bash', '-n'], input=script, text=True, check=True)

    def test_windowed_launch_continues_without_loading_missing_module_images(self):
        # Both Virtual and Dual GPU enter this same owner with module-options.
        import runtime_access
        component = portable.component_path('qemu'); component.mkdir(parents=True)
        (component/'.vm-runtime.json').write_text(json.dumps({'key_id':'fixture','edition':'xetallic',
                                                            'files':{'libexec/qemu-system-x86_64':{}}}))
        directory = self.root/'launch'; directory.mkdir()
        with ExitStack() as stack:
            stack.enter_context(patch.object(vm_session, 'private_memory'))
            stack.enter_context(patch.object(vm_session.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(runtime_access, 'launch_key', return_value=b'x'*32))
            stack.enter_context(patch.object(runtime_access, 'revoke'))
            images = stack.enter_context(patch.object(vm_session, 'load_image', return_value=nullcontext(Mock(fd=-1))))
            stack.enter_context(patch.object(vm_session.tempfile, 'mkdtemp', return_value=str(directory)))
            stack.enter_context(patch.object(vm_session.threading, 'Thread'))
            stack.enter_context(patch.object(vm_session.socket, 'socket'))
            stack.enter_context(patch.object(vm_session.os, 'chmod'))
            module = stack.enter_context(patch.object(vm_session.subprocess, 'run'))
            guest = stack.enter_context(patch.object(vm_session, 'run_pinned', return_value=0))
            self.assertEqual(vm_session.main(['/fixture/guest'], {'KVM_AVIC':'0'}), 0)
            module.assert_not_called()
            guest.assert_called_once_with(['/fixture/guest'], [])
            self.assertEqual([c.args[1] for c in images.call_args_list], ['libexec/qemu-system-x86_64'])

    def test_optional_download_resumes_once_on_success_or_failure_and_respects_session(self):
        import app
        for outcome in ('success', 'failure', 'closed', 'reopened', 'new-profile'):
            with self.subTest(outcome=outcome):
                account = SimpleNamespace(session=object())
                panel = SimpleNamespace(release={'components': {'kvm-amd': {'sha256': 'a'*64}}},
                                        account=account, store=SimpleNamespace(root=self.root, download=Mock()),
                                        info=Mock(), job=None, run=Mock())
                panel.run.side_effect=lambda *a,**k:setattr(panel,'job',SimpleNamespace(finished=Mock()))
                window = SimpleNamespace(cfg=SimpleNamespace(data=self.cfg), package_panel=panel,
                                         status=Mock(), _busy=lambda:False, isVisible=Mock(return_value=True),
                                         _refresh_all=Mock())
                retry = Mock()
                with patch.object(packages, 'compatibility', return_value=''), \
                     patch.object(app.QTimer, 'singleShot') as later:
                    self.assertTrue(app.KVMSettings._prepare_optional_module(window, retry))
                    work, done, failed = panel.run.call_args.args
                    self.assertIs(panel.run.call_args.kwargs['session'], account.session)
                    work(Mock());panel.store.download.assert_called_once()
                    if outcome == 'failure':failed('Offline')
                    else:done(None)
                    self.assertFalse(app.KVMSettings._prepare_optional_module(window, retry))
                    panel.run.assert_called_once()
                    # Simulate a queued completion; even a close/reopen before
                    # that queue drains must not restart the cancelled launch.
                    panel.job.finished.connect.call_args.args[0]()
                    if outcome == 'closed':window.isVisible.return_value=False
                    elif outcome == 'reopened':account.session=object()
                    elif outcome == 'new-profile':window.cfg=SimpleNamespace(data=self.cfg)
                    later.call_args.args[1]()
                    self.assertEqual(retry.call_count, int(outcome in ('success', 'failure')))

    def test_unsupported_kernel_never_downloads_an_optional_module(self):
        import app
        panel = SimpleNamespace(release={'components': {'kvm-amd': {'sha256': 'a'*64}}}, run=Mock(),job=None)
        window = SimpleNamespace(cfg=SimpleNamespace(data=self.cfg), package_panel=panel)
        with patch.object(packages, 'compatibility', return_value='Requires a different kernel'):
            self.assertFalse(app.KVMSettings._prepare_optional_module(window, Mock()))
        panel.run.assert_not_called()

    def test_matching_kernel_prepares_without_a_launch_request(self):
        import app
        panel=SimpleNamespace(release={'components':{'kvm-amd':{'sha256':'a'*64}}},
            account=SimpleNamespace(session=object()),store=SimpleNamespace(root=self.root,download=Mock()),
            job=None,run=Mock(),info=Mock())
        window=SimpleNamespace(cfg=SimpleNamespace(data=self.cfg),package_panel=panel,
            status=Mock(),_busy=lambda:False,_refresh_all=Mock())
        with patch.object(packages,'compatibility',return_value=''):
            self.assertTrue(app.KVMSettings._prepare_optional_module(window))
            work,done,failed=panel.run.call_args.args
            work(Mock());done(None)
            panel.store.download.assert_called_once()
            self.assertNotIn('Continuing launch',window.status.setText.call_args.args[0])
            window._refresh_all.assert_called_once()
            self.assertFalse(app.KVMSettings._prepare_optional_module(window))

    def test_matching_kernel_warning_does_not_claim_kernel_incompatibility(self):
        release={'components':{'kvm-amd':{'cpu':'amd','kernel':'test-kernel'}}}
        with patch.object(module_policy.platform,'release',return_value='test-kernel'):
            text,detail=module_policy.warning(self.cfg,release)
        self.assertIn('is compatible',text)
        self.assertNotIn('Boot that kernel',detail)


if __name__ == '__main__': unittest.main()
