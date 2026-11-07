"""Exercise hardware selection without touching the running PC's modules."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'installer/portable_graphics'
spec=importlib.util.spec_from_file_location('graphics_support',SOURCE/'support.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)


class PortableGraphicsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.sys=self.root/'pci';self.sys.mkdir()
        self.config=self.root/'config';self.config.mkdir()
        self.run=self.root/'run'
        (self.config/'nvidia-supported.txt').write_text('0x2684\n0x2b85\n')
        (self.config/'nouveau-enabled').touch()

    def device(self,slot,vendor,device,cls='0x030000'):
        path=self.sys/slot;path.mkdir()
        for key,value in dict(vendor=vendor,device=device,**{'class':cls}).items():
            (path/key).write_text(value+'\n')

    def select(self):
        result=subprocess.run(['sh',str(SOURCE/'policy.sh'),str(self.sys),str(self.config),str(self.run)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return (self.run/'hyperfusion-gpu-selection').read_text().strip(),(self.run/'modprobe.d/nvidia-utils.conf').read_text()

    def test_virtual_amd_and_intel_leave_nvidia_available(self):
        for slot,vendor in enumerate(('0x1af4','0x1002','0x8086')):self.device(str(slot),vendor,'0x1234')
        mode,config=self.select()
        self.assertEqual(mode,'nvidia');self.assertIn('blacklist nouveau\n',config)
        self.assertNotIn('blacklist amdgpu',config);self.assertNotIn('blacklist i915',config)

    def test_rtx_and_hybrid_load_current_driver(self):
        self.device('0','0x10de','0x2684');self.device('1','0x8086','0x1234')
        self.assertEqual(self.select()[0],'nvidia')

    def test_legacy_or_mixed_nvidia_switches_all_nvidia_to_nouveau(self):
        self.device('0','0x10de','0x1b80');self.device('1','0x10de','0x2684')
        mode,config=self.select()
        self.assertEqual(mode,'nouveau');self.assertNotIn('blacklist nouveau\n',config)
        for module in ('nvidia','nvidia_modeset','nvidia_uvm','nvidia_drm'):
            self.assertIn('blacklist '+module+'\n',config)
        self.assertNotIn('softdep nvidia',config)

    def test_audio_and_usb_functions_do_not_misidentify_modern_gpu(self):
        self.device('0','0x10de','0x2684')
        self.device('1','0x10de','0x9999','0x040300');self.device('2','0x10de','0x9998','0x0c0330')
        self.assertEqual(self.select()[0],'nvidia')

    def test_explicitly_unselected_nouveau_is_not_enabled(self):
        (self.config/'nouveau-enabled').unlink();self.device('0','0x10de','0x1b80')
        self.assertEqual(self.select()[0],'nvidia')

    def test_moving_a_disk_replaces_previous_selection(self):
        self.device('0','0x10de','0x1b80');self.assertEqual(self.select()[0],'nouveau')
        (self.sys/'0/device').write_text('0x2684\n')
        self.assertEqual(self.select()[0],'nvidia')
        self.assertFalse(list((self.run/'modprobe.d').glob('.hyperfusion-*')))

    def test_support_table_only_accepts_current_device_section(self):
        html='<h3>Current NVIDIA GPUs</h3><tbody><tr id="devid2684"><tr id="devid2B85_1"></tbody><h3>Legacy</h3><tr id="devid1B80">'
        self.assertEqual(support.device_ids(html),['0x2684','0x2b85'])
        for html in ('unrecognized','<h3>Current NVIDIA GPUs</h3><tbody></tbody>'):
            with self.assertRaises(ValueError):support.device_ids(html)


if __name__=='__main__':unittest.main()
