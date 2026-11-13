"""No test in this module writes a block device or requests authentication."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ventoy', REPO / 'config/hypr/control_panel/ventoy.py')
ventoy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ventoy)


def disk(existing=False):
    node = {'path': '/dev/sdz', 'type': 'disk', 'size': 32 * 1024**3, 'tran': 'usb', 'ro': False,
            'log-sec': 512, 'model': 'Test USB', 'serial': 'FIXTURE', 'wwn': '', 'maj:min': '65:144',
            'diskseq': '7', 'sys_path': '/sys/devices/usb-test/block/sdz', 'holders': [], 'mountpoints': [],
            'children': []}
    if existing:
        node['children'] = [
            {'path': '/dev/sdz1', 'type': 'part', 'partn': 1, 'start': 2048, 'maj:min': '65:145', 'size': 31 * 1024**3,
             'label': 'Ventoy', 'fstype': 'exfat', 'uuid': '1111-2222', 'mountpoints': [], 'holders': []},
            {'path': '/dev/sdz2', 'type': 'part', 'partn': 2, 'maj:min': '65:146', 'size': 33554432,
             'label': 'VTOYEFI', 'fstype': 'vfat', 'mountpoints': [], 'holders': []}]
    return signed(node)


def signed(node):
    node['identity'] = ventoy.identity(node)
    node['layout'] = ventoy.layout_identity(node)
    node['ventoy'] = bool(ventoy.ventoy_partitions(node))
    node['blocked'] = ventoy.blocked_reason(node, set())
    return node


def request(node):
    return {**node, 'erase_confirmed': node['path'], 'style': 'mbr', 'secure_boot': True}


class DiskBoundaryTests(unittest.TestCase):
    def test_usb_ssd_does_not_need_removable_bit(self):
        node = disk(); node['rm'] = False
        self.assertEqual(ventoy.blocked_reason(node, set()), '')

    def test_internal_partition_readonly_and_4kn_disks_rejected(self):
        for change in ({'tran': 'sata'}, {'tran': 'nvme'}, {'type': 'part'}, {'path': '/dev/sdz1'},
                       {'path': '/dev/sdz;touch bad'}, {'ro': True}, {'log-sec': 4096}, {'diskseq': ''}, {'size': 0}):
            with self.subTest(change=change):
                node = {**disk(), **change}
                self.assertTrue(ventoy.blocked_reason(node, set()))

    def test_system_mounts_and_active_dependents_block_disk(self):
        for mount in ('/', '/boot', '/boot/efi', '/home', '/run/archiso/bootmnt', '[SWAP]', '/custom/system'):
            node = disk(True); node['children'][0]['mountpoints'] = [mount]
            with self.subTest(mount=mount): self.assertTrue(ventoy.blocked_reason(node, set()))
        for dependent in ('crypt', 'lvm', 'raid1'):
            node = disk(True); node['children'][0]['children'] = [{'type': dependent}]
            self.assertTrue(ventoy.blocked_reason(node, set()))
        node = disk(True); node['children'][0]['holders'] = ['dm-0']
        self.assertTrue(ventoy.blocked_reason(node, set()))
        node = disk(True)
        self.assertTrue(ventoy.blocked_reason(node, {'65:145'}))

    def test_mount_changes_allowed_but_reformatted_partition_rejected(self):
        node = disk(True); old = request(node)
        node['children'][0]['mountpoints'] = ['/run/media/test/Ventoy']
        signed(node)
        self.assertEqual(ventoy.selected_disk(old, [node])['path'], '/dev/sdz')
        node['children'][0]['uuid'] = 'reformatted'; signed(node)
        with self.assertRaisesRegex(RuntimeError, 'layout changed'): ventoy.selected_disk(old, [node])

    def test_replugged_same_path_and_anonymous_usb_rejected(self):
        for serial in ('FIXTURE', ''):
            old = disk(); old['serial'] = serial; signed(old)
            new = copy.deepcopy(old); new['diskseq'] = '8'; signed(new)
            with self.assertRaisesRegex(RuntimeError, 'disconnected or changed'):
                ventoy.selected_disk(request(old), [new])
        with self.assertRaises(RuntimeError): ventoy.selected_disk(request(disk()), [])

    def test_fake_ventoy_label_is_not_enough(self):
        node = disk(True)
        self.assertTrue(ventoy.ventoy_partitions(node))
        node['children'][1]['size'] = 1024**3
        self.assertIsNone(ventoy.ventoy_partitions(node))


class OperationTests(unittest.TestCase):
    def test_install_requires_exact_erasure_confirmation(self):
        node = disk(); req = request(node)
        ventoy.validate_operation('install', req, node, None)
        for confirmation in (None, True, '/dev/sda', '/dev/sdz '):
            with self.subTest(confirmation=confirmation), self.assertRaises(ValueError):
                ventoy.validate_operation('install', {**req, 'erase_confirmed': confirmation}, node, None)
        self.assertEqual(ventoy.command('install', req, None), ['bash', './Ventoy2Disk.sh', '-i', '-s', '/dev/sdz'])
        req.update(style='gpt', secure_boot=False)
        self.assertEqual(ventoy.command('install', req, None), ['bash', './Ventoy2Disk.sh', '-i', '-S', '-g', '/dev/sdz'])

    def test_never_force_reinstall_or_downgrade(self):
        node = disk(); req = request(node)
        with self.assertRaisesRegex(RuntimeError, 'already contains'):
            ventoy.validate_operation('install', req, node, {'version': '1.0.99'})
        with self.assertRaisesRegex(RuntimeError, 'not found'):
            ventoy.validate_operation('update', req, node, None)
        with self.assertRaisesRegex(RuntimeError, 'newer'):
            ventoy.validate_operation('update', req, node, {'version': '9.0.0'})
        req['style'] = 'mbr'; node['size'] = 3 * 1024**4
        with self.assertRaisesRegex(ValueError, 'GPT'): ventoy.validate_operation('install', req, node, None)

    def test_update_preserves_secure_boot_and_ignores_new_usb_options(self):
        for secure in (True, False):
            node = disk(True); req = request(node)
            req.update(style='gpt', secure_boot=not secure)
            installed = {'version': '1.1.17', 'secure_boot': secure, 'style': 'mbr'}
            ventoy.validate_operation('update', req, node, installed)
            self.assertEqual(ventoy.command('update', req, installed),
                             ['bash', './Ventoy2Disk.sh', '-u', '-s' if secure else '-S', '/dev/sdz'])

    def test_unmount_is_deepest_first_and_failure_stops(self):
        node = disk(True)
        node['children'][0]['mountpoints'] = ['/media/USB', '/media/USB/nested']
        with patch.object(ventoy, 'run') as run, patch.object(ventoy, 'emit'):
            ventoy.unmount_disk(node)
            self.assertEqual([c.args[0] for c in run.call_args_list],
                             [['umount', '--', '/media/USB/nested'], ['umount', '--', '/media/USB']])
        with patch.object(ventoy, 'run', side_effect=RuntimeError('target is busy')) as run, patch.object(ventoy, 'emit'):
            with self.assertRaisesRegex(RuntimeError, 'busy'): ventoy.unmount_disk(node)
            self.assertEqual(run.call_count, 1)

    def test_root_rechecks_after_unmount_and_does_not_write_changed_disk(self):
        node = disk(); req = request(node)
        # /run, real devices, authentication and upstream processes are all mocked.
        with contextlib.ExitStack() as stack:
            for name in ('requirements', 'client_alive', 'emit', 'unmount_disk'):
                stack.enter_context(patch.object(ventoy, name))
            stack.enter_context(patch.object(ventoy.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(ventoy.os, 'open', return_value=12))
            stack.enter_context(patch.object(ventoy.os, 'fdopen', return_value=io.StringIO()))
            stack.enter_context(patch.object(ventoy.fcntl, 'flock'))
            stack.enter_context(patch.object(ventoy, 'engine', return_value=contextlib.nullcontext(Path('/fake'))))
            stack.enter_context(patch.object(ventoy, 'probe', return_value=None))
            select = stack.enter_context(patch.object(ventoy, 'selected_disk', side_effect=[node, node, RuntimeError('changed')]))
            write = stack.enter_context(patch.object(ventoy, 'write_engine'))
            with self.assertRaisesRegex(RuntimeError, 'changed'): ventoy.apply('install', req)
            self.assertEqual(select.call_count, 3)
            write.assert_not_called()

    def test_closed_client_cannot_write(self):
        with patch.object(ventoy.select, 'select', return_value=([1], [], [])), patch.object(ventoy.os, 'read', return_value=b''):
            with self.assertRaisesRegex(RuntimeError, 'closed'): ventoy.client_alive()

    def test_completion_requires_matching_version_and_settings(self):
        for final in ({'version': ventoy.VERSION, 'style': 'mbr', 'secure_boot': True},
                      {'version': '1.1.17', 'style': 'mbr', 'secure_boot': True},
                      {'version': ventoy.VERSION, 'style': 'gpt', 'secure_boot': True},
                      {'version': ventoy.VERSION, 'style': 'mbr', 'secure_boot': False}, None):
            with self.subTest(final=final), contextlib.ExitStack() as stack:
                node = disk()
                for name in ('requirements', 'client_alive', 'emit', 'unmount_disk', 'run'):
                    stack.enter_context(patch.object(ventoy, name))
                stack.enter_context(patch.object(ventoy.os, 'geteuid', return_value=0))
                stack.enter_context(patch.object(ventoy.os, 'open', return_value=12))
                stack.enter_context(patch.object(ventoy.os, 'fdopen', return_value=io.StringIO()))
                stack.enter_context(patch.object(ventoy.fcntl, 'flock'))
                stack.enter_context(patch.object(ventoy, 'engine', return_value=contextlib.nullcontext(Path('/fake'))))
                stack.enter_context(patch.object(ventoy, 'selected_disk', return_value=node))
                stack.enter_context(patch.object(ventoy, 'probe', side_effect=[None, final]))
                write = stack.enter_context(patch.object(ventoy, 'write_engine'))
                if final == {'version': ventoy.VERSION, 'style': 'mbr', 'secure_boot': True}:
                    self.assertTrue(ventoy.apply('install', request(node))['ok'])
                else:
                    with self.assertRaises(RuntimeError): ventoy.apply('install', request(node))
                write.assert_called_once()

    def test_probe_requires_real_version_not_upstream_zero_exit(self):
        with patch.object(ventoy, 'run', return_value='Ventoy Version: NA\n'):
            self.assertIsNone(ventoy.probe(Path('/fake'), '/dev/sdz'))
        text = 'Ventoy Version in Disk: 1.1.18\nDisk Partition Style  : GPT\nSecure Boot Support   : NO\n'
        with patch.object(ventoy, 'run', return_value=text):
            self.assertEqual(ventoy.probe(Path('/fake'), '/dev/sdz'), {'version': '1.1.18', 'style': 'gpt', 'secure_boot': False})

    def test_open_routes_to_data_partition_and_checks_actual_mount(self):
        node = disk(True); node['children'][0]['mountpoints'] = ['/run/media/test/Ventoy']; signed(node)
        with patch.object(ventoy.os, 'geteuid', return_value=1000), patch.object(ventoy, 'selected_disk', return_value=node), \
             patch.object(ventoy.os, 'stat') as st, patch.object(ventoy, 'run') as run:
            st.return_value.st_dev = ventoy.os.makedev(65, 145)
            self.assertEqual(ventoy.mount_data(request(node))['mountpoint'], '/run/media/test/Ventoy')
            run.assert_not_called()
            st.return_value.st_dev = ventoy.os.makedev(8, 0)
            with self.assertRaisesRegex(RuntimeError, 'mount changed'): ventoy.mount_data(request(node))


class BundleTests(unittest.TestCase):
    def test_shipped_archive_hash_and_offline_extract(self):
        ventoy.verify_bundle()
        with ventoy.engine() as root:
            self.assertEqual((root / 'ventoy/version').read_text().strip(), ventoy.VERSION)
            self.assertTrue((root / 'boot/boot.img').is_file())
            self.assertTrue((root / 'tool/x86_64/vtoycli.xz').is_file())
        self.assertFalse(root.exists())

    def test_corrupt_archive_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken.tar.gz'; path.write_bytes(b'broken')
            with self.assertRaisesRegex(RuntimeError, 'failed verification'): ventoy.verify_bundle(path)

    def test_manifest_and_catalog(self):
        manifest = json.loads((REPO / 'assets-manifest.json').read_text())
        self.assertEqual(manifest[str(ventoy.BUNDLE.relative_to(REPO))], ventoy.SHA256)
        catalog = json.loads((REPO / 'config/hypr/control_panel/tools.json').read_text())
        entries = [t for group in catalog for t in group['tools'] if t['id'] == 'ventoy']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['path'], ['ventoyTab'])


if __name__ == '__main__':
    unittest.main()
