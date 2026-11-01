"""System utilities remain usable in applications launched from a desktop PATH."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]/'config/hypr'
sys.path.insert(0, str(ROOT/'theme'))
spec = importlib.util.spec_from_file_location('desktop_theme_runtime', ROOT/'theme/runtime.py')
theme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theme)


class DesktopCommandPathsTests(unittest.TestCase):
    def test_launched_kvm_tools_inherit_system_paths_without_changing_the_parent(self):
        with tempfile.TemporaryDirectory(prefix='xetal-desktop-path-') as temporary:
            sbin = Path(temporary)/'sbin'
            sbin.mkdir()
            for command in ('dmidecode', 'fsck.fat', 'losetup', 'modinfo'):
                tool = sbin/command
                tool.write_text('#!/bin/sh\nprintf "%s\\n" "'+command+' available"\n')
                tool.chmod(0o755)
            base = {'PATH': temporary, 'HYPRLAND_INSTANCE_SIGNATURE': 'test'}
            original = dict(os.environ)
            with patch.object(theme.command_paths, 'SYSTEM_TOOL_DIRS', (str(sbin),)), \
                 patch.object(theme.command_paths, 'PERL_SCRIPT_DIRS', ()):
                result = theme.environment(base)
                for command in ('dmidecode', 'fsck.fat', 'losetup', 'modinfo'):
                    self.assertEqual(subprocess.check_output([command], env=result, text=True), command+' available\n')
                self.assertEqual(theme.environment(result), result)
            self.assertEqual(base['PATH'], temporary)
            self.assertEqual(dict(os.environ), original)

    def test_other_desktops_keep_their_environment(self):
        base = {'PATH': '/usr/bin:/bin', 'XDG_CURRENT_DESKTOP': 'KDE'}
        self.assertEqual(theme.environment(base), base)


if __name__ == '__main__':
    unittest.main()
