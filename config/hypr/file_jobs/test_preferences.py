"""Persisted choices and live appearance changes must never replace a file job."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QEvent, QObject, QPoint, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from file_jobs import preferences
from file_jobs.app import Windows
from file_jobs.page import FileTransferPage
from file_jobs.samples import sample
from file_jobs.window import ProgressWindow, theme_runtime

QT = QApplication.instance() or QApplication([])


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'preferences.json'

    def test_defaults_and_independent_profiles_survive_reopening(self):
        values, token = preferences.load(self.path)
        values['style'] = 'modern'; values['profiles']['modern'].update(width=600, accent='#77aacc')
        values['information']['remaining'] = True
        saved, token = preferences.save(values, token, self.path)
        reopened, next_token = preferences.load(self.path)
        self.assertEqual((saved, token), (reopened, next_token))
        self.assertEqual(reopened['profiles']['raw']['width'], 448)
        self.assertEqual(reopened['profiles']['breakpoint']['width'], 448)
        for desktop in preferences.PROFILES:
            self.assertEqual(preferences.selected(reopened, desktop), 'modern')
        reopened['style'] = 'follow'
        for desktop in preferences.PROFILES:
            self.assertEqual(preferences.selected(reopened, desktop), desktop)
        self.assertEqual(preferences.DEFAULTS['profiles']['modern']['width'], 448)

    def test_invalid_settings_cannot_replace_saved_choices(self):
        values, token = preferences.load(self.path)
        _, token = preferences.save(values, token, self.path)
        before = self.path.read_bytes()
        invalid = [{'style': []}, {'version': True}, {'profiles': {'raw': {'width': 0}}},
                   {'profiles': {'modern': {'accent': 'red; color:white'}}},
                   {'animation': {'density': 0}}, {'animation': {'enabled': 1}},
                   {'information': {'paths': 'anything'}}, {'behavior': {'show_delay': -1}}]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                preferences.save(candidate, token, self.path)
            self.assertEqual(self.path.read_bytes(), before)

    def test_external_edits_and_failed_atomic_replace_leave_original_intact(self):
        first, stale = preferences.load(self.path)
        first['style'] = 'raw'; _, token = preferences.save(first, stale, self.path)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed elsewhere'):
            preferences.save({'style': 'modern'}, stale, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        with patch.object(preferences.os, 'replace', side_effect=OSError('read only')):
            with self.assertRaises(OSError): preferences.save({'style': 'modern'}, token, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob('.transfer-*')))


class WindowTests(unittest.TestCase):
    def window(self, options=None, preview=False):
        window = ProgressWindow(sample(), options=options or preferences.normalize({}), preview=preview)
        window.show(); QT.processEvents()
        self.addCleanup(window.dismiss)
        return window

    def test_all_designs_mix_with_every_desktop_without_replacing_job_or_controls(self):
        window = self.window(); original = window.job
        actions = []; original.requested.connect(actions.append)
        for mode in theme_runtime.MODES:
            for desktop in preferences.PROFILES:
                with patch.object(theme_runtime, 'state', return_value={'design': desktop, 'mode': mode}), patch.object(theme_runtime, 'mode', return_value=mode):
                    for design in preferences.PROFILES:
                        choice = preferences.normalize({'style': design})
                        window.set_options(choice); QT.processEvents()
                        self.assertEqual(window.design, design)
                        self.assertEqual(window.colors, theme_runtime.colors(mode, design))
                        self.assertIs(window.job, original)
                        self.assertTrue(window.cancel.isEnabled()); self.assertTrue(window.pause.isVisible())
                        self.assertFalse(window.grab().isNull())
        window.toggle_pause(); self.assertEqual(actions, ['suspend'])
        self.assertEqual(original.pending, 'suspend')
        window.set_options({'style': 'raw'})
        self.assertEqual(original.pending, 'suspend')
        original.update({'suspended': True}); window.toggle_pause()
        original.update({'suspended': False}); window.close()
        self.assertEqual(actions, ['suspend', 'resume', 'cancel'])
        self.assertTrue(window.isVisible()); self.assertIsNone(original.result)

    def test_size_opacity_animation_and_hidden_information_change_live(self):
        choice = preferences.normalize({'style': 'breakpoint'})
        choice['profiles']['breakpoint'].update(width=360, height=156, radius=0, opacity=55, glow=0)
        choice['animation'].update(enabled=False, smooth=False)
        choice['information'].update(paths='hidden', percentage=False, amount=False, speed=False, remaining=False)
        window = self.window(choice)
        self.assertEqual((window.width(), window.height()), (360, 156))
        self.assertFalse(window.animation.isActive()); self.assertEqual(window.summary(), '')
        self.assertEqual(window.display_percent, 64)
        image = window.grab().toImage()
        self.assertTrue(135 <= image.pixelColor(100, 35).alpha() <= 145)
        choice['animation']['enabled'] = True; window.set_options(choice)
        self.assertTrue(window.animation.isActive())
        window.job.update({'suspended': True}); self.assertFalse(window.animation.isActive())
        self.assertIn('Paused', window.summary())
        window.hide(); self.assertFalse(window.animation.isActive())

    def test_unknown_size_eta_and_error_information_remain_honest(self):
        choice = preferences.normalize({}); choice['information']['remaining'] = True
        window = self.window(choice)
        self.assertIn('left', window.summary())
        window.job.data.pop('totalBytes'); window.job.data.pop('percent'); window.refresh()
        self.assertIsNone(window.job.percent); self.assertNotIn('left', window.summary())
        window.job.terminate(2, 'Cannot write destination')
        self.assertTrue(window.details.isVisible()); self.assertIn('Cannot write', window.summary())
        self.assertFalse(window.dismiss_timer.isActive())
        for style in preferences.PROFILES:
            window.set_options({'style': style}); self.assertTrue(window.isVisible())
            self.assertFalse(window.dismiss_timer.isActive())

    def test_completion_delay_can_be_disabled_or_changed_without_losing_result(self):
        window = self.window(); window.job.terminate()
        self.assertTrue(window.dismiss_timer.isActive())
        choice = copy.deepcopy(window.options); choice['behavior']['auto_close'] = False
        window.set_options(choice); self.assertFalse(window.dismiss_timer.isActive())
        self.assertTrue(window.isVisible()); self.assertEqual(window.cancel.text(), 'Close')
        choice['behavior'].update(auto_close=True, close_delay=600)
        window.set_options(choice); self.assertEqual(window.dismiss_timer.interval(), 600)
        self.assertTrue(window.dismiss_timer.isActive()); self.assertEqual(window.job.result, 'done')

    def test_preview_close_does_not_cancel_a_job(self):
        window = self.window(preview=True); actions = []; window.job.requested.connect(actions.append)
        window.close()
        self.assertTrue(window.closed); self.assertEqual(actions, [])

    def test_saved_file_changes_apply_to_existing_windows_and_corrupt_file_is_ignored(self):
        class FakeService(QObject):
            created = pyqtSignal(object)
            release = Mock()
        with tempfile.TemporaryDirectory() as directory, patch.object(preferences, 'PATH', Path(directory)/'settings.json'):
            service = FakeService(); manager = Windows(service); job = sample()
            service.created.emit(job); window = manager.windows[job.path]
            self.addCleanup(window.dismiss); self.addCleanup(service.deleteLater)
            values, token = preferences.load(); values['style'] = 'raw'
            preferences.save(values, token); QTest.qWait(200)
            self.assertEqual(window.design, 'raw'); self.assertIs(window.job, job)
            values['style'] = 'breakpoint'; preferences.PATH.write_text(json.dumps(values)); QTest.qWait(200)
            self.assertEqual(window.design, 'breakpoint')
            preferences.PATH.write_text('{broken'); QTest.qWait(200)
            self.assertEqual(window.design, 'breakpoint'); self.assertIsNone(job.result)
            self.assertFalse(service.release.called)


class PageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'settings.json'
        self.setting = patch.object(preferences, 'PATH', self.path); self.setting.start(); self.addCleanup(self.setting.stop)
        def run(work, done, failed):
            try: result = work()
            except Exception as error: failed(str(error))
            else: done(result)
        self.page = FileTransferPage(run)
        self.addCleanup(self.dispose)

    def dispose(self):
        self.page.hide(); self.page.deleteLater(); QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_switching_styles_retains_drafts_and_save_reload_preserves_both_profiles(self):
        self.page.select_style('raw'); self.page.fields[('profile', 'width')].setValue(512)
        self.page.select_style('modern'); self.page.fields[('profile', 'width')].setValue(600)
        self.assertTrue(self.page.dirty)
        self.page.select_style('raw'); self.assertEqual(self.page.fields[('profile', 'width')].value(), 512)
        self.page.save(); self.assertFalse(self.page.dirty)
        saved, _ = preferences.load()
        self.assertEqual(saved['profiles']['raw']['width'], 512)
        self.assertEqual(saved['profiles']['modern']['width'], 600)
        self.page.reset_defaults(); self.assertTrue(self.page.dirty)
        self.page.reset(); self.assertFalse(self.page.dirty)
        self.assertEqual(self.page.draft['profiles']['modern']['width'], 600)

    def test_external_update_keeps_unsaved_edits_and_reports_conflict(self):
        self.page.select_style('raw'); self.page.fields[('profile', 'height')].setValue(200)
        values, token = preferences.load(); values['style'] = 'modern'; preferences.save(values, token)
        self.page.refresh(); self.assertEqual(self.page.draft['style'], 'raw')
        self.page.save(); self.assertTrue(self.page.dirty); self.assertFalse(self.page.busy)
        self.assertIn('changed elsewhere', self.page.status.text())
        self.assertEqual(preferences.load()[0]['style'], 'modern')

    def test_live_preview_stops_when_hidden_and_actions_fit_compact_panel(self):
        self.page.resize(960, 440); self.page.show(); QT.processEvents()
        self.assertTrue(self.page.preview.window.animation.isActive())
        for action in (self.page.defaults, self.page.popup, self.page.reload_button, self.page.discard, self.page.apply):
            origin = action.mapTo(self.page, QPoint(0, 0))
            self.assertTrue(self.page.rect().contains(origin))
            self.assertTrue(self.page.rect().contains(origin+QPoint(action.width()-1, action.height()-1)))
        self.page.hide(); self.assertFalse(self.page.preview.window.animation.isActive())
        self.assertTrue(all(not card.thumbnail.animation.isActive() for card in self.page.cards.values()))

    def test_popup_passes_valid_draft_without_saving_or_starting_a_real_operation(self):
        self.page.select_style('breakpoint'); self.page.operation.setCurrentIndex(self.page.operation.findData('compress'))
        with patch('file_jobs.page.subprocess.Popen') as launch:
            self.page.open_popup()
        argv = launch.call_args.args[0]
        self.assertEqual(json.loads(argv[argv.index('--preview')+1])['style'], 'breakpoint')
        self.assertEqual(argv[-2:], ['--operation', 'compress'])
        self.assertFalse(self.path.exists())


if __name__ == '__main__': unittest.main()
