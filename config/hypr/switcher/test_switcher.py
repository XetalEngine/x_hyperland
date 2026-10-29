import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from switcher import app


class SwitcherTests(unittest.TestCase):
    def test_all_workspaces_and_hidden_group_members_are_listed(self):
        clients=[{'address':'0x1','class':'kitty','mapped':True,'focusHistoryID':3,'workspace':{'name':'20'}},
                 {'address':'0x2','class':'discord','mapped':True,'hidden':True,'focusHistoryID':1,'workspace':{'name':'special:magic'}},
                 {'address':'0x3','class':'xetal-switcher','mapped':True,'focusHistoryID':0},
                 {'address':'0x4','class':'chrome','mapped':False}]
        self.assertEqual([c['address'] for c in app.windows(clients,'0x1')],['0x1','0x2'])
    def test_focus_only_selects_existing_window_and_does_not_move_it(self):
        client={'address':'0x123','mapped':True,'workspace':{'name':'special:magic'},'monitor':2}
        with patch.object(app,'ctl',side_effect=[json.dumps([client]),'ok']) as ctl:
            self.assertTrue(app.focus('0x123'))
        self.assertEqual(ctl.call_args.args,('dispatch','focuswindow','address:0x123'))
        with patch.object(app,'ctl',return_value='[]') as ctl:
            self.assertFalse(app.focus('0x999'));self.assertEqual(ctl.call_count,1)


if __name__=='__main__':unittest.main()
