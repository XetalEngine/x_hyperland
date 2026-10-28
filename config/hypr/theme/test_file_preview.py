"""Regression checks for the shared file picker, independent of the desktop."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from PyQt6 import sip
from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QLineEdit, QScrollArea
import file_preview as preview
from image_picker import ImagePicker


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.settings = tempfile.TemporaryDirectory(prefix='xetal-preview-settings-')
        for format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
            QSettings.setPath(format, QSettings.Scope.UserScope, cls.settings.name)
        preview.install(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.settings.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.picture = self.root/'picture.png'
        image = QImage(800, 400, QImage.Format.Format_RGB32); image.fill(Qt.GlobalColor.red)
        image.save(str(self.picture))
        self.text = self.root/'preset.json'; self.text.write_text('{"enabled": true}\n')

    def tearDown(self):
        self.temp.cleanup()

    def wait_for(self, fn):
        for _ in range(200):
            if fn(): return
            QTest.qWait(10)
        self.fail('Preview did not finish')

    def test_image_thumbnail_has_metadata_and_preserves_aspect_ratio(self):
        data = preview.inspect_path(str(self.picture))
        self.assertEqual(data['dimensions'], '800 × 400 px')
        self.assertEqual(data['format'], 'PNG')
        self.assertEqual(data['image'].width(), 2*data['image'].height())
        self.assertLessEqual(data['image'].width(), 480)
        self.assertNotEqual(data['modified'], '—')

    def test_text_folder_binary_and_new_file(self):
        self.assertEqual(preview.inspect_path(str(self.text))['text'], '{"enabled": true}\n')
        self.text.write_text('x'*100000)
        data = preview.inspect_path(str(self.text))
        self.assertEqual(len(data['text']), 65536); self.assertIn('64 KiB', data['message'])
        self.text.write_bytes(b'\x00binary')
        self.assertFalse(preview.inspect_path(str(self.text))['text'])
        for i in range(45): (self.root/str(i)).touch()
        data = preview.inspect_path(str(self.root))
        self.assertEqual(len(data['text'].splitlines()), 40)
        self.assertIn('40', data['message'])
        self.assertIn('New file', preview.inspect_path(str(self.root/'new.json'))['message'])

    def test_special_files_are_not_opened_and_file_change_is_rechecked(self):
        pipe = self.root/'pipe'; os.mkfifo(pipe)
        with patch.object(preview.os, 'open', side_effect=AssertionError('must not open')):
            self.assertIn('special file', preview.inspect_path(str(pipe))['message'])
        original = os.open
        def changed(path, flags): return original(pipe, flags)
        with patch.object(preview.os, 'open', side_effect=changed):
            self.assertIn('unavailable', preview.inspect_path(str(self.text))['message'])

    def test_every_dialog_mode_gets_one_pane_without_changing_selection(self):
        for mode, accept in [(QFileDialog.FileMode.ExistingFile, QFileDialog.AcceptMode.AcceptOpen),
                             (QFileDialog.FileMode.ExistingFiles, QFileDialog.AcceptMode.AcceptOpen),
                             (QFileDialog.FileMode.AnyFile, QFileDialog.AcceptMode.AcceptSave),
                             (QFileDialog.FileMode.Directory, QFileDialog.AcceptMode.AcceptOpen)]:
            with self.subTest(mode=mode):
                dialog = QFileDialog(None, 'Choose', str(self.root))
                dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
                dialog.setFileMode(mode); dialog.setAcceptMode(accept)
                selected = self.root if mode == QFileDialog.FileMode.Directory else self.picture
                dialog.selectFile(str(selected)); before = dialog.selectedFiles()
                dialog.show(); QTest.qWait(20); preview.attach(dialog)
                self.assertEqual(dialog.selectedFiles(), before)
                self.assertEqual(dialog.fileMode(), mode); self.assertEqual(dialog.acceptMode(), accept)
                self.assertEqual(len(dialog.findChildren(QScrollArea, 'xetalFilePreviewPane')), 1)
                dialog.reject(); sip.delete(dialog)
        dialog = ImagePicker(None, 'Images', str(self.root), 'Images (*.png)')
        dialog.show(); QTest.qWait(20)
        self.assertEqual(len(dialog.findChildren(QScrollArea, 'xetalFilePreviewPane')), 1)
        dialog.reject(); sip.delete(dialog)

    def test_static_dialog_acceptance_keeps_filter_and_filename(self):
        observed = []
        def accept():
            dialog = next(w for w in self.app.topLevelWidgets() if isinstance(w, QFileDialog) and w.isVisible())
            observed.append(dialog.property(preview.MARKER))
            edit = dialog.findChild(QLineEdit, 'fileNameEdit'); edit.clear()
            QTest.keyClicks(edit, str(self.picture))
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open).click()
        QTimer.singleShot(80, accept)
        guard = QTimer(); guard.setSingleShot(True)
        guard.timeout.connect(lambda: self.app.activeModalWidget().reject() if self.app.activeModalWidget() else None)
        guard.start(3000)
        filename, filter = QFileDialog.getOpenFileName(None, 'Open', str(self.root), 'Images (*.png)',
                                                      options=QFileDialog.Option.DontUseNativeDialog)
        guard.stop(); self.assertEqual(observed, [True])
        self.assertEqual(filename, str(self.picture)); self.assertEqual(filter, 'Images (*.png)')

    def test_switching_selection_and_closing_during_work(self):
        started = threading.Event(); release = threading.Event(); inspect = preview.inspect_path
        def slow(path):
            if path == str(self.picture): started.set(); release.wait(3)
            return inspect(path)
        dialog = ImagePicker(None, 'Images', str(self.root), 'All files (*)'); dialog.show()
        pane = dialog.xetal_preview
        with patch.object(preview, 'inspect_path', side_effect=slow):
            pane.selected(str(self.picture)); self.wait_for(started.is_set)
            pane.selected(str(self.text)); release.set()
            self.wait_for(lambda: pane.excerpt.toPlainText() == '{"enabled": true}\n')
            self.assertEqual(pane.name.text(), self.text.name)
            self.assertTrue(pane.preview.pixmap().isNull())
            started.clear(); release.clear(); pane.selected(str(self.picture)); self.wait_for(started.is_set)
            dialog.reject(); sip.delete(dialog); release.set()
            self.wait_for(lambda: not preview.JOBS)

    def test_filenames_and_contents_are_plain_text(self):
        file = self.root/'<b>name.txt'; file.write_text('<img src="file:///private">')
        dialog = ImagePicker(None, 'Files', str(self.root), 'All files (*)'); dialog.show()
        dialog.xetal_preview.selected(str(file))
        self.wait_for(lambda: dialog.xetal_preview.excerpt.toPlainText() == file.read_text())
        self.assertEqual(dialog.xetal_preview.name.textFormat(), Qt.TextFormat.PlainText)
        dialog.reject(); sip.delete(dialog)


if __name__ == '__main__': unittest.main()
