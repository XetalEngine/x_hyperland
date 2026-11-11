"""Deterministic cross-monitor popup races; no session or display is modified."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import menu_focus as focus


def session(focused='DP-5', workspace=3, special=0, active='', left_workspace=2):
    return focus.Session({
        'DP-4': focus.Monitor(left_workspace, 0, (0, 0)),
        'DP-5': focus.Monitor(workspace, special, (1920, 0)),
        'DP-6': focus.Monitor(4, 0, (4480, 0)),
    }, focused, active)


class ContextTests(unittest.TestCase):
    def capture(self, state=None, monitor='DP-5', origin=(1920, 0)):
        return focus.MenuContext.capture(state or session(), monitor, origin)

    def test_entering_clicked_monitor_is_not_leaving_menu(self):
        context = self.capture(session(focused='DP-4'))
        self.assertFalse(context.changed(session(focused='DP-4')))
        self.assertFalse(context.changed(session()))
        self.assertFalse(context.changed(session()))
        self.assertTrue(context.changed(session(focused='DP-4')))

    def test_workspace_and_special_changes_only_affect_menu_output(self):
        context = self.capture()
        self.assertFalse(context.changed(session(left_workspace=7)))
        self.assertTrue(context.changed(session(workspace=8)))
        self.assertTrue(context.changed(session(special=-99)))
        self.assertTrue(self.capture(session(special=-99)).changed(session()))

    def test_application_focus_and_return_to_same_application(self):
        context = self.capture(session(active='0xabc'))
        # An opening-time notification can still mention the old app. The
        # subsequent desktop focus clears it, so returning to that app closes.
        self.assertFalse(context.changed(session(active='0xabc')))
        self.assertFalse(context.changed(session()))
        self.assertTrue(context.changed(session(active='0xabc')))
        self.assertTrue(self.capture().changed(session(active='0xdef')))

    def test_removing_output_dismisses_its_menu(self):
        context = self.capture()
        current = session()
        del current.monitors['DP-5']
        self.assertTrue(context.changed(current))

    def test_first_click_before_layout_resolves_monitor_by_origin(self):
        context = self.capture(monitor='unresolved')
        self.assertEqual(context.monitor, 'DP-5')
        self.assertFalse(context.changed(session()))
        self.assertIsNone(self.capture(monitor=None, origin=(9999, 0)))
        self.assertIsNone(focus.MenuContext.capture(None, 'DP-5', (1920, 0)))

    def test_connector_identity_survives_monitor_rearrangement(self):
        current = session()
        current.monitors['DP-5'] = focus.Monitor(3, 0, (-2560, 1080))
        self.assertEqual(self.capture(current).monitor, 'DP-5')
        self.assertFalse(self.capture().changed(current))

    def test_failed_snapshot_keeps_context_for_next_valid_notification(self):
        context = self.capture()
        self.assertFalse(context.changed(None))
        self.assertTrue(context.changed(session(workspace=8)))


class SnapshotTests(unittest.TestCase):
    def reply(self):
        return json.dumps([dict(name='DP-5', x=1920, y=0, focused=True,
                                activeWorkspace=dict(id=3, name='Work, three'),
                                specialWorkspace=dict(id=0, name=''))])+'\n\n\n{}'

    def test_reads_one_bounded_batch_and_uses_workspace_ids(self):
        env = {'HYPRLAND_INSTANCE_SIGNATURE': 'test-session'}
        with patch.object(focus.subprocess, 'check_output', return_value=self.reply()) as query:
            current = focus.read_session(env)
        self.assertEqual(current, focus.Session({'DP-5': focus.Monitor(3, 0, (1920, 0))}, 'DP-5', ''))
        self.assertEqual(query.call_args.args[0], ['hyprctl', '--batch', 'j/monitors; j/activewindow'])
        self.assertIs(query.call_args.kwargs['env'], env)
        self.assertLessEqual(query.call_args.kwargs['timeout'], .5)

    def test_unavailable_or_partial_snapshot_is_not_a_focus_change(self):
        for reply in ('', 'unsafe state', '{}\n{}', '[{}]\n{}', self.reply()[:-1], '[]\nnull'):
            with self.subTest(reply=reply), patch.object(focus.subprocess, 'check_output', return_value=reply):
                self.assertIsNone(focus.read_session({}))
        for error in (OSError('unavailable'), subprocess.TimeoutExpired('hyprctl', .5),
                      subprocess.CalledProcessError(1, 'hyprctl')):
            with self.subTest(error=error), patch.object(focus.subprocess, 'check_output', side_effect=error):
                self.assertIsNone(focus.read_session({}))


class EventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import the real socket callback without starting Gtk.main or creating
        # layer surfaces. Keep the app's private environment out of other tests.
        spec = importlib.util.spec_from_file_location('desktop_menu_app_test', Path(__file__).with_name('app.py'))
        cls.app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ), patch.object(sys, 'path', list(sys.path)):
            spec.loader.exec_module(cls.app)

    def setUp(self):
        self.desktop = self.app.Desktop.__new__(self.app.Desktop)
        self.desktop.events = bytearray()
        self.window = Mock()
        self.window.desktop_monitor.get_geometry.return_value = SimpleNamespace(x=1920, y=0)
        self.window.menu.get_visible.return_value = True
        self.desktop.surfaces = {'middle': self.window}
        self.desktop.icons = Mock()
        self.desktop.icons.canvases = {self.window: SimpleNamespace(monitor='DP-5')}
        self.current = session()
        self.query = self.enterContext(patch.object(focus, 'read_session', side_effect=lambda _env: self.current))
        self.desktop.watch_menu(self.window)
        self.query.reset_mock()

    def receive(self, data):
        stream = Mock()
        stream.recv.return_value = data
        self.assertTrue(self.desktop.session_event(stream, self.app.GLib.IOCondition.IN))

    def test_late_focus_event_from_right_click_does_not_pop_down_menu(self):
        self.receive(b'focusedmonv2>>DP-5,3\n')
        self.window.menu.popdown.assert_not_called()
        self.query.assert_called_once()

    def test_queued_old_workspace_monitor_and_window_events_use_current_state(self):
        self.receive(b'focusedmonv2>>DP-4,2\nworkspacev2>>2,Two\nactivewindowv2>>deadbeef\n'
                     b'activespecialv2>>-99,old,DP-5\nfocusedmonv2>>DP-5,3\nactivewindowv2>>\n')
        self.window.menu.popdown.assert_not_called()
        self.query.assert_called_once()

    def test_actual_context_changes_still_dismiss(self):
        for state, event in ((session(workspace=8), b'workspacev2>>8,Eight\n'),
                             (session(focused='DP-4'), b'focusedmonv2>>DP-4,2\n'),
                             (session(special=-99), b'activespecialv2>>-99,test,DP-5\n'),
                             (session(active='0xabc'), b'activewindowv2>>abc\n')):
            with self.subTest(event=event):
                self.current = session()
                self.desktop.watch_menu(self.window)
                self.window.menu.popdown.reset_mock()
                self.current = state
                self.receive(event)
                self.window.menu.popdown.assert_called_once()
                self.assertIsNone(self.window.menu_context)

    def test_partial_messages_and_unrelated_notifications(self):
        self.receive(b'focusedmonv2>>DP-')
        self.query.assert_not_called()
        self.receive(b'5,3\nactivelayout>>test\n')
        self.query.assert_called_once()
        self.window.menu.popdown.assert_not_called()
        self.query.reset_mock()
        self.receive(b'configreloaded>>\n')
        self.desktop.icons.schedule_layout.assert_called_once()
        self.query.assert_not_called()

    def test_other_monitors_workspace_and_late_events_after_reopening(self):
        self.current = session(left_workspace=7)
        self.receive(b'workspacev2>>7,Seven\n')
        self.window.menu.popdown.assert_not_called()
        self.desktop.dismiss()
        self.window.menu.popdown.reset_mock()
        self.current = session(workspace=8)
        self.desktop.watch_menu(self.window)
        self.receive(b'workspacev2>>3,Three\nfocusedmonv2>>DP-4,7\n')
        self.window.menu.popdown.assert_not_called()

    def test_file_actions_replacement_inherits_original_workspace(self):
        original = self.window.menu_context
        loading = self.window.menu
        self.window.menu = Mock()
        self.window.menu.get_visible.return_value = True
        self.assertIs(self.window.menu_context, original)
        self.current = session(workspace=8)
        self.receive(b'workspacev2>>8,Eight\n')
        self.window.menu.popdown.assert_called_once()
        loading.popdown.assert_not_called()

    def test_no_queries_for_closed_menus_and_no_reopening_on_ipc_failure(self):
        self.window.menu.get_visible.return_value = False
        self.receive(b'focusedmonv2>>DP-5,3\n')
        self.query.assert_not_called()
        self.window.menu.get_visible.return_value = True
        self.current = None
        self.receive(b'focusedmonv2>>DP-5,3\n')
        self.window.menu.popdown.assert_not_called()
        self.current = session(workspace=8)
        self.receive(b'workspacev2>>8,Eight\n')
        self.window.menu.popdown.assert_called_once()
        self.window.menu.popup_at_pointer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
