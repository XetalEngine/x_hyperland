"""First installation, updates and ISO deferral use distinct factory lifecycles."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'installer'))
import settings_factory
import runtime_install


class FactoryLifecycleTests(unittest.TestCase):
    def test_updates_and_deferred_iso_never_adopt_personal_state(self):
        with patch.object(settings_factory.subprocess, 'run') as run:
            settings_factory.record('/home/fixture/.config/hypr', False, False)
            with patch.dict(os.environ, {'XETAL_FACTORY_SYSTEM_DEFER':'1'}):
                settings_factory.record('/home/fixture/.config/hypr', True, True)
            run.assert_not_called()

    def test_first_setup_authenticates_even_with_packages_already_present(self):
        with patch.dict(os.environ, {'XETAL_FACTORY_SYSTEM_DEFER':'0'}), \
             patch.object(runtime_install, 'administrator', return_value=['sudo','-A']), \
             patch.object(runtime_install, 'check_administrator_result'), \
             patch.object(settings_factory.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,'','')) as run:
            settings_factory.record('/home/fixture/.config/hypr', True, True)
            self.assertEqual(run.call_args.args[0], ['sudo','-k','-A','/usr/bin/python3',
                '/home/fixture/.config/hypr/settings_profiles/system.py','factory'])


if __name__ == '__main__': unittest.main()
