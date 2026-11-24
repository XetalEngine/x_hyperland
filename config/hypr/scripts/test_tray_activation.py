"""Tray activation fixtures: no real bus calls, app launches or workspace changes."""
import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('fusion_tray_activation', Path(__file__).with_name('tray-activate.py'))
tray = importlib.util.module_from_spec(spec); sys.modules[spec.name] = tray; spec.loader.exec_module(tray)


class TrayActivationTests(unittest.TestCase):
    def setUp(self):
        self.item = tray.Item(':1.42', '/StatusNotifierItem', 42, 'stamp', False)
        self.bus = Mock(); self.bus.resolve.return_value = self.item
        self.hypr = Mock()
        self.window = dict(address='0xabc', pid=42, mapped=True, hidden=False,
                           monitor=0, workspace={'id': 1, 'name': '1'}, focusHistoryID=2)
        self.hypr.query.return_value = [self.window]
        self.stamp = patch.object(tray, 'process_stamp', return_value='stamp'); self.stamp.start(); self.addCleanup(self.stamp.stop)
        self.ancestry = patch.object(tray, 'descendant', return_value=False); self.ancestry.start(); self.addCleanup(self.ancestry.stop)

    def test_existing_window_focuses_without_toggling_or_moving(self):
        self.assertTrue(tray.reveal(self.hypr, self.bus, {}))
        self.bus.activate.assert_not_called()
        self.assertEqual([call.args for call in self.hypr.dispatch.call_args_list],
                         [('focuswindow', 'address:0xabc'), ('alterzorder', 'top,address:0xabc')])
        self.assertEqual(self.window['monitor'], 0); self.assertEqual(self.window['workspace']['id'], 1)

    def test_already_visible_window_is_not_hidden_by_a_second_click(self):
        tray.reveal(self.hypr, self.bus, {}); tray.reveal(self.hypr, self.bus, {})
        self.bus.activate.assert_not_called()
        self.assertEqual(self.hypr.dispatch.call_count, 4)

    def test_multiple_windows_choose_last_used_owned_window(self):
        newest = {**self.window, 'address': '0xdef', 'focusHistoryID': 0}
        never = {**self.window, 'address': '0xaaa', 'focusHistoryID': -1}
        unrelated = {**self.window, 'pid': 100, 'focusHistoryID': 0, 'title': 'Echo'}
        self.assertEqual(tray.choose_window([unrelated, never, self.window, newest], self.item), newest)

    def test_process_children_are_supported_but_similar_titles_are_not_identity(self):
        child = {**self.window, 'pid': 43}
        self.assertIsNone(tray.choose_window([child], self.item))
        with patch.object(tray, 'descendant', return_value=True):
            self.assertEqual(tray.choose_window([child], self.item), child)

    def test_reused_process_id_is_rejected(self):
        with patch.object(tray, 'process_stamp', return_value='other'):
            self.assertFalse(tray.reveal(self.hypr, self.bus, {}))
        self.hypr.dispatch.assert_not_called(); self.bus.activate.assert_not_called()

    def test_unmapped_windows_are_reopened_once_and_focused_where_they_appear(self):
        self.hypr.query.side_effect = [[], [self.window], [self.window], [self.window]]
        self.assertTrue(tray.reveal(self.hypr, self.bus, {'x': 99, 'y': 20}))
        self.bus.activate.assert_called_once_with(self.item, 99, 20)
        self.hypr.dispatch.assert_any_call('focuswindow', 'address:0xabc')

    def test_menu_applet_without_windows_uses_native_menu(self):
        self.bus.resolve.return_value = tray.Item(':1.42', '/MenuItem', 42, 'stamp', True)
        self.hypr.query.return_value = []
        self.assertFalse(tray.reveal(self.hypr, self.bus, {}))
        self.bus.activate.assert_not_called(); self.hypr.dispatch.assert_not_called()

    def test_menu_item_with_a_real_window_can_still_be_revealed(self):
        self.bus.resolve.return_value = tray.Item(':1.42', '/MenuItem', 42, 'stamp', True)
        self.assertTrue(tray.reveal(self.hypr, self.bus, {})); self.bus.activate.assert_not_called()

    def test_unknown_or_ambiguous_item_uses_native_behavior(self):
        self.bus.resolve.return_value = None
        self.assertFalse(tray.reveal(self.hypr, self.bus, {})); self.hypr.query.assert_not_called()

    def test_closed_app_that_maps_no_window_is_not_activated_twice(self):
        self.hypr.query.return_value = []
        self.assertTrue(tray.reveal(self.hypr, self.bus, {}, wait_seconds=0))
        self.bus.activate.assert_called_once()

    def test_focus_failure_never_falls_back_to_hiding_the_existing_window(self):
        self.hypr.dispatch.side_effect = ValueError('fixture focus error')
        self.assertTrue(tray.reveal(self.hypr, self.bus, {})); self.bus.activate.assert_not_called()

    def test_activation_timeout_is_not_replayed(self):
        self.hypr.query.return_value = []; self.bus.activate.side_effect = TimeoutError('fixture timeout')
        self.assertTrue(tray.reveal(self.hypr, self.bus, {})); self.bus.activate.assert_called_once()

    def test_minimized_window_uses_the_existing_restore_hook(self):
        minimized = {**self.window, 'hidden': True, 'workspace': {'id': -99, 'name': 'special:xetal-minimized-ws-1'}}
        self.hypr.query.side_effect = [[minimized], [minimized], [self.window]]
        self.assertTrue(tray.reveal(self.hypr, self.bus, {}))
        self.hypr.dispatch.assert_any_call('focuswindow', 'address:0xabc'); self.bus.activate.assert_not_called()


