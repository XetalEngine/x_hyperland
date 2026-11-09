from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from service import Store, Tracker, identity


class MemoryTests(unittest.TestCase):
    def test_forced_workspace_never_receives_an_app_mode_restore(self):
        hypr=Mock();tracker=Tracker(hypr,None)
        for layout in ('tile','floating'):
            for phase in range(3):
                self.assertFalse(tracker.restore({'address':'0x123'}, {'workspace_layout':layout}, {}, {}, phase))
        self.assertFalse(hypr.mock_calls)

    def test_explicit_launcher_choices_never_receive_a_later_restore(self):
        hypr=Mock();tracker=Tracker(hypr,None)
        saved=dict(floating=True,fullscreen=1,client_fullscreen=1,size=[1920,1080],area=[1920,1080])
        monitor=dict(x=0,y=0,width=1920,height=1080,scale=1)
        for mode in ('tile','float'):
            client=dict(address='0x123',size=[950,1040],floating=mode=='float',tags=[f'xetal-{mode}-'+('a'*24)+'-'+('b'*12)+'*'],**{'class':'org.kde.kate'})
            for phase in range(3):self.assertFalse(tracker.restore(client,{},saved,monitor,phase))
        self.assertFalse(hypr.mock_calls)

    def test_tiled_memory_never_resizes_shared_splits(self):
        monitor = dict(x=0, y=0, width=1920, height=1080, scale=1)
        for size in ([1900, 1040], [90, 1040], [950, 520]):
            with self.subTest(saved_size=size):
                hypr = Mock(); tracker = Tracker(hypr, None)
                client = dict(address='0x123', size=[950,1040], floating=False,
                              **{'class': 'terminal'})
                saved = dict(floating=False, fullscreen=0, client_fullscreen=0,
                             size=size, tiled_size=size, area=[1920,1080])
                for phase in range(3):
                    self.assertTrue(tracker.restore(client, {}, saved, monitor, phase))
                self.assertFalse(hypr.mock_calls, 'Tiled geometry belongs to the shared layout')
                # Restoring tiled/maximized mode still works without imposing
                # the previous layout's pixel dimensions on other windows.
                client['floating'] = True
                saved.update(fullscreen=1, client_fullscreen=1)
                tracker.restore(client, {}, saved, monitor, 0)
                client['floating'] = False
                tracker.restore(client, {}, saved, monitor, 1)
                tracker.restore(client, {}, saved, monitor, 2)
                hypr.dispatch.assert_called_once_with('settiled', 'address:0x123')
                hypr.command.assert_called_once_with('xetal-window-state 0x123 1 1')

    def test_forced_workspace_does_not_replace_normal_app_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'windows.json');hypr=Mock();tracker=Tracker(hypr,store)
            client=dict(address='0x123',pid=123,mapped=True,hidden=False,floating=True,size=[600,400],
                        workspace={'id':3},monitor=0,**{'class':'test'})
            meta={'workspace_layout':'floating'}
            key=identity(client,meta)
            saved=dict(floating=False,fullscreen=0,client_fullscreen=0,size=[950,1040],area=[1920,1080])
            store.put(key,saved)
            hypr.query.side_effect=lambda name: [client] if name=='clients' else {client['address']:meta} if name=='xetal-windows' else [dict(id=0,x=0,y=0,width=1920,height=1080,scale=1)]
            for now in (0,1,2):tracker.update(now)
            for field in saved:self.assertEqual(store.data[key][field],saved[field])
            self.assertEqual(store.data[key]['floating_size'],[600,400])
            self.assertFalse(tracker.pending)

    def test_files_launch_mode_is_not_replaced_by_stale_memory(self):
        hypr = Mock(); tracker = Tracker(hypr, None)
        monitor = dict(x=0, y=0, width=1920, height=1080, scale=1)
        saved = dict(floating=True, fullscreen=1, client_fullscreen=1, size=[1920,1080], area=[1920,1080])
        for app in ('xetal-files', 'xetal-files-external'):
            client = dict(address='0x123', size=[1000,700], floating=False, **{'class': app})
            for phase in range(3):
                self.assertFalse(tracker.restore(client, {}, saved, monitor, phase))
        self.assertFalse(hypr.mock_calls)
        # Real child dialogs still have independent geometry memory.
        self.assertTrue(tracker.restore(client, {'dialog': True}, saved, monitor, 0))
        hypr.dispatch.assert_called_once_with('setfloating', 'address:0x123')

    def test_identity_separates_dialogs_without_titles(self):
        window = {'class': 'org.example.Editor'}
        main = identity(window, {'role': 'main'})
        self.assertNotEqual(main, identity(window, {'role': 'save', 'dialog': True}))
        window['title'] = '/private/document.txt'
        self.assertEqual(main, identity(window, {'role': 'main'}))
        self.assertRegex(main, '^[a-f0-9]{32}$')
        window['class'] = 'xetal-file-picker-123'
        self.assertEqual(identity(window, {'role': 'one'}), identity(window, {'role': 'two', 'dialog': True}))

    def test_store_preserves_normal_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'windows.json'; store = Store(path)
            value = dict(floating=True, fullscreen=1, client_fullscreen=1, size=[1920,1080],
                         area=[1920,1080], floating_size=[850,600])
            store.put('a'*32, value);store.save()
            self.assertEqual(Store(path).data['a'*32]['floating_size'], [850,600])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_transfer_popup_memory_survives_closing_browser_without_sharing_its_size(self):
        browser = {'class': 'xetal-files', 'initialTitle': 'Home — Fusion Files'}
        queue = dict(browser, initialTitle='Transfer queue — Fusion Files')
        key = identity(queue, {'role': 'dialog-role', 'dialog': True})
        self.assertNotEqual(key, identity(browser, {'role': 'main'}))
        self.assertEqual(key, identity(queue, {'role': 'main', 'dialog': False}))

    def test_restore_phases_and_monitor_limits(self):
        class Hypr:
            def __init__(self): self.calls = []
            def dispatch(self, action, args): self.calls.append((action, args))
            def command(self, command): self.calls.append((command, '')); return 'ok'
        hypr=Hypr();tracker=Tracker(hypr,None)
        client=dict(address='0x123',floating=False,size=[1200,800],at=[0,0],**{'class':'test'})
        saved=dict(floating=True,fullscreen=1,client_fullscreen=1,size=[1920,1080],floating_size=[850,600],area=[1920,1080])
        monitor=dict(x=0,y=0,width=800,height=600,scale=1,reserved=[0,30,0,0])
        tracker.restore(client,{},saved,monitor,0)
        self.assertEqual(hypr.calls,[('setfloating','address:0x123')])
        tracker.restore(client,{},saved,monitor,1)
        self.assertEqual(hypr.calls,[('setfloating','address:0x123')])
        client['floating']=True;tracker.restore(client,{},saved,monitor,1)
        self.assertIn(('resizewindowpixel','exact 784 554,address:0x123'),hypr.calls)
        tracker.restore(client,{},saved,monitor,2)
        self.assertIn(('xetal-window-state 0x123 1 1',''),hypr.calls)
        self.assertFalse(any('focuswindow' in action for action,_ in hypr.calls))


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'windows.json';self.store=Store(self.path)
        self.monitor=dict(id=0,x=-1920,y=200,width=1920,height=1080,scale=1,reserved=[0,40,0,0])
        self.client=dict(address='0x123',pid=123,stableId='1',mapped=True,hidden=False,floating=True,
                         size=[800,600],at=[-1800,340],workspace={'id':3,'name':'3'},monitor=0,
                         fullscreen=0,fullscreenClient=0,focusHistoryID=0,**{'class':'test'})
        self.clients=[self.client];self.meta={};self.hypr=Mock()
        self.hypr.query.side_effect=lambda name: self.clients if name=='clients' else {c['address']:self.meta for c in self.clients} if name=='xetal-windows' else [self.monitor]
        self.tracker=Tracker(self.hypr,self.store);self.key=identity(self.client,self.meta)
        self.saved=dict(floating=True,fullscreen=0,client_fullscreen=0,size=[800,600],area=[1920,1040],
                        floating_size=[800,600],floating_position=[120,100])

    def test_geometry_restores_for_every_explicit_mode_without_changing_mode(self):
        for client,meta in [
            (self.client,{'workspace_layout':'floating'}),
            *[(dict(self.client,tags=[f'xetal-{mode}-'+('a'*24)+'-'+('b'*12)+'*']),{}) for mode in ('float','tile')],
            (dict(self.client,tags=['fusion-managed-rule*']),{}),
            *[({**self.client,'class':app},{}) for app in ('xetal-files','xetal-files-external','xetal-file-picker-123')],
        ]:
            with self.subTest(client=client,meta=meta):
                self.hypr.reset_mock()
                # A remembered maximized mode must not defeat the chosen mode.
                saved=dict(self.saved,floating=False,fullscreen=1,client_fullscreen=1)
                for phase in range(3):self.assertTrue(self.tracker.restore(client,meta,saved,self.monitor,phase))
                self.hypr.command.assert_not_called()
                self.assertEqual([c.args for c in self.hypr.dispatch.call_args_list],
                                 [('resizewindowpixel','exact 800 600,address:0x123'),
                                  ('movewindowpixel','exact -1800 340,address:0x123')])

    def test_resize_then_immediate_maximize_and_close_keeps_normal_rectangle(self):
        self.tracker.update(0)
        self.client.update(size=[900,650],at=[-1600,400]);self.tracker.update(.2)
        self.client.update(size=[1920,1040],at=[-1920,240],fullscreen=1,fullscreenClient=1)
        self.tracker.update(.3);self.clients=[];self.tracker.update(.4)
        self.store.save();value=Store(self.path).data[self.key]
        self.assertEqual(value['floating_size'],[900,650]);self.assertEqual(value['floating_position'],[320,160])
        self.assertEqual(value['fullscreen'],1)

    def test_force_floating_without_prior_mode_only_records_geometry(self):
        self.meta['workspace_layout']='floating'
        for now in (0,.5,1):self.tracker.update(now)
        saved=self.store.data[self.key];self.assertFalse(saved['mode_saved'])
        tiled=dict(self.client,floating=False)
        self.assertFalse(self.tracker.restore(tiled,{},saved,self.monitor))
        self.assertTrue(self.tracker.restore(self.client,{},saved,self.monitor))
        self.hypr.dispatch.assert_not_called();self.hypr.command.assert_not_called()

    def test_force_tiled_drag_target_never_replaces_floating_geometry(self):
        self.store.put(self.key,self.saved);self.meta['workspace_layout']='tile'
        self.client.update(size=[1500,1000],at=[0,0])
        for now in (0,.5,1):self.tracker.update(now)
        self.assertEqual(self.store.data[self.key],self.saved)
        self.hypr.dispatch.assert_not_called()

    def test_entering_force_tiled_flushes_last_unsettled_normal_rectangle(self):
        self.tracker.update(0);self.client.update(size=[900,650]);self.tracker.update(.1)
        self.meta['workspace_layout']='tile';self.client.update(size=[1900,1000])
        self.tracker.update(.2)
        self.assertEqual(self.store.data[self.key]['floating_size'],[900,650])

    def test_restart_observes_existing_windows_without_moving_them(self):
        self.store.put(self.key,dict(self.saved,floating_size=[600,400]))
        for now in (0,.5,1):self.tracker.update(now)
        self.hypr.dispatch.assert_not_called();self.hypr.command.assert_not_called()
        self.assertEqual(self.store.data[self.key]['floating_position'],[120,100])

    def test_last_closed_sibling_supplies_its_own_normal_rectangle(self):
        second=dict(self.client,address='0x234',stableId='2',size=[700,500],at=[-1700,300],focusHistoryID=1)
        self.clients.append(second)
        for now in (0,.5):self.tracker.update(now)
        self.clients=[second];self.tracker.update(.6)
        self.clients=[];self.tracker.update(.7)
        self.assertEqual(self.store.data[self.key]['floating_size'],[700,500])
        self.assertEqual(self.store.data[self.key]['floating_position'],[220,60])

    def test_new_stable_id_is_a_new_window_even_if_address_and_pid_are_reused(self):
        self.tracker.update(0);self.client['stableId']='2';self.tracker.update(.1)
        self.assertTrue(self.tracker.pending)

    def test_batch_close_prefers_focused_sibling_and_shutdown_flushes_unsettled_resize(self):
        self.clients.append(dict(self.client,address='0x234',stableId='2',size=[700,500],focusHistoryID=1))
        self.tracker.update(0);self.clients=[];self.tracker.update(.1)
        self.assertEqual(self.store.data[self.key]['floating_size'],[800,600])
        self.clients=[self.client];self.tracker=Tracker(self.hypr,self.store)
        self.tracker.update(0);self.client['size']=[900,650];self.tracker.update(.1)
        self.tracker.flush()
        self.assertEqual(Store(self.path).data[self.key]['floating_size'],[900,650])

    def test_minimized_and_hidden_geometry_is_not_sampled_but_special_workspaces_are(self):
        self.tracker.update(0)
        self.client.update(size=[1800,1000],hidden=True);self.tracker.update(.1)
        self.client.update(hidden=False,workspace={'id':-98,'name':'special:xetal-minimized-ws-3'});self.tracker.update(.2)
        self.clients=[];self.tracker.update(.3)
        self.assertEqual(self.store.data[self.key]['floating_size'],[800,600])
        self.clients=[self.client];self.client['workspace']={'id':-1,'name':'special:scratch'}
        self.tracker=Tracker(self.hypr,self.store)
        for now in (0,.5):self.tracker.update(now)
        self.assertEqual(self.store.data[self.key]['floating_size'],[1800,1000])

    def test_scaled_rotated_destination_fits_saved_position_without_changing_saved_record(self):
        monitor=dict(self.monitor,x=0,y=-500,width=1080,height=1920,scale=2,transform=1)
        self.tracker.restore(self.client,{},self.saved,monitor,1)
        self.assertEqual([c.args for c in self.hypr.dispatch.call_args_list],
                         [('resizewindowpixel','exact 800 484,address:0x123'),
                          ('movewindowpixel','exact 120 -444,address:0x123')])
        self.assertEqual(self.saved['floating_position'],[120,100])

    def test_fixed_size_windows_restore_position_and_keep_application_constraints(self):
        self.tracker.restore(self.client,{'fixed':True},dict(self.saved,floating_size=[600,400]),self.monitor,1)
        self.hypr.dispatch.assert_called_once_with('movewindowpixel','exact -1800 340,address:0x123')

    def test_old_fullscreen_size_is_never_used_as_a_normal_rectangle(self):
        saved={k:v for k,v in self.saved.items() if not k.startswith('floating_')}
        saved.update(fullscreen=1,client_fullscreen=1,size=[1920,1040])
        self.tracker.restore(self.client,{},saved,self.monitor,1)
        self.hypr.dispatch.assert_not_called()

    def test_missing_app_class_falls_back_to_executable_without_persisting_pid(self):
        with patch('service.os.readlink',return_value='/usr/bin/example'):
            self.assertEqual(identity({'pid':1},{}),identity({'pid':2},{}))

    def test_position_roundtrip_validation_and_private_file_permissions(self):
        self.store.put(self.key,self.saved);self.store.save()
        self.assertEqual(Store(self.path).data[self.key],self.saved)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        self.store.put(self.key,dict(self.saved,floating_position=[float('nan'),0]));self.store.save()
        with self.assertRaisesRegex(ValueError,'position'):Store(self.path)


if __name__ == '__main__': unittest.main()
