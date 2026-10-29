import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import launch
import login_settings


class LoginScreenTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        environment = patch.dict(os.environ, XETAL_HYPR_ROOT=str(self.root),
                                 HYPRLAND_INSTANCE_SIGNATURE='fixture', XDG_RUNTIME_DIR=str(self.root))
        environment.start()
        self.addCleanup(environment.stop)

    def test_default_and_save_preserve_unknown_settings(self):
        self.assertTrue(login_settings.enabled())
        login_settings.save(False)
        path = login_settings.settings_path()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        path.write_text(json.dumps({'show_on_login': False, 'other': 'keep'}))
        login_settings.save(True)
        self.assertEqual(login_settings.load(), {'show_on_login': True, 'other': 'keep'})

    def test_bad_values_do_not_overwrite_the_file(self):
        login_settings.save(False)
        for value in ('false', 0, None):
            with self.assertRaises(ValueError): login_settings.save(value)
        self.assertFalse(login_settings.enabled())

    def test_disabled_login_never_touches_compositor_or_launches_panes(self):
        login_settings.save(False)
        with patch.object(sys, 'argv', ['launch.py', '--login']), patch.object(launch, 'ctl') as ctl, \
             patch.object(launch, 'wait_for_login') as wait:
            launch.main()
            wait.assert_not_called()
            ctl.assert_not_called()

    def test_disabling_during_the_login_delay_also_skips_startup(self):
        def wait(*_):
            login_settings.save(False)
            return True
        with patch.object(sys, 'argv', ['launch.py', '--login']), patch.object(launch, 'ctl') as ctl, \
             patch.object(launch, 'wait_for_login', side_effect=wait):
            launch.main()
            ctl.assert_not_called()

    def test_manual_hotkey_still_toggles_existing_dashboard_when_disabled(self):
        login_settings.save(False)
        (self.root/'hypr/fixture').mkdir(parents=True)
        monitor = {'name':'fixture', 'specialWorkspace': {'name': launch.WORKSPACE}}
        with patch.object(sys, 'argv', ['launch.py', '--toggle']), \
             patch.object(launch, 'ctl', side_effect=[[monitor], '', '']) as ctl:
            launch.main()
            self.assertEqual(ctl.call_args.args, ('dispatch', 'togglespecialworkspace', 'xetal-startup'))

    def test_manual_open_still_reuses_panes_when_disabled(self):
        login_settings.save(False)
        (self.root/'hypr/fixture').mkdir(parents=True)
        monitor = {'name':'fixture', 'focused':True, 'specialWorkspace': {}}
        clients = [{'class':'xetal-startup-'+mode, 'mapped':True} for mode in ['info','matrix','clock','projects']]
        with patch.object(sys, 'argv', ['launch.py']), \
             patch.object(launch, 'ctl', side_effect=[[monitor], clients, '', '']) as ctl:
            launch.main()
            self.assertEqual(ctl.call_args.args, ('dispatch', 'togglespecialworkspace', 'xetal-startup'))


if __name__ == '__main__': unittest.main()
