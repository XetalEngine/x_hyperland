from pathlib import Path
import tempfile
import unittest
from service import Store, Tracker, identity


class MemoryTests(unittest.TestCase):
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
        client['floating']=True;tracker.restore(client,{},saved,monitor,1)
        self.assertIn(('resizewindowpixel','exact 784 554,address:0x123'),hypr.calls)
        tracker.restore(client,{},saved,monitor,2)
        self.assertIn(('xetal-window-state 0x123 1 1',''),hypr.calls)
        self.assertFalse(any('focuswindow' in action for action,_ in hypr.calls))


if __name__ == '__main__': unittest.main()
