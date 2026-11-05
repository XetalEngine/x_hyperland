"""Exercise the real async D-Bus client on a private bus, never system logind."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import time
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from power import Power


class FakeLogind(QObject):
    def __init__(self):
        super().__init__()
        self.capability = 'yes'
        self.requests = []

    @pyqtSlot(result=str)
    def CanReboot(self): return self.capability

    @pyqtSlot(result=str)
    def CanPowerOff(self): return self.capability

    @pyqtSlot(bool)
    def Reboot(self, interactive): self.requests.append(('reboot', interactive))

    @pyqtSlot(bool)
    def PowerOff(self, interactive): self.requests.append(('poweroff', interactive))


class PowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        guard = patch('power.QDBusConnection.systemBus', side_effect=AssertionError('Never contact system logind in tests'))
        guard.start(); self.addCleanup(guard.stop)
        self.daemon = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_bus)
        address = self.daemon.stdout.readline().strip()
        self.name = 'fusion-power-test-'+str(self.daemon.pid)
        self.bus = QDBusConnection.connectToBus(address, self.name)
        self.addCleanup(QDBusConnection.disconnectFromBus, self.name)
        self.assertTrue(self.bus.isConnected())
        self.service = FakeLogind()
        self.assertTrue(self.bus.registerService('org.freedesktop.login1'))
        self.assertTrue(self.bus.registerObject('/org/freedesktop/login1', 'org.freedesktop.login1.Manager', self.service,
                                               QDBusConnection.RegisterOption.ExportAllSlots))
        self.power = Power(bus=self.bus)
        self.messages = []; self.power.message.connect(self.messages.append)

    def stop_bus(self):
        self.daemon.terminate(); self.daemon.communicate(timeout=5)

    def wait(self, predicate):
        deadline = time.monotonic()+3
        while not predicate() and time.monotonic() < deadline: QTest.qWait(10)
        self.assertTrue(predicate(), 'D-Bus reply timed out')

    def ready(self):
        self.power.refresh(); self.wait(lambda: not self.power.refreshing)

    def test_both_power_actions_are_noninteractive_and_cannot_be_duplicated(self):
        for action in ('reboot', 'poweroff'):
            self.power = Power(bus=self.bus); self.ready()
            self.assertEqual(self.power.available[action], 'yes')
            self.power.request(action); self.power.request(action)
            self.wait(lambda: not self.power.pending)
            self.assertEqual(self.service.requests[-1], (action, False))
            self.assertTrue(self.power.busy)
        self.assertEqual(len(self.service.requests), 2)

    def test_denied_challenge_unsupported_and_unknown_actions_never_call_logind(self):
        for capability in ('no', 'challenge', 'na'):
            self.service.capability = capability; self.ready()
            self.power.request('reboot'); self.power.request('poweroff')
            self.assertFalse(self.power.busy)
            self.assertTrue(self.messages[-1])
        self.power.request('shell-command')
        self.assertEqual(self.service.requests, [])

    def test_service_loss_after_confirmation_recovers_login_controls(self):
        self.ready()
        self.bus.unregisterService('org.freedesktop.login1')
        self.power.request('reboot')
        self.wait(lambda: not self.power.busy and not self.power.refreshing)
        self.assertIn('Could not restart', self.messages[-1])
        self.assertEqual(self.power.available['reboot'], 'unavailable')
        self.assertFalse(self.service.requests)

    def test_preview_never_opens_a_bus_or_sends_a_power_command(self):
        preview = Power(preview=True)
        messages = []; preview.message.connect(messages.append)
        preview.refresh(); preview.request('reboot'); preview.request('poweroff')
        self.assertIsNone(preview.bus)
        self.assertFalse(self.service.requests)
        self.assertEqual(len(messages), 2)
        self.assertIn('Preview only', messages[0])


if __name__ == '__main__': unittest.main()
