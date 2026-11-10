from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from window_rules.window_types import geometry_managed, window_metadata


class WindowTypesTests(unittest.TestCase):
    def test_native_protocol_types(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'window-types'
            result = subprocess.run(['g++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                                     str(Path(__file__).with_suffix('.cpp')), '-o', str(binary)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_only_matching_verified_metadata_allows_geometry(self):
        client = {'address': '0x123', 'stableId': 'abc'}
        meta = {'stableId': 'abc', 'geometry_managed': True}
        self.assertTrue(geometry_managed(client, meta))
        for invalid in (None, {}, [], {**meta, 'stableId': 'def'}, {**meta, 'geometry_managed': False},
                        {**meta, 'geometry_managed': 1}, {**meta, 'geometry_managed': 'true'}):
            self.assertFalse(geometry_managed(client, invalid))
        self.assertFalse(geometry_managed({}, meta))

    def test_missing_or_old_adapter_is_safe(self):
        hypr = Mock()
        for response in ([], None, 'unknown request', {}):
            hypr.query.return_value = response
            self.assertEqual(window_metadata(hypr), {})
        for error in (OSError('unavailable'), ValueError('not JSON')):
            hypr.query.side_effect = error
            self.assertEqual(window_metadata(hypr), {})


if __name__ == '__main__': unittest.main()
