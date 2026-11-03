import runpy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

activate=runpy.run_path(str(Path(__file__).with_name('activate-window.py')))['activate']


class ActivateTests(unittest.TestCase):
    def test_focus_then_raise_only_requested_address(self):
        c=dict(address='0x123',pid=42,mapped=True,workspace={'name':'2'})
        hypr=Mock();hypr.query.return_value=[c]
        activate(hypr,'123')
        self.assertEqual([c.args for c in hypr.dispatch.call_args_list],[('focuswindow','address:0x123'),('alterzorder','top,address:0x123')])

    def test_minimize_restore_waits_for_unhide(self):
        c=dict(address='0x123',pid=42,mapped=True,workspace={'name':'2'})
        stash=dict(c,workspace={'name':'special:xetal-minimized-ws-2'})
        hypr=Mock();hypr.query.side_effect=[[stash],[stash],[dict(c,hidden=True)],[c]]
        with patch('time.sleep'):activate(hypr,'0x123')
        self.assertEqual(hypr.dispatch.call_args_list[-1].args,('alterzorder','top,address:0x123'))

    def test_closed_or_reused_address_is_never_raised(self):
        c=dict(address='0x123',pid=42,mapped=True)
        for after in ([],[dict(c,pid=99)]):
            hypr=Mock();hypr.query.side_effect=[[c],after]
            activate(hypr,'0x123')
            hypr.dispatch.assert_called_once_with('focuswindow','address:0x123')

    def test_rejects_commands_in_place_of_address(self):
        hypr=Mock()
        with self.assertRaises(ValueError):activate(hypr,'0x123; killactive')
        self.assertFalse(hypr.mock_calls)


if __name__=='__main__':unittest.main()
