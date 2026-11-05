"""Session actions and small-screen layouts without touching the real session."""
import copy
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QScrollArea
from PyQt6.QtTest import QTest

import app
import keys
import runtime
from system_page import SystemPage

QT=QApplication.instance() or QApplication([])
QT.setStyle('Fusion')
READING=dict(cpu=21,memory=48,disk=65,cpu_detail='16 logical processors',
             memory_detail='15.4 / 32.0 GiB in use',disk_detail='300 GiB free of 1000 GiB',
             temperatures='CPU 48°C  ·  GPU 51°C',uptime='2h 15m')


def synchronous(fn, done, failed):
    try: result=fn()
    except Exception as error: failed(str(error))
    else: done(result)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.launch=Mock();self.navigate=Mock()
        self.page=SystemPage(synchronous,self.launch,self.navigate)
        self.binding=keys.Binding(keys.MONITOR_ID,'Open system monitor','Applications',True,'SUPER','Escape','exec',
                                  '[float] '+keys.ADMIN_WRAPPER+' "/tmp/My monitor" --all')
        self.binding_patch=patch.object(self.page,'monitor_binding',return_value=self.binding);self.binding_patch.start()
        self.snapshot_patch=patch('system_page.snapshot',return_value=READING);self.snapshot_patch.start()
        self.sound_patch=patch('system_page.before_power');self.sound=self.sound_patch.start()

    def tearDown(self):
        self.page.close();self.page.deleteLater();QT.processEvents()
        self.binding_patch.stop();self.snapshot_patch.stop()
        self.sound_patch.stop()

    def test_monitor_button_uses_the_configured_command_and_admin_wrapper(self):
        self.page.open_monitor()
        self.launch.assert_called_once_with(['hyprctl','dispatch','exec',self.binding.args])
        self.page.edit_shortcut();self.navigate.assert_called_once_with('hotkeys')

    def test_power_actions_require_confirmation_and_report_failure(self):
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel), \
                patch('system_page.subprocess.run') as run:
            self.page.power('Restart',['systemctl','reboot']);run.assert_not_called()
            self.sound.assert_not_called()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes) as confirm, \
                patch('system_page.subprocess.run',return_value=subprocess.CompletedProcess([],1,'','Not authorized')) as run:
            self.page.power('Restart',['systemctl','reboot'])
            run.assert_called_once_with(['systemctl','reboot'],text=True,capture_output=True,timeout=20)
            self.sound.assert_called_once_with(['systemctl','reboot'])
            self.assertEqual(confirm.call_args.args[-1],QMessageBox.StandardButton.Cancel)
        self.assertIn('Not authorized',self.page.status.text())
        self.assertFalse(self.page.power_busy)
        self.assertTrue(all(tile.isEnabled() for tile in self.page.power_tiles))

    def test_dashboard_fits_small_pages_in_every_theme_and_palette(self):
        self.page.resize(790,560);self.page.show()
        for design in runtime.DESIGNS:
            for mode in runtime.MODES:
                with self.subTest(design=design,mode=mode), patch.object(runtime,'state',return_value=dict(design=design,mode=mode)), \
                        patch.object(runtime,'mode',return_value=mode):
                    QT.setPalette(runtime.palette());QT.setStyleSheet(runtime.stylesheet(app.STYLE))
                    self.page.update_design();self.page.refresh();QT.processEvents()
                    scroll=self.page.findChild(QScrollArea)
                    self.assertEqual(scroll.horizontalScrollBar().maximum(),0)
                    # A single vertical viewport remains available on very small displays.
                    for tile in self.page.tiles:
                        self.assertGreaterEqual(tile.width(),140)
                        self.assertGreaterEqual(tile.height(),87)
                    self.assertFalse(self.page.grab().isNull())
        self.assertEqual(self.page.metrics['cpu'].value,21)
        self.assertIn('Super + Esc',self.page.monitor.detail)
        self.assertTrue(self.page.timer.isActive());self.page.hide()
        self.assertFalse(self.page.timer.isActive())


if __name__=='__main__':unittest.main()
