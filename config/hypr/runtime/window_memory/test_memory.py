from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from service import Store, Tracker, identity


class MemoryTests(unittest.TestCase):
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


if __name__ == '__main__': unittest.main()
