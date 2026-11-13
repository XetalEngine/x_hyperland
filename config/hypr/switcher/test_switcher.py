import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from switcher import app


class OverlappingWindows:
    """Pinned core focus semantics, with the existing raise/stack adapter.

    Both windows cover the pointer. Focus grants an over-fullscreen render
    permission but does not reorder them; input still walks the stack backwards.
    """
    def __init__(self, maximized):
        self.order = ['0xf', '0xe']  # Files is behind Echo after clicking Echo.
        self.fullscreen = '0xe' if maximized else None
        self.focused = '0xe'
        self.above = set()
        self.clients = [dict(address=address, mapped=True, floating=True,
                             workspace={'id': 3, 'name': '3'}, monitor=2,
                             at=[100, 100], size=[800, 600], fullscreen=int(address == self.fullscreen))
                        for address in self.order]

    def ctl(self, *args):
        if args == ('-j', 'clients'): return json.dumps(self.clients)
        action, selector = args[1:]
        address = selector.split('address:', 1)[1]
        if action == 'focuswindow':
            self.focused = address
            if self.fullscreen and address != self.fullscreen: self.above.add(address)
        elif action == 'alterzorder':
            assert selector.startswith('top,address:')
            self.order.remove(address); self.order.append(address)
            if self.fullscreen: self.above = set(self.order[self.order.index(self.fullscreen)+1:])
        else:
            raise AssertionError('Activation must not change placement or fullscreen: '+action)
        return 'ok'

    def drawn(self):
        if not self.fullscreen: return self.order[-1]
        return next((w for w in reversed(self.order) if w in self.above), self.fullscreen)

    def clicked(self):
        return next(w for w in reversed(self.order) if not self.fullscreen or w == self.fullscreen or w in self.above)


class SwitcherTests(unittest.TestCase):
    def test_all_workspaces_and_hidden_group_members_are_listed(self):
        clients=[{'address':'0x1','class':'kitty','mapped':True,'focusHistoryID':3,'workspace':{'name':'20'}},
                 {'address':'0x2','class':'discord','mapped':True,'hidden':True,'focusHistoryID':1,'workspace':{'name':'special:magic'}},
                 {'address':'0x3','class':'xetal-switcher','mapped':True,'focusHistoryID':0},
                 {'address':'0x4','class':'chrome','mapped':False}]
        self.assertEqual([c['address'] for c in app.windows(clients,'0x1')],['0x1','0x2'])
    def test_focus_and_raise_only_selects_existing_window_and_does_not_move_it(self):
        client={'address':'0x123','mapped':True,'workspace':{'name':'special:magic'},'monitor':2}
        with patch.object(app,'ctl',side_effect=[json.dumps([client]),'ok','ok']) as ctl:
            self.assertTrue(app.focus('0x123'))
        self.assertEqual([c.args for c in ctl.call_args_list[1:]],
                         [('dispatch','focuswindow','address:0x123'),('dispatch','alterzorder','top,address:0x123')])
        with patch.object(app,'ctl',return_value='[]') as ctl:
            self.assertFalse(app.focus('0x999'));self.assertEqual(ctl.call_count,1)

    def test_selected_window_is_both_visible_and_clickable_above_echo(self):
        for maximized in (False, True):
            with self.subTest(maximized=maximized):
                desktop = OverlappingWindows(maximized)
                placement = json.dumps(desktop.clients)
                with patch.object(app, 'ctl', side_effect=desktop.ctl):
                    for _ in range(3):
                        for address in ('0xf', '0xe'):
                            self.assertTrue(app.focus(address))
                            self.assertEqual((desktop.focused, desktop.drawn(), desktop.clicked()), (address,)*3)
                            self.assertEqual(json.dumps(desktop.clients), placement)

    def test_pending_minimize_restore_is_accepted_without_retry_or_fallback(self):
        client=dict(address='0x123', mapped=True, workspace={'name':'special:xetal-minimized-ws-3'})
        for reply in ('Restore the minimized window first', ValueError('Restore the minimized window first')):
            with self.subTest(reply=reply), patch.object(app, 'ctl', side_effect=[json.dumps([client]), 'ok', reply]) as ctl:
                self.assertTrue(app.focus('0x123'))
                self.assertEqual(ctl.call_count, 3) # native completion owns the eventual raise

    def test_cancel_restores_focus_without_reordering_overlapping_windows(self):
        desktop = OverlappingWindows(False)
        with patch.object(app, 'ctl', side_effect=desktop.ctl):
            self.assertTrue(app.focus('0xf', raise_window=False))
        self.assertEqual(desktop.focused, '0xf')
        self.assertEqual(desktop.order, ['0xf', '0xe'])

    def test_failed_focus_never_raises_and_failed_raise_is_not_reported_as_success(self):
        client=dict(address='0x123', mapped=True)
        for replies, calls in ((['window gone'], 2), (['ok', ValueError('Unknown dispatcher')], 3)):
            with patch.object(app, 'ctl', side_effect=[json.dumps([client]), *replies]) as ctl:
                self.assertFalse(app.focus('0x123'))
                self.assertEqual(ctl.call_count, calls)


if __name__=='__main__':unittest.main()
