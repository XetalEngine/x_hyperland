import runpy
from pathlib import Path
import unittest
from unittest.mock import Mock

module = runpy.run_path(str(Path(__file__).with_name('floating-drag.py')))
Drag, in_grip = module['Drag'], module['in_grip']


class FloatingDragTests(unittest.TestCase):
    def setUp(self):
        self.window = dict(address='0x123', stableId='1', pid=42, mapped=True, hidden=False,
                           floating=True, fullscreen=0, at=[-1000, 200], size=[800, 600])
        self.point = dict(x=-700, y=220)
        self.hypr = Mock()
        self.guard = Mock()
        self.guard.allowed.return_value = 1
        self.drag = Drag(self.hypr, self.guard, lambda: (dict(distance=2,hold_ms=120), "test"))
        self.drag.hovered = Mock(return_value=(self.point, self.window))
        self.query = Mock(return_value=self.point)
        self.clients = [self.window]
        self.state = {'native_drag': False}
        self.metadata = {'0x123': {'geometry_managed': True, 'stableId': '1'}}
        self.hypr.query.side_effect = lambda what: {'xetal-windows': self.metadata, 'clients': self.clients,
                                                   'xetal-cursor': self.state}.get(what, self.query(what))

    def test_only_title_band_of_floating_normal_windows(self):
        self.assertTrue(in_grip(self.window, self.point))
        for changes in ({'floating': False}, {'fullscreen': 1}, {'mapped': False}, {'hidden': True}):
            self.assertFalse(in_grip(dict(self.window, **changes), self.point))
        for point in (dict(x=-990,y=220),dict(x=-220,y=220),dict(x=-700,y=199),dict(x=-700,y=250)):
            self.assertFalse(in_grip(self.window, point))

    def test_grip_starts_at_the_uppermost_pixel_including_the_actual_border(self):
        for border in (0, 1, 2, 4):
            with self.subTest(border=border):
                for y in (200-border, 200, 201, 202, 203, 204, 205, 231.9):
                    self.assertTrue(in_grip(self.window, dict(x=-700, y=y), border))
                for y in (199.9-border, 232):
                    self.assertFalse(in_grip(self.window, dict(x=-700, y=y), border))

    def test_press_uses_recorded_origin_after_pointer_has_already_left_window(self):
        self.state.update(serial=1, origin=dict(self.point, address='0x123', stableId='1', border=2))
        self.query.return_value = dict(x=-700, y=100)
        self.drag.hovered.return_value = (self.query.return_value, None)
        self.drag.press(0)
        self.assertEqual(self.drag.candidate[0], self.window)
        self.assertEqual(self.drag.candidate[1]['y'], 220)
        self.drag.hovered.assert_not_called()
        self.guard.allowed.assert_called_once_with(1)

    def test_border_press_is_kept_even_before_client_surface_begins(self):
        self.state.update(serial=1, origin=dict(x=-700, y=198, address='0x123', stableId='1', border=2))
        self.drag.press(0)
        self.assertIsNotNone(self.drag.candidate)

    def test_non_window_press_does_not_turn_into_drag_when_pointer_enters_header(self):
        self.state['origin'] = None
        self.drag.press(0)
        self.assertIsNone(self.drag.candidate)
        self.guard.allowed.assert_not_called()

    def test_unavailable_probe_cannot_start_a_grab_or_crash_the_helper(self):
        for self.state in (None, [], 'unknown request', 0):
            self.drag.press(0)
            self.assertIsNone(self.drag.candidate)
        self.guard.allowed.assert_not_called()

    def test_reused_window_address_cannot_inherit_a_press(self):
        self.state.update(serial=1, origin=dict(self.point, address='0x123', stableId='previous', border=2))
        self.drag.press(0)
        self.assertIsNone(self.drag.candidate)

    def test_new_button_serial_cannot_inherit_an_old_origin(self):
        self.state.update(serial=1, origin=dict(self.point, address='0x123', stableId='1', border=2))
        self.guard.allowed.return_value = None
        self.drag.press(0)
        self.guard.allowed.assert_called_once_with(1)
        self.assertIsNone(self.drag.candidate)

    def test_fast_upward_drag_survives_leaving_the_window_during_hold(self):
        self.drag.press(0)
        self.query.return_value = dict(x=-680, y=150)
        self.drag.hovered.return_value = (self.query.return_value, None)
        self.drag.tick(.15)
        self.assertTrue(self.drag.dragging)
        self.hypr.dispatch.assert_called_once_with('tagwindow', '+xetal-title-drag,address:0x123')
        self.query.return_value = dict(x=-660, y=130)
        self.drag.tick(.2)
        self.hypr.dispatch.assert_called_with('movewindowpixel', 'exact -980 180,address:0x123')

    def test_crossing_another_window_does_not_transfer_or_cancel_the_grab(self):
        self.drag.press(0)
        self.query.return_value = dict(x=-680, y=150)
        self.drag.hovered.return_value = (self.query.return_value, dict(self.window, address='0x456'))
        self.drag.tick(.15)
        self.assertTrue(self.drag.dragging)
        self.hypr.dispatch.assert_called_once_with('tagwindow', '+xetal-title-drag,address:0x123')
        self.query.return_value = dict(x=-660, y=130)
        self.drag.tick(.2)
        self.hypr.dispatch.assert_called_with('movewindowpixel', 'exact -980 180,address:0x123')

    def test_takeover_discards_pending_motion_and_tracks_only_subsequent_delta(self):
        for dx, dy in ((300, 0), (-300, 0), (0, -120), (0, 300), (210, -100)):
            with self.subTest(pending_motion=(dx, dy)):
                self.hypr.dispatch.reset_mock()
                self.drag.press(0)
                self.query.return_value = dict(x=self.point['x']+dx, y=self.point['y']+dy)
                self.drag.tick(.5)
                self.assertTrue(self.drag.dragging)
                self.hypr.dispatch.assert_called_once_with('tagwindow', '+xetal-title-drag,address:0x123')
                self.drag.tick(.55)  # A held, stationary pointer cannot jump later.
                self.assertEqual(self.hypr.dispatch.call_count, 1)
                self.query.return_value = dict(x=self.point['x']+dx+7, y=self.point['y']+dy-9)
                self.drag.tick(.6)
                self.hypr.dispatch.assert_called_with('movewindowpixel', 'exact -993 191,address:0x123')
                self.drag.release()

    def test_click_and_small_movement_pass_through(self):
        self.drag.press(0)
        self.query.return_value = dict(x=-696,y=222)
        self.drag.tick(.08); self.drag.release()
        self.hypr.dispatch.assert_not_called()

    def test_hold_and_distance_are_both_required(self):
        self.drag.press(0)
        self.query.return_value = dict(x=-699,y=220)
        self.drag.tick(1)
        self.hypr.dispatch.assert_not_called()
        self.drag.release()
        self.drag.press(2)
        self.query.return_value = dict(x=-680,y=220)
        self.drag.tick(2.08)
        self.drag.release()
        self.hypr.dispatch.assert_not_called()

    def test_saved_thresholds_take_effect_on_next_press(self):
        self.drag.settings_loader = lambda: (dict(distance=12,hold_ms=250), "custom")
        self.drag.press(0)
        self.query.return_value = dict(x=-690,y=220)
        self.drag.tick(.3)
        self.hypr.dispatch.assert_not_called()
        self.query.return_value = dict(x=-680,y=220)
        self.drag.hovered.return_value = (dict(x=-680,y=220), self.window)
        self.drag.tick(.35)
        self.assertTrue(self.drag.dragging)
        self.drag.release()

    def test_drag_starts_once_and_release_ends_it(self):
        self.drag.press(0)
        self.query.return_value = dict(x=-680,y=222)
        self.drag.hovered.return_value = (dict(x=-680,y=222), self.window)
        self.drag.tick(.15); self.drag.tick(.2)
        self.assertEqual(self.hypr.dispatch.call_count, 1)
        self.query.return_value = dict(x=-660,y=232)
        self.drag.tick(.25); self.drag.tick(.3)
        self.assertEqual(self.hypr.dispatch.call_count, 2)
        self.drag.release(); self.drag.release()
        self.assertEqual([call.args for call in self.hypr.dispatch.call_args_list],
                         [('tagwindow','+xetal-title-drag,address:0x123'),
                          ('movewindowpixel','exact -980 210,address:0x123'),
                          ('tagwindow','-xetal-title-drag,address:0x123')])

    def test_native_drag_resize_closed_or_replaced_window_is_left_alone(self):
        for changes in ({'at': [-990,220]}, {'size': [820,600]}, {'address': '0x456'},
                        {'pid': 99}, {'stableId': 'reused'}, {'mapped': False}, {'hidden': True},
                        {'floating': False}, {'fullscreen': 1}):
            self.drag.hovered.return_value = (self.point, self.window)
            self.drag.press(0)
            self.query.return_value = dict(x=-680,y=222)
            self.clients = [dict(self.window, **changes)]
            self.drag.tick(.15)
        self.hypr.dispatch.assert_not_called()

    def test_closed_window_during_release_does_not_stop_the_helper(self):
        self.drag.press(0)
        self.query.return_value = dict(x=-680,y=222)
        self.drag.hovered.return_value = (dict(x=-680,y=222), self.window)
        self.drag.tick(.15)
        self.hypr.dispatch.side_effect = ValueError('Window no longer exists')
        self.drag.release()
        self.assertIsNone(self.drag.candidate)
        self.assertFalse(self.drag.dragging)

    def test_text_press_never_becomes_a_window_drag_after_leaving_field(self):
        self.guard.allowed.return_value = None
        self.drag.press(0)
        self.guard.allowed.return_value = 1
        self.query.return_value = dict(x=-550,y=220)
        self.drag.tick(.15)
        self.assertIsNone(self.drag.candidate)
        self.hypr.dispatch.assert_not_called()

    def test_delayed_text_cursor_cancels_before_movement_threshold(self):
        self.drag.press(0)
        self.guard.allowed.return_value = None
        self.drag.tick(.01)
        self.guard.allowed.return_value = 1
        self.query.return_value = dict(x=-550,y=220)
        self.drag.tick(.15)
        self.hypr.dispatch.assert_not_called()

    def test_started_header_drag_continues_over_text(self):
        self.drag.press(0)
        self.query.return_value = dict(x=-680,y=222)
        self.drag.hovered.return_value = (dict(x=-680,y=222), self.window)
        self.drag.tick(.15)
        self.guard.allowed.return_value = None
        self.query.return_value = dict(x=-660,y=222)
        self.drag.tick(.2)
        self.assertTrue(self.drag.dragging)
        self.hypr.dispatch.assert_called_with('movewindowpixel','exact -980 200,address:0x123')

    def test_native_grip_leaves_motion_to_compositor(self):
        self.state['native_drag'] = True
        self.drag.press(0)
        self.query.return_value = dict(x=-680,y=222)
        self.drag.hovered.return_value=(dict(x=-680,y=222),self.window)
        self.drag.tick(.15);self.drag.tick(.2)
        self.hypr.dispatch.assert_called_once_with('xetaldrag:begin','0x123 1')
        self.drag.release();self.drag.release()
        self.assertEqual([c.args for c in self.hypr.dispatch.call_args_list],
                         [('xetaldrag:begin','0x123 1'),('xetaldrag:end','')])

    def test_menu_and_unknown_surface_never_acquire_title_grip(self):
        for meta in ({}, {'geometry_managed':False,'stableId':'1'},
                     {'geometry_managed':True,'stableId':'reused'}):
            self.metadata['0x123']=meta
            self.drag.press(0)
            self.query.return_value=dict(x=-680,y=222)
            self.drag.tick(.2)
            self.assertIsNone(self.drag.candidate)
        self.hypr.dispatch.assert_not_called()

    def test_role_change_before_or_during_drag_stops_geometry_changes(self):
        self.drag.press(0)
        self.metadata['0x123']['geometry_managed']=False
        self.query.return_value=dict(x=-680,y=222)
        self.drag.tick(.2)
        self.hypr.dispatch.assert_not_called()
        self.metadata['0x123']['geometry_managed']=True
        self.drag.press(1)
        self.drag.hovered.return_value=(dict(x=-680,y=222),self.window)
        self.drag.tick(1.2)
        self.hypr.dispatch.reset_mock()
        self.metadata['0x123']['geometry_managed']=False
        self.drag.tick(1.3)
        self.assertFalse(self.drag.dragging)
        self.hypr.dispatch.assert_called_once_with('tagwindow','-xetal-title-drag,address:0x123')


if __name__ == '__main__': unittest.main()
