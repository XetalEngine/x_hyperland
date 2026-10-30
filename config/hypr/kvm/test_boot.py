"""Boot editing tests use only temporary files and a synthetic generator."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parent/'backend/lib'))
import iommu_edit


class BootTests(unittest.TestCase):
    def test_failure_restores_both_files_and_success_quotes_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'defaults';boot=root/'grub.cfg'
            original=b'GRUB_TIMEOUT=5\nGRUB_CMDLINE_LINUX_DEFAULT="quiet"\n'
            config.write_bytes(original);config.chmod(0o640);boot.write_bytes(b'working menu')
            expected=hashlib.sha256(original).hexdigest()
            fail=[sys.executable,'-c',f'from pathlib import Path;Path({str(boot)!r}).write_text("broken menu");raise SystemExit(1)']
            with self.assertRaises(Exception):iommu_edit.apply(config,boot,expected,'quiet amd_iommu=on iommu=pt',fail)
            self.assertEqual(config.read_bytes(),original);self.assertEqual(boot.read_bytes(),b'working menu')
            self.assertEqual(config.stat().st_mode&0o777,0o640)
            cmdline='quiet intel_iommu=on iommu=pt param="hello world" literal=$(false)'
            iommu_edit.apply(config,boot,expected,cmdline,[sys.executable,'-c','pass'])
            self.assertIn("GRUB_CMDLINE_LINUX_DEFAULT='"+cmdline+"'",config.read_text())

    def test_changed_preview_and_symlink_do_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'defaults';boot=root/'grub.cfg'
            config.write_text('unchanged');boot.write_text('working')
            with self.assertRaisesRegex(ValueError,'changed'):
                iommu_edit.apply(config,boot,'0'*64,'new',[])
            link=root/'link';link.symlink_to(config)
            with self.assertRaisesRegex(ValueError,'symlink'):
                iommu_edit.apply(link,boot,'0'*64,'new',[])
            self.assertEqual(config.read_text(),'unchanged');self.assertEqual(boot.read_text(),'working')


if __name__=='__main__':unittest.main()
