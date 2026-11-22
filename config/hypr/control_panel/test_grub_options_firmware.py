"""Private file trees and simulated NVRAM only; never authenticate or use disks."""
import copy
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import grub_editor as grub
import grub_preferences as prefs
import grub_firmware as efi
from test_grub_editor import Fixtures, pe

MENU = '''set theme=/keep/my/theme.txt
if [ -s $prefix/grubenv ]; then
  load_env
fi
menuentry 'Linux' --id linux {
  linux /vmlinuz root=UUID=fixture quiet
}
submenu 'Advanced' --id advanced {
  menuentry 'Fallback' --id fallback { linux /vmlinuz fallback; }
}
menuentry 'Windows' --id windows { chainloader /EFI/Microsoft/Boot/bootmgfw.efi; }
'''


class PreferenceTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.file('boot/grub/grub.cfg', MENU)
        self.file('boot/grub/grubenv', '# GRUB Environment Block\n'+ '#'*(1024-25))
        self.file('etc/default/grub', '# user choices\nGRUB_THEME="/keep/my/theme.txt"\nGRUB_CMDLINE_LINUX="quiet splash"\nGRUB_DEFAULT=0\nGRUB_TIMEOUT=8\n')
        (self.root/'etc/grub.d').mkdir(parents=True)
        self.store = prefs.Preferences(self.root)

    def request(self, **updates):
        return {'options_revision': self.store.revision(), 'menu_revision': grub.digest(self.store.config.read_bytes()),
                'options': {'default': 'advanced>fallback', 'remember': False, 'timeout': 12, 'style': 'menu', **updates}}

    def save(self, **updates):
        with self.store.locked(): return self.store.save(self.request(**updates))

    def test_preferences_preserve_theme_kernel_commands_and_unrelated_defaults(self):
        backup = Path(self.save())
        text = self.store.config.read_text()
        self.assertTrue(text.startswith(MENU))
        self.assertIn("set default='advanced>fallback'", text)
        self.assertIn('set timeout=12', text)
        defaults = self.store.defaults.read_text()
        self.assertIn('GRUB_THEME="/keep/my/theme.txt"', defaults)
        self.assertIn('GRUB_CMDLINE_LINUX="quiet splash"', defaults)
        self.assertEqual((backup/'config').read_text(), MENU)
        self.assertEqual(self.store.options_status()['options']['default'], 'advanced>fallback')
        self.store.check(text)

    def test_remember_saves_os_entries_but_respects_one_time_boots(self):
        with patch.object(self.store, 'remember_support', return_value=(True, 'supported')):
            self.save(remember=True)
        text = self.store.config.read_text()
        self.assertEqual(text.count(prefs.CALL), 3)
        self.assertIn('"${boot_once}"', text)
        self.assertIn('save_env -f "${env_block}" saved_entry', text)
        self.assertIn('GRUB_SAVEDEFAULT=true', self.store.defaults.read_text())
        with patch.object(self.store, 'remember_support', return_value=(True, 'supported')): self.save(remember=True)
        self.assertEqual(self.store.config.read_text(), text)
        self.save(remember=False)
        self.assertNotIn(prefs.CALL, self.store.config.read_text())
        self.assertEqual(self.store.config.read_text().count(prefs.BEGIN), 1)
        self.store.check(self.store.config.read_text())

    def test_preference_undo_restores_all_previous_files(self):
        original = self.store.defaults.read_bytes()
        self.save()
        with self.store.locked(): self.store.undo(self.store.revision())
        self.assertEqual(self.store.config.read_text(), MENU)
        self.assertEqual(self.store.defaults.read_bytes(), original)
        self.assertFalse(self.store.generator.exists())

    def test_failed_config_write_restores_defaults_and_generator(self):
        original = self.store.defaults.read_bytes(); actual = grub.atomic; failed = False
        def write(path, data, mode=0o600):
            nonlocal failed
            if path == self.store.config and not failed: failed = True; raise OSError('disk full')
            return actual(path, data, mode)
        with patch.object(grub, 'atomic', side_effect=write), self.assertRaises(OSError): self.save()
        self.assertEqual(self.store.defaults.read_bytes(), original)
        self.assertEqual(self.store.config.read_text(), MENU)
        self.assertFalse(self.store.generator.exists())

    def test_stale_menu_and_invalid_options_are_rejected(self):
        req = self.request(); self.store.config.write_text(MENU+'# changed\n')
        with self.store.locked(), self.assertRaisesRegex(RuntimeError, 'changed'): self.store.save(req)
        for update in ({'default': 'missing'}, {'timeout': True}, {'timeout': -2}, {'style': 'menu;reboot'}, {'remember': 'true'}):
            with self.store.locked(), self.assertRaises(ValueError): self.store.save(self.request(**update))

    def test_unsupported_environment_keeps_other_preferences_usable(self):
        self.store.config.parent.joinpath('grubenv').unlink()
        status = self.store.options_status(); self.assertFalse(status['remember_supported'])
        with self.assertRaises(ValueError): self.save(remember=True)
        self.save(remember=False)

    def test_environment_filesystem_and_abstraction_checks(self):
        # No host grub-probe: the response reflects each simulated boot volume.
        env = self.store.config.parent/'grubenv'; env.write_bytes(b'# GRUB Environment Block\n'+b'#'*999)
        self.assertEqual(env.stat().st_size, 1024)
        for fs, abstraction, expected in [('ext2', '', True), ('fat', '', True), ('ext2', 'lvm', False), ('btrfs', '', False), ('zfs', '', False)]:
            with patch.object(grub, 'command', side_effect=lambda args, **kw: (fs if '--target=fs' in args else abstraction).encode()):
                self.assertEqual(self.store.remember_support()[0], expected, fs+abstraction)

    def test_saving_defaults_never_executes_shell_values(self):
        sentinel = self.root/'not-executed'
        self.store.defaults.write_text(f'GRUB_DEFAULT="$(touch {sentinel})"\nGRUB_THEME=/unchanged\n')
        self.save(); self.assertFalse(sentinel.exists()); self.assertIn('GRUB_THEME=/unchanged', self.store.defaults.read_text())

    def test_symlink_defaults_are_rejected(self):
        self.store.defaults.unlink(); other = self.file('outside', 'keep')
        self.store.defaults.symlink_to(other)
        with self.assertRaisesRegex(RuntimeError, 'symbolic'):
            with self.store.locked(): pass
        self.assertEqual(other.read_text(), 'keep')

    def test_compound_or_multiline_defaults_are_not_partially_overwritten(self):
        for original in ['GRUB_DEFAULT=0; GRUB_THEME=/keep/theme\n', 'GRUB_DEFAULT="Linux\nName"\n']:
            self.store.defaults.write_text(original)
            with self.assertRaisesRegex(ValueError, 'own line'): self.save()
            self.assertEqual(self.store.defaults.read_text(), original); self.assertEqual(self.store.config.read_text(), MENU)

    def test_interrupted_preferences_are_recovered_before_loading_current_menu(self):
        original = self.store.defaults.read_bytes(); self.save()
        (self.store.state/'pending.json').write_bytes((self.store.state/'last.json').read_bytes())
        session = grub.Session.__new__(grub.Session); session.store = grub.Store(self.root)
        with patch.object(grub, 'status_payload', side_effect=session.store.status):
            result = session.handle({'action': 'refresh'})
        self.assertEqual(self.store.config.read_text(), MENU); self.assertEqual(self.store.defaults.read_bytes(), original)
        self.assertFalse((self.store.state/'pending.json').exists()); self.assertTrue(result['current_entries'])


