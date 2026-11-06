"""Offline edition/crypto checks. No account, VM, module or host mutation."""
import base64
import copy
from contextlib import ExitStack,nullcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
import editions
import packages
import portable
import echo_account
import vm_memory
import edition_migration


def sealed_fixture(path,data=b'private executable fixture',name='libexec/qemu-system-x86_64'):
    key=os.urandom(32);nonce=os.urandom(12)
    body=vm_memory.MAGIC+nonce+AESGCM(key).encrypt(nonce,data,vm_memory.aad('xetallic','qemu',name))
    path.write_bytes(body)
    entry={'size':len(data),'sha256':hashlib.sha256(body).hexdigest()}
    return key,entry


class EditionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vm-editions-test-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        environment=patch.dict(os.environ,{'XETAL_KVM_DATA':str(self.root)})
        environment.start();self.addCleanup(environment.stop)

    def test_stock_is_default_and_custom_module_disabled(self):
        cfg=portable.configuration('windows')
        self.assertEqual(editions.selected(),'stock')
        self.assertIn('/editions/stock/components/qemu/',cfg['_meta']['binary'])
        self.assertFalse(cfg['tools']['kvm_build_enabled'])

    def test_switch_preserves_disks_nvram_tpm_identity_and_roundtrips_tools(self):
        cfg=portable.configuration('windows')
        cfg['blockdevs'].append({'filename':str(self.root/'my-guest.qcow2'),'node-name':'guest-disk'})
        original=copy.deepcopy(cfg)
        editions.switch(cfg,'xetallic');cfg['tools']['kvm_build_enabled']=True
        editions.switch(cfg,'stock');self.assertFalse(cfg['tools']['kvm_build_enabled'])
        editions.switch(cfg,'xetallic');self.assertTrue(cfg['tools']['kvm_build_enabled'])
        for before,after in zip(original['blockdevs'],cfg['blockdevs']):
            if not before.get('filename','').endswith('OVMF_CODE.fd'):self.assertEqual(before,after)
        for name in ('swtpm_state','tpm_root','tpm_reconstruct'):
            self.assertEqual(original['tools'][name],cfg['tools'][name])

    def test_max_cannot_be_selected_and_custom_paths_survive_refresh(self):
        with self.assertRaises(ValueError):editions.select('max')
        cfg=portable.configuration('windows');cfg['_meta']['binary']='/opt/my-qemu'
        editions.apply(cfg);self.assertEqual(cfg['_meta']['binary'],'/opt/my-qemu')

    def test_refresh_and_edition_switch_keep_live_editor_references(self):
        cfg=portable.configuration('windows')
        disk={'filename':str(self.root/'old.iso'),'node-name':'test-cd'}
        device={'driver':'ide-cd','drive':'test-cd','id':'test-cd-device'}
        cfg['blockdevs'].append(disk);cfg['devices'].append(device)
        blocks,devices,tools=cfg['blockdevs'],cfg['devices'],cfg['tools']
        for edition in ('stock','xetallic','stock'):
            editions.apply(cfg,edition=edition)
            self.assertIs(cfg['blockdevs'],blocks)
            self.assertIs(cfg['devices'],devices)
            self.assertIs(cfg['tools'],tools)
            self.assertIs(cfg['blockdevs'][-1],disk)
            self.assertIs(cfg['devices'][-1],device)
            disk['filename']=str(self.root/(edition+'.iso'))
            device['_disabled']=True
            self.assertEqual(cfg['blockdevs'][-1]['filename'],str(self.root/(edition+'.iso')))
            self.assertTrue(cfg['devices'][-1]['_disabled'])

    def test_profile_reopen_preserves_per_edition_module_choice(self):
        cfg=portable.configuration('windows')
        editions.switch(cfg,'xetallic');cfg['tools']['kvm_build_enabled']=True
        editions.select('stock');editions.apply(cfg)
        self.assertFalse(cfg['tools']['kvm_build_enabled'])
        editions.select('xetallic');editions.apply(cfg)
        self.assertTrue(cfg['tools']['kvm_build_enabled'])

    def legacy_runtime(self,name='qemu'):
        directory=self.root/'components'/name/'1.0.3-fixture';directory.mkdir(parents=True)
        (directory.parent/'current').symlink_to(directory.name)
        files={}
        originals=['libexec/qemu-system-x86_64'] if name=='qemu' else ['kvm.ko','kvm-amd.ko']
        for original in originals:
            file=directory/(original+'.xvm');file.parent.mkdir(parents=True,exist_ok=True)
            _,image=sealed_fixture(file)
            files[original]=dict(image,file=original+'.xvm')
        runtime={'component':name,'edition':'xetallic','key_id':'a'*64,'files':files}
        entry={'version':'1.0.3','sha256':'b'*64,'runtime':runtime,'cpu':'amd','kernel':'test-kernel'}
        packages.atomic_json(directory/'.vm-runtime.json',runtime)
        packages.atomic_json(directory/'.component.json',entry)
        if name=='qemu':
            (directory/'bin').mkdir()
            (directory/'bin/qemu-system-x86_64').write_text('#!/bin/sh\nexit 1\n')
        (self.root/'release.json').write_text('signed fixture')
        return directory,entry

    def test_migration_preserves_guest_bytes_and_repairs_old_installer(self):
        directory,entry=self.legacy_runtime()
        (self.root/'downloads').mkdir()
        guests={'last-session.json':b'{"tools":{"kvm_build_enabled":true}}',
                'firmware/OVMF_VARS.fd':b'my variables','macos/boot/OpenCore.img':b'my boot disk',
                'tpm-workspace/state':b'my TPM','guest.qcow2':b'my guest'}
        for name,data in guests.items():
            file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
        before=(directory/'libexec/qemu-system-x86_64.xvm').read_bytes()
        release={'edition':'xetallic','components':{'qemu':entry}}
        with patch.object(packages,'decode',return_value=release):
            self.assertTrue(edition_migration.migrate())
            self.assertFalse(edition_migration.migrate())
        self.assertEqual(editions.selected(),'xetallic')
        self.assertEqual(portable.component_path('qemu').resolve(),directory)
        self.assertIn('vm_memory.py',(directory/'bin/qemu-system-x86_64').read_text())
        self.assertEqual(before,(directory/'libexec/qemu-system-x86_64.xvm').read_bytes())
        self.assertFalse((directory/'libexec/qemu-system-x86_64').exists())
        for name,data in guests.items():self.assertEqual((self.root/name).read_bytes(),data)
        editions.select('stock')
        self.assertFalse(portable.component_path('qemu').exists())
        self.assertTrue((self.root/'components/qemu/current').exists())

    def test_migration_rejects_unsigned_runtime_and_can_resume(self):
        directory,entry=self.legacy_runtime()
        with patch.object(packages,'decode',side_effect=ValueError('signature verification failed')):
            with self.assertRaisesRegex(ValueError,'signature'):edition_migration.migrate()
        self.assertFalse((self.root/'edition.json').exists())
        self.assertNotIn('vm_memory.py',(directory/'bin/qemu-system-x86_64').read_text())
        original=packages.atomic_json
        def interrupted(file,value):
            if file.name=='.edition-migration.json':raise OSError('interrupted')
            original(file,value)
        with patch.object(packages,'decode',return_value={'edition':'xetallic','components':{'qemu':entry}}):
            with patch.object(packages,'atomic_json',side_effect=interrupted):
                with self.assertRaises(OSError):edition_migration.migrate()
            self.assertTrue(edition_migration.migrate())
        self.assertEqual(portable.component_path('qemu').resolve(),directory)

    def test_updated_module_check_does_not_use_modinfo_or_extract_images(self):
        import module_tool
        directory,entry=self.legacy_runtime('kvm-amd')
        files={f.name:f.read_bytes() for f in directory.iterdir()}
        with patch.object(packages,'decode',return_value={'edition':'xetallic','components':{'kvm-amd':entry}}):
            edition_migration.migrate()
        with patch.object(packages,'compatibility',return_value=''), \
             patch.object(module_tool.subprocess,'check_output',side_effect=AssertionError('modinfo must not run')):
            self.assertEqual(module_tool.check(self.root).resolve(),directory)
            (directory/'kvm.ko.xvm').write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError,'release metadata'):module_tool.check(self.root)
        self.assertEqual(set(f.name for f in directory.iterdir()),set(files))

    def test_memory_image_is_locked_sealed_and_never_materialized(self):
        path=self.root/'main.xvm';key,entry=sealed_fixture(path)
        initial=list(self.root.iterdir())
        with vm_memory.Image(path,entry,key,vm_memory.aad('xetallic','qemu','libexec/qemu-system-x86_64')) as image:
            self.assertEqual(os.read(image.fd,entry['size']),b'private executable fixture')
            self.assertIn('memfd:xetal-vm',os.readlink(image.path))
            self.assertNotEqual(fcntl.fcntl(image.fd,fcntl.F_GET_SEALS)&0x10,0)
            with self.assertRaises(OSError):os.write(image.fd,b'bad')
            self.assertEqual(list(self.root.iterdir()),initial)
            locked=int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmLck:')))
            self.assertGreater(locked,0)
        self.assertEqual(list(self.root.iterdir()),initial)

    def test_corruption_wrong_key_and_wrong_component_never_return_an_image(self):
        path=self.root/'main.xvm';key,entry=sealed_fixture(path)
        for bad_key,associated in [(os.urandom(32),vm_memory.aad('xetallic','qemu','libexec/qemu-system-x86_64')),
                                   (key,vm_memory.aad('xetallic','kvm-amd','kvm.ko'))]:
            with self.assertRaises(InvalidTag):vm_memory.Image(path,entry,bad_key,associated)
        blob=bytearray(path.read_bytes());blob[23]^=1;path.write_bytes(blob)
        with self.assertRaises(InvalidTag):vm_memory.Image(path,entry,key,vm_memory.aad('xetallic','qemu','libexec/qemu-system-x86_64'))
        self.assertEqual(list(self.root.iterdir()),[path])

    def test_locked_memory_failure_has_no_disk_fallback(self):
        path=self.root/'main.xvm';key,entry=sealed_fixture(path)
        with patch.object(vm_memory,'LIBC') as libc:
            libc.mlock.return_value=-1
            with self.assertRaisesRegex(RuntimeError,'locked memory'):
                vm_memory.Image(path,entry,key,b'fixture')
        self.assertEqual(list(self.root.iterdir()),[path])

    def test_real_elf_executes_from_the_pinned_descriptor(self):
        path=self.root/'fixture.xvm';key,entry=sealed_fixture(path,Path('/usr/bin/true').read_bytes())
        with vm_memory.Image(path,entry,key,vm_memory.aad('xetallic','qemu','libexec/qemu-system-x86_64')) as image:
            self.assertEqual(vm_memory.run_pinned([image.path],[image]),0)
        self.assertEqual(list(self.root.iterdir()),[path])

    def test_launch_errors_are_safe_and_redirects_are_refused(self):
        with self.assertRaises(echo_account.AccountError):echo_account.request('account',{'token':'synthetic'},site='http://example.com')
        from download_access import NoRedirect
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid'))

    def test_no_plaintext_password_wallet_fallback(self):
        account=echo_account.Account()
        with patch('echo_account.shutil.which',return_value=None),patch('echo_account.request',return_value={'token':'synthetic','user':{'username':'test'}}):
            account.login('test','synthetic-password',remember=True)
            self.assertEqual(account.token,'synthetic')
        self.assertEqual(list(self.root.iterdir()),[])

    def test_session_only_login_removes_previous_wallet_account(self):
        account=echo_account.Account()
        with patch('echo_account.shutil.which',return_value='/usr/bin/secret-tool'), \
             patch('echo_account.request',return_value={'token':'synthetic','user':{'username':'test'}}), \
             patch('echo_account.subprocess.run',return_value=subprocess.CompletedProcess([],1,'','')) as run:
            account.login('test','synthetic-password',remember=False)
            self.assertEqual(run.call_args.args[0][1],'clear')
            self.assertNotIn('synthetic',str(run.call_args))
        self.assertEqual(account.token,'synthetic')
        self.assertEqual(list(self.root.iterdir()),[])

    def test_update_checks_never_open_echo_wallet_or_session(self):
        from package_ui import PackagesPanel
        for edition in ('stock','xetallic'):
            with self.subTest(edition=edition):
                panel=SimpleNamespace(info=Mock(),store=Mock(edition=edition),account=Mock(),
                                      run=lambda work,finished:work(Mock()))
                PackagesPanel.check_updates(panel)
                self.assertEqual(panel.account.mock_calls,[])
                panel.store.check.assert_called_once_with()

    def test_all_launch_modes_use_preflight_owner(self):
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('edition_runtime',portable.ROOT/'backend/lib/edition_runtime.py');module=module_from_spec(spec);spec.loader.exec_module(module)
        cmd=module.command(['/usr/bin/true'])
        self.assertEqual(cmd[-1],'/usr/bin/true');self.assertEqual(cmd[1],str(portable.ROOT/'vm_session.py'))
        cfg=SimpleNamespace(data={'_meta':{'vm_edition':'xetallic'},'tools':{
            'kvm_build_enabled':True,'kvm_build':str(portable.ROOT/'module-tool.sh'),
            'kvm_build_args':'','kvm_env':{'KVM_AVIC':'0'}}})
        cmd=module.command(['/usr/bin/true'],cfg)
        self.assertEqual(json.loads(cmd[cmd.index('--module-options')+1]),{'KVM_AVIC':'0'})
        cfg.data['tools']['kvm_build_enabled']=False
        self.assertNotIn('--module-options',module.command(['/usr/bin/true'],cfg))
        cfg.data['tools']['kvm_build_enabled']=True
        cfg.data['_meta']['vm_edition']='stock'
        self.assertNotIn('--module-options',module.command(['/usr/bin/true'],cfg))

    def test_qemu_device_checks_share_one_authenticated_probe(self):
        sys.path.insert(0,str(portable.ROOT/'backend/lib'));self.addCleanup(sys.path.pop,0)
        import edition_runtime
        edition_runtime._inspections.clear()
        editions.select('xetallic')
        component=portable.component_path('qemu');(component/'bin').mkdir(parents=True)
        binary=component/'bin/qemu-system-x86_64';binary.write_text('#!/bin/sh\nexit 1\n')
        metadata=component/'.vm-runtime.json';metadata.write_text('{"key_id":"fixture"}')
        result={'capabilities':{'devices':['VGA','virtio-serial-pci'],'spice':True,'vnc':True},
                'guest_device_ids':{'virtio-serial-pci':{'vendor':0x1af4}},'ivshmem_ids':{},'errors':{}}
        with patch.object(edition_runtime.os,'geteuid',return_value=1000), \
             patch.object(edition_runtime.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(result),'')) as run:
            self.assertEqual(edition_runtime.inspection(binary,'capabilities')['devices'],{'VGA','virtio-serial-pci'})
            self.assertEqual(edition_runtime.inspection(binary,'guest_device_ids'),result['guest_device_ids'])
            run.assert_called_once()
            argv=run.call_args.args[0]
            self.assertEqual(argv[:3],['sudo','-n','/usr/bin/env'])
            self.assertIn('XETAL_KVM_DATA='+str(self.root),argv)
            self.assertIn('XETAL_KVM_EDITION=xetallic',argv)
            metadata.write_text('{"key_id":"updated"}')
            edition_runtime.inspection(binary,'capabilities');self.assertEqual(run.call_count,2)
        with patch.object(edition_runtime.os,'geteuid',return_value=0), \
             patch.dict(os.environ,{'XETAL_KVM_LAUNCH_SOCKET':'/fixture/socket'}), \
             patch.object(edition_runtime.subprocess,'run',side_effect=AssertionError('Recursive probe')):
            self.assertIsNone(edition_runtime.inspection(binary,'capabilities'))
        self.assertIsNone(edition_runtime.inspection('/usr/bin/true','capabilities'))

    def test_device_probe_never_loads_module_or_consumes_launch_authorization(self):
        import runtime_probe,vm_session
        with patch.object(runtime_probe.sys,'argv',['runtime_probe.py']),patch.object(vm_session,'main',return_value=0) as run:
            self.assertEqual(runtime_probe.main(),0)
        self.assertEqual(run.call_args.kwargs,{'components':('qemu',),'revoke_session':False})

    def test_account_or_module_failure_cannot_start_guest_preparation(self):
        import vm_session,runtime_access,module_policy
        component=self.root/'qemu';component.mkdir()
        (component/'.vm-runtime.json').write_text(json.dumps({'key_id':'a'*64,'edition':'xetallic',
            'files':{'libexec/qemu-system-x86_64':{}}}))
        for failed_stage in ('account','module'):
            with self.subTest(stage=failed_stage),ExitStack() as stack:
                directory=self.root/'launch';directory.mkdir()
                stack.enter_context(patch.object(vm_session.editions,'selected',return_value='xetallic'))
                stack.enter_context(patch.object(vm_session,'private_memory'))
                stack.enter_context(patch.object(module_policy,'unavailable',return_value=''))
                stack.enter_context(patch.object(vm_session.os,'geteuid',return_value=0))
                stack.enter_context(patch.object(vm_session.portable,'component_path',side_effect=lambda name:component if name=='qemu' else self.root/'absent'))
                key=stack.enter_context(patch.object(runtime_access,'launch_key',return_value=b'x'*32))
                stack.enter_context(patch.object(runtime_access,'revoke'))
                stack.enter_context(patch.object(vm_session,'load_image',return_value=nullcontext(Mock(fd=-1))))
                stack.enter_context(patch.object(vm_session.tempfile,'mkdtemp',return_value=str(directory)))
                stack.enter_context(patch.object(vm_session.threading,'Thread'))
                stack.enter_context(patch.object(vm_session.socket,'socket'))
                stack.enter_context(patch.object(vm_session.os,'chmod'))
                module=stack.enter_context(patch.object(vm_session.subprocess,'run'))
                guest=stack.enter_context(patch.object(vm_session,'run_pinned'))
                if failed_stage=='account':key.side_effect=RuntimeError('Account denied')
                else:module.side_effect=RuntimeError('Module rejected')
                with self.assertRaises(RuntimeError):vm_session.main(['/fixture/guest'],{})
                guest.assert_not_called()
                if failed_stage=='account':module.assert_not_called();directory.rmdir()

    def test_integrated_test_run_preserves_recipient_and_edition_through_sudo(self):
        sys.path.insert(0,str(portable.ROOT/'backend/lib'))
        self.addCleanup(sys.path.pop,0)
        import launcher
        from types import SimpleNamespace
        cfg=SimpleNamespace(data={'_meta':{'vm_edition':'xetallic'}})
        with patch.object(launcher,'RUN_DIR',str(self.root)), \
             patch.object(launcher,'TESTRUN',str(self.root/'test-run.sh')), \
             patch.object(launcher,'build_testrun',return_value=('true\n',[])), \
             patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'ok','')) as run:
            self.assertEqual(launcher.test_run(cfg),(True,'ok'))
        argv=run.call_args.args[0]
        self.assertEqual(argv[:3],['sudo','-n','/usr/bin/env'])
        self.assertIn('XETAL_KVM_DATA='+str(self.root),argv)
        self.assertIn('XETAL_KVM_EDITION=xetallic',argv)
        self.assertIn(str(portable.ROOT/'vm_session.py'),argv)


if __name__=='__main__':unittest.main()
