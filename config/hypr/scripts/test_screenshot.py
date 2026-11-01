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
        self.assertEqual(self.commands,[[str(notify.ROOT/'scripts/image-viewer.sh'),'--',str(self.path)],[str(notify.ROOT/'scripts/dolphin.sh'),'--select',str(self.path)]])
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

    def test_recording_banner_and_folder_button_select_the_video(self):
        video=Path(self.temp.name)/'video $(literal) & <final>.mp4';video.write_bytes(b'video')
        self.bus.call_sync.return_value=GLib.Variant('(u)',(42,))
        self.actions.show(video,'Recording saved',kind='recording',body='Display disconnected.\n'+str(video))
        args=self.bus.call_sync.call_args.args[4].unpack()
        self.assertEqual((args[0],args[2]),('Hyper Fusion Recorder','media-record'))
        self.assertEqual(args[5],['default','Show in folder','folder-open','📂  Show in folder'])
        self.assertNotIn('image-path',args[6])
        self.assertIn('Display disconnected.\n',args[4]);self.assertIn('&lt;final&gt;',args[4])
        self.actions.event('ActionInvoked',(42,'folder-open'));self.actions.event('ActionInvoked',(42,'default'))
        expected=[str(notify.ROOT/'scripts/dolphin.sh'),'--select',str(video)]
        self.assertEqual(self.commands,[expected,expected])
        # Sharing the broker must not change a screenshot's default action.
        self.actions.event('ActionInvoked',(41,'default'))
        self.assertEqual(self.commands[-1][0],str(notify.ROOT/'scripts/image-viewer.sh'))

    def test_recording_history_keeps_the_original_video_after_more_captures(self):
        video=Path(self.temp.name)/'first.mp4';video.write_bytes(b'video')
        self.bus.call_sync.return_value=GLib.Variant('(u)',(42,))
        self.actions.show(video,'Recording saved',kind='recording')
        self.actions.event('NotificationClosed',(42,1))
        self.bus.call_sync.return_value=GLib.Variant('(u)',(43,))
        self.actions.show(self.path,'Screenshot saved')
        self.actions.event('ActionInvoked',(42,'folder-open'))
        self.assertEqual(self.commands,[[str(notify.ROOT/'scripts/dolphin.sh'),'--select',str(video)]])
        self.actions.event('NotificationClosed',(42,2));self.actions.event('ActionInvoked',(42,'folder-open'))
        self.assertEqual(len(self.commands),1)

    def test_removed_recording_reports_error_without_launching_dolphin(self):
        self.actions.show(self.path,'Recording saved',kind='recording')
        self.path.unlink();self.actions.event('ActionInvoked',(41,'folder-open'))
        self.assertEqual(self.commands[0][:4],['notify-send','-a','Hyper Fusion Recorder','Cannot open recording'])


if __name__=='__main__':unittest.main()
