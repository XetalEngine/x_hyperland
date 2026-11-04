"""ELF metadata and syscall contract tests; never loads a kernel module."""
import ctypes
import errno
import os
import struct
import unittest
from unittest.mock import Mock, patch
import module_image


def elf(vermagic=b'fixture-kernel SMP'):
    names=b'\0.shstrtab\0.modinfo\0'
    info=b'license=GPL\0vermagic='+vermagic+b'\0'
    header=bytearray(64)
    header[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HH',header,16,1,62)
    struct.pack_into('<Q',header,40,64)
    struct.pack_into('<HHH',header,58,64,3,1)
    sections=bytearray(3*64)
    struct.pack_into('<IIQQQQIIQQ',sections,64,1,3,0,0,256,len(names),0,0,1,0)
    struct.pack_into('<IIQQQQIIQQ',sections,128,11,1,0,0,256+len(names),len(info),0,0,1,0)
    return header+sections+names+info


class ModuleImageTests(unittest.TestCase):
    def descriptor(self, data):
        fd=os.memfd_create('module-test',os.MFD_CLOEXEC)
        self.addCleanup(os.close,fd)
        os.write(fd,data)
        return fd

    def test_reads_real_elf_section_layout_without_modinfo(self):
        fd=self.descriptor(elf())
        self.assertEqual(module_image.vermagic(fd),'fixture-kernel SMP')

    def test_rejects_truncation_wrong_arch_and_invalid_section_bounds(self):
        wrong_arch=elf();struct.pack_into('<H',wrong_arch,18,183)
        bad_bounds=elf();struct.pack_into('<Q',bad_bounds,40,2**63)
        bad_names=elf();struct.pack_into('<I',bad_names,128,9000)
        for data in (b'',elf()[:63],elf()[:-1],wrong_arch,bad_bounds,bad_names,elf(b''),elf(b'\0vermagic=other')):
            with self.subTest(size=len(data)),self.assertRaises(ValueError):
                module_image.vermagic(self.descriptor(data))

    def test_finit_module_uses_descriptor_and_preserves_kernel_checks(self):
        fd=self.descriptor(elf())
        libc=Mock();libc.syscall.return_value=0
        with patch.object(module_image.os,'geteuid',return_value=0), \
             patch.object(module_image.platform,'machine',return_value='x86_64'), \
             patch.object(module_image.platform,'release',return_value='fixture-kernel'), \
             patch.object(module_image.ctypes,'CDLL',return_value=libc):
            module_image.load(fd,['avic=0','ignore_msrs=0'])
            args=libc.syscall.call_args.args
            self.assertEqual([v.value for v in args],[313,fd,b'avic=0 ignore_msrs=0',0])
            libc.syscall.return_value=-1
            with patch.object(module_image.ctypes,'get_errno',return_value=errno.EKEYREJECTED),self.assertRaises(OSError) as raised:
                module_image.load(fd,[])
            self.assertEqual(raised.exception.errno,errno.EKEYREJECTED)

    def test_mismatched_abi_and_parameters_stop_before_syscall(self):
        fd=self.descriptor(elf())
        with patch.object(module_image.os,'geteuid',return_value=0), \
             patch.object(module_image.platform,'machine',return_value='x86_64'), \
             patch.object(module_image.platform,'release',return_value='different-kernel'), \
             patch.object(module_image.ctypes,'CDLL') as library:
            with self.assertRaisesRegex(RuntimeError,'ABI'):module_image.load(fd,[])
            library.assert_not_called()
        with patch.object(module_image.os,'geteuid',return_value=0), \
             patch.object(module_image.platform,'machine',return_value='x86_64'), \
             patch.object(module_image.platform,'release',return_value='fixture-kernel'), \
             patch.object(module_image.ctypes,'CDLL') as library:
            with self.assertRaises(ValueError):module_image.load(fd,['avic=1 other=1'])
            library.assert_not_called()


if __name__=='__main__':unittest.main()
