import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
KIT = PROJECT/'macos/performance/shared-store-driver'


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common=load('fixed_driver_common',KIT/'common.py')
with patch.dict(sys.modules,{'common':common}):
    runner=load('fixed_driver_runner',KIT/'run.py')
installer=load('fixed_driver_installer',KIT/'install.py')


def fixture(root):
    original=b'original nvK runtime';candidate=b'new fixed compiler'
    expected={}
    for index,name in enumerate(installer.BASELINE):
        p=installer.path_at(root,name);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(original if name==installer.TARGET else ('original-component-'+str(index)).encode())
        p.chmod(0o644)
        expected[name]=installer.digest(p)
    cfg=installer.path_at(root,installer.CONFIG);cfg.write_bytes(b'unchanged configuration\n')
    delivery=root/'delivery';delivery.mkdir()
    (delivery/'libvulkan_nouveau.dylib').write_bytes(candidate)
    receipt={'version':installer.VERSION,'native_qualified':True,'candidate':{
        'sha256':hashlib.sha256(candidate).hexdigest(),'uuid':'11'*16},
        'original_uuid':'22'*16,'baseline':expected,'config_sha256':installer.digest(cfg)}
    (delivery/'qualified.json').write_text(json.dumps(receipt))
    return delivery,expected,original,candidate


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vm2-installer-test-')
        self.root=Path(self.temp.name)
        self.delivery,self.expected,self.original,self.candidate=fixture(self.root)
        self.mock1=patch.object(installer,'ORIGINAL',self.expected[installer.TARGET]);self.mock1.start()
        self.mock2=patch.object(installer,'BASELINE',self.expected);self.mock2.start()

    def tearDown(self):
        self.mock2.stop();self.mock1.stop();self.temp.cleanup()

    def install(self):
        return installer.install(self.delivery,self.root,verify_signature=False)

    def target(self):
        return installer.path_at(self.root,installer.TARGET)

    def assert_other_files(self):
        for path,digest in self.expected.items():
            if path!=installer.TARGET:
                self.assertEqual(installer.digest(installer.path_at(self.root,path)),digest)
        self.assertEqual(installer.path_at(self.root,installer.CONFIG).read_bytes(),b'unchanged configuration\n')

    def test_atomic_install_and_rollback_preserve_components_permissions_backup(self):
        inode=self.target().stat().st_ino
        state=self.install()
        self.assertEqual(self.target().read_bytes(),self.candidate)
        self.assertNotEqual(self.target().stat().st_ino,inode)
        self.assertEqual(self.target().stat().st_mode&0o777,0o644)
        store=installer.path_at(self.root,installer.STORE)
        backup=store/state['backup_id']
        self.assertEqual((backup/'original.dylib').read_bytes(),self.original)
        self.assertEqual((backup/'original.conf').read_bytes(),b'unchanged configuration\n')
        self.assertEqual(store.stat().st_mode&0o777,0o700)
        subprocess.run(['bash','-n',str(backup/'Restore-from-Recovery.sh')],check=True)
        self.assert_other_files()
        restored=installer.rollback(self.root,hashlib.sha256(self.candidate).hexdigest())
        self.assertEqual(restored['state'],'restored')
        self.assertEqual(self.target().read_bytes(),self.original)
        self.assert_other_files()
        self.assertEqual(installer.rollback(self.root)['state'],'restored')

    def test_payload_changed_after_qualification_refuses_without_backup_or_write(self):
        (self.delivery/'libvulkan_nouveau.dylib').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'checksum'):self.install()
        self.assertEqual(self.target().read_bytes(),self.original)
        self.assertFalse(installer.path_at(self.root,installer.STORE).exists())

    def test_baseline_config_and_incomplete_receipt_refuse_before_replacement(self):
        receipt_path=self.delivery/'qualified.json'
        valid=json.loads(receipt_path.read_text())
        for bad in ('qualified','uuid','baseline','config'):
            row=json.loads(json.dumps(valid))
            if bad=='qualified':row['native_qualified']=False
            elif bad=='uuid':row['candidate']['uuid']=row['original_uuid']
            elif bad=='baseline':row['baseline']={installer.TARGET:self.expected[installer.TARGET]}
            else:row['config_sha256']='0'*64
            receipt_path.write_text(json.dumps(row))
            with self.assertRaises(ValueError):self.install()
            self.assertEqual(self.target().read_bytes(),self.original)
        self.assert_other_files()

    def test_failure_after_atomic_replace_restores_original(self):
        real=installer.replace_bytes
        def fail_after_write(target,data,metadata):
            real(target,data,metadata)
            if data==self.candidate:raise OSError('simulated failure after rename')
        with patch.object(installer,'replace_bytes',fail_after_write):
            with self.assertRaisesRegex(OSError,'simulated'):self.install()
        self.assertEqual(self.target().read_bytes(),self.original)
        self.assertEqual(json.loads((installer.path_at(self.root,installer.STORE)/'active.json').read_text())['state'],'restored')
        self.assert_other_files()

    def test_restore_refuses_unrelated_replacement_or_wrong_candidate(self):
        self.install()
        with self.assertRaisesRegex(ValueError,'different candidate'):installer.rollback(self.root,'f'*64)
        self.assertEqual(self.target().read_bytes(),self.candidate)
        self.target().write_bytes(b'unrelated later driver')
        with self.assertRaisesRegex(ValueError,'changed after'):installer.rollback(self.root)
        self.assertEqual(self.target().read_bytes(),b'unrelated later driver')

    def test_restore_refuses_corrupted_backup(self):
        state=self.install()
        p=installer.path_at(self.root,installer.STORE)/state['backup_id']/'original.dylib'
        p.write_bytes(b'bad backup')
        with self.assertRaisesRegex(ValueError,'Backup checksum'):installer.rollback(self.root)
        self.assertEqual(self.target().read_bytes(),self.candidate)

    def test_symlink_target_and_backup_parent_refused(self):
        target=self.target();target.unlink()
        other=self.root/'elsewhere';other.write_bytes(self.original);target.symlink_to(other)
        with self.assertRaisesRegex(ValueError,'regular file'):self.install()
        self.assertEqual(other.read_bytes(),self.original)
        target.unlink();target.write_bytes(self.original)
        support=installer.path_at(self.root,'/Library/Application Support')
        support.symlink_to(self.root/'outside',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Symlink'):self.install()
        self.assertFalse((self.root/'outside').exists())

    def test_modified_other_component_refused(self):
        name=next(n for n in self.expected if n!=installer.TARGET)
        installer.path_at(self.root,name).write_bytes(b'new translator or kext')
        with self.assertRaisesRegex(ValueError,'baseline changed'):self.install()
        self.assertEqual(self.target().read_bytes(),self.original)


class QualificationTests(unittest.TestCase):
    def test_gate_includes_cpu_readback_and_complete_validation(self):
        a={'validated_dispatches':105,'median_iteration_total_ms':94.,'median_cpu_validation_ms':2.3}
        b=dict(a,median_iteration_total_ms=2.9,median_cpu_validation_ms=2.1)
        self.assertGreater(runner.gate_results(a,b,a)['speedup'],30)
        for edit in ({'median_iteration_total_ms':1222.}, {'median_cpu_validation_ms':1200.},
                     {'validated_dispatches':104}, {'median_iteration_total_ms':float('nan')},
                     {'median_cpu_validation_ms':float('nan')}):
            with self.assertRaises(ValueError):runner.gate_results(a,dict(b,**edit),a)
        with self.assertRaises(ValueError):
            runner.gate_results(dict(a,median_iteration_total_ms=float('inf')),b,a)

    def test_report_archive_preserves_nested_manifests_and_omits_build_trees(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'report';output.mkdir()
            for name in ('state.json','installer/SHA256SUMS.json','delivery/qualified.json',
                         'mesa/object.o','build-nvk/object.o','installer/__pycache__/unused.pyc'):
                p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
            runner.package_report(output)
            with zipfile.ZipFile(output.with_suffix('.zip')) as archive:
                self.assertIsNone(archive.testzip())
                manifest=json.loads(archive.read('report/REPORT-SHA256SUMS.json'))
                self.assertEqual(set(manifest),{'state.json','installer/SHA256SUMS.json','delivery/qualified.json'})
                self.assertEqual(set(archive.namelist()),{'report/'+name for name in manifest}|{'report/REPORT-SHA256SUMS.json'})
                for name,digest in manifest.items():
                    self.assertEqual(hashlib.sha256(archive.read('report/'+name)).hexdigest(),digest)

    def test_changed_native_source_stops_before_editing_any_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);kit=root/'kit';kit.mkdir();(kit/'inputs').mkdir()
            source=root/'source';source.mkdir()
            (source/'a.c').write_text('before');(source/'b.c').write_text('unexpected native change')
            expected={n:hashlib.sha256(b'before').hexdigest() for n in ('a.c','b.c')}
            (kit/'inputs/native-source-before.json').write_text(json.dumps(expected))
            with patch.object(common,'HERE',kit):
                with self.assertRaisesRegex(ValueError,'Native source changed: b.c'):
                    common.apply_fixed_sources(source)
            self.assertEqual((source/'a.c').read_text(),'before')

    def test_read_only_cd_inputs_become_private_writable_probe_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);kit=root/'kit';origin=kit/'inputs/probe-source/probe'
            origin.mkdir(parents=True)
            p=origin/'private_runtime.h';p.write_text('old');p.chmod(0o444)
            origin.chmod(0o555)
            try:
                with patch.object(runner,'HERE',kit):runner.copy_probe_source(root/'probe-copy')
                copied=root/'probe-copy/probe/private_runtime.h'
                copied.write_text('qualified candidate identity')
                (copied.parent/'new-source.h').write_text('new')
                self.assertEqual(p.read_text(),'old')
                self.assertEqual(p.stat().st_mode&0o777,0o444)
            finally:
                origin.chmod(0o755);p.chmod(0o644)

    def test_bounds_requires_all_guard_checks(self):
        cases=[{'limit':a,'offset':b,'passed':True,'validated_words':2**21,
                'valid_components':sum(b+i*4+4<=a for i in range(4))}
               for a in (4,8,12,16,20,24,28,32,36,48,64)
               for b in (0,16,32,48,0xffffffe0,0xfffffff0)]
        rows=[{'record':'bounds-result','result':{'passed':True,'dispatches':66,'cases':cases}},
              {'record':'bounds-complete','passed':True,'dispatches':66}]
        runner.validate_bounds(rows)
        for key,value in [('passed',False),('validated_words',0),('valid_components',4),('offset',999)]:
            broken=json.loads(json.dumps(rows));broken[0]['result']['cases'][0][key]=value
            with self.assertRaises(ValueError):runner.validate_bounds(broken)

    def test_macho_validates_real_uuid_dependencies_and_command_bounds(self):
        uuid=struct.pack('<II',0x1b,24)+bytes(range(16))
        name=b'/usr/lib/libSystem.B.dylib\0'
        size=(24+len(name)+7)&~7
        dep=struct.pack('<6I',0xc,size,24,0,0,0)+name+b'\0'*(size-24-len(name))
        header=struct.pack('<8I',0xfeedfacf,0x01000007,3,6,2,len(uuid)+len(dep),0,0)
        good=header+uuid+dep
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'candidate';p.write_bytes(good)
            self.assertEqual(common.macho(p)['uuid'],bytes(range(16)).hex())
            for data in (good[:40],good.replace(b'/usr/lib/',b'/tmp/lib/'),good[:12]+struct.pack('<I',2)+good[16:]):
                p.write_bytes(data)
                with self.assertRaises(ValueError):common.macho(p)

    def test_linux_launchers_refuse_without_mutating_host(self):
        for name in ('Install-Shared-Store-Driver.command','Restore-Shared-Store-Driver.command'):
            result=subprocess.run(['bash',str(KIT/name)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Nothing was changed',result.stderr)

    def test_fixed_source_keeps_original_predicate_and_removes_only_activation(self):
        original=PROJECT/'macos/performance/shared-store-vector-prototype/bounded-vec4-stores.patch'
        source=(KIT/'source/src/compiler/nir/nir_lower_explicit_io.c').read_text()
        self.assertNotIn('VM2_BOUNDED_VEC4_STORES',source)
        self.assertIn('nir_uge_imm(b, limit, 16)',source)
        self.assertIn('nir_uge(b, nir_iadd_imm(b, limit, -16), offset)',source)
        self.assertIn('write_mask == 0xf',source)
        self.assertIn('align_mul >= 16 && align_offset % 16 == 0',source)
        self.assertIn('debug_get_bool_option("VM2_BOUNDED_VEC4_STORES", false)',original.read_text())


if __name__=='__main__':unittest.main()
