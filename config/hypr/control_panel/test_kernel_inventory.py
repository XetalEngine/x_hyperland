import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import kernel_inventory as kernels


def description(**values):
    return '\n\n'.join('%'+name+'%\n'+'\n'.join(value if isinstance(value,list) else [value]) for name,value in values.items())+'\n'


class KernelTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.db=self.root/'var/lib/pacman'
        self.pkg('linux','7.2.14-1',['usr/lib/modules/7.2.14-arch1-1/pkgbase','usr/lib/modules/7.2.14-arch1-1/vmlinuz'])
        self.pkg('linux-headers','7.2.14-1',[])

    def pkg(self,name,version,files):
        folder=self.db/'local'/(name+'-'+version);folder.mkdir(parents=True)
        (folder/'desc').write_text(description(NAME=name,VERSION=version))
        (folder/'files').write_text(description(FILES=files))

    def modules(self,release,base='linux'):
        directory=self.root/'usr/lib/modules'/release;directory.mkdir(parents=True)
        (directory/'pkgbase').write_text(base);(directory/'vmlinuz').touch()
        return directory

    def test_running_kernel_is_detected_without_readable_boot_partition(self):
        self.modules('7.2.14-arch1-1')
        rows=kernels.inventory(self.root,'7.2.14-arch1-1',self.db)['kernels']
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['running']);self.assertTrue(rows[0]['installed'])
        self.assertEqual(rows[0]['package'],'linux');self.assertTrue(rows[0]['headers'])

    def test_running_old_kernel_remains_visible_after_upgrade(self):
        self.modules('7.2.14-arch1-1')
        rows=kernels.inventory(self.root,'7.2.11-arch1-1',self.db)['kernels']
        self.assertTrue(rows[0]['running']);self.assertFalse(rows[0]['installed'])
        self.assertEqual(rows[1]['release'],'7.2.14-arch1-1');self.assertFalse(rows[1]['running'])

    def test_package_file_owner_wins_over_pkgbase_and_headers_only_is_ignored(self):
        self.pkg('linux-custom-pds','7.2.14-1',['usr/lib/modules/7.2.14-custom/pkgbase'])
        self.modules('7.2.14-custom','linux-custom')
        (self.root/'usr/lib/modules/6.12-headers-only/build').mkdir(parents=True)
        rows=kernels.inventory(self.root,'7.2.14-custom',self.db)['kernels']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['package'],'linux-custom-pds')

    def test_uki_and_modules_merge_by_release(self):
        self.modules('7.2.14-arch1-1')
        image=self.root/'efi/EFI/Linux/arch-linux.efi';image.parent.mkdir(parents=True);image.touch()
        with patch.object(kernels,'image_release',return_value='7.2.14-arch1-1'):
            rows=kernels.inventory(self.root,'7.2.14-arch1-1',self.db)['kernels']
        self.assertEqual(len(rows),1);self.assertIn('/efi/EFI/Linux/arch-linux.efi',rows[0]['images'])

    def repo(self,name,records):
        directory=self.db/'sync';directory.mkdir(exist_ok=True)
        with tarfile.open(directory/(name+'.db'),'w:gz') as archive:
            for record in records:
                data=description(**record).encode();member=tarfile.TarInfo(record['NAME']+'/desc');member.size=len(data)
                archive.addfile(member,io.BytesIO(data))

    def test_catalog_uses_all_configured_repositories_without_headers_or_driver_packages(self):
        self.repo('core',[dict(NAME='linux',VERSION='7.2.14-1',DESC='The Linux kernel and modules'),
                          dict(NAME='linux-headers',VERSION='7.2.14-1',DESC='Headers for the Linux kernel')])
        self.repo('cachyos',[dict(NAME='linux-cachyos-bore',BASE='linux-cachyos-bore',VERSION='7.2-1',DESC='Linux BORE kernel and modules'),
                             dict(NAME='linux-cachyos-bore-r8125',BASE='linux-cachyos-bore',VERSION='7.2-1',DESC='r8125 modules for the Linux kernel')])
        self.repo('manjaro',[dict(NAME='linux70',VERSION='7.0-1',DESC='The Linux70 kernel and modules')])
        self.repo('disabled-testing',[dict(NAME='linux-rc',VERSION='8.0-1',DESC='Linux kernel and modules')])
        data=kernels.catalog(self.db,['core','cachyos','manjaro','missing'])
        self.assertEqual([r['package'] for r in data['kernels']],['linux','linux-cachyos-bore','linux70'])
        self.assertEqual(data['kernels'][0]['headers'],'linux-headers')
        self.assertEqual(data['kernels'][0]['installed'],'7.2.14-1')
        self.assertEqual(data['missing_repositories'],['missing'])


if __name__=='__main__':unittest.main()