class TrayIdentityTests(unittest.TestCase):
    def setUp(self):
        self.bus = tray.TrayBus.__new__(tray.TrayBus)
        self.bus.GLib = SimpleNamespace(Error=LookupError)
        self.registered = ['org.example.App/Item']
        self.props = {(':1.42', '/Item'): {'Menu': '/Menu', 'Title': 'App', 'ItemIsMenu': False}}
        self.bus.owner = lambda name: ':1.42' if name in ('org.example.App', ':1.42') else ':1.99'
        self.bus.call = lambda owner, path, interface, method, signature, args: (
            (self.registered,) if method == 'Get' else (42,))
        self.bus.property = lambda owner, path, name, default=None: self.props.get((owner, path), {}).get(name, default)
        change = patch.object(tray, 'process_stamp', return_value='stamp'); change.start(); self.addCleanup(change.stop)

    def test_attached_menu_selects_exact_endpoint_and_authenticated_process_identity(self):
        self.registered.append('other.App/Item')
        self.props[(':1.99', '/Item')] = {'Menu': '/Menu', 'Title': 'App'}
        self.assertEqual(self.bus.resolve({'bus': 'org.example.App', 'menu': '/Menu'}),
                         tray.Item(':1.42', '/Item', 42, 'stamp', False))

    def test_multiple_items_in_one_process_use_the_clicked_menu_path(self):
        self.registered.append('org.example.App/OtherItem')
        self.props[(':1.42', '/OtherItem')] = {'Menu': '/OtherMenu', 'Title': 'App'}
        self.assertEqual(self.bus.resolve({'bus': ':1.42', 'menu': '/OtherMenu'}).path, '/OtherItem')

    def test_duplicate_service_aliases_are_one_item(self):
        self.registered.append(':1.42/Item')
        self.assertIsNotNone(self.bus.resolve({'bus': ':1.42', 'menu': '/Menu'}))

    def test_same_tooltip_for_two_apps_does_not_guess_a_window(self):
        self.registered.append('other.App/Item')
        self.props[(':1.99', '/Item')] = {'Title': 'App'}
        self.assertIsNone(self.bus.resolve({'tooltip': 'App'}))

    def test_menu_less_item_can_match_its_exact_tooltip_title(self):
        self.props[(':1.42', '/Item')] = {'ToolTip': ('', [], 'Tooltip app', 'Description')}
        self.assertIsNotNone(self.bus.resolve({'tooltip': 'Tooltip app\nDescription'}))
        self.assertIsNone(self.bus.resolve({'tooltip': 'Tooltip'}))

    def test_missing_process_is_not_activated(self):
        with patch.object(tray, 'process_stamp', return_value=None):
            self.assertIsNone(self.bus.resolve({'bus': ':1.42', 'menu': '/Menu'}))


if __name__ == '__main__': unittest.main()
