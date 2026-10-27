import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('kill_hovered', Path(__file__).with_name('kill-hovered.py'))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class HoverKillTests(unittest.TestCase):
    def setUp(self):
        self.cursor = {'x': 150, 'y': 150}
        self.monitors = [{'name': 'DP-1', 'x': 0, 'y': 0, 'width': 1920, 'height': 1080,
                          'scale': 1, 'activeWorkspace': {'id': 1}, 'specialWorkspace': {'id': 0}}]
        self.window = {'address': '0x123', 'pid': 4242, 'mapped': True, 'hidden': False,
                       'workspace': {'id': 1}, 'at': [0, 0], 'size': [700, 700],
                       'floating': False, 'focusHistoryID': 3}
        self.focused = dict(self.window, address='0x456', pid=4343, at=[800, 0], focusHistoryID=0)
        self.clients = [self.window, self.focused]
        self.layers = {}

    def snapshot(self):
        return self.cursor, self.monitors, self.clients, self.layers

    def target(self):
        return helper.target_at(*self.snapshot())

    def test_hovered_target_can_differ_from_focused_application(self):
        self.assertIs(self.target(), self.window)

    def test_empty_desktop_never_falls_back_to_focused_window(self):
        self.cursor = {'x': 1800, 'y': 900}
        with patch.object(helper, 'snapshot', side_effect=self.snapshot), patch.object(helper, 'ctl') as ctl:
            self.assertIsNone(helper.force_kill())
        ctl.assert_not_called()

    def test_hidden_unmapped_and_other_workspace_windows_are_excluded(self):
        for change in ({'hidden': True}, {'mapped': False}, {'workspace': {'id': 2}}):
            with self.subTest(change=change):
                self.clients = [dict(self.window, **change)]
                self.assertIsNone(self.target())

    def test_floating_window_over_tiled_window_wins(self):
        overlay = dict(self.window, address='0x789', pid=4444, floating=True, focusHistoryID=1)
        self.clients.append(overlay)
        self.assertIs(self.target(), overlay)

    def test_fullscreen_blocks_older_floats_but_not_newer_dialog(self):
        self.window.update(fullscreen=2, focusHistoryID=1)
        overlay = dict(self.window, address='0x789', fullscreen=0, floating=True, focusHistoryID=2)
        self.clients.append(overlay)
        self.assertIs(self.target(), self.window)
        overlay['focusHistoryID'] = 0
        self.assertIs(self.target(), overlay)

    def test_special_workspace_does_not_kill_dimmed_windows_behind_it(self):
        self.monitors[0]['specialWorkspace']['id'] = -99
        self.assertIsNone(self.target())
        special = dict(self.window, address='0x789', workspace={'id': -99})
        self.clients.append(special)
        self.assertIs(self.target(), special)

    def test_pinned_window_is_visible_on_another_workspace(self):
        self.window.update(pinned=True, workspace={'id': 2})
        self.assertIs(self.target(), self.window)

    def test_top_and_overlay_layers_block_windows_behind_them(self):
        for level in ('2', '3'):
            self.layers = {'DP-1': {'levels': {level: [{'x': 0, 'y': 0, 'w': 300, 'h': 300}]}}}
            self.assertIsNone(self.target())
        self.layers = {'DP-1': {'levels': {'0': [{'x': 0, 'y': 0, 'w': 1920, 'h': 1080}]}}}
        self.assertIs(self.target(), self.window)

    def test_rotated_scaled_monitor_uses_logical_coordinates(self):
        self.monitors[0].update(x=-720, width=2560, height=1440, scale=2, transform=1)
        self.cursor = {'x': -100, 'y': 1000}
        self.window.update(at=[-500, 800], size=[500, 400])
        self.assertIs(self.target(), self.window)
        self.cursor['x'] = 100
        self.assertIsNone(self.target())

    def test_invalid_identity_cannot_dispatch_signal(self):
        for change in ({'address': 'activewindow'}, {'address': '0x0'}, {'pid': 0}, {'pid': -1}):
            self.clients = [dict(self.window, **change)]
            with self.subTest(change=change), patch.object(helper, 'snapshot', side_effect=self.snapshot), patch.object(helper, 'ctl') as ctl:
                with self.assertRaises(ValueError):helper.force_kill()
                ctl.assert_not_called()

    def test_changed_target_is_not_killed_or_retargeted(self):
        first = copy.deepcopy(self.snapshot())
        self.window['pid'] = 9999
        with patch.object(helper, 'snapshot', side_effect=[first, self.snapshot()]), patch.object(helper, 'ctl') as ctl:
            self.assertIsNone(helper.force_kill())
        ctl.assert_not_called()

    def test_force_kill_uses_exact_address_without_focusing_it(self):
        with patch.object(helper, 'snapshot', side_effect=self.snapshot), patch.object(helper, 'ctl', return_value='ok') as ctl:
            self.assertIs(helper.force_kill(), self.window)
        ctl.assert_called_once_with('dispatch', 'signalwindow', 'address:0x123,9')

    def test_dry_run_cannot_send_signals(self):
        with patch.object(helper, 'snapshot', side_effect=self.snapshot), patch.object(helper, 'ctl') as ctl:
            self.assertIs(helper.force_kill(dry_run=True), self.window)
        ctl.assert_not_called()


if __name__ == '__main__':
    unittest.main()
