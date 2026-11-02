"""Exercise app selection without writing the real desktop associations."""
import copy
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit, QListWidget
import default_apps_page as page

QT = QApplication.instance() or QApplication([])


def synchronous(fn, done, failed):
    try:
        value = fn()
    except Exception as error:
        failed(str(error))
    else:
        done(value)


class DefaultAppsPageTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            'revision': 'revision-one',
            'apps': [
                dict(id='old.desktop', name='Old files', icon='folder', types=['inode/directory']),
                dict(id='new.desktop', name='Fusion Files', icon='folder', types=['inode/directory'])],
            'roles': [dict(id='files', title='File manager', description='Folders and Show in folder',
                           icon='folder', types=['inode/directory'], default='old.desktop')],
        }
        self.calls = []
        def backend(action='snapshot', data=None):
            self.calls.append((action, data))
            if action == 'snapshot':
                return copy.deepcopy(self.snapshot)
            if action == 'apply':
                self.snapshot['roles'][0]['default'] = data['app']
                return dict(undo='undo-token', message='Saved')
            self.snapshot['roles'][0]['default'] = 'old.desktop'
            return dict(message='Restored')
        self.backend = patch.object(page, 'request', side_effect=backend)
        self.backend.start()
        self.addCleanup(self.backend.stop)
        self.page = page.DefaultAppsPage(synchronous, lambda *_: None)
        self.page.refresh()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        QT.processEvents()

    def test_search_apply_and_undo_use_shared_defaults_backend(self):
        def select():
            dialog = QApplication.activeModalWidget()
            self.assertIsInstance(dialog, QDialog)
            dialog.findChild(QLineEdit).setText('Fusion')
            apps = dialog.findChild(QListWidget)
            visible = [apps.item(n) for n in range(apps.count()) if not apps.item(n).isHidden()]
            self.assertEqual(len(visible), 1)
            apps.setCurrentItem(visible[0])
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
        QTimer.singleShot(0, select)
        self.page.choose(self.snapshot['roles'][0])
        applied = [data for action, data in self.calls if action == 'apply']
        self.assertEqual(applied, [dict(role='files', app='new.desktop', revision='revision-one')])
        self.assertTrue(self.page.undo_button.isEnabled())
        self.page.undo()
        self.assertIn(('undo', {'token':'undo-token'}), self.calls)
        self.assertFalse(self.page.undo_button.isEnabled())

    def test_cancel_does_not_change_defaults(self):
        QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
        self.page.choose(self.snapshot['roles'][0])
        self.assertFalse(any(action == 'apply' for action, _ in self.calls))

    def test_failed_request_is_visible_and_refresh_is_available(self):
        with patch.object(page, 'request', side_effect=ValueError('Defaults changed elsewhere')):
            self.page.refresh()
        self.assertEqual(self.page.status.text(), 'Defaults changed elsewhere')
        self.assertTrue(self.page.refresh_button.isEnabled())


if __name__ == '__main__':
    unittest.main()
