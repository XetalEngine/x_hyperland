import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from gi.repository import GLib

spec=importlib.util.spec_from_file_location('screenshot_notify',Path(__file__).with_name('screenshot-notify.py'))
notify=importlib.util.module_from_spec(spec);spec.loader.exec_module(notify)


class ScreenshotActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'screen $(literal) & image.png';self.path.write_bytes(b'image')
        self.bus=Mock();self.bus.call_sync.return_value=GLib.Variant('(u)',(41,));self.commands=[]
        self.actions=notify.Notifications(self.bus,self.commands.append);self.ident=self.actions.show(self.path,'Screenshot saved')
    def tearDown(self):self.temp.cleanup()
    def test_banner_and_folder_actions_use_original_file_as_one_argument(self):
        args=self.bus.call_sync.call_args.args[4].unpack()
        self.assertEqual(args[5],['default','Open image','folder-open','📂  Show in folder'])
        self.assertIn('&amp;',args[4])
        self.actions.event('ActionInvoked',(41,'default'));self.actions.event('ActionInvoked',(41,'folder-open'))
        self.assertEqual(self.commands,[['xdg-open',str(self.path)],[str(notify.ROOT/'scripts/dolphin.sh'),'--select',str(self.path)]])
    def test_expired_banner_remains_actionable_in_history(self):
        self.actions.event('NotificationClosed',(41,1));self.actions.event('ActionInvoked',(41,'default'))
        self.assertEqual(len(self.commands),1)
        self.actions.event('NotificationClosed',(41,2));self.actions.event('ActionInvoked',(41,'default'))
        self.assertEqual(len(self.commands),1)
    def test_unrelated_notifications_are_ignored(self):
        self.actions.event('ActionInvoked',(42,'default'));self.assertEqual(self.commands,[])
    def test_removed_file_reports_error_without_opening(self):
        self.path.unlink();self.actions.event('ActionInvoked',(41,'default'))
        self.assertEqual(self.commands[0][0],'notify-send')


if __name__=='__main__':unittest.main()
