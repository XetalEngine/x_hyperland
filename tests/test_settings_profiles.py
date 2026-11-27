"""Exercise real archives and transactions inside isolated homes/system roots."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from settings_profiles import archive, audio, backend, catalog, factory, packages, system, windows
from updates.file_policy import KEEP, PREFERENCES


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.home = self.base/'home'; self.profile = self.home/'.config/hypr'
        self.system = self.base/'system'; self.state = self.base/'transactions'
        self.profile.mkdir(parents=True); (self.system/'etc').mkdir(parents=True)
        (self.system/'etc/machine-id').write_text('fixture-machine')
        self.roots = catalog.roots(self.profile, self.home, self.system)

    def put(self, scope, path, value):
        target = self.roots[scope]/path; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.encode(value) if not isinstance(value, bytes) else value)
        return target

    def snapshot(self, groups):
        records, blobs = archive.collect(self.roots, groups)
        return archive.manifest(groups, records, home=str(self.home), profile=str(self.profile)), blobs

    def test_registry_covers_every_updater_preference(self):
        for name in KEEP | PREFERENCES:
            with self.subTest(name=name): self.assertIn(catalog.profile_category(name), catalog.USER_IDS)
        self.assertIsNone(catalog.profile_category('.xetal-update.json'))
        self.assertIsNone(catalog.profile_category('.xetal-install.json'))
        self.assertEqual(catalog.profile_category('my-bindings.conf'), 'desktop')

    def test_window_and_private_app_inventory(self):
        cases = {'runtime/window_memory/state/windows.json': 'windows', 'effects/window_close/kde-rules.json': 'windows',
                 'effects/window_close/behavior-settings.json': 'windows', 'file_manager/state/settings.ini': 'files',
                 'control_panel/state/rdp/connections.json': 'remote', 'calculator/state/settings.ini': 'tools'}
        for name, group in cases.items(): self.assertEqual(catalog.profile_category(name), group)
        self.assertEqual(catalog.home_category('.local/state/hyperfusion/monitor-picture.json'), 'power')
        self.assertEqual(catalog.home_category('.local/share/xetal-kvm/presets/gaming.json'), 'virtualization')
        self.assertIsNone(catalog.home_category('.local/share/xetal-kvm/windows.img'))
        self.assertIsNone(catalog.home_category('.config/chromium/Default/History'))
        self.assertEqual(catalog.home_category('.config/chromium/Default/Preferences'), 'applications')

    def test_roundtrip_selected_and_absence(self):
        theme = self.put('profile', 'theme/state.json', {'design': 'amazon'})
        self.put('profile', 'effects/window_close/kde-rules.json', {'version': 1, 'apps': {'editor': {'titlebar': False}}})
        self.put('profile', 'runtime/window_memory/state/windows.json', {'version': 1, 'windows': {'a': {'size': [800, 600]}}})
        doc, blobs = self.snapshot(['windows'])
        target = self.base/'saved.hfsettings'; archive.write(target, doc, blobs)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        doc, blobs = archive.read(target)
        extra = self.put('profile', 'effects/window_close/saved-windows.json', {'version': 1, 'windows': []})
        memory = self.put('profile', 'runtime/window_memory/state/windows.json', {'changed': True})
        source = self.put('profile', 'effects/window_close/controller.py', b'unchanged code')
        archive.restore_files(doc, blobs, self.roots, ['windows'], self.state)
        self.assertFalse(extra.exists()); self.assertIn('windows', json.loads(memory.read_text()))
        self.assertEqual(json.loads(theme.read_text())['design'], 'amazon'); self.assertEqual(source.read_bytes(), b'unchanged code')
        recovery, objects = archive.read(self.state/'before.hfsettings')
        archive.restore_files(recovery, objects, self.roots, ['windows'], self.base/'undo')
        self.assertTrue(extra.exists()); self.assertEqual(json.loads(memory.read_text()), {'changed': True})

    def test_hidden_wallpapers_roundtrip_and_reset_in_existing_wallpaper_category(self):
        # Keep the previous category so existing wallpaper backups stay valid.
        name = 'wallpaper/state/browser.json'; group = catalog.profile_category(name)
        saved = {'version':1,'folders':[],'hidden':['/pictures/keep.png'],'style':'overlay',
                 'hidden_tabs':[{'id':'hidden','name':'Hidden','paths':[]},
                                {'id':'favorites','name':'Favorites','paths':['/pictures/keep.png']}],
                 'active_hidden_tab':'favorites'}
        path = self.put('profile',name,saved)
        document,blobs = self.snapshot([group])
        path.write_text('{"version":1,"hidden":[]}')
        archive.restore_files(document,blobs,self.roots,[group],self.state)
        self.assertEqual(json.loads(path.read_text()),saved)
        empty = archive.manifest([group],[],home=str(self.home),profile=str(self.profile),factory=True)
        archive.restore_files(empty,{},self.roots,[group],self.base/'reset')
        self.assertFalse(path.exists())

    def test_checksum_damage_and_traversal_rejected(self):
        self.put('profile', 'sounds/settings.json', {'enabled': True}); doc, blobs = self.snapshot(['audio'])
        corrupt = copy.deepcopy(doc); corrupt['files'][0]['sha256'] = '0'*64
        with self.assertRaises(ValueError): archive.validate(corrupt, blobs)
        corrupt = copy.deepcopy(doc); corrupt['files'][0]['path'] = '../outside'
        with self.assertRaises(ValueError): archive.validate(corrupt, blobs)
        corrupt['files'][0]['path'] = '/etc/sudoers'
        with self.assertRaises(ValueError): archive.validate(corrupt, blobs)
        target = self.base/'bad.hfsettings'
        with zipfile.ZipFile(target, 'w') as z:
            z.writestr('manifest.json', archive.encode(doc)); z.writestr('../escape', b'evil')
        with self.assertRaises(ValueError): archive.read(target)
        self.assertFalse((self.base.parent/'escape').exists())

    def test_hidden_preset_tabs_roundtrip_and_reset_with_appearance(self):
        name='theme/state/preset-gallery.json';self.assertEqual(catalog.profile_category(name),'appearance')
        value={'version':1,'hidden':['raw','integra'],'hidden_tabs':[{'id':'cars','name':'Cars','paths':['integra']},
               {'id':'later','name':'Later','paths':['raw']}],'active_hidden_tab':'cars','hidden_dock_collapsed':True}
        path=self.put('profile',name,value);document,blobs=self.snapshot(['appearance'])
        path.write_text('{}');archive.restore_files(document,blobs,self.roots,['appearance'],self.state)
        self.assertEqual(json.loads(path.read_text()),value)
        empty=archive.manifest(['appearance'],[],home=str(self.home),profile=str(self.profile),factory=True)
        archive.restore_files(empty,{},self.roots,['appearance'],self.base/'reset')
        self.assertFalse(path.exists())

    def test_unknown_scope_category_and_duplicate_rejected(self):
        self.put('profile', 'sounds/settings.json', {'enabled': True}); doc, blobs = self.snapshot(['audio'])
        for change in ({'scope': 'root'}, {'category': 'system'}, {'path': 'sounds/model.py'}):
            bad = copy.deepcopy(doc); bad['files'][0].update(change)
            with self.assertRaises(ValueError): archive.validate(bad, blobs)
        doc['files'] *= 2
        with self.assertRaises(ValueError): archive.validate(doc, blobs)

    def test_symlink_parent_and_escape_fail_before_any_write(self):
        self.put('profile', 'sounds/settings.json', {'enabled': True}); doc, blobs = self.snapshot(['audio'])
        outside = self.base/'outside'; outside.mkdir(); (outside/'settings.json').write_text('original')
        shutil.rmtree(self.profile/'sounds'); (self.profile/'sounds').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): archive.restore_files(doc, blobs, self.roots, ['audio'], self.state)
        self.assertEqual((outside/'settings.json').read_text(), 'original')
        (self.profile/'sounds').unlink(); (self.profile/'sounds').mkdir()
        bad = copy.deepcopy(doc); bad['files'][0] = {'scope':'profile', 'path':'sounds/settings.json', 'category':'audio', 'kind':'link', 'target':'/etc/shadow', 'mode':0o777}
        with self.assertRaises(ValueError): archive.restore_files(bad, {}, self.roots, ['audio'], self.state)
        self.assertFalse((self.profile/'sounds/settings.json').exists())

    def test_transaction_rolls_back_after_write_failure(self):
        a = self.put('profile', 'theme/state.json', {'design':'old'})
        b = self.put('profile', 'theme/icons.json', {'icons':'old'})
        doc, blobs = self.snapshot(['appearance'])
        a.write_text('new-a'); b.write_text('new-b')
        original = archive.atomic; failed = False
        def fault(path, data, mode=0o600):
            nonlocal failed
            if Path(path) == a and not failed: failed = True; raise OSError('fixture failure')
            return original(path, data, mode)
        with patch.object(archive, 'atomic', side_effect=fault), self.assertRaises(OSError):
            archive.restore_files(doc, blobs, self.roots, ['appearance'], self.state)
        self.assertEqual(a.read_text(), 'new-a'); self.assertEqual(b.read_text(), 'new-b')
        self.assertEqual(json.loads((self.state/'journal.json').read_text())['status'], 'rolled-back')

    def test_private_inventory_redacts_values_but_saves_them(self):
        self.put('profile', 'control_panel/state/rdp/connections.json', {'password':'private', 'host':'server', 'options':{'fullscreen':True}})
        doc, blobs = self.snapshot(['remote']); rows = list(archive.values(doc, blobs))[0][2]
        self.assertIn(('password', 'Included · hidden'), rows)
        self.assertIn(('options.fullscreen', 'True'), rows)
        self.assertIn(b'private', next(iter(blobs.values())))

    def test_custom_artwork_embedded_and_relocated(self):
        picture = self.base/'my wallpaper.png'; picture.write_bytes(b'image fixture')
        self.put('profile', 'wallpaper/selection.json', {'DP-1': {'path': str(picture)}})
        records, blobs = archive.collect(self.roots, ['appearance']); records += archive.referenced_artwork(records, blobs, self.roots)
        doc = archive.manifest(['appearance'], records, home=str(self.home), profile=str(self.profile))
        picture.unlink(); archive.restore_files(doc, blobs, self.roots, ['appearance'], self.state)
        path = Path(json.loads((self.profile/'wallpaper/selection.json').read_text())['DP-1']['path'])
        self.assertEqual(path.read_bytes(), b'image fixture'); self.assertIn('imported-assets', str(path))
        # A second export must embed the previously imported artwork again.
        records, objects = backend.user_snapshot(['appearance'], self.roots, live=False)
        saved = archive.manifest(['appearance'], records, home=str(self.home), profile=str(self.profile))
        path.unlink()
        archive.restore_files(saved, objects, self.roots, ['appearance'], self.base/'second-load')
        again = Path(json.loads((self.profile/'wallpaper/selection.json').read_text())['DP-1']['path'])
        self.assertEqual(again.read_bytes(), b'image fixture')

    def test_archived_symlink_parent_rejected_before_package_work(self):
        self.put('home', '.config/example/config/inside.json', b'{}')
        doc, blobs = self.snapshot(['applications'])
        doc['files'].append(dict(scope='home', path='.config/example/config', category='applications', kind='link', mode=0o777, target='elsewhere'))
        with patch.object(backend, 'package_terminal') as packages_run, self.assertRaises(ValueError):
            backend.validate_load(doc, blobs, ['applications'], self.roots)
        packages_run.assert_not_called()

    def test_private_network_values_are_not_shown(self):
        self.put('system', 'etc/NetworkManager/system-connections/home.nmconnection', b'[wifi-security]\npsk=private-network-password\n')
        self.put('system', 'etc/example.conf', b'PSK=private-psk\nname=visible\n')
        doc, blobs = system.capture(['network', 'system'], self.roots)
        values = str(list(archive.values(doc, blobs)))
        self.assertNotIn('private-network-password', values); self.assertNotIn('private-psk', values)
        self.assertIn('visible', values)

    def test_empty_machine_identity_cannot_be_a_factory_baseline(self):
        (self.system/'etc/machine-id').write_text('')
        with self.assertRaisesRegex(ValueError, 'permanent machine identity'):
            system.capture(['system'], self.roots)

    def test_load_is_queued_and_applies_on_next_login(self):
        path = self.put('profile', 'sounds/settings.json', {'enabled': False}); doc, blobs = self.snapshot(['audio'])
        path.write_text('{"enabled":true}')
        result = backend.load(doc, blobs, ['audio'], roots=self.roots, state=self.state, live=False)
        self.assertEqual(result['status'], 'pending-sign-in'); self.assertTrue(json.loads(path.read_text())['enabled'])
        with self.assertRaises(RuntimeError): backend.load(doc, blobs, ['audio'], roots=self.roots, state=self.state, live=False)
        self.assertTrue(backend.activate(self.roots, self.state, render=False)); self.assertFalse(json.loads(path.read_text())['enabled'])
        self.assertFalse(backend.activate(self.roots, self.state, render=False))

    def test_pending_archive_tampering_fails(self):
        path = self.put('profile', 'sounds/settings.json', {'enabled': False}); doc, blobs = self.snapshot(['audio'])
        backend.load(doc, blobs, ['audio'], roots=self.roots, state=self.state, live=False)
        pending = json.loads((self.state/'pending.json').read_text())
        (self.state/'recovery'/pending['transaction']/'requested.hfsettings').write_bytes(b'corrupt')
        path.write_text('unchanged')
        with self.assertRaises(ValueError): backend.activate(self.roots, self.state, render=False)
        self.assertEqual(path.read_text(), 'unchanged')

    def test_cancel_does_not_change_current_values(self):
        path = self.put('profile', 'sounds/settings.json', {'enabled': False}); doc, blobs = self.snapshot(['audio'])
        backend.load(doc, blobs, ['audio'], roots=self.roots, state=self.state, live=False)
        backend.cancel_pending(self.state)
        self.assertFalse(backend.activate(self.roots, self.state)); self.assertTrue(path.exists())

    def test_system_categories_and_machine_guard(self):
        self.put('system', 'etc/hyperfusion/system-tweaks.json', {'governor':'powersave'})
        self.put('system', 'etc/default/grub', b'GRUB_TIMEOUT=5\n')
        self.put('system', 'etc/ufw/user.rules', b'fixture firewall')
        self.put('system', 'etc/shadow', b'identity must stay')
        doc, blobs = system.capture(['system', 'boot', 'network'], self.roots)
        self.assertEqual({r['category'] for r in doc['files']}, {'system','boot','network'})
        self.assertNotIn('etc/shadow', [r['path'] for r in doc['files']])
        bad = copy.deepcopy(doc); bad['machine'] = 'wrong machine'
        with self.assertRaises(ValueError): system.restore(bad, blobs, ['system'], self.roots, self.state, lambda _: '')

    def test_grub_generation_failure_restores_original_config(self):
        path = self.put('system', 'etc/default/grub', b'GRUB_TIMEOUT=5\n')
        (self.system/'boot/grub').mkdir(parents=True)
        doc, blobs = system.capture(['boot'], self.roots); path.write_text('GRUB_TIMEOUT=30\n')
        def runner(argv):
            if argv[0] == 'grub-mkconfig': raise RuntimeError('fixture generation failure')
            return ''
        with self.assertRaises(RuntimeError): system.restore(doc, blobs, ['boot'], self.roots, self.state, runner)
        self.assertEqual(path.read_text(), 'GRUB_TIMEOUT=30\n')

    def test_package_plan_tracks_pacman_foreign_reasons_and_removals(self):
        row = lambda name, source='pacman', version='1': dict(name=name, source=source, version=version, explicit=True)
        plan = packages.plan([row('discord'), row('xetal-tool', 'foreign'), row('bash', version='2')], [row('old-app'), row('bash')])
        self.assertEqual(plan['pacman'], ['discord']); self.assertEqual(plan['foreign'], ['xetal-tool']); self.assertEqual(plan['remove'], ['old-app'])
        self.assertEqual(plan['different_versions'][0]['name'], 'bash')
        with self.assertRaises(ValueError): packages.plan([], [row('bash')])
        with self.assertRaises(ValueError): packages.validate([row('--overwrite=*')])

    def test_factory_does_not_copy_personal_state(self):
        self.put('profile', 'theme/state.json', {'design':'amazon'})
        self.put('profile', 'wallpaper/default.json', {'image':'binaryknife/workstation-2.png','fit':'cover'})
        self.put('profile', 'runtime/window_memory/state/windows.json', {'personal':True})
        self.put('profile', 'theme/custom-presets.json', {'secret':True})
        target = self.base/'factory.hfsettings'; factory.build(self.profile, target, self.home)
        doc, blobs = archive.read(target); names = {r['path']:r for r in doc['files']}
        self.assertNotIn('runtime/window_memory/state/windows.json', names); self.assertNotIn('theme/custom-presets.json', names)
        self.assertEqual(json.loads(blobs[names['theme/state.json']['sha256']])['design'], 'hp4')
        self.assertEqual(json.loads(blobs[names['launcher/bar-pins.json']['sha256']])['pins'], [])
        self.assertEqual(set(doc['categories']), catalog.USER_IDS)

    def test_legacy_install_does_not_invent_factory_settings(self):
        with patch.object(backend, 'SYSTEM_FACTORY', self.base/'absent'):
            self.assertFalse(backend.factory_status(self.profile)['system'])
            with self.assertRaises(RuntimeError): backend.factory_snapshot(root=self.profile)

    def test_audio_uses_names_not_recycled_numeric_ids(self):
        value = {'version':1, 'default_sink':'speaker', 'default_source':'mic', 'devices':[
            {'kind':'sink', 'name':'speaker','mute':False,'volume':[40000,41000]},
            {'kind':'source','name':'mic','mute':True,'volume':[20000]}]}
        calls=[]
        def runner(args):
            calls.append(args)
            return json.dumps([{'name':'speaker' if args[-1]=='sinks' else 'mic'}]) if 'list' in args else ''
        audio.restore(value, runner)
        self.assertIn(['set-sink-volume','speaker','40000','41000'], calls)
        self.assertIn(['set-source-mute','mic','1'], calls)
        value['devices'][0]['volume']=[-1]
        with self.assertRaises(ValueError): audio.validate(value)

    def test_window_matching_separates_roles_and_occurrences(self):
        clients = [{'address':'0x1','stableId':'5','class':'editor','initialTitle':'Document','mapped':True},
                   {'address':'0x2','stableId':'8','class':'editor','initialTitle':'Document','mapped':True},
                   {'address':'0x3','stableId':'9','class':'editor','initialTitle':'Document','mapped':True}]
        metadata = {c['address']:{'stableId':c['stableId'], 'role':'dialog' if c['address']=='0x3' else 'main'} for c in clients}
        result = list(windows.identities(clients, metadata))
        self.assertEqual([r[1]['occurrence'] for r in result], [0,1,0]); self.assertEqual(result[2][1]['role'], 'dialog')
        metadata['0x1']['stableId']='old'
        self.assertEqual(len(list(windows.identities(clients, metadata))), 2)

    def test_hex_window_id_captures_and_restores_individual_titlebar(self):
        from effects.window_close import rules
        instance = self.base/'instance'; instance.mkdir()
        rule = dict(rules.DEFAULTS, mode='auto', titlebar=False)
        archive.atomic(instance/'xetal-windowbuttons-kde-rules.json', archive.encode({'version':1,'windows':{'402653198':rule}}))
        client = {'address':'0x1','stableId':'1800000e','class':'editor','initialTitle':'Document','mapped':True}
        metadata = {'0x1':{'stableId':'1800000e','role':'main'}}
        class Hypr:
            def query(self, name): return [client] if name=='clients' else metadata
            def dispatch(self, name, args): pass
        value = windows.capture(Hypr(), instance)
        self.assertFalse(value['windows'][0]['rules']['kde']['titlebar'])
        self.put('profile', windows.FILE, value)
        (instance/'xetal-windowbuttons-kde-rules.json').unlink()
        client['stableId']='1800001f'; metadata['0x1']['stableId']='1800001f'
        restore = windows.Restore(self.profile, instance, Hypr()); restore.update([client],metadata)
        restored = json.loads((instance/'xetal-windowbuttons-kde-rules.json').read_text())
        self.assertIn(str(int('1800001f',16)), restored['windows'])
        self.assertNotIn('402653198', restored['windows'])

    def test_identical_sibling_keeps_identity_when_first_closes(self):
        clients = [{'address':f'0x{n}', 'stableId':str(n), 'class':'editor', 'initialTitle':'Document','mapped':True} for n in (1,2)]
        meta = {c['address']:{'stableId':c['stableId'],'role':'main'} for c in clients}
        assignments = {}; before = list(windows.identities(clients,meta,assignments))
        after = list(windows.identities(clients[1:],meta,assignments))
        self.assertEqual(before[1][1],after[0][1]); self.assertEqual(after[0][1]['occurrence'],1)

    def test_geometry_keeps_normal_rectangle_beneath_maximize(self):
        normal = dict(at=[100,200],size=[800,600],floating=True,fullscreen=0,fullscreenClient=0)
        saved = windows.geometry(normal)
        maximized = dict(normal, at=[0,30],size=[1920,1050],fullscreen=2)
        saved = windows.geometry(maximized,saved)
        self.assertEqual(saved['normal_size'], [800,600]); self.assertEqual(saved['normal_at'],[100,200])
        self.assertEqual(saved['fullscreen'],2)

    def test_power_loss_journal_recovers_before_retry(self):
        path = self.put('profile','sounds/settings.json',{'enabled':True})
        doc,blobs = self.snapshot(['audio']); self.state.mkdir()
        archive.write(self.state/'before.hfsettings',doc,blobs)
        new = self.put('profile','settings_profiles/audio.json',{'version':1})
        archive.atomic(self.state/'journal.json',archive.encode({'status':'applying','paths':[['profile','sounds/settings.json'],['profile','settings_profiles/audio.json']],
                      'roots':{k:str(v) for k,v in self.roots.items()}}))
        path.write_text('partially written settings')
        self.assertTrue(archive.recover_transaction(self.state,self.roots))
        self.assertTrue(json.loads(path.read_text())['enabled']); self.assertFalse(new.exists())

    def test_foreign_local_package_reuses_cache(self):
        cache = self.base/'pkg';cache.mkdir(); package=cache/'local-tool-1-1-x86_64.pkg.tar.zst';package.write_bytes(b'fixture')
        row = {'name':'local-tool','version':'1-1','explicit':True,'source':'foreign'}
        found=packages.cached_foreign([row],['local-tool'],[cache],lambda argv:'local-tool 1-1\n')
        self.assertEqual(found,{'local-tool':package})


if __name__ == '__main__': unittest.main()
