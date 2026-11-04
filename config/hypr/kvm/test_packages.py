"""Offline regression tests; synthetic payloads, no VMs or host changes."""
from pathlib import Path
import base64
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import packages
import portable


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys=tempfile.TemporaryDirectory(prefix='kvm-test-key-')
        cls.private=Path(cls.keys.name)/'private.pem';cls.public=Path(cls.keys.name)/'public.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(cls.private)],check=True,capture_output=True)
        subprocess.run(['openssl','pkey','-in',str(cls.private),'-pubout','-out',str(cls.public)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.keys.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='kvm-fixture-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def artifact(self,name='ovmf',value='1.0.0',files=None):
        file=self.root/f'XetalKVM-{name}-{value}-linux-x86_64.tar.xz'
        files=files or {'OVMF_CODE.fd':b'fixture code','OVMF_VARS.fd':b'empty variables'}
        with tarfile.open(file,'w:xz') as tar:
            for path,data in files.items():
                info=tarfile.TarInfo(path);info.size=len(data);info.mode=0o644
                tar.addfile(info,io.BytesIO(data))
        return file,dict(version=value,file=file.name,size=file.stat().st_size,unpacked_size=sum(map(len,files.values())),sha256=packages.digest(file),label=name)

    def envelope(self,entry,value='1.0.0'):
        release=dict(schema=1,app='kvm',architecture='x86_64',version=value,notes='Fixture',components={'ovmf':entry})
        payload=json.dumps(release).encode()
        sig=subprocess.run(['openssl','dgst','-sha256','-sign',str(self.private)],input=payload,check=True,capture_output=True).stdout
        return json.dumps(dict(payload=base64.b64encode(payload).decode(),signature=base64.b64encode(sig).decode())).encode()

    def test_valid_signature_and_tampering(self):
        _,entry=self.artifact();raw=self.envelope(entry)
        self.assertEqual(packages.decode(raw,self.public)['version'],'1.0.0')
        bad=json.loads(raw);bad['payload']=base64.b64encode(b'{}').decode()
        with self.assertRaises(ValueError):packages.decode(json.dumps(bad).encode(),self.public)

    def test_install_is_atomic_preserves_previous_and_nvram(self):
        file,entry=self.artifact();root=self.root/'data';components=root/'editions/stock'
        self.assertTrue(packages.install_archive('ovmf',entry,file,components))
        old=(components/'components/ovmf/current').resolve()
        with patch.dict(os.environ,{'XETAL_KVM_DATA':str(root)}):
            portable.prepare_firmware()
            nvram=root/'firmware/OVMF_VARS.fd';nvram.write_bytes(b'my VM variables')
            new,new_entry=self.artifact(value='1.0.1',files={'OVMF_CODE.fd':b'new code','OVMF_VARS.fd':b'new template'})
            self.assertTrue(packages.install_archive('ovmf',new_entry,new,components))
            portable.prepare_firmware()
            self.assertEqual(nvram.read_bytes(),b'my VM variables')
        self.assertTrue(old.is_dir())
        self.assertFalse(packages.install_archive('ovmf',new_entry,new,components))
        with self.assertRaisesRegex(ValueError,'downgrade'):packages.install_archive('ovmf',entry,file,components)

    def test_corrupt_archive_leaves_current_untouched(self):
        file,entry=self.artifact();root=self.root/'data';packages.install_archive('ovmf',entry,file,root)
        old=(root/'components/ovmf/current').resolve()
        new,a=self.artifact(value='1.0.1');new.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):packages.install_archive('ovmf',a,new,root)
        self.assertEqual((root/'components/ovmf/current').resolve(),old)

    def test_archive_traversal_and_links_are_rejected(self):
        for name in ('../escape','/absolute','a/../../escape','.component.json','a\\escape'):
            file,entry=self.artifact(files={name:b'bad'})
            with self.assertRaises(ValueError):packages.install_archive('ovmf',entry,file,self.root/'data')
        link=self.root/'link.tar.xz'
        with tarfile.open(link,'w:xz') as tar:
            info=tarfile.TarInfo('link');info.type=tarfile.SYMTYPE;info.linkname='/tmp';tar.addfile(info)
        with tarfile.open(link) as tar:
            with self.assertRaises(ValueError):packages.safe_members(tar,1)

    def test_abi_and_cpu_are_independent_gates(self):
        entry={'kernel':'7.2.11-arch1-1','cpu':'amd'}
        self.assertEqual(packages.compatibility('kvm-amd',entry,kernel=entry['kernel'],cpu='amd',arch='x86_64'),'')
        self.assertIn('AMD',packages.compatibility('kvm-amd',entry,kernel=entry['kernel'],cpu='intel',arch='x86_64'))
        self.assertIn('kernel',packages.compatibility('kvm-amd',entry,kernel='other',cpu='amd',arch='x86_64'))

    def test_update_notice_requires_newer_installed_component(self):
        current={'version':'1.0.9','sha256':'a'*64}
        entry={'version':'1.0.10','sha256':'b'*64,'cpu':'amd','kernel':'fixture-kernel'}
        with patch.object(packages.platform,'machine',return_value='x86_64'), \
             patch.object(packages.platform,'release',return_value='fixture-kernel'), \
             patch.object(packages,'cpu_vendor',return_value='amd'):
            for name in packages.IDS:
                with self.subTest(component=name):
                    self.assertTrue(packages.update_available(name,entry,current))
                    for installed in ({}, entry, dict(current,version='2.0.0'),
                                      dict(current,version=entry['version']),
                                      dict(current,sha256=entry['sha256'])):
                        self.assertFalse(packages.update_available(name,entry,installed))

    def test_update_notice_ignores_incompatible_module(self):
        current={'version':'1.0.0','sha256':'a'*64}
        entry={'version':'1.0.1','sha256':'b'*64,'cpu':'amd','kernel':'fixture-kernel'}
        with patch.object(packages.platform,'machine',return_value='x86_64'):
            with patch.object(packages,'cpu_vendor',return_value='intel'):
                self.assertFalse(packages.update_available('kvm-amd',entry,current))
            with patch.object(packages,'cpu_vendor',return_value='amd'), \
                 patch.object(packages.platform,'release',return_value='other-kernel'):
                self.assertFalse(packages.update_available('kvm-amd',entry,current))
        with patch.object(packages.platform,'machine',return_value='aarch64'):
            self.assertFalse(packages.update_available('qemu',entry,current))

    def test_captured_profiles_are_relocatable_and_assets_are_private_copies(self):
        import sys
        import shutil
        sys.path.insert(0,str(portable.ROOT/'backend/lib'))
        shutil.copytree(portable.ROOT/'defaults',self.root/'profile/kvm/defaults')
        with patch.dict(os.environ,{'XETAL_KVM_DATA':str(self.root/'new-user')}), patch.object(portable,'ROOT',self.root/'profile/kvm'):
            portable.prepare()
            for profile in ('windows','macos'):
                cfg=portable.configuration(profile);text=json.dumps(cfg)
                self.assertNotIn(str(Path.home()),text)
                self.assertNotIn('a_xetal_engine',text)
                self.assertFalse(cfg['wizard']['complete'])
                self.assertEqual(cfg['smp']['vcpus'],'16')
                self.assertFalse(any(d['driver'] in ('vfio-pci','usb-host') for d in cfg['devices']))
                self.assertFalse(cfg['tools']['kvm_build_enabled'])
                self.assertTrue(all('${' not in str(value) for value in cfg.values()))
            bios=portable.data_root()/'smbios/smbios.bin'
            self.assertFalse(bios.exists(), 'First run must not install bundled binary assets')
            asset,entry=self.artifact(name='baseline',files={'assets/smbios/smbios.bin':b'baseline',
                'assets/acpi/dsdt.aml':b'table', 'assets/firmware/OVMF_VARS.fd':b'variables'})
            import editions
            packages.install_archive('baseline',entry,asset,editions.component_root())
            portable.prepare_firmware()
            self.assertEqual(bios.read_bytes(),b'baseline')
            self.assertEqual((portable.data_root()/'acpi/dsdt.aml').read_bytes(),b'table')
            bios.write_bytes(b'personal edit');portable.prepare()
            self.assertEqual(bios.read_bytes(),b'personal edit')

    def test_source_inventory_is_rejected_even_when_validly_signed(self):
        _,entry=self.artifact()
        release=packages.decode(self.envelope(entry),self.public)
        _,source=self.artifact(name='sources-qemu')
        release['components']['sources-qemu']=source
        payload=json.dumps(release).encode()
        sig=subprocess.run(['openssl','dgst','-sha256','-sign',str(self.private)],input=payload,check=True,capture_output=True).stdout
        raw=json.dumps(dict(payload=base64.b64encode(payload).decode(),signature=base64.b64encode(sig).decode())).encode()
        with self.assertRaisesRegex(ValueError,'inventory'):packages.decode(raw,self.public)
        self.assertEqual(set(packages.decode(raw,self.public,local_legacy=True)['components']),{'ovmf'})


if __name__=='__main__':unittest.main()
