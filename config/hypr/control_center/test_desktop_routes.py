"""Legacy remote-hosting shortcuts continue in the existing native RDP tool."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import app


class DesktopRoutesTests(unittest.TestCase):
    def test_legacy_remote_shortcut_opens_control_panel(self):
        with patch.object(app, 'launch') as launch:
            app.Window.switch(SimpleNamespace(), 'remote-desktop')
        launch.assert_called_once_with([str(app.keys.ROOT/'scripts/control-panel.sh'), '--section', 'rdp-host'])

    def test_remote_ipc_request_does_not_raise_settings_over_the_panel(self):
        window = SimpleNamespace(pages={}, switch=Mock())
        with patch.object(app, 'BarActivation') as activation:
            app.Window.request(window, {'tab': 'remote-desktop'})
        window.switch.assert_called_once_with('remote-desktop')
        activation.assert_not_called()


if __name__ == '__main__': unittest.main()
