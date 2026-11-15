"""Popup placement, focus and toggling without touching the real clipboard."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipboard import placement, launch
from clipboard import app as ui
import test_ui


def monitor(**overrides):
    return dict(dict(id=2, x=4480, y=0, width=2560, height=1440, scale=1,
                     transform=0, reserved=[0, 38, 0, 0]), **overrides)


class Geometry(unittest.TestCase):
    def test_bar_click_is_anchored_on_its_own_monitor(self):
        output = monitor()
        monitors = [monitor(id=0, x=0, width=1920), monitor(id=1, x=1920), output]
        cursor = dict(x=6650, y=20)
        selected = placement.monitor_at(monitors, cursor)
        self.assertEqual(selected['id'], 2)
        result = placement.geometry(selected, cursor, from_bar=True)
        self.assertEqual(result['relative_y'], 48)
        self.assertEqual(result['relative_x'] + result['width'], 6650-4480+24)
        self.assertEqual(result['monitor'], 2)

    def test_scaled_rotated_negative_origin_bottom_bar_and_edge_clamping(self):
        output = monitor(x=-960, y=-400, width=2160, height=3840, scale=2,
                         transform=1, reserved=[0, 0, 0, 48])
        for x in (-959, -700, 950):
            with self.subTest(x=x):
                result = placement.geometry(output, dict(x=x, y=650), 'bottom', from_bar=True)
                self.assertGreaterEqual(result['relative_x'], 12)
                self.assertLessEqual(result['relative_x']+result['width'], 1920-12)
                self.assertEqual(result['relative_y']+result['height'], 1080-48-10)
                self.assertEqual(result['edge'], 'bottom')

    def test_small_display_and_shortcut_ignore_horizontal_mouse_position(self):
        output = monitor(width=400, height=480)
        a = placement.geometry(output, dict(x=4481, y=70))
        b = placement.geometry(output, dict(x=4800, y=200))
        self.assertEqual(a, b)
        self.assertEqual((a['width'], a['height']), (376, 422))

    def test_rule_is_prepared_before_any_popup_can_map(self):
        request = placement.geometry(monitor(), dict(x=6500, y=20), from_bar=True)
        with patch('quick_panel.placement.subprocess.run', return_value=SimpleNamespace(
                returncode=0, stdout='ok\nok\nok\nok\n', stderr='')) as run:
            self.assertEqual(placement.prepare(request, rule='fusion-clipboard-history'), (440, 540))
            command = run.call_args.args[0][-1]
            self.assertIn('windowrule[fusion-clipboard-history]:move', command)
            self.assertNotIn('windowrule[fusion-quick-panel]', command)
        with self.assertRaises(ValueError):
            placement.prepare(request, rule='other; dispatch exit')

    def test_missing_bar_preferences_use_top_and_do_not_prevent_opening(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(placement, 'ROOT', Path(directory)), \
                patch.object(placement.subprocess, 'check_output', side_effect=[
                    '{"x":6500,"y":10}', '[{"id":2,"x":4480,"y":0,"width":2560,"height":1440,"reserved":[0,38,0,0]}]']), \
                patch.object(placement, 'prepare', return_value=(440, 540)) as prepare:
            self.assertEqual(placement.prepare_popup(from_bar=True), (440, 540))
            self.assertEqual(prepare.call_args.args[0]['relative_y'], 48)


class Popup(test_ui.ClipboardFixture):
    def setUp(self):
        super().setUp()
        self.placement = self.stack.enter_context(patch.object(ui, 'prepare_popup', return_value=(440, 540)))
        self.activation = self.stack.enter_context(patch.object(ui, 'BarActivation'))
        self.pointer = self.stack.enter_context(patch.object(ui, 'check_pointer'))
        self.now = self.stack.enter_context(patch.object(ui.time, 'monotonic', return_value=100.))

    def events(self, *lines):
        queue = list(lines)
        return SimpleNamespace(canReadLine=lambda:bool(queue), readLine=lambda:queue.pop(0))

    def test_placement_failure_never_flashes_a_centered_window(self):
        self.placement.side_effect = RuntimeError('no compositor')
        self.window.reveal(from_bar=True)
        self.assertFalse(self.window.isVisible())
        self.activation.assert_not_called()

    def test_repeated_bar_click_closes_and_does_not_reopen_from_same_click(self):
        self.window.reveal(from_bar=True)
        self.assertTrue(self.window.isVisible())
        self.activation.return_value.start.assert_called_once()
        self.window.reveal(from_bar=True)
        self.assertFalse(self.window.isVisible())
        self.activation.return_value.cancel.assert_called()
        self.window.reveal(from_bar=True)
        self.assertFalse(self.window.isVisible())
        self.now.return_value = 101.
        self.window.reveal(from_bar=True)
        self.assertTrue(self.window.isVisible())

    def test_outside_click_closes_without_destroying_history_or_stealing_focus(self):
        self.store.add('text/plain;charset=utf-8', b'Keep this copy')
        self.window.reveal(); self.now.return_value = 101.
        self.window.compositor_events(self.events(ui.CLICK_EVENT))
        callback = self.pointer.call_args.args[1]
        callback(False); self.assertTrue(self.window.isVisible())
        self.ctl.reset_mock(); callback(True)
        self.assertFalse(self.window.isVisible()); self.ctl.assert_not_called()
        self.assertEqual(self.store.items[0].text, 'Keep this copy')
        self.assertFalse(self.window.stopping)
        self.window.reveal(from_bar=True)
        self.assertFalse(self.window.isVisible())
        # A deliberate keyboard shortcut is never eaten by bar debounce.
        self.window.reveal(); self.assertTrue(self.window.isVisible())

    def test_late_outside_query_cannot_close_a_reopened_popup(self):
        self.window.reveal(); self.now.return_value = 101.
        self.window.compositor_events(self.events(ui.CLICK_EVENT))
        callback = self.pointer.call_args.args[1]
        self.window.hide(); self.window.reveal()
        callback(True); self.assertTrue(self.window.isVisible())

    def test_opening_click_is_ignored_and_workspace_switch_never_refocuses_previous(self):
        self.window.reveal()
        self.window.compositor_events(self.events(ui.CLICK_EVENT))
        self.pointer.assert_not_called()
        self.ctl.reset_mock()
        self.window.compositor_events(self.events(b'workspacev2>>2,2'))
        self.assertFalse(self.window.isVisible()); self.ctl.assert_not_called()


class Launch(unittest.TestCase):
    def test_bar_and_hotkey_requests_are_small_and_distinct(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            address = Path(directory) / 'clipboard.sock'
            try:server.bind(str(address))
            except PermissionError:self.skipTest('This sandbox does not allow local socket listeners.')
            server.listen(1); server.settimeout(.5)
            for bar, expected in ((False, b'show\n'), (True, b'bar\n')):
                self.assertTrue(launch.send(address, from_bar=bar))
                peer, _ = server.accept()
                with peer:
                    self.assertEqual(peer.recv(32), expected)
            self.assertFalse(launch.send(Path(directory)/'missing.sock'))


if __name__ == '__main__': unittest.main()