class OrderTests(Fixtures):
    def test_siblings_and_submenus_move_without_losing_commands(self):
        items = grub.menu_entries(MENU)
        moved, group = grub.move_menu(MENU, items[-1]['id'], -1)
        self.assertFalse(group)
        self.assertEqual([e['name'] for e in grub.menu_entries(moved)], ['Linux', 'Windows', 'Advanced', 'Fallback'])
        self.assertIn('root=UUID=fixture quiet', moved)

    def test_generator_boundaries_move_as_complete_groups(self):
        a = '### BEGIN /etc/grub.d/10_linux ###\ninsmod gzio\n'+MENU+'### END /etc/grub.d/10_linux ###\n'
        b = '### BEGIN /etc/grub.d/30_os-prober ###\nset other=keep\nmenuentry "Other" { chainloader /efi; }\n### END /etc/grub.d/30_os-prober ###\n'
        moved, group = grub.move_menu(a+b, grub.menu_entries(a+b)[-1]['id'], -1)
        self.assertTrue(group); self.assertEqual(moved, b+a)

    def test_conditional_boundary_cannot_be_split(self):
        text = "if [ yes ]; then\nmenuentry 'a' { linux /a; }\nfi\nmenuentry 'b' { linux /b; }\n"
        with self.assertRaisesRegex(ValueError, 'conditions'):
            grub.move_menu(text, grub.menu_entries(text)[0]['id'], 1)

    def test_move_transaction_and_undo(self):
        self.file('boot/grub/grub.cfg', MENU); (self.root/'etc/grub.d').mkdir(parents=True)
        store = grub.Store(self.root)
        with store.locked():
            store.move_current({'id': grub.menu_entries(MENU)[-1]['id'], 'direction': -1,
                                'revision': store.revision(), 'menu_revision': grub.digest(MENU.encode())})
            self.assertEqual(grub.menu_entries(store.config.read_text())[1]['name'], 'Windows')
            store.undo(store.revision())
        self.assertEqual(store.config.read_text(), MENU)


class FirmwareTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.file('boot/grub/grub.cfg', MENU); (self.root/'etc/grub.d').mkdir(parents=True)
        self.store = grub.Store(self.root); self.firmware = efi.Firmware(self.store)
        for module in ('normal', 'configfile', 'linux', 'echo', 'halt'):
            self.file('usr/lib/grub/x86_64-efi/'+module+'.mod', b'fixture module '+module.encode())
        self.uuid = '12121212-3434-5656-7878-909090909090'
        self.part = {'partition': '/dev/fixture1', 'disk': '/dev/fixture', 'number': 1, 'partuuid': '12345678-1111-2222-3333-abcdefabcdef',
                     'mount': str(self.root/'efi'), 'device': '8:1', 'token': 'test-esp'}
        (self.root/'efi').mkdir()
        self.nvram = {'order': ['0002', '0001'], 'entries': [
            {'number': '0002', 'active': True, 'label': 'Windows Boot Manager', 'partuuid': 'windows', 'loader': r'\efi\microsoft\boot\bootmgfw.efi'},
            {'number': '0001', 'active': True, 'label': 'Existing Linux', 'partuuid': 'other', 'loader': r'\efi\other\grubx64.efi'}]}
        self.calls = []; self.fail_order = False
        for obj, name, value in [(self.firmware, 'platform_check', lambda: None), (self.firmware, 'partitions', lambda: [self.part]),
                                 (self.firmware, 'status', lambda: {'scope': 'Fixture VM firmware only'}),
                                 (self.firmware, 'nvram', self.read_nvram), (grub, 'current_config', lambda _: (self.uuid, '/boot/grub/grub.cfg')),
                                 (grub, 'inventory', lambda: [{'path': '/dev/fixture', 'uuid': self.uuid},
                                                            {'path': self.part['partition'], 'partuuid': self.part['partuuid']}]),
                                 (grub, 'command', self.command)]:
            p = patch.object(obj, name, side_effect=value); p.start(); self.addCleanup(p.stop)
        p = patch.object(grub, 'executable', side_effect=lambda *names: names[0]); p.start(); self.addCleanup(p.stop)
        self.request = {'revision': self.store.revision(), 'partition_token': 'test-esp', 'label': 'Hyper Fusion', 'first': False}

    def read_nvram(self):
        return {**copy.deepcopy(self.nvram), 'raw': json.dumps(self.nvram, sort_keys=True)}

    def command(self, args, **kwargs):
        self.calls.append(list(map(str, args)))
        if args[0] == 'grub-mkstandalone':
            image = next(a.split('=', 1)[1] for a in args if a.startswith('--output=')); Path(image).write_bytes(pe()); return b''
        if args[0] == 'grub-probe': return b'ext2' if '--target=fs' in args else b''
        if args[0] == 'efibootmgr':
            if '--create-only' in args:
                self.nvram['entries'].append({'number': args[args.index('--bootnum')+1], 'active': True, 'label': args[args.index('--label')+1],
                    'loader': args[args.index('--loader')+1].lower(), 'partuuid': self.part['partuuid']})
            if '--bootorder' in args:
                if self.fail_order: raise RuntimeError('firmware full')
                self.nvram['order'] = args[args.index('--bootorder')+1].split(',')
            if '--delete-bootnum' in args:
                num = args[args.index('--bootnum')+1]; self.nvram['entries'] = [e for e in self.nvram['entries'] if e['number'] != num]
                self.nvram['order'] = [e for e in self.nvram['order'] if e != num]
            if '--delete-bootorder' in args: self.nvram['order'] = []
            return b''
        if args[0].endswith('grub-script-check'): return b''
        self.fail('Unexpected external command '+repr(args))

    def test_review_only_builds_private_image_and_backups(self):
        original = self.read_nvram(); plan = self.firmware.prepare(self.request)
        self.assertFalse(Path(plan['target']).exists()); self.assertEqual(self.read_nvram(), original)
        self.assertFalse(any(c[0] == 'efibootmgr' for c in self.calls))
        self.assertTrue((Path(plan['backup'])/'RECOVERY.txt').exists())
        self.assertIn(self.uuid, (Path(plan['backup'])/'embedded.cfg').read_text())
        self.assertTrue(plan['modules']['install']); self.assertFalse(Path(plan['modules']['target']).exists())

    def test_register_appends_and_preserves_other_firmware_entries(self):
        plan = self.firmware.prepare(self.request); original = copy.deepcopy(self.nvram['entries'])
        self.firmware.install(plan, plan['token'])
        self.assertEqual(self.nvram['order'], ['0002', '0001', '0000'])
        self.assertEqual(self.nvram['entries'][:2], original)
        self.assertTrue(Path(plan['target']).is_file())
        self.assertEqual(self.firmware.module_files(Path(plan['modules']['target'])), plan['modules']['hashes'])
        self.assertTrue(any('--create-only' in c for c in self.calls))

    def test_explicit_first_and_duplicate_registration_reuses_entry(self):
        plan = self.firmware.prepare({**self.request, 'first': True}); self.firmware.install(plan, plan['token'])
        self.assertEqual(self.nvram['order'], ['0000', '0002', '0001'])
        again = self.firmware.prepare(self.request); self.assertEqual(again['existing'], '0000')
        self.firmware.install(again, again['token']); self.assertEqual(len(self.nvram['entries']), 3)

    def test_expired_wrong_token_and_stale_partition_are_rejected(self):
        plan = self.firmware.prepare(self.request)
        with self.assertRaisesRegex(RuntimeError, 'expired'): self.firmware.install(plan, 'wrong')
        plan['created'] = time.monotonic()-301
        with self.assertRaisesRegex(RuntimeError, 'expired'): self.firmware.install(plan, plan['token'])
        plan['created'] = time.monotonic()
        with patch.object(self.firmware, 'partitions', return_value=[]), self.assertRaisesRegex(RuntimeError, 'partition changed'):
            self.firmware.install(plan, plan['token'])
        self.assertFalse(Path(plan['target']).exists())

    def test_stale_menu_and_firmware_are_rejected_without_writes(self):
        plan = self.firmware.prepare(self.request); self.store.config.write_text(MENU+'# other program\n')
        with self.assertRaisesRegex(RuntimeError, 'menu changed'): self.firmware.install(plan, plan['token'])
        self.store.config.write_text(MENU); self.nvram['order'].reverse()
        with self.assertRaisesRegex(RuntimeError, 'Firmware boot entries changed'): self.firmware.install(plan, plan['token'])
        self.assertFalse(Path(plan['target']).exists())

    def test_failed_nvram_write_removes_only_created_entry_and_new_loader(self):
        original = copy.deepcopy(self.nvram); plan = self.firmware.prepare(self.request); self.fail_order = True
        with self.assertRaisesRegex(RuntimeError, 'rolled back'): self.firmware.install(plan, plan['token'])
        self.assertEqual(self.nvram, original); self.assertFalse(Path(plan['target']).exists())
        self.assertFalse(Path(plan['modules']['target']).exists())

    def test_existing_mismatched_efi_modules_are_not_overwritten(self):
        for module in ('normal', 'configfile', 'linux', 'echo', 'halt'):
            self.file('boot/grub/x86_64-efi/'+module+'.mod', 'older module')
        with self.assertRaisesRegex(RuntimeError, 'differ'): self.firmware.prepare(self.request)
        self.assertEqual((self.root/'boot/grub/x86_64-efi/normal.mod').read_text(), 'older module')

    def standard_installed_modules(self):
        source = self.root/'usr/lib/grub/x86_64-efi'
        self.file('usr/lib/grub/x86_64-efi/fdt.lst', b'')
        self.file('usr/lib/grub/x86_64-efi/moddep.lst', b'normal: terminal\n')
        self.file('usr/lib/grub/x86_64-efi/command.lst', b'configfile: configfile\n')
        # Normal grub-install output, including the ISO installer's output.
        for path in source.iterdir():
            if path.name != 'fdt.lst': self.file('boot/grub/x86_64-efi/'+path.name, path.read_bytes())

    def test_normal_grub_install_without_empty_fdt_index_registers(self):
        self.standard_installed_modules()
        target = self.root/'boot/grub/x86_64-efi'
        original = self.firmware.module_files(target)
        plan = self.firmware.prepare(self.request)
        self.assertFalse(plan['modules']['install'])
        self.firmware.install(plan, plan['token'])
        self.assertEqual(self.firmware.module_files(target), original)
        self.assertFalse((target/'fdt.lst').exists())
        self.assertEqual(self.nvram['order'], ['0002', '0001', '0000'])

    def test_runtime_index_missing_or_changed_is_still_rejected(self):
        self.standard_installed_modules()
        index = self.root/'boot/grub/x86_64-efi/moddep.lst'
        for content in (None, b'older dependencies'):
            if content is None: index.unlink()
            else: index.write_bytes(content)
            with self.assertRaisesRegex(RuntimeError, 'moddep.lst'): self.firmware.prepare(self.request)

    def test_nonempty_fdt_index_is_not_silently_ignored(self):
        self.standard_installed_modules()
        (self.root/'usr/lib/grub/x86_64-efi/fdt.lst').write_bytes(b'new platform metadata')
        with self.assertRaisesRegex(RuntimeError, 'fdt.lst'): self.firmware.prepare(self.request)

    def test_existing_modules_changed_after_review_still_block_registration(self):
        self.standard_installed_modules(); plan = self.firmware.prepare(self.request)
        (self.root/'boot/grub/x86_64-efi/linux.mod').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'changed after review'): self.firmware.install(plan, plan['token'])
        self.assertFalse(Path(plan['target']).exists())

    def test_staged_module_tampering_blocks_registration(self):
        plan = self.firmware.prepare(self.request)
        (Path(plan['backup'])/'modules/normal.mod').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'verification'): self.firmware.install(plan, plan['token'])
        self.assertFalse(Path(plan['target']).exists())

    def test_failed_cleanup_keeps_bootable_files_and_reports_recovery(self):
        plan = self.firmware.prepare(self.request); real = self.command
        def fail(args, **kwargs):
            if '--bootorder' in args or '--delete-bootnum' in args: raise RuntimeError('firmware unavailable')
            return real(args, **kwargs)
        with patch.object(grub, 'command', side_effect=fail), self.assertRaisesRegex(RuntimeError, 'Recovery needs attention'):
            self.firmware.install(plan, plan['token'])
        self.assertTrue(Path(plan['target']).exists()); self.assertTrue(Path(plan['modules']['target']).exists())
        record = json.loads((Path(plan['backup'])/'result.json').read_text()); self.assertTrue(record['recovery_errors'])

    def test_source_module_change_after_review_prevents_any_registration(self):
        plan = self.firmware.prepare(self.request)
        (self.root/'usr/lib/grub/x86_64-efi/normal.mod').write_bytes(b'package update')
        with self.assertRaisesRegex(RuntimeError, 'tools changed'): self.firmware.install(plan, plan['token'])
        self.assertFalse(Path(plan['target']).exists()); self.assertEqual(len(self.nvram['entries']), 2)

    def test_cloned_efi_partition_connected_after_review_is_rejected(self):
        plan = self.firmware.prepare(self.request)
        devices = [{'path': '/dev/root', 'uuid': self.uuid}, {'path': '/dev/esp1', 'partuuid': self.part['partuuid']},
                   {'path': '/dev/clone1', 'partuuid': self.part['partuuid']}]
        with patch.object(grub, 'inventory', return_value=devices), self.assertRaisesRegex(RuntimeError, 'unique partition UUID'):
            self.firmware.install(plan, plan['token'])
        self.assertFalse(Path(plan['target']).exists())

    def test_preexisting_foreign_loader_never_overwritten(self):
        plan = self.firmware.prepare(self.request); target = Path(plan['target']); target.parent.mkdir(parents=True); target.write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'not owned'): self.firmware.prepare(self.request)
        with self.assertRaisesRegex(RuntimeError, 'changed after review'): self.firmware.install(plan, plan['token'])
        self.assertEqual(target.read_bytes(), b'foreign')

    def test_symlink_efi_target_rejected(self):
        outside = self.root/'outside'; outside.mkdir(); (self.root/'efi/EFI').symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'symbolic'): self.firmware.prepare(self.request)
        self.assertEqual(list(outside.iterdir()), [])

    def test_image_tamper_and_duplicate_filesystem_uuid_rejected(self):
        plan = self.firmware.prepare(self.request); (Path(plan['backup'])/'grubx64.efi').write_bytes(b'bad')
        with self.assertRaisesRegex(RuntimeError, 'EFI image changed'): self.firmware.install(plan, plan['token'])
        with patch.object(grub, 'inventory', return_value=[{'path': '/dev/a', 'uuid': self.uuid}, {'path': '/dev/b', 'uuid': self.uuid}]), self.assertRaisesRegex(RuntimeError, 'unique UUID'):
            self.firmware.prepare(self.request)

    def test_firmware_parser_accepts_both_device_path_formats(self):
        for path in [r'File(\EFI\HyperFusion\grubx64.efi)', r'\EFI\HyperFusion\grubx64.efi']:
            text = 'BootOrder: 0002,00a1\nBoot00A1* Hyper Fusion\tHD(1,GPT,'+self.part['partuuid']+',0x800,0x80000)/'+path+'\n'
            result = efi.parse_firmware(text); self.assertEqual(result['order'], ['0002', '00A1'])
            self.assertEqual(result['entries'][0]['label'], 'Hyper Fusion')
            self.assertEqual(result['entries'][0]['loader'], r'\efi\hyperfusion\grubx64.efi')

    def test_firmware_loader_excludes_hex_encoded_optional_data(self):
        for path in [r'\EFI\Microsoft\Boot\bootmgfw.efi57494e444f575300010000',
                     r'File(\EFI\Microsoft\Boot\bootmgfw.efi)57494e444f575300010000']:
            text = 'BootCurrent: 0000\nBoot0000* Windows Boot Manager\tHD(2,GPT,'+self.part['partuuid']+',0x800,0x80000)/'+path+'\n'
            entry = efi.parse_firmware(text)['entries'][0]
            self.assertEqual(entry['loader'], r'\efi\microsoft\boot\bootmgfw.efi')
            with patch.object(grub, 'command', return_value=text.encode()):
                self.assertEqual(grub.current_efi(), (self.part['partuuid'], '/efi/microsoft/boot/bootmgfw.efi'))
        text = 'HD(2,GPT,'+self.part['partuuid']+',0x800,0x80000)/\\EFI\\BOOT\\BOOTX64.EFI0000424f'
        self.assertEqual(grub.efi_device_path(text)[1], '/efi/boot/bootx64.efi')


