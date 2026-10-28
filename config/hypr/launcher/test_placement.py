import json
from pathlib import Path
import tempfile
import unittest
import os
import socket
from unittest.mock import patch

from placement import bar_edge, bounds, selected_monitor,contact_existing


class PlacementTests(unittest.TestCase):
    def test_open_menu_receives_toggle_and_edit_without_launching_qt(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'XDG_RUNTIME_DIR':directory,'HYPRLAND_INSTANCE_SIGNATURE':'test'}):
            path=Path(directory)/'hypr/test';path.mkdir(parents=True)
            self.assertFalse(contact_existing(['--from-bar']))
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.bind(str(path/'xetal-launcher.sock'));server.listen(2);server.settimeout(1)
                for arguments,expected in [(['--from-bar'],b'toggle\n'),(['--edit','test.desktop'],b'{"edit": "test.desktop"}\n')]:
                    self.assertTrue(contact_existing(arguments))
                    peer,_=server.accept()
                    with peer:self.assertEqual(peer.recv(1000),expected)

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
