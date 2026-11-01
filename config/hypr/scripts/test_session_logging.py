"""Log choices preserve preferences and redirect actual child writes to /dev/null."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import session_logging as logs


class SessionLoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fusion-log-policy-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.instance = self.root/'session'; self.instance.mkdir()

    def test_new_setting_migrates_old_preferences_and_both_choices_are_preserved(self):
        logs.write_json(logs.setting_path(self.root), {'version': 1, 'enabled': False, 'future': 'keep'})
        self.assertFalse(logs.preferences(self.root)['disable_file_logs'])
        logs.save('disable_file_logs', True, self.root)
        logs.save('enabled', True, self.root)
        self.assertEqual(logs.preferences(self.root),
                         {'version': 1, 'enabled': True, 'disable_file_logs': True, 'future': 'keep'})

    def test_disabling_keeps_existing_logs_and_discards_child_output(self):
        path = self.instance/'cached-panel.log'; path.write_text('Existing diagnostics\n')
        logs.save('disable_file_logs', True, self.root)
        logs.begin(self.instance, self.root)
        with logs.log_path(self.instance, path.name).open('ab') as stream:
            result = subprocess.run([sys.executable, '-c', 'import os;os.write(1,b"secret stdout");os.write(2,b"secret stderr")'],
                                    stdout=stream, stderr=stream)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), 'Existing diagnostics\n')
        self.assertEqual(logs.log_path(self.instance, 'waybar.log'), Path(os.devnull))
        self.assertFalse((self.instance/'waybar.log').exists())

    def test_changes_only_apply_at_next_login_in_both_directions(self):
        self.assertFalse(logs.begin(self.instance, self.root)['disabled'])
        logs.save('disable_file_logs', True, self.root)
        self.assertFalse(logs.begin(self.instance, self.root)['disabled'])
        second = self.root/'second'; second.mkdir()
        self.assertTrue(logs.begin(second, self.root)['disabled'])
        logs.save('disable_file_logs', False, self.root)
        self.assertTrue(logs.begin(second, self.root)['disabled'])
        third = self.root/'third'; third.mkdir()
        self.assertFalse(logs.begin(third, self.root)['disabled'])
        with logs.log_path(third, 'waybar.log').open('w') as stream: stream.write('Normal logging')
        self.assertEqual((third/'waybar.log').read_text(), 'Normal logging')

    def test_failed_save_retains_previous_choices(self):
        logs.save('disable_file_logs', True, self.root)
        with patch.object(logs.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): logs.save('disable_file_logs', False, self.root)
        self.assertTrue(logs.preferences(self.root)['disable_file_logs'])

    def test_legacy_session_and_invalid_filename(self):
        self.assertEqual(logs.log_path(self.instance, 'waybar.log'), self.instance/'waybar.log')
        for name in ('../elsewhere.log', '/tmp/elsewhere.log', 'settings.json'):
            with self.assertRaises(ValueError): logs.log_path(self.instance, name)


if __name__ == '__main__': unittest.main()
