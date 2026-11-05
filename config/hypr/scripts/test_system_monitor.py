import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('system_monitor',Path(__file__).with_name('system-monitor.py'))
monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def test_uses_available_graphical_monitor(self):
        installed={'plasma-systemmonitor':'/usr/bin/plasma-systemmonitor','htop':'/usr/bin/htop'}
        self.assertEqual(monitor.command(installed.get),['/usr/bin/plasma-systemmonitor'])
        self.assertEqual(monitor.command({'gnome-system-monitor':'/usr/bin/gnome-system-monitor'}.get),['/usr/bin/gnome-system-monitor'])

    def test_fresh_install_has_a_profile_local_terminal_fallback(self):
        installed={'htop':'/usr/bin/htop','kitty':'/usr/bin/kitty'}
        self.assertEqual(monitor.command(installed.get),['/usr/bin/kitty','--config',str(monitor.ROOT/'kitty.conf'),'-e','/usr/bin/htop'])
        with self.assertRaisesRegex(RuntimeError,'Hotkeys'):monitor.command({}.get)


if __name__=='__main__':unittest.main()
