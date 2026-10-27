"""Floating size memory without a real desktop or application launch."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import floating

KEY = 'a' * 24
OTHER = 'b' * 24


def client(address='0x123', size=None, **changes):
    return dict(address=address, size=size or [640, 420], mapped=True, floating=True,
                fullscreen=0, fullscreenClient=0, tags=[f'xetal-float-{KEY}-123456abcdef*'],
                focusHistoryID=0, monitor=0, initialClass='example', **changes)


class FloatingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'sizes.json'
        self.store = floating.Store(self.path)
        self.hypr = Mock()
        self.hypr.query.return_value = []
        self.tracker = floating.Tracker(self.hypr, self.store)
        self.request = {'key': KEY, 'classes': ['example'], 'terminal': False, 'name': 'Example'}

    def tearDown(self):self.temp.cleanup()

    def test_first_launch_centers_without_forcing_a_size(self):
        ticket = self.tracker.prepare(self.request, 0)
        self.assertIn('float on; center on;', ticket['rules'])
        self.assertNotIn('size ', ticket['rules'])
        self.assertFalse(self.path.exists())

    def test_last_floating_size_survives_restart_and_is_used_on_next_launch(self):
        self.tracker.update([client()], 0)
        self.tracker.update([client()], .6)
        resized = client(size=[990, 720])
        self.tracker.update([resized], 1)
        self.tracker.update([resized], 1.6)
        reopened = floating.Tracker(self.hypr, floating.Store(self.path))
        self.assertIn('size 990 720', reopened.prepare(self.request, 2)['rules'])

    def test_tiling_maximize_and_fullscreen_do_not_replace_floating_size(self):
        self.store.save({KEY: [640, 420]})
        for flags in ({'floating': False}, {'fullscreen': 1}, {'fullscreen': 2}, {'fullscreenClient': 1}):
            changed = {**client(size=[1920, 1042]), **flags}
            self.tracker.update([changed], 0)
            self.tracker.update([changed], 1)
            self.assertEqual(self.store.read()[KEY], [640, 420])

    def test_intentionally_large_floating_size_is_preserved(self):
        large = client(size=[1900, 1042])
        self.tracker.update([large], 0)
        self.tracker.update([large], .6)
        self.assertIn('size 1900 1042', self.tracker.prepare(self.request, 2)['rules'])

    def test_close_soon_after_resize_keeps_last_sample_without_saving_tiled_size(self):
        self.tracker.update([client()], 0)
        self.tracker.update([client()], .6)
        self.tracker.update([client(size=[850, 650])], 1)
        self.tracker.update([], 1.1)
        self.assertEqual(self.store.read()[KEY], [850, 650])

    def test_current_floating_size_takes_precedence_over_older_saved_size(self):
        self.store.save({KEY: [640, 420]})
        self.hypr.query.return_value = [client(size=[810, 610])]
        self.assertIn('size 810 610', self.tracker.prepare(self.request, 0)['rules'])

    def test_untagged_windows_and_other_shortcuts_do_not_overwrite_size(self):
        self.store.save({KEY: [640, 420]})
        unrelated = {**client(size=[990, 800]), 'tags': []}
        other = {**client('0x234', [720, 530]), 'tags': [f'xetal-float-{OTHER}-123456abcdef*']}
        for now in (0, .6):self.tracker.update([unrelated, other], now)
        self.assertEqual(self.store.read(), {KEY: [640, 420], OTHER: [720, 530]})

    def test_samples_settle_and_inactive_old_window_cannot_overwrite_recent_resize(self):
        old = {**client('0x456', [640, 420]), 'focusHistoryID': 3}
        resized = client(size=[800, 600])
        self.tracker.update([old, resized], 0)
        self.assertFalse(self.path.exists())
        self.tracker.update([old, resized], .6)
        self.assertEqual(self.store.read()[KEY], [800, 600])
        for now in (1, 1.6):self.tracker.update([old, client(size=[900, 640])], now)
        self.tracker.update([old, client(size=[900, 640])], 2)
        self.assertEqual(self.store.read()[KEY], [900, 640])

    def test_failed_launch_cannot_change_existing_window(self):
        current = {**client(), 'floating': False, 'tags': []}
        self.hypr.query.return_value = [current]
        ticket = self.tracker.prepare(self.request, 0)
        self.tracker.finish(ticket['token'], False, .1)
        self.tracker.update([current], 2)
        self.hypr.dispatch.assert_not_called()

    def test_reused_existing_window_is_floated_restored_and_centered(self):
        before = {**client(size=[1920, 1042]), 'floating': False, 'tags': []}
        self.hypr.query.return_value = [before]
        self.store.save({KEY: [800, 600]})
        ticket = self.tracker.prepare(self.request, 0)
        self.tracker.finish(ticket['token'], True, .1)
        self.tracker.pending[ticket['token']]['process'] = (99999999, 'old-process')
        self.hypr.query.side_effect = [[client(size=[800, 600])],
                                      [{'id': 0, 'x': -1920, 'y': 200, 'width': 1920, 'height': 1080,
                                        'scale': 1, 'reserved': [0, 38, 0, 0]}]]
        self.tracker.update([before], 2)
        calls = [call.args for call in self.hypr.dispatch.call_args_list]
        self.assertEqual(calls[:3], [('setfloating', 'address:0x123'),
                         ('resizewindowpixel', 'exact 800 600,address:0x123'),
                         ('movewindowpixel', 'exact -1360 459,address:0x123')])
        self.assertEqual(calls[3][0], 'tagwindow')
        self.assertTrue(calls[-1][1].startswith('+xetal-float-' + KEY))

    def test_slow_new_invocation_never_floats_an_existing_window(self):
        current = {**client(), 'floating': False, 'tags': []}
        self.hypr.query.return_value = [current]
        ticket = self.tracker.prepare(self.request, 0)
        self.tracker.finish(ticket['token'], True, .1)
        self.tracker.pending[ticket['token']]['process'] = (123, 'still-running')
        with patch.object(floating, 'process_stamp', return_value='still-running'):
            self.tracker.update([current], 2)
        self.hypr.dispatch.assert_not_called()

    def test_new_window_prevents_touching_preexisting_window(self):
        old = {**client(), 'floating': False, 'tags': []}
        self.hypr.query.return_value = [old]
        ticket = self.tracker.prepare(self.request, 0)
        pending = self.tracker.pending[ticket['token']]
        new = {**client('0x456'), 'tags': [pending['tag'] + '*']}
        self.tracker.finish(ticket['token'], True, .1)
        self.tracker.update([old, new], 2)
        self.hypr.dispatch.assert_not_called()

    def test_atomic_updates_merge_and_invalid_existing_data_is_not_overwritten(self):
        self.store.save({KEY: [640, 420]})
        floating.Store(self.path).save({OTHER: [800, 600]})
        self.assertEqual(self.store.read(), {KEY: [640, 420], OTHER: [800, 600]})
        self.path.write_text('{broken')
        with self.assertRaises(ValueError):self.store.save({KEY: [900, 700]})
        self.assertEqual(self.path.read_text(), '{broken')

    def test_scaled_rotated_monitor_workarea(self):
        self.assertEqual(floating.workarea({'width': 2560, 'height': 1440, 'x': 0, 'y': -100,
                         'scale': 1.5, 'transform': 1, 'reserved': [0, 40, 0, 0]}), (0, -60, 960, 1667))

    def test_watcher_exits_when_session_connection_closes_and_cleans_its_socket(self):
        root = Path(self.temp.name) / 'hypr/test'
        root.mkdir(parents=True)
        env = dict(os.environ, XDG_RUNTIME_DIR=self.temp.name, HYPRLAND_INSTANCE_SIGNATURE='test')
        with socket.socket(socket.AF_UNIX) as events:
            events.bind(str(root / '.socket2.sock'));events.listen(1);events.settimeout(3)
            process = subprocess.Popen([sys.executable, str(Path(floating.__file__)), '--watch',
                                        '--state', str(self.path)], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                connection, _ = events.accept()
                deadline = time.monotonic() + 3
                while not (root / 'floating-geometry.sock').exists() and time.monotonic() < deadline:time.sleep(.01)
                self.assertTrue((root / 'floating-geometry.sock').exists())
                connection.close()
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, stderr.decode())
                self.assertFalse((root / 'floating-geometry.sock').exists())
            finally:
                if process.poll() is None:process.terminate();process.communicate(timeout=3)


if __name__ == '__main__':unittest.main()
