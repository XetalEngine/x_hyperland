"""Visual settings transactions, capture identity and UI interaction regressions."""
from copy import deepcopy
import importlib.util
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'config/hypr'
sys.path[:0]=[str(ROOT),str(ROOT/'theme')]
from visuals import model,controller
from visuals.service import CaptureState,resolve_hover,current_request
from visuals.overview import clients_for_workspace,move_window,Overview
from visuals.page import VisualsPage
sys.path.insert(0,str(ROOT/'control_center'))
from visuals.appearance import AppearancePage, INITIAL
from compat.hypr_compat import Renderer
from PyQt6.QtWidgets import QApplication
QT=QApplication.instance() or QApplication([])

CLIENT=dict(address='0x123',pid=123,title='Example',**{'class':'example'},mapped=True,hidden=False,workspace={'id':2,'name':'2'})


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'theme').mkdir();(self.root/'theme/state.json').write_text('{"design":"raw"}')
        self.settings=deepcopy(model.DEFAULTS)

    def test_default_focus_coordinates_headers_glow_and_shadows_only(self):
        rendered=model.native_settings(self.settings,self.root)
        self.assertTrue(self.settings['focus']['enabled'])
        self.assertTrue(rendered['decoration.glow.enabled'])
        self.assertEqual(rendered['decoration.glow.range'],3)
        self.assertTrue(rendered['decoration.shadow.enabled'])
        self.assertEqual(rendered['decoration.shadow.range'],8)
        self.assertEqual(self.settings['focus']['exceptions'],[])
        self.assertNotIn('animations.enabled',rendered)
        self.assertNotIn('decoration.blur.enabled',rendered)
        self.assertEqual(model.load(self.root)[0],model.DEFAULTS)
        self.assertFalse((self.root/'visuals/settings.json').exists())

    def test_profiles_and_reduced_motion_are_non_destructive(self):
        default_focus=model.native_settings(self.settings,self.root)
        self.settings['themes']['raw']=deepcopy(model.THEME)
        m=self.settings['themes']['raw']['material'];m.update(enabled=True,variant='water',size=12,passes=4)
        before=deepcopy(self.settings)
        self.settings.update(quality='balanced',reduced_motion=True)
        result=model.native_settings(self.settings,self.root)
        self.assertEqual(result,default_focus)
        self.assertEqual(self.settings['themes'],before['themes'])
        self.settings.update(quality='current',reduced_motion=False)
        restored=model.native_settings(self.settings,self.root)
        self.assertEqual(restored,default_focus)
        self.assertNotIn('animations.enabled',restored)
        self.settings['quality']='lightweight'
        self.assertEqual(model.native_settings(self.settings,self.root),default_focus)
        self.assertFalse(model.active_settings(self.settings)['hover_previews'])

    def test_focus_preferences_survive_switching_themes(self):
        self.settings['focus'].update(enabled=True,border=3,shadow=9,glow=True,glow_size=4,exceptions=['mpv'])
        (self.root/'theme/state.json').write_text('{"design":"polaris"}')
        before=model.native_settings(self.settings,self.root)
        (self.root/'theme/state.json').write_text('{"design":"starcraft"}')
        after=model.native_settings(self.settings,self.root)
        for key in ('general.border_size','decoration.shadow.range','decoration.glow.range','decoration.glow.enabled'):
            self.assertEqual(before[key],after[key])
        self.assertEqual(after['general.border_size'],3)

    def test_toggling_shadows_keeps_their_saved_size(self):
        self.settings['focus'].update(enabled=True,shadow=9)
        for enabled in (False,True):
            self.settings['appearance']['decoration:shadow:enabled']=enabled
            result=model.native_settings(self.settings,self.root)
            self.assertEqual(result['decoration.shadow.enabled'],enabled)
            self.assertEqual(result['decoration.shadow.range'],9)

    def test_old_focus_preferences_are_promoted_without_discarding_saved_materials(self):
        legacy=deepcopy(model.DEFAULTS);legacy.pop('focus');legacy.pop('appearance');legacy['version']=1
        legacy['themes']['starcraft']=deepcopy(model.THEME)
        legacy['themes']['starcraft']['focus'].update(enabled=True,glow=True,border=1,shadow=8,glow_size=3)
        legacy['themes']['starcraft']['material']['variant']='water'
        upgraded=model.upgrade(legacy,'starcraft')
        self.assertEqual(upgraded['focus'],legacy['themes']['starcraft']['focus'])
        self.assertEqual(upgraded['themes'],legacy['themes'])
        self.assertEqual(upgraded['version'],2)

    def test_invalid_values_rejected(self):
        for key,value in [('quality',[]),('quality','extreme'),('hover_previews',1),('preview_fps',True),('preview_size',100000)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):model.validate({**self.settings,key:value})
        self.settings['themes']['raw']=deepcopy(model.THEME)
        for value in ('unknown',[],None):
            self.settings['themes']['raw']['material']['variant']=value
            with self.assertRaises(ValueError):model.validate(self.settings)

    def test_malformed_optional_preferences_cannot_break_login(self):
        (self.root/'hyprland.conf').write_text('animations:enabled = true\n')
        (self.root/'visuals').mkdir();(self.root/'visuals/model.py').touch();(self.root/'visuals/settings.json').write_text('{broken')
        source=Renderer(self.root).render()
        self.assertIn('using existing desktop effects',source)
        self.assertIn('hyperfusion-disable-native-wobble',source)

    def test_native_appearance_and_focus_options_validate(self):
        self.settings['focus'].update(enabled=True,glow=True,exceptions=['app.with[punctuation]'])
        self.settings['appearance']=dict(INITIAL)
        for border in (0,3,10):
            self.settings['focus']['border']=border
            path=self.root/'hyprland.lua';path.write_text(model.lua_config(self.settings,self.root))
            result=subprocess.run(['Hyprland','--verify-config','--config',str(path)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.instance=self.root/'session';(self.instance/'fusion-visuals').mkdir(parents=True)
        self.path=self.root/'visuals/settings.json';self.path.parent.mkdir()
        existing=deepcopy(model.DEFAULTS);existing['focus']['enabled']=False
        self.original=json.dumps(existing,indent=2)+'\n';self.path.write_text(self.original)
        self.settings,self.token=model.load(self.root);self.settings['focus']['enabled']=True
        for name,value in [('instance',self.instance),('verify',None),('reload',None)]:
            p=patch.object(controller,name,return_value=value);setattr(self,name+'_mock',p.start());self.addCleanup(p.stop)
        p=patch.object(controller.subprocess,'Popen');p.start();self.addCleanup(p.stop)

    def test_preview_discard_never_changes_saved_preferences(self):
        token=controller.preview(self.settings,self.root)
        self.assertTrue(controller.runtime_settings(self.root)['focus']['enabled'])
        self.assertEqual(self.path.read_text(),self.original)
        controller.discard('wrong-token',self.root)
        self.assertTrue(controller.runtime_settings(self.root)['focus']['enabled'])
        controller.discard(token,self.root)
        self.assertFalse(controller.runtime_settings(self.root)['focus']['enabled'])
        self.assertEqual(self.path.read_text(),self.original)

    def test_guard_expires_preview_and_reloads(self):
        token=controller.preview(self.settings,self.root,seconds=-1)
        controller.expire(token,self.root)
        self.assertFalse((self.instance/'fusion-visuals/preview.json').exists())
        self.assertEqual(self.reload_mock.call_count,2)

    def test_failed_preview_restores_saved_state(self):
        self.reload_mock.side_effect=[ValueError('rejected'),None]
        with self.assertRaisesRegex(ValueError,'rejected'):controller.preview(self.settings,self.root)
        self.assertFalse((self.instance/'fusion-visuals/preview.json').exists())
        self.assertEqual(self.path.read_text(),self.original)

    def test_failed_apply_restores_file(self):
        self.reload_mock.side_effect=[ValueError('rejected'),None]
        with self.assertRaisesRegex(ValueError,'rejected'):controller.save(self.settings,self.token,self.root)
        self.assertEqual(self.path.read_text(),self.original)

    def test_other_editor_and_other_preview_are_protected(self):
        self.path.write_text(self.original+'\n')
        with self.assertRaisesRegex(ValueError,'changed in another'):controller.save(self.settings,self.token,self.root)
        _,self.token=model.load(self.root)
        lease=self.instance/'fusion-visuals/preview.json'
        lease.write_text(json.dumps({'expires':time.time()+60,'pid':os.getppid()}))
        with self.assertRaisesRegex(ValueError,'Another visual preview'):controller.save(self.settings,self.token,self.root)
        with self.assertRaisesRegex(ValueError,'Another visual preview'):controller.preview(self.settings,self.root)

    def test_successful_apply_ends_preview(self):
        controller.preview(self.settings,self.root)
        values,_=controller.save(self.settings,self.token,self.root)
        self.assertTrue(values['focus']['enabled']);self.assertFalse((self.instance/'fusion-visuals/preview.json').exists())


class CaptureTests(unittest.TestCase):
    def test_overlapping_screenshots_on_different_monitors_stay_quiet(self):
        state=CaptureState()
        for n in range(20):
            state.event(f'screencastv2>>1,monitor,DP-{n%3}',n*.3)
            if n:state.event(f'screencastv2>>0,monitor,DP-{(n-1)%3}',n*.3+.1)
            self.assertFalse(state.active(n*.3+.2))

    def test_window_thumbnails_and_screenshots_do_not_trigger_sharing_mode(self):
        state=CaptureState();state.event('screencastv2>>1,window,Preview',0)
        self.assertFalse(state.active(10))
        state.event('screencastv2>>1,monitor,DP-1',10);self.assertFalse(state.active(10.5))
        state.event('screencastv2>>0,monitor,DP-1',10.6);self.assertFalse(state.active(20))

    def test_multiple_streams_restore_only_after_last_stream(self):
        state=CaptureState()
        for _ in range(2):state.event('screencastv2>>1,monitor,DP-1',0)
        state.event('screencastv2>>1,workspace,Work, desk',.2)
        self.assertTrue(state.active(1.1))
        for _ in range(2):state.event('screencastv2>>0,monitor,DP-1',2)
        self.assertTrue(state.active(3));self.assertIn('Work, desk',state.caption())
        state.event('screencastv2>>0,workspace,Work, desk',4);self.assertFalse(state.active(5))
        state.event('screencastv2>>0,workspace,Work, desk',6);self.assertFalse(state.active(7))

    def test_hover_never_guesses_between_duplicate_titles(self):
        request={'title':'Example','workspace':2}
        self.assertEqual(resolve_hover(request,[CLIENT]),CLIENT)
        self.assertIsNone(resolve_hover(request,[CLIENT,{**CLIENT,'address':'0x234'}]))
        self.assertIsNone(resolve_hover({'title':'Example','workspace':3},[CLIENT]))
        minimized={**CLIENT,'hidden':True,'workspace':{'id':-20,'name':'special:xetal-minimized-ws-2'}}
        self.assertEqual(resolve_hover(request,[minimized]),minimized)

    def test_expired_hover_and_malformed_requests_are_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'fusion-hover.json'
            for value in ({'show':False}, {'show':True,'time':time.time()-5},[],{'show':True,'time':'bad'}):
                path.write_text(json.dumps(value));self.assertEqual(current_request(root),{})


class OverviewTests(unittest.TestCase):
    def test_minimized_windows_remain_in_their_original_workspace(self):
        minimized={**CLIENT,'hidden':True,'workspace':{'id':-20,'name':'special:xetal-minimized-ws-2'}}
        overlay={**CLIENT,'class':'fusion-visual-service'}
        self.assertEqual(clients_for_workspace([minimized,overlay],2),[minimized])

    def test_move_revalidates_window_identity_and_destination(self):
        def ctl(*args):
            if args==('-j','clients'):return json.dumps([CLIENT])
            if args==('-j','workspaces'):return '[{"id":3}]'
            return 'ok'
        with patch('visuals.overview.controller.ctl',side_effect=ctl) as mock:
            self.assertEqual(move_window({'address':'0x123','pid':123},3),'ok')
            mock.assert_called_with('dispatch','movetoworkspacesilent','3,address:0x123')
            for identity,target in (({'address':'0x123','pid':124},3),({'address':'0x123','pid':123},4)):
                with self.assertRaises(ValueError):move_window(identity,target)

    def test_search_and_drag_hold_keep_cards_stable(self):
        window=Overview(lambda *args:None)
        self.addCleanup(window.close)
        window.data={'monitors':[{'id':0,'name':'DP-1'}],'workspaces':[{'id':2,'name':'2','monitor':'DP-1'}],'clients':[CLIENT]}
        window.rebuild();self.assertEqual(len(window.cards),1)
        window.search.setText('missing');self.assertEqual(len(window.cards),0)
        window.search.setText('example');self.assertEqual(len(window.cards),1)
        original=window.cards[0];window.dragging=True;window.rebuild();self.assertIs(window.cards[0],original)
        window.dragging=False;window.close();QT.processEvents()


class PageTests(unittest.TestCase):
    def test_appearance_edits_preview_discard_and_save_global_focus(self):
        saved=[]
        def run(fn,done,failed):
            try:done(fn())
            except Exception as error:failed(str(error))
        page=AppearancePage(run);self.addCleanup(page.close)
        baseline=deepcopy(model.DEFAULTS)
        page.loaded((dict(INITIAL),(baseline,'token')))
        page.coordinate.setChecked(True);page.glow.setChecked(True);page.glow_size.setValue(5)
        page.fields['general:border_size'].setValue(3)
        self.assertTrue(page.dirty);self.assertEqual(page.preview.focus['glow_size'],5)
        def read(keys):
            values={**INITIAL,**(saved[-1]['appearance'] if saved else {})}
            return {key:values[key] for key in keys}
        with patch('visuals.appearance.settings.read_options',side_effect=read),patch.object(controller,'save',side_effect=lambda values,token:saved.append(deepcopy(values))),patch.object(model,'load',side_effect=lambda:(saved[-1],'new-token')):
            page.save()
            self.assertFalse(page.dirty)
            page.coordinate.setChecked(False);page.save()
        self.assertFalse(saved[1]['focus']['enabled'])
        self.assertEqual(saved[1]['appearance']['general:border_size'],3)
        self.assertEqual(saved[1]['appearance']['decoration:shadow:range'],INITIAL['decoration:shadow:range'])
        self.assertEqual(saved[0]['focus']['border'],3);self.assertTrue(saved[0]['focus']['glow'])
        self.assertEqual(saved[0]['appearance']['general:border_size'],3)
        page.glow_size.setValue(9);page.reset();self.assertEqual(page.glow_size.value(),5)

    def test_parameter_edits_survive_material_switch_and_discard(self):
        def run(fn,done,failed):
            try:done(fn())
            except Exception as error:failed(str(error))
        with patch('visuals.page.model.load',return_value=(deepcopy(model.DEFAULTS),'token')),patch('visuals.page.controller.discard'):
            page=VisualsPage(run);self.addCleanup(page.close)
            page.material.setChecked(True);page.variant.setCurrentIndex(page.variant.findData('acrylic'))
            page.parameter_controls['acrylic','clarity'].setValue(.5)
            page.variant.setCurrentIndex(page.variant.findData('water'))
            page.variant.setCurrentIndex(page.variant.findData('acrylic'))
            self.assertEqual(page.parameter_controls['acrylic','clarity'].value(),.5)
            self.assertTrue(page.dirty);page.discard();self.assertFalse(page.dirty)
            self.assertFalse(page.material.isChecked());page.close();QT.processEvents()


class NativePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.binary=cls.root/'probe'
        source='#include "'+str(ROOT/'runtime/visual_policy_057.hpp')+'"\n#include <iostream>\nint main(int argc,char**argv){auto p=FusionVisuals::read(argv[1]);std::cout<<p.fps<<" "<<p.width<<" "<<p.hover<<" "<<p.lightweight;}'
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','json-c'],text=True))
        result=subprocess.run(['g++','-std=c++23','-x','c++','-','-o',str(cls.binary),*flags],input=source,text=True,capture_output=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def policy(self,value):
        path=self.root/'profile/visuals/settings.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))
        result=subprocess.check_output([str(self.binary),str(path.parent.parent)],text=True,
                                       env={**os.environ,'HYPRLAND_INSTANCE_SIGNATURE':''})
        return tuple(map(int,result.split()))
    def test_missing_and_malformed_fields_keep_native_defaults(self):
        self.assertEqual(self.policy({}),(144,360,0,0))
        self.assertEqual(self.policy({'quality':None,'preview_size':None,'hover_previews':None}),(144,360,0,0))
        self.assertEqual(self.policy([]),(144,360,0,0))
    def test_caps_and_explicit_hover_preferences(self):
        self.assertEqual(self.policy({'quality':'lightweight','preview_size':480,'hover_previews':True}),(144,360,0,0))
        self.assertEqual(self.policy({'quality':'balanced'}),(144,360,0,0))
        self.assertEqual(self.policy({'quality':'full'}),(144,360,0,0))


class InstallTests(unittest.TestCase):
    def test_retiring_preview_shortcut_keeps_user_assignments_and_is_idempotent(self):
        spec=importlib.util.spec_from_file_location('visual_installer',REPO/'tools/install-visuals-preview.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for text in ('bind = SUPER, O, exec, my-app\n','bind = $mainMod, o, exec, my-app\n'):
            self.assertEqual(module.retire_overview_binding(text),(text,False))
        original='bind = SUPER, K, exec, settings\n'
        updated,removed=module.retire_overview_binding(original+module.HOTKEY)
        self.assertTrue(removed);self.assertEqual(updated,original)
        self.assertEqual(module.retire_overview_binding(updated),(updated,False))

    def test_visual_preferences_are_personal_update_data(self):
        from updates.file_policy import policy
        self.assertEqual(policy('visuals/settings.json'),'preferences')


if __name__=='__main__':unittest.main()
