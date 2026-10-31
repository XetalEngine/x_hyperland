"""Host-independent checks for first-run hardware and private setup operations."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
import gpu_rom
import portable
import tpm_setup


def rom_image(vendor=0x10de,device=0x2684,uefi=True,last=True):
    image=bytearray(512);image[:2]=b'\x55\xaa';image[24:26]=(32).to_bytes(2,'little')
    image[32:36]=b'PCIR';image[36:38]=vendor.to_bytes(2,'little');image[38:40]=device.to_bytes(2,'little')
    image[48:50]=(1).to_bytes(2,'little');image[52]=3 if uefi else 0;image[53]=128 if last else 0
    return bytes(image)


class RuntimeSetupTests(unittest.TestCase):
    def test_only_untouched_default_snapshots_are_upgraded(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);app=root/'app';(app/'defaults').mkdir(parents=True)
            old={'tools':{'binary':'${KVM_DATA}/old'}};new={'tools':{'binary':str(root/'new')}}
            digest=hashlib.sha256(json.dumps(old,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            (app/'defaults/manifest.json').write_text(json.dumps({'previous_profile_content':{'windows':digest}}))
            path=root/'settings_default.json';path.write_text(json.dumps({'tools':{'binary':str(root/'old')}}))
            with patch.object(portable,'ROOT',app),patch.object(portable,'data_root',return_value=root),patch.object(portable,'configuration',return_value=new):
                portable._refresh_default(path,'windows')
                self.assertEqual(json.loads(path.read_text()),new)
                self.assertTrue(path.with_name(path.name+'.before-device-defaults').exists())
                edited={'tools':{'binary':'/user/chosen/qemu'}};path.write_text(json.dumps(edited))
                portable._refresh_default(path,'windows')
                self.assertEqual(json.loads(path.read_text()),edited)

    def test_defaults_have_no_host_assignments_and_resolve_for_another_user(self):
        with patch.dict(os.environ,{'XETAL_KVM_DATA':'/home/recipient/.local/share/xetal-kvm'}):
            for profile in ('windows','macos'):
                data=portable.configuration(profile)
                self.assertFalse(any(d.get('driver') in ('vfio-pci','usb-host') for d in data['devices']))
                self.assertFalse(any(str(b.get('filename','')).startswith('/dev/') for b in data['blockdevs']))
                self.assertNotIn(str(Path.home()),json.dumps(data['tools']).replace(str(portable.ROOT),'APP'))
                self.assertTrue(data['_meta']['binary'].startswith('/home/recipient/'))
                names={b['node-name'] for b in data['blockdevs']}
                self.assertTrue(all(d.get('drive') in names for d in data['devices'] if d.get('drive')))
                if profile=='macos':self.assertIn('opencore-boot-storage',names)

    def test_rom_chain_validates_and_strips_preheader(self):
        image=rom_image(uefi=False,last=False)+rom_image()
        self.assertEqual(gpu_rom.validated_image(b'preheader'+image,0x10de,0x2684),image)
        for data in (image[:-4],rom_image(device=0x1111),rom_image(uefi=False),b''):
            with self.assertRaises(ValueError):gpu_rom.validated_image(data,0x10de,0x2684)

    def test_rom_read_access_is_disabled_after_failed_read(self):
        rom=Mock();rom.exists.return_value=True
        rom.open.side_effect=OSError('GPU in use')
        cls=Mock();cls.read_text.return_value='0x030000'
        device=Mock();device.__truediv__=Mock(side_effect=lambda key:rom if key=='rom' else cls)
        with patch.object(gpu_rom,'device_path',return_value=device):
            with self.assertRaises(OSError):gpu_rom.read_rom('0000:01:00.0')
        self.assertEqual([call.args[0] for call in rom.write_text.call_args_list],['1','0'])

    def test_bad_pci_addresses_never_reach_sysfs(self):
        for slot in ('../../etc','0000:01:00.0;reboot','01:00.0','0000:01:00.8'):
            with self.assertRaises(ValueError):gpu_rom.device_path(slot)

    def test_tpm_failure_is_retryable_and_existing_keys_are_untouched(self):
        with tempfile.TemporaryDirectory() as name,patch.dict(os.environ,{'XETAL_KVM_DATA':name}):
            root=Path(name);binary=root/'bin/swtpm';binary.parent.mkdir();binary.touch()
            binary.with_name('swtpm_setup').touch();state=root/'tpm-state'
            with self.assertRaises(ValueError):tpm_setup.initialize(root/'..'/'outside',str(binary))
            with patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','failed')):
                with self.assertRaisesRegex(RuntimeError,'retry'):tpm_setup.initialize(state,str(binary))
            self.assertFalse(state.exists())
            self.assertEqual(list(root.glob('.tpm-initialize-*')),[])
            state.mkdir();blob=state/'tpm2-00.permall';blob.write_bytes(b'original guest keys')
            with patch.object(subprocess,'run',side_effect=AssertionError('Must not replace keys')):
                with self.assertRaisesRegex(RuntimeError,'preserved'):tpm_setup.initialize(state,str(binary))
            self.assertEqual(blob.read_bytes(),b'original guest keys')

    def test_kernel_mismatch_stops_before_modinfo_or_module_loader(self):
        import module_tool,packages
        entry={'kernel':'different-kernel','cpu':packages.cpu_vendor()}
        with patch.object(packages,'installed',return_value=entry),patch.object(subprocess,'check_output',side_effect=AssertionError('Must not inspect/load incompatible module')):
            with self.assertRaisesRegex(RuntimeError,'Requires kernel'):module_tool.check(Path('/fixture'))

    def test_tpm_identity_builder_failure_restores_input_files(self):
        import sys
        sys.path.insert(0,str(portable.ROOT/'backend/lib'))
        import tpm_actions
        from tabs_tpm import PRESETS
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)/'builder'
            for rel in ('libtpms/build.sh','swtpm/build.sh','scripts/gen-tpm-vendor-identity-h.sh','scripts/relink-origin.py','libtpms/src/tpm_vendor_identity.h','tpm_real_dump.env'):
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('original')
            saved={p:p.read_bytes() for p in (root/'tpm_real_dump.env',root/'libtpms/src/tpm_vendor_identity.h')}
            with patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
                with self.assertRaisesRegex(RuntimeError,'unchanged'):
                    tpm_actions.build(root,next(iter(PRESETS.values())),Path(name)/'new',lambda text:None)
            self.assertEqual(saved,{p:p.read_bytes() for p in saved})
        bad={**next(iter(PRESETS.values())),'TPM_IDENT_MODEL_JSON_TPM2':'$(touch /tmp/unwanted)'}
        with self.assertRaises(ValueError):tpm_actions.environment_text(bad)

    def test_tpm_host_copy_normalizes_all_public_properties(self):
        import sys
        sys.path.insert(0,str(portable.ROOT/'backend/lib'))
        import tpm_actions
        from tabs_tpm import PRESETS
        expected=next(iter(PRESETS.values()))
        properties={number:int(expected[key],0) for key,number in tpm_actions.PROPERTIES.items()}
        with patch.object(tpm_actions,'read_host',return_value=properties):result=tpm_actions.host_identity()
        for key in tpm_actions.PROPERTIES:self.assertEqual(int(result[key],0),int(expected[key],0))


if __name__=='__main__':unittest.main()
