"""Exercise real Qt resolution and save/import behavior in a temporary profile."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'theme')]
from PyQt6.QtGui import QIcon,QImage
from PyQt6.QtWidgets import QApplication
from icon_themes import model,art

APP=QApplication.instance() or QApplication([])


class IconTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        (self.root/'theme').mkdir();(self.root/'theme/state.json').write_text('{"design":"hollowgrove","mode":"dark"}')
        (self.root/'icon_themes').mkdir();(self.root/'icon_themes/packs').symlink_to(model.ROOT/'icon_themes/packs',target_is_directory=True)
        self.set=self.root/'icon_themes/imported/Test-Other';(self.set/'scalable').mkdir(parents=True)
        (self.set/'index.theme').write_text('[Icon Theme]\nName=Test Other\nDirectories=scalable\n\n[scalable]\nSize=64\nType=Scalable\nMinSize=16\nMaxSize=512\n')
        for name,color in [('folder','#bb2255'),('imaginary-app','#22bb55')]:
            (self.set/'scalable'/(name+'.svg')).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="{color}"/></svg>')
        model.ensure(self.root)
    def tearDown(self):self.temporary.cleanup();model.lookup.cache_clear()
    def activate(self,values):
        model.save(values,model.load(self.root)[1],self.root);model.apply_qt(self.root)
    def color(self,name):return QIcon.fromTheme(name).pixmap(64,64).toImage().pixelColor(32,32).name()

    def test_all_themes_render_at_small_and_large_sizes_with_real_aliases(self):
        seen=set()
        for style in art.STYLES:
            values=deepcopy(model.DEFAULTS);values['system']='builtin:'+style;self.activate(values)
            seen.add(QIcon.themeName())
            for name in art.ALIASES:
                with self.subTest(style=style,name=name):
                    icon=QIcon.fromTheme(name);self.assertFalse(icon.isNull())
                    for size in (20,96):self.assertFalse(icon.pixmap(size,size).isNull())
        self.assertEqual(len(seen),len(art.STYLES))

    def test_other_apps_fall_back_to_selected_pack_and_it_can_replace_system_icons(self):
        values=deepcopy(model.DEFAULTS);values['system']='follow';values['other']='theme:Test-Other';self.activate(values)
        self.assertEqual(self.color('imaginary-app'),'#22bb55')
        self.assertNotEqual(self.color('folder'),'#bb2255')
        values['system']='other';self.activate(values);self.assertEqual(self.color('folder'),'#bb2255')
        values['system']='theme:Test-Other';self.activate(values);self.assertEqual(self.color('folder'),'#bb2255')

    def test_individual_image_is_portable_and_wins_across_aliases_and_themes(self):
        original=self.root/'chosen.svg';original.write_bytes((self.set/'scalable/folder.svg').read_bytes())
        relative=model.import_image(original,self.root);original.unlink()
        for style in ('hollowgrove','gildedhollow','other'):
            values=deepcopy(model.DEFAULTS);values['system']='other' if style=='other' else 'builtin:'+style
            values['overrides']={'folder-open':relative};self.activate(values)
            for name in ('folder','folder-open','inode-directory'):self.assertEqual(self.color(name),'#bb2255')
        self.assertTrue(list((self.root/'icon_themes/backups').glob('*.json')))

    def test_follow_and_pinned_sets_survive_palette_changes_and_reopen(self):
        self.activate({**model.DEFAULTS,'system':'follow','other':'auto'})
        model.apply_qt(self.root);before=QIcon.themeName()
        (self.root/'theme/state.json').write_text('{"design":"gildedhollow","mode":"light"}')
        model.apply_qt(self.root);self.assertNotEqual(QIcon.themeName(),before)
        values=deepcopy(model.DEFAULTS);values['system']='builtin:porcelainink';values['other']='theme:Test-Other';self.activate(values)
        pinned=QIcon.themeName();(self.root/'theme/state.json').write_text('{"design":"binaryknife","mode":"dark"}')
        model.apply_qt(self.root);self.assertEqual(QIcon.themeName(),pinned)
        self.assertEqual(model.load(self.root)[0],values)

    def test_old_and_new_readers_never_rewrite_each_others_catalog(self):
        self.activate({**model.DEFAULTS,'system':'follow'})
        path=self.root/'theme/icons.json';before=path.read_bytes();stamp=path.stat().st_mtime_ns
        (self.root/'theme/state.json').write_text('{"design":"mycelium","mode":"dark"}')
        expected=json.loads(before)['resolved']['themes']['mycelium:dark']
        old={name:value for name,value in art.STYLES.items() if name!='mycelium'}
        for _ in range(3):
            with patch.object(art,'STYLES',old):
                self.assertEqual(model.apply_qt(self.root),expected)
            self.assertEqual(model.apply_qt(self.root),expected)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(path.stat().st_mtime_ns,stamp)

    def test_unprepared_or_invalid_icon_info_is_read_only(self):
        path=self.root/'theme/icons.json';path.unlink()
        self.assertEqual(model.info(self.root)['iconTheme'],'Papirus-Dark')
        self.assertFalse(path.exists())
        for text in ('broken','{}','{"resolved":{"themes":[]}}'):
            path.write_text(text)
            self.assertEqual(model.info(self.root)['iconTheme'],'Papirus-Dark')
            self.assertEqual(path.read_text(),text)

    def test_old_icon_editor_refresh_does_not_drop_new_resolved_themes(self):
        from icon_themes.page import IconsPage
        path=self.root/'theme/icons.json';before=path.read_bytes()
        old={name:value for name,value in art.STYLES.items() if name!='mycelium'}
        with patch.object(model,'ROOT',self.root),patch.object(art,'STYLES',old):
            page=IconsPage(lambda work,ok,bad:ok(work()))
            page.refresh()
            self.assertEqual(path.read_bytes(),before)
            page.deleteLater();APP.sendPostedEvents(None,0)

    def test_stale_editor_cannot_overwrite_newer_choices_or_corrupt_preferences(self):
        _,old=model.load(self.root);values={**model.DEFAULTS,'system':'follow'};self.activate(values)
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):model.save(model.DEFAULTS,old,self.root)
        self.assertEqual(model.load(self.root)[0]['system'],'follow')
        path=self.root/'theme/icons.json';path.write_text('broken')
        with self.assertRaises(ValueError):model.ensure(self.root)
        self.assertEqual(path.read_text(),'broken')

    def test_imported_pack_is_self_contained_and_private(self):
        source=self.root/'third-party';shutil.copytree(self.set,source)
        (source/'scalable/alias.svg').symlink_to('folder.svg')
        name=model.import_pack(source,self.root);shutil.rmtree(source)
        self.assertIn(name,model.installed(self.root))
        self.assertTrue((self.root/'icon_themes/imported'/name/'scalable/alias.svg').is_file())
        values={**model.DEFAULTS,'system':'theme:'+name};self.activate(values)
        self.assertEqual(self.color('folder'),'#bb2255')

    def test_individual_paths_cannot_point_outside_the_profile(self):
        for path in ('/tmp/icon.png','icon_themes/custom/../outside.svg','icon_themes/custom/other.svg'):
            with self.assertRaises(ValueError):model.validate({**model.DEFAULTS,'overrides':{'folder':path}})

    def test_legacy_fusion_shortcuts_follow_icons_but_explicit_shortcut_edits_win(self):
        self.assertEqual(model.application_name('My VM.desktop','/profile/kvm/icon.svg'),'xetal-kvm-settings')
        self.assertEqual(model.application_name('xetal-files.desktop','/my/icon.png',custom=True),'')
        from gi.repository import Gio
        icon=Gio.ThemedIcon.new_from_names(['xetal-kvm-settings','virt-manager','computer'])
        self.assertIn('computer',icon.get_names())

    def test_gallery_and_individual_edits_are_previews_until_apply(self):
        from icon_themes.page import IconsPage
        with patch.object(model,'ROOT',self.root):
            page=IconsPage(lambda work,ok,bad:ok(work()))
            before=(self.root/'theme/icons.json').read_bytes()
            for i in range(page.system_list.count()):
                if page.system_list.item(i).data(256)=='builtin:gildedhollow':page.system_list.setCurrentRow(i);break
            self.assertTrue(page.dirty);self.assertEqual(page.draft['system'],'builtin:gildedhollow')
            page.individual.setCurrentRow(0);page.single_set.setCurrentIndex(page.single_set.findData('porcelainink'));page.borrow()
            self.assertIn('folder',page.draft['overrides']);self.assertEqual((self.root/'theme/icons.json').read_bytes(),before)
            page.save();self.assertFalse(page.dirty)
            reopened=IconsPage(lambda work,ok,bad:ok(work()));self.assertEqual(reopened.draft,page.draft)
            reopened.reset_icon();self.assertTrue(reopened.dirty);self.assertIn('folder',model.load(self.root)[0]['overrides'])
            page.close();reopened.close();page.deleteLater();reopened.deleteLater();APP.processEvents()

    def test_preset_keeps_other_icons_and_individual_choices_when_system_design_changes(self):
        import runtime,presets
        relative=model.import_image(self.set/'scalable/folder.svg',self.root)
        values={**deepcopy(model.DEFAULTS),'system':'follow','other':'theme:Test-Other','overrides':{'user-home':relative}}
        self.activate(values)
        target={'theme':{'design':'gildedhollow'},'icons':{**values,'system':'builtin:gildedhollow'}}
        files,_=presets.resources(self.root,target,{'icons'},'hollowgrove')
        result=model.validate(json.loads(files[self.root/'theme/icons.json']))
        self.assertEqual(result['overrides'],values['overrides']);self.assertEqual(result['other'],values['other'])
        files,_=presets.resources(self.root,target,{'colors'},'hollowgrove')
        self.assertEqual(json.loads(files[self.root/'theme/icons.json'])['system'],'builtin:hollowgrove')


if __name__=='__main__':unittest.main()
