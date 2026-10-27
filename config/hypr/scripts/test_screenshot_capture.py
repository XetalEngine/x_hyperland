"""Exercise the capture script with fake tools; never capture the desktop."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

SCRIPT = Path(__file__).with_name('screenshot.sh')


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.runtime = self.root / 'runtime'
        self.session = self.runtime / 'hypr' / 'test-capture'
        self.session.mkdir(parents=True)
        self.guard = self.session / 'screenshot-active.lock'
        helper = self.bin / 'fake-tool'
        helper.write_text('''#!/usr/bin/python3
import fcntl,json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
root=Path(os.environ['CAPTURE_TEST_ROOT'])
guard=root/'runtime/hypr/test-capture/screenshot-active.lock'
with guard.open('rb') as fd:
    try: fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB); held=False
    except BlockingIOError: held=True
with (root/'events.jsonl').open('a') as stream:
    stream.write(json.dumps({'tool':name,'guard':held})+'\\n')
if name=='xdg-user-dir': print(root/'Pictures')
elif name=='slurp':
    if os.environ.get('CAPTURE_CANCEL'): sys.exit(1)
    print('10,20 300x400')
elif name=='grim':
    if os.environ.get('CAPTURE_FAIL'): sys.exit(1)
    Path(sys.argv[-1]).write_bytes(b'fake png')
elif name=='wl-copy':
    sys.stdin.buffer.read()
    if os.environ.get('CLIPBOARD_FAIL'): sys.exit(1)
''')
        helper.chmod(0o755)
        for name in ('slurp', 'grim', 'wl-copy', 'xdg-user-dir', 'notify-send', 'python3'):
            (self.bin / name).symlink_to(helper.name)
        self.env = dict(os.environ, PATH=str(self.bin) + ':/usr/bin:/bin', XDG_RUNTIME_DIR=str(self.runtime),
                        HYPRLAND_INSTANCE_SIGNATURE='test-capture', WAYLAND_DISPLAY='test', CAPTURE_TEST_ROOT=str(self.root))

    def events(self):
        path = self.root / 'events.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def run_capture(self, mode='area', **environment):
        result = subprocess.run(['/bin/bash', str(SCRIPT), mode], env=dict(self.env, **environment),
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and not environment.get('CAPTURE_CANCEL'):
            deadline = time.monotonic() + 2
            while 'python3' not in [event['tool'] for event in self.events()] and time.monotonic() < deadline:
                time.sleep(.01)
        return result

    def assert_released(self):
        with self.guard.open('rb') as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_area_capture_keeps_menu_visible_until_image_is_copied(self):
        result = self.run_capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        stages = {event['tool']: event['guard'] for event in self.events()}
        self.assertTrue(all(stages[tool] for tool in ('slurp', 'grim', 'wl-copy')))
        self.assertFalse(stages['python3'])
        self.assert_released()
        self.assertEqual(len(list((self.root / 'Pictures/Screenshots').glob('*.png'))), 1)

    def test_full_screen_capture_also_releases_guard_before_notification(self):
        result = self.run_capture('screen')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('slurp', [event['tool'] for event in self.events()])
        self.assertFalse(self.events()[-1]['guard'])
        self.assert_released()

    def test_cancelled_region_releases_guard_without_capturing(self):
        result = self.run_capture(CAPTURE_CANCEL='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([event['tool'] for event in self.events()], ['slurp'])
        self.assert_released()

    def test_failed_capture_releases_guard_and_removes_empty_output(self):
        result = self.run_capture(CAPTURE_FAIL='1')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assert_released()
        self.assertEqual(list((self.root / 'Pictures/Screenshots').glob('*.png')), [])
        self.assertNotIn('python3', [event['tool'] for event in self.events()])

    def test_clipboard_failure_does_not_leave_capture_guard_held(self):
        result = self.run_capture(CLIPBOARD_FAIL='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.events()[-1]['guard'])
        self.assert_released()

    def test_second_capture_cannot_replace_an_active_guard(self):
        with self.guard.open('wb') as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run(['/bin/bash', str(SCRIPT), 'area'], env=self.env,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.events(), [])


if __name__ == '__main__':unittest.main()
