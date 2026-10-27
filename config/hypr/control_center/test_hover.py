import json
import unittest
from unittest.mock import patch

from app import hovered_window


class HoverTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            'cursorpos': {'x': 150, 'y': 150},
            'monitors': [{'x': 0, 'y': 0, 'width': 1920, 'height': 1080, 'scale': 1,
                          'activeWorkspace': {'id': 1}, 'specialWorkspace': {'id': 0}}],
            'clients': [
                {'class': 'focused-elsewhere', 'at': [800, 0], 'size': [500, 500], 'workspace': {'id': 1},
                 'mapped': True, 'floating': False, 'focusHistoryID': 0},
                {'class': 'under-pointer', 'at': [0, 0], 'size': [700, 700], 'workspace': {'id': 1},
                 'mapped': True, 'floating': False, 'focusHistoryID': 3},
                {'class': 'other-workspace', 'at': [0, 0], 'size': [700, 700], 'workspace': {'id': 2},
                 'mapped': True, 'floating': True, 'focusHistoryID': 1},
            ],
        }

    def lookup(self):
        with patch('app.run', side_effect=lambda argv: json.dumps(self.data[argv[-1]])):
            return hovered_window()

    def test_pointer_target_is_independent_of_keyboard_focus(self):
        self.assertEqual(self.lookup()['class'], 'under-pointer')

    def test_floating_overlay_wins_but_hidden_windows_do_not(self):
        self.data['clients'].append({'class': 'floating', 'at': [100, 100], 'size': [400, 400],
                                     'workspace': {'id': 1}, 'mapped': True, 'floating': True, 'focusHistoryID': 2})
        self.assertEqual(self.lookup()['class'], 'floating')
        self.data['clients'][-1]['hidden'] = True
        self.assertEqual(self.lookup()['class'], 'under-pointer')

    def test_empty_desktop_does_not_choose_an_unrelated_window(self):
        self.data['cursorpos'] = {'x': 1800, 'y': 900}
        with self.assertRaisesRegex(RuntimeError, 'Place the pointer'):
            self.lookup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
