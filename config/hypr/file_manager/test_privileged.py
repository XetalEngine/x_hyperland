import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import unquote

spec = importlib.util.spec_from_file_location('fusion_privileged', Path(__file__).with_name('privileged.py'))
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)


class ProtectedRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fusion-protected-removal-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root/'home'; self.home.mkdir()
        self.account = SimpleNamespace(pw_dir=str(self.home), pw_uid=os.getuid(), pw_gid=os.getgid())
        self.data = self.home/'.local/share'

    def request(self, path, operation='trash'):
        info = path.lstat()
        return dict(operation=operation, dataHome=str(self.data), items=[dict(path=str(path), dev=str(info.st_dev), ino=str(info.st_ino))])

    def test_trash_keeps_data_metadata_and_original_permissions(self):
        file = self.home/'private # %.txt'; file.write_bytes(b'protected contents'); file.chmod(0o400)
        result = helper.perform(self.request(file), self.account)
        self.assertTrue(result['ok'], result)
        self.assertFalse(file.exists())
        trashed = Path(result['completed'][0]['trash'])
        self.assertEqual(trashed.read_bytes(), b'protected contents')
        self.assertEqual(stat.S_IMODE(trashed.stat().st_mode), 0o400)
        info = self.data/'Trash/info'/(trashed.name+'.trashinfo')
        self.assertIn('Path='+str(file), unquote(info.read_text()))
        self.assertEqual(info.stat().st_uid, os.getuid())
        self.assertEqual(stat.S_IMODE(info.stat().st_mode), 0o600)

    def test_existing_readable_trash_is_secured_and_operation_completes(self):
        folders = [self.data/'Trash', self.data/'Trash/files', self.data/'Trash/info']
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True); folder.chmod(0o755)
        file = self.home/'protected'; file.write_text('keep contents'); file.chmod(0o400)
        result = helper.perform(self.request(file), self.account)
        self.assertTrue(result['ok'], result)
        trashed = Path(result['completed'][0]['trash'])
        self.assertEqual(trashed.read_text(), 'keep contents')
        self.assertFalse(file.exists())
        for folder in folders:
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
            folder.chmod(0o755)
        result = helper.perform(self.request(trashed, 'restore'), self.account)
        self.assertTrue(result['ok'], result)
        self.assertEqual(file.read_text(), 'keep contents')

    def test_foreign_trash_is_not_chmodded_or_used(self):
        folder = self.data/'Trash'; folder.mkdir(parents=True); folder.chmod(0o755)
        fd = os.open(folder, helper.OPEN_DIR)
        try:
            with self.assertRaises(ValueError):helper.secure_trash_directory(fd, os.getuid()+1)
        finally:os.close(fd)
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o755)

    def test_directory_trash_and_delete_do_not_follow_symlinks(self):
        outside = self.root/'keep.txt'; outside.write_text('keep')
        directory = self.home/'folder'; directory.mkdir()
        (directory/'link').symlink_to(outside)
        (directory/'content').write_text('data')
        result = helper.perform(self.request(directory), self.account)
        self.assertTrue(result['ok'], result)
        trashed = Path(result['completed'][0]['trash'])
        result = helper.perform(self.request(trashed, 'delete'), self.account)
        self.assertTrue(result['ok'], result)
        self.assertEqual(outside.read_text(), 'keep')
        self.assertFalse(trashed.exists())

    def test_replaced_item_is_never_deleted(self):
        file = self.home/'selected'; file.write_text('old')
        request = self.request(file, 'delete')
        file.rename(self.home/'old'); file.write_text('replacement')
        result = helper.perform(request, self.account)
        self.assertFalse(result['ok'])
        self.assertEqual(file.read_text(), 'replacement')

    def test_parent_symlink_and_private_trash_symlink_are_rejected(self):
        real = self.home/'real'; real.mkdir()
        (real/'keep').write_text('keep')
        linked = self.home/'linked'; linked.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):helper.perform(self.request(linked/'keep', 'delete'), self.account)
        self.data.mkdir(parents=True)
        (self.data/'Trash').symlink_to(real, target_is_directory=True)
        result = helper.perform(self.request(real/'keep'), self.account)
        self.assertFalse(result['ok'])
        self.assertEqual((real/'keep').read_text(), 'keep')

    def test_nested_mount_and_home_root_are_rejected(self):
        folder = self.home/'folder'; folder.mkdir()
        nested = folder/'mounted'; nested.mkdir()
        (nested/'keep').write_text('keep')
        with patch.object(helper, 'mount_points', return_value={b'/':b'ext4', os.fsencode(nested):b'ext4'}):
            result = helper.perform(self.request(folder, 'delete'), self.account)
        self.assertFalse(result['ok'])
        self.assertTrue((nested/'keep').exists())
        with self.assertRaises(ValueError):helper.perform(self.request(self.home, 'delete'), self.account)

    def test_trash_failure_never_falls_back_to_deletion(self):
        file = self.home/'keep'; file.write_text('keep')
        with patch.object(helper, 'rename_noreplace', side_effect=PermissionError('read-only fixture')):
            result = helper.perform(self.request(file), self.account)
        self.assertFalse(result['ok'])
        self.assertEqual(file.read_text(), 'keep')
        self.assertEqual(list((self.data/'Trash/info').iterdir()), [])

    def test_restore_preserves_original_name_and_refuses_overwrite(self):
        file = self.home/'return # %.txt'; file.write_text('original')
        result = helper.perform(self.request(file), self.account)
        trashed = Path(result['completed'][0]['trash'])
        file.write_text('new file')
        result = helper.perform(self.request(trashed, 'restore'), self.account)
        self.assertFalse(result['ok'])
        self.assertEqual(file.read_text(), 'new file')
        self.assertEqual(trashed.read_text(), 'original')
        file.unlink()
        result = helper.perform(self.request(trashed, 'restore'), self.account)
        self.assertTrue(result['ok'], result)
        self.assertEqual(file.read_text(), 'original')
        self.assertFalse(trashed.exists())
        self.assertFalse((self.data/'Trash/info'/(trashed.name+'.trashinfo')).exists())

    def test_permanent_removal_from_trash_cleans_only_its_record(self):
        file = self.home/'delete.txt'; file.write_text('fixture')
        result = helper.perform(self.request(file), self.account)
        trashed = Path(result['completed'][0]['trash'])
        request = self.request(trashed, 'delete'); request['items'][0]['fromTrash'] = True
        result = helper.perform(request, self.account)
        self.assertTrue(result['ok'], result)
        self.assertFalse((self.data/'Trash/info'/(trashed.name+'.trashinfo')).exists())


if __name__ == '__main__':unittest.main()
