"""Output tests target the selected device and never change its volume or mute."""
import copy
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication
import audio_backend as backend
import audio_preview
from audio_page import AudioPage
from test_audio import fixture, immediate

QT = QApplication.instance() or QApplication([])


class OutputPreviewTests(unittest.TestCase):
    def setUp(self):
        self.page = AudioPage(immediate, listen=False)
        self.data = fixture(1)
        self.page.data = self.data
        self.page.render()
        self.button = self.page.test_output
        self.addCleanup(self.page.deleteLater)
        self.addCleanup(self.button.stop)

    def test_click_plays_current_theme_on_selected_sink_and_keeps_mute(self):
        before = copy.deepcopy(self.data)
        self.data['devices']['sink'][0]['mute'] = True
        with patch.object(audio_preview, 'QProcess') as process_type, patch.object(backend, 'pactl') as write:
            process = process_type.return_value
            self.button.click()
            args = process.start.call_args.args[1]
            self.assertIn('success', args)
            self.assertEqual(args[args.index('--pack')+1], 'follow')
            self.assertEqual(args[args.index('--sink')+1], 'speakers')
            self.assertIn('--preview', args)
            write.assert_not_called()
            self.assertEqual(self.data['devices']['sink'][0]['volume'], before['devices']['sink'][0]['volume'])
            self.assertTrue(self.data['devices']['sink'][0]['mute'])
            self.button.click()
            process.terminate.assert_called_once()
            self.assertIsNone(self.button.player)

    def test_route_change_or_disconnection_stops_only_our_preview(self):
        with patch.object(audio_preview, 'QProcess') as process_type:
            self.button.click()
            process = process_type.return_value
            self.button.set_device(None)
            process.terminate.assert_called_once()
            self.assertFalse(self.button.isEnabled())
            self.assertIsNone(self.button.player)

    def test_preview_errors_are_visible_and_stale_completions_are_ignored(self):
        with patch.object(audio_preview, 'QProcess') as process_type:
            process = process_type.return_value
            process.readAllStandardError.return_value = b'Output disconnected'
            self.button.click()
            self.button.finished(Mock(), 1)
            self.assertIs(self.button.player, process)
            self.button.finished(process, 1)
            self.assertIn('Output disconnected', self.page.status.text())
            self.assertIsNone(self.button.player)
            self.assertEqual(self.button.text(), '▶ Test')

    def test_switching_monitor_disables_test_until_actual_sink_arrives(self):
        self.data['outputs'] = [*self.data['devices']['sink'],
            {'name':'monitor:gpu:hdmi-2','description':'Second monitor','monitor_route':{}}]
        self.page.render()
        self.page.async_run = Mock()
        combo = self.page.devices['sink'][0]
        combo.setCurrentIndex(combo.findData('monitor:gpu:hdmi-2'))
        self.page.device_action('sink', 'default', None)
        self.assertFalse(self.button.isEnabled())
        with patch.object(audio_preview, 'QProcess') as process_type:
            self.button.click()
            process_type.assert_not_called()

    def test_hidden_page_stops_preview_and_refresh_never_plays(self):
        self.page.show()
        QT.processEvents()
        with patch.object(audio_preview, 'QProcess') as process_type:
            self.page.render()
            process_type.assert_not_called()
            self.button.click()
            self.page.hide()
            process_type.return_value.terminate.assert_called_once()


if __name__ == '__main__': unittest.main()
