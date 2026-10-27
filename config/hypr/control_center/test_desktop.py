"""Exercise display rollback and settings transactions without changing real outputs."""
import copy
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch,Mock
import desktop_settings as settings
import display_guard


def monitors():
    return [{'name':'DP-1','model':'Left','width':1920,'height':1080,'refreshRate':60,'x':0,'y':0,'scale':1,'transform':0,
             'availableModes':['1920x1080@60.00Hz','1920x1080@144.00Hz']},
            {'name':'DP-2','model':'Right','width':2560,'height':1440,'refreshRate':60,'x':1920,'y':0,'scale':1,'transform':0,
             'availableModes':['2560x1440@60.00Hz','2560x1440@144.00Hz']}]


class LayoutTests(unittest.TestCase):
    def setUp(self):self.before=settings.display_models(monitors());self.draft=copy.deepcopy(self.before)
    def test_overlap_and_all_disabled_are_rejected(self):
        self.draft[1]['x']=1900
        with self.assertRaisesRegex(ValueError,'overlap'):settings.validate_displays(self.draft,self.before)
        for m in self.draft:m['enabled']=False
        with self.assertRaisesRegex(ValueError,'at least one'):settings.validate_displays(self.draft,self.before)
    def test_rotation_scale_and_mirroring(self):
        self.draft[0].update(transform=1,scale=1.5)
        self.assertEqual(settings.logical_size(self.draft[0]),(720,1280))
        self.draft[1].update(mirror='DP-1',x=0)
        settings.validate_displays(self.draft,self.before)
        self.draft[0]['mirror']='DP-2'
        with self.assertRaisesRegex(ValueError,'mirrored display'):settings.validate_displays(self.draft,self.before)
    def test_unsupported_mode_and_invalid_scale(self):
        self.draft[0]['rate']=120
        with self.assertRaisesRegex(ValueError,'supported'):settings.validate_displays(self.draft,self.before)
        self.draft[0].update(rate=60,scale=float('nan'))
        with self.assertRaisesRegex(ValueError,'scaling'):settings.validate_displays(self.draft,self.before)
    def test_hotplug_invalidates_confirmation(self):
        self.assertFalse(settings.matches_layout(self.before,self.before+[dict(self.before[0],name='HDMI-1')]))
    def test_disconnected_saved_outputs_are_preserved(self):
        config=settings.display_config(self.draft,'# personal\nmonitor = HDMI-A-1,1920x1080@60,0x1440,1\nmonitor = DP-1,disable\n')
        self.assertIn('HDMI-A-1,1920',config);self.assertIn('# personal',config);self.assertEqual(config.count('monitor = DP-1,'),1)


class GuardianTests(unittest.TestCase):
    def run_trial(self,decision='revert',failure=None):
        before=settings.display_models(monitors());draft=copy.deepcopy(before);draft[0]['rate']=144
        request={'models':draft,'baseline':settings.layout_state(before),'token':'original'}
        store=Mock();store.load.return_value=('# config','original')
        events=[]
        if failure=='save':store.save.side_effect=ValueError('Save failed')
        runtime=Mock(side_effect=[ValueError('driver failed'),None] if failure=='driver' else None)
        with patch.object(settings,'Store',return_value=store),patch.object(settings,'monitors',return_value=monitors()),\
             patch.object(settings,'apply_runtime',runtime),patch.object(settings,'matches_layout',return_value=True),\
             patch.object(display_guard,'decide',return_value=decision):
            if failure:
                with self.assertRaises(ValueError):display_guard.trial(request,None,None,emit=lambda event,**kw:events.append(event))
            else:display_guard.trial(request,None,None,emit=lambda event,**kw:events.append(event))
        return store,runtime,events,before,draft
    def test_keep_saves_only_after_confirmation(self):
        store,runtime,events,before,draft=self.run_trial('keep')
        store.check.assert_called_once();store.save.assert_called_once();self.assertEqual(runtime.call_args_list[0].args[0],draft)
        self.assertEqual(runtime.call_count,1);self.assertEqual(events,['preview','kept'])
    def test_cancel_and_timeout_restore_without_saving(self):
        for decision in ['revert','timeout']:
            store,runtime,events,before,_=self.run_trial(decision)
            store.save.assert_not_called();self.assertEqual(runtime.call_args.args[0],before);self.assertEqual(events,['preview','reverted'])
    def test_partial_driver_failure_and_save_failure_restore(self):
        for failure in ['driver','save']:
            store,runtime,events,before,_=self.run_trial('keep',failure)
            self.assertEqual(runtime.call_args.args[0],before)
    def test_logout_does_not_write_to_another_session(self):
        store,runtime,events,*_=self.run_trial('session-ended')
        store.save.assert_not_called();self.assertEqual(runtime.call_count,1)
    def test_parent_eof_and_timer(self):
        a,b=socket.socketpair();reader,writer=os.pipe()
        try:
            with os.fdopen(reader,'r') as stream:
                self.assertEqual(display_guard.decide(stream,a,.005),'timeout')
                os.close(writer);writer=None
                self.assertEqual(display_guard.decide(stream,a,.1),'revert')
        finally:
            if writer is not None:os.close(writer)
            a.close();b.close()
    def test_changed_baseline_prevents_any_preview(self):
        before=settings.display_models(monitors());store=Mock();store.load.return_value=('', 'token')
        with patch.object(settings,'Store',return_value=store),patch.object(settings,'monitors',return_value=monitors()),patch.object(settings,'apply_runtime') as apply:
            with self.assertRaisesRegex(ValueError,'changed while'):
                display_guard.trial({'token':'token','baseline':[],'models':before},None,None)
            apply.assert_not_called()


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'control_center').mkdir()
        (self.root/'hyprland.conf').write_text('source = ~/.config/hypr/control_center/input.conf\n')
        (self.root/'control_center/input.conf').write_text('input:sensitivity = 0\n')
        self.run=Mock(side_effect=lambda args:'config ok' if args[0]=='Hyprland' else 'ok' if args[-1]=='reload' else '')
        self.store=settings.Store('input',self.root,self.root/'state',self.run)
    def tearDown(self):self.temp.cleanup()
    def test_failed_reload_restores_exact_content(self):
        before,token=self.store.load();self.run.side_effect=['config ok','error','ok']
        with self.assertRaises(ValueError):self.store.save('input:sensitivity = .2\n',token)
        self.assertEqual(self.store.path.read_text(),before)
    def test_external_main_or_page_edit_is_never_overwritten(self):
        _,token=self.store.load();self.store.main.write_text(self.store.main.read_text()+'# other edit\n')
        with self.assertRaisesRegex(ValueError,'outside'):self.store.save('input:sensitivity = .2\n',token)
        self.run.assert_not_called()


if __name__=='__main__':unittest.main()
