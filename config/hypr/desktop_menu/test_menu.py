"""Menu documents, action routing and hotkey transactions use disposable files."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import menu_config as config
import menu_hotkeys as hotkeys
import run


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.store=config.Store(self.root/'menu.json',self.root/'history')
        self.document=config.defaults(); self.saved=self.store.save(self.document,'missing')
        self.records=hotkeys.keys.parse('bind = SUPER, Q, exec, kitty\nsubmap = hypr-control-capture\nbind = , Escape, submap, reset\nsubmap = reset\n')
        self.records[-1].protected=True
        (self.root/'hyprland.conf').write_text('$mainMod = SUPER\n'+hotkeys.keys.SOURCE+'\n')
        (self.root/'keybindings.conf').write_text(hotkeys.keys.serialize(self.records))
        self.calls=[]
        def runner(argv):
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv,0,'config ok' if argv[0]=='Hyprland' else ('ok' if argv[1]=='reload' else ''),'')
        self.keys=hotkeys.keys.Store(self.root,self.root/'keys-history',runner)

    def test_stock_order_migrates_once_without_changing_custom_layouts(self):
        draft=copy.deepcopy(self.document); draft.pop('layout_version', None)
        draft['items'][1],draft['items'][2]=draft['items'][2],draft['items'][1]
        self.store.save(draft,self.saved)
        restored,digest=self.store.load()
        self.assertEqual([item['id'] for item in restored['items']],['file-manager','displays','wallpaper'])
        restored['items'].reverse()
        self.store.save(restored,digest)
        self.assertEqual(self.store.load()[0]['items'],restored['items'])

    def test_nested_roundtrip_and_disabled_parent(self):
        item=config.new_item(label='Quoted command',value='/usr/bin/printf "%s" "hello world"')
        group=config.new_item('submenu',label='Tools',children=[item,config.new_item('separator'),config.new_item('spacer'),config.new_item('column')])
        self.document['items'].append(group)
        self.assertEqual(config.decode(config.encode(self.document)),self.document)
        group['enabled']=False
        self.assertIsNone(config.find(self.document,item['id'],active=True))
        self.assertEqual(config.find(self.document,item['id'])['label'],'Quoted command')

    def test_rejects_invalid_presets_before_any_write(self):
        before=self.store.path.read_bytes()
        invalid=[]
        data=copy.deepcopy(self.document);data['items'].append(copy.deepcopy(data['items'][0]));invalid.append(data)
        for field,value in [('width',99999),('accent','red; background:url(file:///tmp/a)'),('font_family','font"; color:red')]:
            data=copy.deepcopy(self.document);data['style'][field]=value;invalid.append(data)
        data=copy.deepcopy(self.document);data['items'][0]['children']=[config.new_item('separator')];invalid.append(data)
        data=copy.deepcopy(self.document);data['items'].append(config.new_item(target='url',value='file:///etc/passwd'));invalid.append(data)
        for data in invalid:
            with self.assertRaises(ValueError):self.store.save(data,self.saved)
        self.assertEqual(self.store.path.read_bytes(),before)
        with self.assertRaises(ValueError):config.decode(b' '*1048577)

    def test_export_and_read_do_not_activate_changes(self):
        draft=copy.deepcopy(self.document);draft['style']['width']=350
        with patch.object(subprocess,'Popen') as launch:
            self.store.export(self.root/'preset.json',draft)
            self.assertEqual(config.read_preset(self.root/'preset.json'),draft);launch.assert_not_called()
        self.assertEqual(self.store.load()[0],self.document)
        with self.assertRaisesRegex(ValueError,'Apply'):self.store.export(self.store.path,draft)
        alias=self.root/'alias.json';alias.symlink_to(self.store.path)
        with self.assertRaisesRegex(ValueError,'Apply'):self.store.export(alias,draft)

    def test_external_edit_is_not_overwritten_and_backups_are_exact(self):
        original=self.store.path.read_bytes();draft=copy.deepcopy(self.document);draft['style']['width']=300
        new_hash=self.store.save(draft,self.saved)
        self.assertEqual(next((self.root/'history').glob('context-menu-*')).read_bytes(),original)
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):self.store.save(self.document,self.saved)
        self.assertEqual(self.store.load()[1],new_hash)

    def test_runtime_resolves_current_action_through_the_default_folder_launcher(self):
        launch=Mock()
        run.execute('file-manager',self.store,launch)
        argv=launch.call_args.args[0];self.assertTrue(argv[0].endswith('/scripts/file-manager.sh'))
        self.assertNotIn('xdg-open',argv)
        self.document['items'][0].update(target='command',value='/usr/bin/printf "%s" "a b; $(do-not-run)"',directory=str(self.root),terminal=True)
        self.store.save(self.document,self.saved);run.execute('file-manager',self.store,launch)
        argv=launch.call_args.args[0];self.assertEqual(argv[0],'kitty');self.assertIn('--hold',argv)
        self.assertEqual(argv[-3:],['/usr/bin/printf','%s','a b; $(do-not-run)']);self.assertEqual(launch.call_args.kwargs['cwd'],str(self.root))

    def test_disabled_removed_and_structural_items_cannot_launch(self):
        launch=Mock(); self.document['enabled']=False; self.store.save(self.document,self.saved)
        for ident in ('file-manager','removed'):
            with self.assertRaises(ValueError):run.execute(ident,self.store,launch)
        launch.assert_not_called()

    def binding(self,ident='file-manager'):
        records=hotkeys.edited(self.records,hotkeys.Entry(config.find(self.document,ident)),None,'SUPER CTRL','F10')
        self.keys.path.write_text(hotkeys.keys.serialize(records));return records

    def test_hotkey_matches_identity_after_rename_and_preserves_shared_safeguards(self):
        records=self.binding();entry=config.find(self.document,'file-manager');entry['label']='Files renamed'
        self.assertEqual(hotkeys.matches(hotkeys.Entry(entry),records,{}),[records[-1]])
        edited=hotkeys.edited(records,hotkeys.Entry(entry),records[-1].id,'SUPER CTRL','F11')
        _,expected=self.keys.load();self.keys.apply(edited,expected)
        current,_=self.keys.load();self.assertEqual(current[1],self.records[1]);self.assertEqual(current[-1].category,'Applications')
        conflict=hotkeys.edited(current,hotkeys.Entry(entry),current[-1].id,'SUPER','Q')
        with self.assertRaises(hotkeys.keys.ConfigError):self.keys.check(conflict,self.keys.main.read_text())

    def test_delete_prunes_only_its_managed_hotkey(self):
        self.binding();draft=copy.deepcopy(self.document);draft['items'].pop(0)
        hotkeys.save_menu(self.store,draft,self.saved,self.keys)
        self.assertEqual(self.keys.load()[0],self.records)
        self.assertEqual(self.store.load()[0],draft)
        self.assertEqual(self.calls[-2:],[['hyprctl','reload'],['hyprctl','configerrors']])

    def test_failed_hotkey_apply_rolls_back_menu(self):
        self.binding();draft=copy.deepcopy(self.document);draft['items'].pop(0)
        with patch.object(self.keys,'apply',side_effect=ValueError('external edit')):
            with self.assertRaisesRegex(ValueError,'rolled back'):hotkeys.save_menu(self.store,draft,self.saved,self.keys)
        self.assertEqual(self.store.load()[0],self.document)

    def test_visual_changes_do_not_write_or_reload_hotkeys(self):
        before=self.keys.path.read_bytes();draft=copy.deepcopy(self.document);draft['style']['accent_width']=6
        hotkeys.save_menu(self.store,draft,self.saved,self.keys)
        self.assertEqual(self.keys.path.read_bytes(),before);self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
