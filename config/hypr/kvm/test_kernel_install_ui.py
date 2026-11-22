"""Confirmation and result behavior; no package operations or network access."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
import kernel_install_ui as ui


class KernelDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for name, value in (('platform_problem',''), ('complete',False)):
            mock = patch.object(ui.kernel, name, return_value=value);mock.start();self.addCleanup(mock.stop)

    def test_opening_and_canceling_never_starts_an_installation(self):
        with patch.object(ui.kernel.Installer, 'install') as install:
            dialog = ui.KernelInstallDialog('7.2.11-arch1-1');dialog.show();self.app.processEvents()
            self.assertTrue(dialog.proceed.isEnabled());self.assertTrue(dialog.aur.isChecked())
            self.assertIn('7.2.11-arch1-1', dialog.description.text())
            dialog.cancel_or_close();self.app.processEvents();install.assert_not_called()

    def test_failed_worker_reports_reason_and_leaves_close_available(self):
        import module_policy
        with patch.object(ui.kernel.Installer, 'install', side_effect=RuntimeError('Exact version is unavailable')), \
             patch.object(module_policy, 'busy_reason', return_value=''):
            dialog = ui.KernelInstallDialog('7.2.11-arch1-1');dialog.show();dialog.start()
            deadline = time.monotonic()+3
            while dialog.job and time.monotonic() < deadline:self.app.processEvents();time.sleep(.005)
            self.assertIsNone(dialog.job)
            self.assertIn('Exact version is unavailable', dialog.status.text())
            self.assertEqual(dialog.cancel_button.text(), 'Close');self.assertTrue(dialog.cancel_button.isEnabled())
            dialog.close()

    def test_other_distro_disables_proceed_with_explanation(self):
        with patch.object(ui.kernel, 'platform_problem', return_value='Arch-family systems only'):
            dialog = ui.KernelInstallDialog('7.2.11-arch1-1')
            self.assertFalse(dialog.proceed.isEnabled());self.assertIn('Arch-family', dialog.status.text());dialog.close()

    def test_newest_first_selects_running_kernel_without_installing(self):
        from test_kernel_catalog import catalog,NEW,OLD
        with patch.object(ui.platform,'release',return_value=OLD), patch.object(ui.kernel.Installer,'install') as install:
            dialog=ui.KernelInstallDialog(catalog=catalog())
            self.assertEqual([dialog.kernels.itemData(i) for i in range(dialog.kernels.count())],[NEW,OLD])
            self.assertEqual(dialog.target.release,OLD)
            dialog.kernels.setCurrentIndex(0)
            self.assertEqual(dialog.target.release,NEW)
            self.assertIn('7.3.5.arch1-1',dialog.description.text())
            install.assert_not_called();dialog.close()

    def test_unknown_kernel_defaults_to_newest_and_existing_install_can_change(self):
        from test_kernel_catalog import catalog,NEW,OLD
        with patch.object(ui.platform,'release',return_value='unknown'), \
             patch.object(ui.kernel,'complete',side_effect=lambda target:target.release==NEW):
            dialog=ui.KernelInstallDialog(catalog=catalog())
            self.assertEqual(dialog.target.release,NEW);self.assertFalse(dialog.proceed.isEnabled())
            dialog.kernels.setCurrentIndex(1)
            self.assertEqual(dialog.target.release,OLD);self.assertTrue(dialog.proceed.isEnabled());dialog.close()


if __name__ == '__main__':unittest.main()
