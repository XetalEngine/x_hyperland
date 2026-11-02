import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from drag_cursor import CursorGuard, arrow_images, fingerprint


class CursorGuardTests(unittest.TestCase):
    def setUp(self):
        self.hypr = Mock()
        self.guard = CursorGuard(self.hypr, roots=[])
        self.state = dict(down=True, serial=4, press={'kind':'arrow'}, current={'kind':'arrow'})
        self.hypr.query.return_value = self.state

    def test_only_ordinary_pointer_allows_drag(self):
        self.assertEqual(self.guard.allowed(), 4)
        for kind in ('text', 'other', 'unknown', '', None):
            with self.subTest(kind=kind):
                self.state['current'] = {'kind':kind}
                self.assertIsNone(self.guard.allowed())

    def test_origin_stays_blocked_even_when_current_shape_is_arrow(self):
        self.state['press'] = {'kind':'text'}
        self.assertIsNone(self.guard.allowed())

    def test_missing_probe_release_and_new_gesture_are_not_drag_permission(self):
        self.assertIsNone(self.guard.allowed(3))
        self.state['down'] = False
        self.assertIsNone(self.guard.allowed())
        for state in ({}, None, [], 'unknown request', {'down':True,'serial':True}):
            self.hypr.query.return_value = state
            self.assertIsNone(self.guard.allowed())
        self.hypr.query.side_effect = ValueError('Unknown request')
        self.assertIsNone(self.guard.allowed())

    def test_bitmap_must_match_an_installed_arrow_exactly(self):
        pixels = bytes.fromhex('010203ff040506ff')
        data = (struct.pack('<4I', 0x72756358,16,1,1) + struct.pack('<3I',0xfffd0002,24,28) +
                struct.pack('<9I',36,0xfffd0002,24,1,2,1,0,0,0) + pixels)
        expected = (2, 1, fingerprint(pixels))
        self.assertEqual(arrow_images(data), {expected})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'test/cursors/left_ptr';path.parent.mkdir(parents=True);path.write_bytes(data)
            guard = CursorGuard(self.hypr, [Path(temp)])
            self.assertTrue(guard.ordinary(dict(kind='bitmap',width=2,height=1,hash=expected[2])))
            self.assertFalse(guard.ordinary(dict(kind='bitmap',width=2,height=1,hash='other')))
            self.assertFalse(guard.ordinary(dict(kind='bitmap',width=1,height=2,hash=expected[2])))
        for count in range(len(data)):
            self.assertEqual(arrow_images(data[:count]), set())


if __name__ == '__main__': unittest.main()
