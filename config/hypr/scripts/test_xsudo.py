"""Verify the elevation wrapper with mock commands; never call real sudo/xhost."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('xsudo.sh')


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xetal-xsudo-test-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        for name in ('xhost', 'sudo'):
            command = self.root/name
            command.write_text('''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
name=Path(sys.argv[0]).name
with Path(os.environ['TEST_LOG']).open('a') as f:
 f.write(json.dumps([name,sys.argv[1:],os.environ.get('SUDO_ASKPASS')])+'\\n')
if name=='xhost' and len(sys.argv)==1:
 print('access control enabled')
 if os.environ.get('ROOT_ALREADY_ALLOWED'):print('SI:localuser:root')
if name=='sudo':sys.exit(int(os.environ.get('SUDO_EXIT','0')))
''')
            command.chmod(0o755)
        self.log = self.root/'calls.jsonl'
        self.env = {**os.environ, 'PATH': str(self.root)+':/usr/bin', 'HOME': str(self.root),
                    'DISPLAY': ':99', 'HYPRLAND_INSTANCE_SIGNATURE': 'test', 'TEST_LOG': str(self.log)}
    def run_wrapper(self, **changes):
        result = subprocess.run(['bash', str(SCRIPT), '/program with spaces', 'literal $(command)'],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, env={**self.env, **changes})
        return result, [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_graphical_password_prompt_and_literal_arguments_with_cleanup_on_failure(self):
        result, calls = self.run_wrapper(SUDO_EXIT='7')
        self.assertEqual(result.returncode, 7)
        sudo = next(call for call in calls if call[0]=='sudo')
        self.assertEqual(sudo[1], ['--askpass', '--preserve-env=DISPLAY,XAUTHORITY', '--',
                                   '/program with spaces', 'literal $(command)'])
        self.assertEqual(sudo[2], str(self.root/'.config/hypr/scripts/sudo-askpass.sh'))
        self.assertEqual(calls[-1][1], ['-SI:localuser:root'])

    def test_existing_root_access_is_never_revoked(self):
        result, calls = self.run_wrapper(ROOT_ALREADY_ALLOWED='1')
        self.assertEqual(result.returncode, 0)
        self.assertEqual([call[1] for call in calls if call[0]=='xhost'], [[]])

    def test_no_display_does_not_change_x_access(self):
        result, calls = self.run_wrapper(DISPLAY='')
        self.assertEqual(result.returncode, 0)
        self.assertEqual([call[0] for call in calls], ['sudo'])


if __name__ == '__main__': unittest.main()
