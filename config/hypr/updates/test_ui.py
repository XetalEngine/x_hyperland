"""Palette, badge CSS and update controls in an isolated offscreen window."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import service
import update_engine as engine
from app import Window, theme_runtime, STYLE


class UpdateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-update-controls-')
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)/'updates'
        mock = patch.object(service, 'STATE', self.state); mock.start(); self.addCleanup(mock.stop)
        service.publish(phase='available', current='1'*40, latest='2'*40,
                        title='A tested new desktop version', github={'relation': 'ahead'})

    def window(self):
        window = Window(); window.timer.stop(); window.show(); self.application.processEvents()
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        return window

    def ready(self):
        stage = self.state/'prepared'; stage.mkdir(exist_ok=True)
        engine.write_json(stage/'plan.json', {'revision': '2'*40})
        engine.write_json(self.state/'pending.json', {'revision': '2'*40, 'stage': str(stage), 'automatic': True})
        service.publish(phase='ready', prepared='2'*40, message=service.READY_MESSAGE)

    def test_three_themes_and_settings_use_private_state(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix='xetal-updates-ui-') as directory:
            state = Path(directory)/'updates'
            with patch.object(service, 'STATE', state):
                service.publish(phase='available', current='1'*40, latest='2'*40,
                                title='A tested new desktop version', message='A new Xetal desktop update is available.',
                                github={'relation':'ahead'})
                for design in ('raw', 'modern', 'breakpoint'):
                    with patch.object(theme_runtime, 'design', return_value=design):
                        app.setPalette(theme_runtime.palette('dark',design)); app.setStyleSheet(STYLE)
                        window = Window(); window.show(); app.processEvents()
                        self.assertTrue(window.prepare.isEnabled()); self.assertFalse(window.progress.isVisible())
                        self.assertEqual(window.prepare.text(), 'Update!')
                        self.assertLess(window.prepare.geometry().bottom(), window.height())
                        self.assertFalse(window.grab().isNull())
                        window.automatic.setChecked(False)
                        self.assertFalse(service.preferences()['automatic'])
                        service.publish(phase='preparing'); window.refresh(); app.processEvents()
                        self.assertFalse(window.prepare.isEnabled()); self.assertTrue(window.progress.isVisible())
                        self.assertEqual(window.prepare.text(), 'Updating…')
                        service.publish(phase='runtime-required',current='2'*40,latest='2'*40)
                        window.refresh(); app.processEvents()
                        self.assertTrue(window.prepare.isEnabled())
                        self.assertEqual(window.prepare.text(),'Update!')
                        with patch('app.subprocess.Popen'):
                            window.prepare.click()
                        self.assertEqual(service.take_request(),'setup')
                        window.close(); window.deleteLater()
                        service.publish(phase='available', current='1'*40, latest='2'*40,
                                        github={'base':'1'*40, 'relation':'ahead'})

    def test_log_opens_at_end_follows_growth_and_preserves_manual_scroll(self):
        service.publish(phase='preparing')
        log = self.state/'update.log'
        log.write_text(''.join(f'Building component {i}\n' for i in range(180)))
        window = self.window(); bar = window.details.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertEqual(bar.value(), bar.maximum())
        with log.open('a') as stream: stream.write('New output at the end\n'*20)
        window.refresh(); self.application.processEvents()
        self.assertEqual(bar.value(), bar.maximum())
        bar.setValue(bar.maximum()//3); position = bar.value()
        with log.open('a') as stream: stream.write('More output while reading earlier lines\n'*10)
        window.refresh(); self.application.processEvents()
        self.assertEqual(bar.value(), position)
        bar.setValue(bar.maximum())
        # Exercise the bounded log tail, not only short output.
        with log.open('a') as stream: stream.write('Compiler output\n'*2500+'Validation finished\n')
        self.ready(); window.refresh(); self.application.processEvents()
        self.assertEqual(bar.value(), bar.maximum())
        self.assertTrue(window.details.toPlainText().endswith('Validation finished\n'))
        self.assertEqual(window.prepare.text(), 'Restart')

    def test_update_button_transitions_from_request_through_build_to_restart(self):
        window = self.window()
        with patch('app.subprocess.Popen'):
            window.prepare.click()
            self.assertEqual(service.take_request(), 'prepare')
        self.assertEqual(window.prepare.text(), 'Updating…')
        self.assertFalse(window.prepare.isEnabled())
        window.refresh()
        self.assertEqual(window.prepare.text(), 'Updating…')
        service.publish(phase='preparing'); window.refresh()
        self.assertFalse(window.prepare.isEnabled())
        self.ready(); window.refresh()
        self.assertEqual(window.prepare.text(), 'Restart')
        self.assertTrue(window.prepare.isEnabled())
        (self.state/'pending.json').unlink()
        service.publish(phase='attention', message='Compiler error'); window.refresh()
        self.assertEqual(window.prepare.text(), 'Update!')
        self.assertTrue(window.prepare.isEnabled())

    def test_restart_cancel_does_not_launch_or_change_pending_update(self):
        from PyQt6.QtWidgets import QMessageBox
        self.ready(); window = self.window()
        before = (self.state/'pending.json').read_bytes()
        with patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Cancel), \
             patch('app.QProcess.start') as start:
            window.prepare.click()
        start.assert_not_called()
        self.assertEqual((self.state/'pending.json').read_bytes(), before)
        self.assertEqual(window.prepare.text(), 'Restart')

    def test_restart_uses_normal_reboot_and_recovers_from_inhibitor_failure(self):
        from PyQt6.QtCore import QProcess
        from PyQt6.QtWidgets import QMessageBox
        original_start = QProcess.start
        for exit_code in (1, 0):
            with self.subTest(exit_code=exit_code):
                self.ready(); window = self.window()
                commands = []
                def harmless_start(process, program, arguments):
                    commands.append((program, arguments))
                    # Execute a harmless child instead of invoking a power command.
                    original_start(process, sys.executable,
                                   ['-c', f'print("Restart inhibited by another application"); raise SystemExit({exit_code})'])
                with patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
                     patch('app.QMessageBox.warning') as warning, patch.object(QProcess, 'start', harmless_start):
                    window.prepare.click()
                    self.assertEqual(window.prepare.text(), 'Restarting…')
                    deadline = time.monotonic()+5
                    while window.restart_process is not None and window.restart_process.state() != QProcess.ProcessState.NotRunning and time.monotonic()<deadline:
                        self.application.processEvents(); time.sleep(.01)
                    self.application.processEvents()
                    self.assertEqual(commands, [('systemctl', ['reboot'])])
                    self.assertFalse(engine.json_file(self.state/'pending.json')['automatic'])
                    if exit_code:
                        self.assertEqual(window.prepare.text(), 'Restart'); self.assertTrue(window.prepare.isEnabled())
                        self.assertIn('inhibited', warning.call_args.args[2])
                    else:
                        warning.assert_not_called()
                        self.assertTrue(window.restarting); self.assertFalse(window.prepare.isEnabled())

    def test_restart_failure_to_start_leaves_retry_available(self):
        from PyQt6.QtCore import QProcess
        from PyQt6.QtWidgets import QMessageBox
        original_start = QProcess.start
        self.ready(); window = self.window()
        def missing_start(process, _program, _arguments):
            original_start(process, str(self.state/'nonexistent-reboot-command'), [])
        with patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), \
             patch('app.QMessageBox.warning') as warning, patch.object(QProcess, 'start', missing_start):
            window.prepare.click()
            deadline = time.monotonic()+5
            while window.restarting and time.monotonic()<deadline:
                self.application.processEvents(); time.sleep(.01)
            self.assertFalse(window.restarting)
            self.assertEqual(window.prepare.text(), 'Restart'); self.assertTrue(window.prepare.isEnabled())
            warning.assert_called_once()

    def test_restart_rechecks_readiness_after_confirmation(self):
        from PyQt6.QtWidgets import QMessageBox
        self.ready(); window = self.window()
        def changed(*args):
            service.publish(phase='preparing')
            return QMessageBox.StandardButton.Yes
        with patch('app.QMessageBox.question', side_effect=changed), \
             patch('app.QMessageBox.warning') as warning, patch('app.QProcess.start') as start:
            window.prepare.click()
        start.assert_not_called(); warning.assert_called_once()
        self.assertEqual(window.prepare.text(), 'Updating…')

    def test_gtk_badge_animation_parses_in_all_palettes(self):
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk
        import update_widget
        for design in ('raw','modern','breakpoint'):
            for mode in ('dark','light','contrast'):
                provider = Gtk.CssProvider()
                provider.load_from_data(update_widget.style(theme_runtime.colors(mode,design)).encode())


if __name__ == '__main__': unittest.main()
