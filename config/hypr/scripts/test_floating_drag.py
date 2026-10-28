import runpy
from pathlib import Path
import unittest
from unittest.mock import Mock

module = runpy.run_path(str(Path(__file__).with_name('floating-drag.py')))
Drag, in_grip = module['Drag'], module['in_grip']


class FloatingDragTests(unittest.TestCase):
    def setUp(self):
        self.window = dict(address='0x123', pid=42, mapped=True, hidden=False,
                           floating=True, fullscreen=0, at=[-1000, 200], size=[800, 600])
        self.point = dict(x=-700, y=220)
        self.hypr = Mock()
        self.drag = Drag(self.hypr)
        self.drag.hovered = Mock(return_value=(self.point, self.window))
        self.hypr.query.return_value = self.point

    def test_only_title_band_of_floating_normal_windows(self):
        self.assertTrue(in_grip(self.window, self.point))
        for changes in ({'floating': False}, {'fullscreen': 1}, {'mapped': False}, {'hidden': True}):
            self.assertFalse(in_grip(dict(self.window, **changes), self.point))
        for point in (dict(x=-990,y=220),dict(x=-220,y=220),dict(x=-700,y=202),dict(x=-700,y=250)):
            self.assertFalse(in_grip(self.window, point))

    def test_click_and_small_movement_pass_through(self):
        self.drag.press(0)
        self.hypr.query.return_value = dict(x=-696,y=222)
        self.drag.tick(.1); self.drag.release()
        self.hypr.dispatch.assert_not_called()

    def test_drag_starts_once_and_release_ends_it(self):
        self.drag.press(0)
        self.hypr.query.return_value = dict(x=-680,y=222)
        self.drag.hovered.return_value = (dict(x=-680,y=222), self.window)
        self.drag.tick(.1); self.drag.tick(.2)
        self.assertEqual(self.hypr.dispatch.call_count, 2)
        self.drag.release(); self.drag.release()
        self.assertEqual([call.args for call in self.hypr.dispatch.call_args_list],
                         [('tagwindow','+xetal-title-drag,address:0x123'),
                          ('movewindowpixel','exact -980 202,address:0x123'),
                          ('tagwindow','-xetal-title-drag,address:0x123')])

    def test_native_drag_resize_or_different_window_is_left_alone(self):
        for changes in ({'at': [-990,220]}, {'size': [820,600]}, {'address': '0x456'},
                        {'pid': 99}, {'floating': False}, {'fullscreen': 1}):
            self.drag.hovered.return_value = (self.point, self.window)
            self.drag.press(0)
            self.hypr.query.return_value = dict(x=-680,y=222)
            self.drag.hovered.return_value = (dict(x=-680,y=222), dict(self.window, **changes))
            self.drag.tick(.1)
        self.hypr.dispatch.assert_not_called()

    def test_closed_window_during_release_does_not_stop_the_helper(self):
        self.drag.press(0)
        self.hypr.query.return_value = dict(x=-680,y=222)
        self.drag.hovered.return_value = (dict(x=-680,y=222), self.window)
        self.drag.tick(.1)
        self.hypr.dispatch.side_effect = ValueError('Window no longer exists')
        self.drag.release()
        self.assertIsNone(self.drag.candidate)
        self.assertFalse(self.drag.dragging)


if __name__ == '__main__': unittest.main()
