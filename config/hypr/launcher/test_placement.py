import json
from pathlib import Path
import tempfile
import unittest

from placement import bar_edge, bounds, selected_monitor


class PlacementTests(unittest.TestCase):
    def test_both_edges_reserve_bar_and_keep_saved_size(self):
        monitor = dict(x=4480, y=0, width=2560, height=1440, scale=1, reserved=[0, 38, 0, 0])
        self.assertEqual(bounds(monitor, (1140, 680), 'top'), (24, 52, 1140, 680))
        monitor['reserved'] = [0, 0, 0, 38]
        self.assertEqual(bounds(monitor, (1140, 680), 'bottom'), (24, 708, 1140, 680))

    def test_small_scaled_and_rotated_outputs_clamp_inside_workarea(self):
        monitor = dict(x=-1080, y=-200, width=1920, height=1080, scale=1.5,
                       transform=1, reserved=[0, 0, 0, 38])
        self.assertEqual(bounds(monitor, (1140, 1600), 'bottom'), (24, 14, 672, 1214))
        selected = selected_monitor([dict(monitor, id=1), dict(monitor, id=2, x=0)], {'x': -1000, 'y': -100})
        self.assertEqual(selected['id'], 1)

    def test_old_and_invalid_settings_default_top(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'options.json'
            self.assertEqual(bar_edge(path), 'top')
            for value, expected in [({'version': 1, 'hidden': []}, 'top'),
                                    ({'version': 1, 'position': 'bottom'}, 'bottom'),
                                    ({'version': 1, 'position': 'left'}, 'top'), ([], 'top')]:
                path.write_text(json.dumps(value))
                self.assertEqual(bar_edge(path), expected)


if __name__ == '__main__': unittest.main()
