import copy
import json
import unittest
from unittest.mock import patch
import backend
import presets
import runtime
import quick_mix
import test_presets as fixture


class QuickMixTests(unittest.TestCase):
    def setUp(self):
        fixture.PresetTests.setUp(self)
        path=self.root/'cursors/settings.json';path.parent.mkdir()
        path.write_bytes(presets.cursors.encode(dict(presets.cursors.DEFAULTS,size=48,duration=780,intensity=38)))
        self.library=self.root/'theme/custom-presets.json'
        self.library.write_text('{"version":1,"presets":[]}')
    def tearDown(self):fixture.PresetTests.tearDown(self)
    def apply_mix(self,changes):
        baseline,token,_=quick_mix.read()
        with patch.object(backend.Path,'iterdir',return_value=iter(())),patch.object(backend.effect_colors,'reload_active'),patch('cursors.controller.prepare'):
            return quick_mix.apply(dict(baseline,**changes),baseline,token)
    def test_transfer_mix_updates_the_existing_preferences_only(self):
        before=self.library.read_bytes();baseline,_,config=quick_mix.read()
        self.apply_mix({'transfer':'breakpoint','transfer_animation':False})
        value=presets.transfer.load(self.root/'file_jobs/preferences.json')[0]
        self.assertEqual(value['style'],'breakpoint');self.assertFalse(value['animation']['enabled'])
        self.assertEqual(value['information'],config['transfer']['information'])
        self.assertEqual(value['profiles'],config['transfer']['profiles'])
        self.assertEqual(quick_mix.read()[0]['transfer'],'breakpoint')
        self.assertEqual(runtime.design(),'binaryknife');self.assertEqual(self.library.read_bytes(),before)
        self.assertEqual(quick_mix.read()[0]['trail'],baseline['trail'])
    def test_detailed_transfer_changes_are_read_back_and_do_not_replace_other_drafts(self):
        baseline,_,_=quick_mix.read();path=self.root/'file_jobs/preferences.json'
        value,token=presets.transfer.load(path);value['style']='porcelainink';presets.transfer.save(value,token,path)
        saved=quick_mix.read()[0];edited=dict(baseline,trail='glow')
        merged,conflicts=quick_mix.merge(baseline,edited,saved)
        self.assertEqual(merged['transfer'],'porcelainink');self.assertEqual(merged['trail'],'glow');self.assertFalse(conflicts)
        _,conflicts=quick_mix.merge(baseline,dict(baseline,transfer='tidalglass'),saved)
        self.assertEqual(conflicts,['transfer'])
    def test_cursor_and_marker_mix_preserves_detailed_options_and_palette(self):
        colors=(self.root/'theme/current.colors').read_bytes()
        self.apply_mix({'cursor':'sumi','trail':'glow','marker':'curve'})
        value=presets.cursors.load(self.root/'cursors/settings.json')[0]
        self.assertEqual((value['style'],value['trail'],value['size'],value['duration'],value['intensity']),('sumi','glow',48,780,38))
        self.assertEqual(runtime.selection_marker(),'curve');self.assertEqual((self.root/'theme/current.colors').read_bytes(),colors)
        for design in runtime.DESIGNS:self.assertEqual(presets.builtin(design,root=self.root)['theme']['selection_marker'],'none')
    def test_failed_reload_rolls_back_and_external_changes_block_apply(self):
        baseline,token,_=quick_mix.read()
        paths=[runtime.STATE,self.root/'cursors/settings.json',self.root/'file_jobs/preferences.json',self.library]
        before={p:p.read_bytes() for p in paths}
        with patch('cursors.controller.prepare'),patch.object(backend.effect_colors,'reload_active',side_effect=ValueError('Renderer rejected change')):
            with self.assertRaisesRegex(ValueError,'Renderer rejected'):quick_mix.apply(dict(baseline,trail='glow',transfer='breakpoint'),baseline,token)
        for path,data in before.items():self.assertEqual(path.read_bytes(),data)
        path=self.root/'cursors/settings.json';value=json.loads(path.read_text());value['size']=32;path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):quick_mix.apply(dict(baseline,marker='line'),baseline,token)
        self.assertEqual(runtime.STATE.read_bytes(),before[runtime.STATE])
    def test_selection_marker_validates_and_mixes_without_the_layout(self):
        baseline,_,config=quick_mix.read()
        target,parts=quick_mix.plan(config,baseline,dict(baseline,marker='line'))
        self.assertEqual(parts,{'selection'});self.assertEqual(target['theme']['layout'],config['theme']['layout'])
        with self.assertRaises(ValueError):quick_mix.plan(config,baseline,dict(baseline,marker='anything'))

    def test_dock_mix_only_changes_shared_design_and_tracks_detailed_edits(self):
        path=self.root/'effects/minimize/settings.conf';path.parent.mkdir(parents=True)
        original=dict(presets.minimize.DEFAULTS,hide_delay=4600,dock_edge='left',dock_zoom=140,color='#90abcf',size=112,presentation='stack')
        path.write_text(presets.minimize.encode(original))
        colors=(self.root/'theme/current.colors').read_bytes();library=self.library.read_bytes()
        baseline,_,config=quick_mix.read();target,parts=quick_mix.plan(config,baseline,dict(baseline,dock='hollowgrove'))
        self.assertEqual(parts,{'dock'})
        self.apply_mix({'dock':'hollowgrove'})
        actual=presets.minimize.load(path)[0]
        self.assertEqual(actual,dict(original,dock_style='hollowgrove'))
        self.assertEqual((self.root/'theme/current.colors').read_bytes(),colors);self.assertEqual(self.library.read_bytes(),library)
        self.assertEqual(quick_mix.read()[0]['dock'],'hollowgrove')
        baseline=quick_mix.read()[0];path.write_text(presets.minimize.encode(dict(actual,dock_style='candycloud')))
        saved=quick_mix.read()[0]
        merged,conflicts=quick_mix.merge(baseline,dict(baseline,waybar='modern'),saved)
        self.assertEqual(merged['dock'],'candycloud');self.assertEqual(merged['waybar'],'modern');self.assertFalse(conflicts)
        _,conflicts=quick_mix.merge(baseline,dict(baseline,dock='modern'),saved);self.assertEqual(conflicts,['dock'])

    def test_dock_reload_failure_rolls_back_shared_preferences(self):
        path=self.root/'effects/minimize/settings.conf';path.parent.mkdir(parents=True)
        path.write_text(presets.minimize.encode(dict(presets.minimize.DEFAULTS,dock_style='tidalglass')))
        before=path.read_bytes();baseline,token,_=quick_mix.read()
        with patch.object(backend.effect_colors,'reload_active',side_effect=ValueError('Dock reload failed')):
            with self.assertRaisesRegex(ValueError,'Dock reload failed'):
                quick_mix.apply(dict(baseline,dock='breakpoint'),baseline,token)
        self.assertEqual(path.read_bytes(),before)

    def test_quick_and_detailed_pages_share_applied_values_and_persistent_off(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication
        from page import ThemePage
        from cursors import controller
        qt=QApplication.instance() or QApplication([])
        cursor_path=self.root/'cursors/settings.json'
        cursor_load=presets.cursors.load;cursor_save=controller.save
        minimize_path=self.root/'effects/minimize/settings.conf';minimize_path.parent.mkdir(parents=True)
        minimize_path.write_text(presets.minimize.encode(presets.minimize.DEFAULTS));minimize_load=presets.minimize.load
        def run(task,done,failed):
            try:result=task()
            except Exception as error:failed(str(error))
            else:done(result)
        with patch.object(presets.transfer,'PATH',self.root/'file_jobs/preferences.json'), \
             patch.object(presets.minimize,'load',side_effect=lambda path=None:minimize_load(path or minimize_path)), \
             patch.object(presets.cursors,'load',side_effect=lambda path=None:cursor_load(path or cursor_path)), \
             patch.object(controller,'save',side_effect=lambda values,token:cursor_save(values,token,cursor_path)), \
             patch.object(controller,'prepare'),patch.object(controller,'apply'),patch.object(controller.cube,'instance_dir',return_value=self.root), \
             patch.object(backend.effect_colors,'reload_active'),patch.object(backend.Path,'iterdir',return_value=iter(())):
            page=ThemePage(run)
            try:
                mix=page.mix_page;mouse=page.appearance.mouse
                mix.fields['dock'].setValue('hollowgrove');mix.save()
                self.assertFalse(mix.dirty,mix.status.text());self.assertEqual(page.appearance.minimize.dock_style.value(),'hollowgrove')
                mix.open_dock();self.assertIs(page.tabs.currentWidget(),page.appearance)
                self.assertIs(page.appearance.tabs.currentWidget(),page.appearance.minimize)
                detailed=minimize_load(minimize_path)[0];detailed['dock_style']='obsidianforge'
                minimize_path.write_text(presets.minimize.encode(detailed));page.appearance.minimize.refresh();mix.refresh()
                self.assertEqual(mix.fields['dock'].value(),'obsidianforge')
                mix.fields['transfer'].setCurrentIndex(mix.fields['transfer'].findData('breakpoint'));mix.save()
                self.assertFalse(mix.dirty,mix.status.text())
                self.assertEqual(page.file_transfer.style.currentData(),'breakpoint')
                page.file_transfer.style.setCurrentIndex(page.file_transfer.style.findData('porcelainink'));page.file_transfer.save()
                mix.refresh();self.assertEqual(mix.fields['transfer'].currentData(),'porcelainink')
                mix.trail_enabled.setChecked(False);mix.save()
                self.assertFalse(mix.dirty,mix.status.text());self.assertFalse(mouse.enabled.isChecked())
                self.assertEqual(page.cursors.draft['trail'],'none')
                reopened=ThemePage(run)
                try:
                    self.assertFalse(reopened.mix_page.trail_enabled.isChecked())
                    self.assertFalse(reopened.appearance.mouse.enabled.isChecked())
                finally:reopened.deleteLater();qt.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                mouse.cards['glow'].click();mouse.save();mix.refresh();page.cursors.refresh()
                self.assertEqual(mix.fields['trail'].currentData(),'glow')
                self.assertTrue(mix.trail_enabled.isChecked());self.assertEqual(page.cursors.draft['trail'],'glow')
            finally:page.deleteLater();qt.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_busy_page_refresh_retries_after_a_preset_changes_the_trail(self):
        from types import SimpleNamespace
        from PyQt6.QtCore import QEvent,QTimer
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication,QWidget
        from mix_page import MixMatchPage
        qt=QApplication.instance() or QApplication([])
        path=self.root/'cursors/settings.json';value,_=presets.cursors.load(path)
        path.write_bytes(presets.cursors.encode(dict(value,trail='glow')))
        owner=SimpleNamespace(busy=False,start_menu_page=QWidget(),appearance=QWidget(),file_transfer=QWidget(),task_switcher=QWidget())
        mix=MixMatchPage(owner);owner.mix_page=mix;mix.show();QTest.qWait(10)
        try:
            self.assertEqual(mix.fields['trail'].currentData(),'glow')
            owner.busy=True
            with patch.object(backend.Path,'iterdir',return_value=iter(())),patch.object(backend.effect_colors,'reload_active'),patch('cursors.controller.prepare'):
                backend.apply_components(presets.builtin('modern',root=self.root),{'colors','cursors','transfer'},backend.theme_token())
            mix.refresh() # The preset callback and file watcher can both arrive while busy.
            QTimer.singleShot(240,lambda:setattr(owner,'busy',False));QTest.qWait(450)
            self.assertEqual(mix.fields['trail'].currentData(),'follow')
            self.assertEqual(mix.fields['transfer'].currentData(),'modern')
            self.assertTrue(mix.trail_enabled.isChecked());self.assertFalse(mix.dirty)
            self.assertEqual(mix.active_trail.text(),'Active trail: Orbital bloom · follows Xetal Modern')
        finally:mix.deleteLater();qt.sendPostedEvents(None,QEvent.Type.DeferredDelete)


if __name__=='__main__':unittest.main()
