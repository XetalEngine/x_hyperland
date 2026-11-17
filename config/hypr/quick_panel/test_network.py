"""Connection decisions and explicit controls, with no live radio changes."""
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import network_status as network
from protocol import Request
import model


def fixture(**changes):
    raw = dict(general='connected:full:enabled:enabled',
               devices='eth0:ethernet:connected:Wired connection\nwlan0:wifi:connected:Cafe\\: Wi-Fi',
               ipv4='[{"dev":"eth0","metric":100},{"dev":"wlan0","metric":600}]', ipv6='[]',
               connections='ethernet:Wired connection\nwifi:Cafe\\: Wi-Fi',
               bluetooth='Controller AA:BB:CC:DD:EE:FF Test\n\tPowered: yes',
               bluetooth_devices='Device 11:22:33:44:55:66 Headphones')
    raw.update(changes)
    return network.summarize(raw)


class NetworkStatus(unittest.TestCase):
    def test_icon_follows_primary_physical_route_and_has_no_text(self):
        data = fixture()
        self.assertEqual(data['kind'], 'lan'); self.assertEqual(network.bar_status(data)['text'], network.LAN)
        data = fixture(ipv4='[{"dev":"wlan0","metric":10},{"dev":"eth0","metric":100}]')
        self.assertEqual(data['kind'], 'wifi'); self.assertEqual(network.bar_status(data)['text'], network.WIFI)
        self.assertIn('Cafe: Wi-Fi', network.bar_status(data)['tooltip'])

    def test_ipv6_and_vpn_do_not_hide_wifi(self):
        data = fixture(devices='wlan0:wifi:connected:Home\nwg0:wireguard:connected:Work',
                       ipv4='[{"dev":"wg0"}]', ipv6='[{"dev":"wlan0"}]',
                       connections='wireguard:Work\nvpn:Office\\: Secure')
        self.assertEqual(data['kind'], 'wifi'); self.assertEqual(data['vpn'], ['Work', 'Office: Secure'])

    def test_bridge_uses_connected_ethernet_not_virtual_device(self):
        data = fixture(devices='br0:bridge:connected:Bridge\neth0:ethernet:connected:Bridge port\nwlan0:wifi:disconnected:--',
                       ipv4='[{"dev":"br0"}]')
        self.assertEqual(data['kind'], 'lan'); self.assertEqual(data['active']['name'], 'eth0')
        data = fixture(devices='virbr0:bridge:connected:VM bridge\nwlan0:wifi:disconnected:--', ipv4='[]')
        self.assertEqual(data['kind'], 'offline')

    def test_disconnected_radios_and_unavailable_services(self):
        data = fixture(devices='wlan0:wifi:disconnected:--', ipv4='[]')
        self.assertEqual(data['icon'], network.WIFI_IDLE)
        data = fixture(general='disconnected:none:disabled:enabled', devices='wlan0:wifi:unavailable:--', ipv4='[]')
        self.assertEqual(data['icon'], network.WIFI_OFF); self.assertFalse(data['wifi']['enabled'])
        data = network.summarize({})
        self.assertFalse(data['available']); self.assertFalse(data['bluetooth']['available'])
        self.assertEqual(data['kind'], 'offline'); self.assertIn('unavailable', data['internet'])

    def test_special_names_are_preserved_and_tooltip_markup_escaped(self):
        self.assertEqual(network.fields(r'wifi:A\:B\\C'), ['wifi', 'A:B\\C'])
        data = fixture(devices='wlan0:wifi:connected:<Home & Work>', ipv4='[]', general='connected:portal:enabled:enabled')
        tooltip = network.bar_status(data)['tooltip']
        self.assertIn('&lt;Home &amp; Work&gt;', tooltip); self.assertIn('sign-in required', tooltip)
        self.assertEqual(data['bluetooth']['devices'], ['Headphones'])

    def test_reads_are_bounded_localized_and_never_toggle_or_scan(self):
        response = SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(network.subprocess, 'run', return_value=response) as run:
            network.snapshot()
        self.assertEqual(run.call_count, 7)
        for call in run.call_args_list:
            argv = call.args[0]
            self.assertNotIn('power', argv); self.assertNotIn('rescan', argv); self.assertNotIn('radio', argv)
            self.assertEqual(call.kwargs['env']['LC_ALL'], 'C'); self.assertEqual(call.kwargs['timeout'], 3)

    def test_only_explicit_radio_actions_write_and_report_failures(self):
        with patch.object(network.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='Changing power on succeeded', stderr='')) as run:
            network.set_radio('wifi', False)
            self.assertEqual(run.call_args.args[0], ['nmcli', '--wait', '5', 'radio', 'wifi', 'off'])
            network.set_radio('bluetooth', True)
            self.assertEqual(run.call_args.args[0], ['bluetoothctl', '--timeout', '5', 'power', 'on'])
        with patch.object(network.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='Failed to set power on: Blocked', stderr='')):
            with self.assertRaisesRegex(RuntimeError, 'Blocked'): network.set_radio('bluetooth', True)

    def test_network_popup_request_and_small_monitor_placement(self):
        self.assertEqual(Request().feed(b'{"kind":"network"}\n'), {'kind': 'network'})
        monitor = dict(id=0, x=0, y=0, width=800, height=600, scale=1.5, reserved=[0, 40, 0, 0])
        placement = model.placement(monitor, 'network', 'bottom')
        self.assertLessEqual(placement['width'], 510); self.assertLessEqual(placement['height'], 340)
        self.assertGreaterEqual(placement['y'], 40)


class NetworkWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        import app
        cls.ui = app
        cls.application = app.QApplication.instance() or app.QApplication([])

    def setUp(self):
        self.owner = Mock()
        self.page = self.ui.NetworkPage(self.owner)
        self.addCleanup(self.page.deleteLater)

    def test_status_updates_do_not_change_radios_and_missing_adapter_is_disabled(self):
        with patch.object(self.ui, 'async_run') as worker:
            self.page.updated(fixture())
            self.assertTrue(self.page.toggles['wifi'].isChecked())
            self.assertIn('Cafe: Wi-Fi', self.page.details['wifi'].text())
            self.page.updated(network.summarize({}))
            self.assertFalse(self.page.toggles['wifi'].isEnabled())
            self.assertFalse(self.page.toggles['bluetooth'].isEnabled())
            worker.assert_not_called()

    def test_explicit_click_failure_restores_actual_state_and_keeps_error(self):
        self.page.updated(fixture())
        def worker(fn, success, failure):
            try: success(fn())
            except Exception as error: failure(str(error))
        with patch.object(self.ui, 'async_run', side_effect=worker), \
             patch.object(network, 'snapshot', side_effect=lambda: fixture()), \
             patch.object(network, 'set_radio', side_effect=RuntimeError('Permission denied')) as change:
            self.page.toggles['wifi'].click()
        change.assert_called_once_with('wifi', False)
        self.assertTrue(self.page.toggles['wifi'].isChecked())
        self.assertTrue(self.page.toggles['wifi'].isEnabled())
        self.assertEqual(self.page.message.text(), 'Permission denied')

    def test_settings_shortcuts_keep_vpn_and_bluetooth_controls_accessible(self):
        with patch.object(self.ui.subprocess, 'Popen') as launch:
            self.page.open_settings('vpn'); self.assertEqual(launch.call_args.args[0][-1], 'nm-connection-editor')
            self.page.open_settings('bluetooth'); self.assertEqual(launch.call_args.args[0][-2:], ['--tab', 'bluetooth'])
            self.page.open_settings('wifi'); self.assertEqual(launch.call_args.args[0][-2:], ['--tab', 'network'])
        self.assertEqual(self.owner.hide.call_count, 3)

    def test_pending_poll_cannot_restore_stale_radio_state_after_click(self):
        self.page.updated(fixture())
        tasks = []
        with patch.object(self.ui, 'async_run', side_effect=lambda fn, success, error: tasks.append((fn, success, error))):
            self.page.refresh()
            self.page.toggles['wifi'].click()
            self.assertEqual(len(tasks), 2)
            tasks[1][1](None)  # Radio command finishes before the old read.
            tasks[0][1](fixture())
            self.assertEqual(len(tasks), 3)  # A fresh read replaces the stale poll.
            tasks[2][1](fixture(general='connected:full:disabled:enabled'))
        self.assertFalse(self.page.toggles['wifi'].isChecked())
        self.assertTrue(self.page.toggles['wifi'].isEnabled())


if __name__ == '__main__': unittest.main()