class FirmwareDiscoveryTests(Fixtures):
    def setUp(self):
        super().setUp(); self.file('boot/grub/grub.cfg', MENU)
        self.firmware = efi.Firmware(grub.Store(self.root))

    def test_bios_and_secure_boot_rejected_before_building_or_writing(self):
        with self.assertRaisesRegex(RuntimeError, 'UEFI mode'): self.firmware.platform_check()
        variable = self.file('sys/firmware/efi/efivars/SecureBoot-test', b'\x07\x00\x00\x00\x01')
        with patch.object(efi.platform, 'machine', return_value='x86_64'), self.assertRaisesRegex(RuntimeError, 'Secure Boot is enabled'):
            self.firmware.platform_check()
        variable.write_bytes(b'invalid')
        with patch.object(efi.platform, 'machine', return_value='x86_64'), self.assertRaisesRegex(RuntimeError, 'could not be verified'):
            self.firmware.platform_check()

    def test_only_mounted_whole_readwrite_esp_is_offered(self):
        mount = self.root/'efi'; mount.mkdir()
        self.file('sys/class/block/test1/partition', '1\n')
        part = {'path': '/dev/test1', 'type': 'part', 'parttype': efi.ESP_TYPE, 'fstype': 'vfat', 'partuuid': 'fixture-esp',
                'maj:min': '8:1', 'mountpoints': [str(mount)]}
        disk = {'path': '/dev/test', 'size': 10000, 'serial': 'test', 'children': [part]}
        mounted = {'filesystems': [{'target': str(mount), 'maj:min': '8:1', 'fsroot': '/', 'options': 'rw,nosuid,nodev'}]}
        with patch.object(grub, 'inventory', return_value=[disk]), patch.object(grub, 'command', side_effect=lambda *a, **k: json.dumps(mounted).encode()):
            self.assertEqual(self.firmware.partitions()[0]['number'], 1)
            mounted['filesystems'][0]['options'] = 'ro,nosuid'; self.assertEqual(self.firmware.partitions(), [])
            mounted['filesystems'][0]['options'] = 'rw'; mounted['filesystems'][0]['fsroot'] = '/subdirectory'
            self.assertEqual(self.firmware.partitions(), [])
            mounted['filesystems'][0]['fsroot'] = '/'; part['parttype'] = 'other'
            self.assertEqual(self.firmware.partitions(), [])

    def test_unavailable_firmware_is_a_visible_status_not_an_empty_success(self):
        with patch.object(self.firmware, 'platform_check', side_effect=RuntimeError('UEFI variables are read-only')):
            status = self.firmware.status()
        self.assertFalse(status['available']); self.assertIn('read-only', status['reason'])


if __name__ == '__main__': unittest.main()
