"""Archive extraction handoff without touching the live desktop or bus."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from gi.repository import Gio, GLib
from desktop_files import Files


class ArchiveHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)/'Target # café'; self.folder.mkdir()
        self.files = Files.__new__(Files)
        self.files.bus = Mock(); self.files.error = Mock()
        self.finished = Mock()

    def test_extraction_is_async_and_keeps_literal_destination_characters(self):
        self.files.extract_archive(':1.42', '/Archive/drag/one', self.folder.as_uri(), self.finished)
        arguments = self.files.bus.call.call_args.args
        self.assertEqual(arguments[:4], (':1.42', '/Archive/drag/one', 'org.kde.ark.DndExtract', 'extractSelectedFilesTo'))
        self.assertEqual(arguments[4].unpack(), (str(self.folder),))
        self.assertEqual(arguments[6], Gio.DBusCallFlags.NO_AUTO_START)
        self.finished.assert_not_called()
        arguments[-2](self.files.bus, Mock(), None)
        self.finished.assert_called_once_with(True)
        self.files.error.assert_not_called()

    def test_invalid_or_disappeared_destination_does_not_call_source(self):
        for service, path, destination in [
                ('not a bus', '/Archive', self.folder.as_uri()),
                (':1.42', 'relative', self.folder.as_uri()),
                (':1.42', '/Archive', (self.folder/'gone').as_uri()),
                (':1.42', '/Archive', 'smb://example/share')]:
            self.finished.reset_mock()
            self.files.extract_archive(service, path, destination, self.finished)
            self.finished.assert_called_once_with(False)
        self.files.bus.call.assert_not_called()

    def test_expired_archive_connection_reports_failure(self):
        self.files.extract_archive(':1.42', '/Archive/drag/old', self.folder.as_uri(), self.finished)
        self.files.bus.call_finish.side_effect = GLib.Error('Archive drag expired')
        self.files.bus.call.call_args.args[-2](self.files.bus, Mock(), None)
        self.finished.assert_called_once_with(False)
        self.files.error.assert_called_once()


if __name__ == '__main__': unittest.main()
