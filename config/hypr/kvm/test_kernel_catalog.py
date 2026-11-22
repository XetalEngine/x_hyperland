"""Multi-kernel catalogue and install isolation, using inert fixture archives."""
import copy
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import packages
import portable

OLD='7.2.11-arch1-1'
NEW='7.3.5-arch1-1'


def entry(kernel, *, legacy=False, version='1.0.0'):
    return dict(kernel=kernel,cpu='amd',version=version,label='Module '+kernel,
                file=f'XetalKVM-kvm-amd{("-"+kernel) if not legacy else ""}-{version}-linux-x86_64.tar.xz',
                size=32,unpacked_size=64,sha256=('a' if legacy else 'b')*64,
                runtime=dict(edition='xetallic',component='kvm-amd',key_id=('c' if legacy else 'd')*64,
                             files={name:dict(file=name+'.xvm',size=8,sha256='e'*64) for name in ('kvm.ko','kvm-amd.ko')}))


def catalog():
    old=entry(OLD,legacy=True,version='1.0.3')
    return dict(schema=1,app='kvm',edition='xetallic',architecture='x86_64',version='1.0.10',notes='Fixture',
                components={'kvm-amd':old},kernel_modules={OLD:copy.deepcopy(old),NEW:entry(NEW)})


class CatalogTests(unittest.TestCase):
    def test_exact_match_and_newest_fallback_leave_signed_data_unchanged(self):
        release=catalog();original=copy.deepcopy(release)
        packages.validate(release)
        for kernel,expected in ((OLD,OLD),(NEW,NEW),('unknown-kernel',NEW)):
            self.assertEqual(packages.component_entries(release,kernel)['kvm-amd']['kernel'],expected)
        self.assertEqual(release,original)
        self.assertEqual(len(packages.artifacts(release)),2)

    def test_numeric_order_and_legacy_feed(self):
        self.assertEqual(sorted([NEW,OLD,'7.3.15-arch1-1'],key=packages.kernel_order,reverse=True),
                         ['7.3.15-arch1-1',NEW,OLD])
        release=catalog();del release['kernel_modules']
        packages.validate(release)
        self.assertEqual(list(packages.kernel_entries(release)),[OLD])

    def test_reject_invalid_variant_including_cpu_key_and_filename(self):
        for change in ({'kernel':OLD},{'cpu':'intel'},{'file':'../module.tar.xz'},
                       {'runtime':None},{'size':-1},{'sha256':'invalid'}):
            with self.subTest(change=change):
                release=catalog();release['kernel_modules'][NEW].update(change)
                with self.assertRaises(ValueError):packages.validate(release)
        release=catalog();release['kernel_modules'][OLD]['version']='1.0.4'
        with self.assertRaises(ValueError):packages.validate(release)
        release=catalog();release['edition']='stock';release['app']='kvm-stock'
        with self.assertRaises(ValueError):packages.validate(release)

    def test_signed_inventory_limit_and_paths(self):
        release=catalog();release['kernel_modules']['../escape']=release['kernel_modules'].pop(NEW)
        with self.assertRaises(ValueError):packages.validate(release)
        with self.assertRaises(ValueError):packages.component_path('kvm-amd',Path('/tmp'),kernel='../escape')


class InstallTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        for target,value in ((packages,'amd'),):
            mock=patch.object(target,'cpu_vendor',return_value=value);mock.start();self.addCleanup(mock.stop)
        mock=patch.object(packages.platform,'machine',return_value='x86_64');mock.start();self.addCleanup(mock.stop)

    def archive(self,kernel,value='1.0.0'):
        data={'.vm-runtime.json':b'', 'kvm.ko.xvm':b'inert encrypted fixture',
              'kvm-amd.ko.xvm':b'inert encrypted second fixture','load-kvm.sh':b'# inert; never execute'}
        e=entry(kernel,version=value)
        for name in e['runtime']['files']:
            import hashlib
            e['runtime']['files'][name]['sha256']=hashlib.sha256(data[name+'.xvm']).hexdigest()
        data['.vm-runtime.json']=json.dumps(e['runtime']).encode()
        archive=self.root/e['file']
        with tarfile.open(archive,'w:xz') as tar:
            for name,body in data.items():
                member=tarfile.TarInfo(name);member.size=len(body);tar.addfile(member,io.BytesIO(body))
        e.update(size=archive.stat().st_size,unpacked_size=sum(map(len,data.values())),sha256=packages.digest(archive))
        return archive,e

    def install(self,kernel,value='1.0.0'):
        archive,e=self.archive(kernel,value)
        with patch.object(packages.platform,'release',return_value=kernel):
            packages.install_archive('kvm-amd',e,archive,self.root)
        return e

    def test_new_kernel_has_independent_version_and_keeps_old_bytes(self):
        old=self.install(OLD,'1.0.3');old_path=packages.component_path('kvm-amd',self.root,kernel=OLD)
        before={p.name:p.read_bytes() for p in old_path.iterdir()}
        new=self.install(NEW,'1.0.0')
        self.assertEqual(packages.installed('kvm-amd',self.root,kernel=OLD),old)
        self.assertEqual(packages.installed('kvm-amd',self.root,kernel=NEW),new)
        self.assertEqual(before,{p.name:p.read_bytes() for p in old_path.iterdir()})
        archive,e=self.archive(OLD,'1.0.2')
        with patch.object(packages.platform,'release',return_value=OLD):
            with self.assertRaisesRegex(ValueError,'downgrade'):packages.install_archive('kvm-amd',e,archive,self.root)

    def test_legacy_install_is_reused_and_preserved(self):
        archive,e=self.archive(OLD,'1.0.3')
        legacy=self.root/'components/kvm-amd/current';legacy.mkdir(parents=True)
        with tarfile.open(archive) as tar:tar.extractall(legacy,filter='data')
        packages.atomic_json(legacy/'.component.json',e)
        with patch.object(packages.platform,'release',return_value=OLD):
            self.assertFalse(packages.install_archive('kvm-amd',e,archive,self.root))
        self.assertEqual(packages.component_path('kvm-amd',self.root,kernel=OLD),legacy)
        self.assertEqual(packages.installed('kvm-amd',self.root,kernel=NEW),{})
        self.install(NEW)
        self.assertEqual(packages.read_json(legacy/'.component.json'),e)

    def test_wrong_kernel_rejected_without_changing_install(self):
        archive,e=self.archive(NEW)
        with patch.object(packages.platform,'release',return_value=OLD):
            with self.assertRaisesRegex(ValueError,'Requires kernel'):packages.install_archive('kvm-amd',e,archive,self.root)
        self.assertFalse((self.root/'components').exists())

    def test_runtime_path_follows_running_kernel(self):
        for value in (OLD,NEW):self.install(value)
        with patch('editions.component_root',return_value=self.root):
            for value in (OLD,NEW):
                with patch.object(packages.platform,'release',return_value=value):
                    self.assertEqual(portable.component_path('kvm-amd'),self.root/'components/kvm-amd/kernels'/value/'current')


if __name__=='__main__':unittest.main()
