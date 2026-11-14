"""Check Python/native policy agreement using disposable settings files."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspaces import model


class NativePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='workspace-policy-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.binary = cls.root/'policy-reader'
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'json-c'], text=True))
        subprocess.run(['g++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                        str(Path(__file__).with_suffix('.cpp')), '-o', str(cls.binary), *flags],
                       check=True, capture_output=True, text=True, timeout=30)

    def test_profile_fallback_overrides_legacy_and_special_workspaces(self):
        cases = [None, {'version':1, 'workspaces':{}}]
        for layout in model.LAYOUTS:
            cases.append({'version':1, 'default_layout':layout, 'workspaces':{
                '203':dict(model.DEFAULT, layout='tile'), '204':dict(model.DEFAULT, layout='off')}})
        path = self.root/'rules.json'
        for data in cases:
            with self.subTest(data=data):
                if data is None: path.unlink(missing_ok=True)
                else: path.write_text(model.encode(data))
                loaded,_ = model.load(path)
                ids = (1, 203, 204, 1004, 2147483647)
                result = subprocess.run([str(self.binary), str(path), *map(str, (*ids, 0, -99))],
                                        capture_output=True, text=True, check=True, timeout=5)
                expected = [str(int(model.needs_controls(loaded)))]
                expected += [p['layout']+' '+p['controls'] for p in (model.effective(loaded, i) for i in ids)]
                expected += ['off individual', 'off individual']
                self.assertEqual(result.stdout.splitlines(), expected)

    def test_both_readers_reject_invalid_profile_defaults(self):
        path = self.root/'invalid.json'
        for value in (None, True, [], 'unknown'):
            path.write_text(json.dumps({'version':1, 'default_layout':value, 'workspaces':{}}))
            with self.subTest(value=value), self.assertRaises(ValueError): model.load(path)
            result = subprocess.run([str(self.binary), str(path), '1'], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__': unittest.main()
