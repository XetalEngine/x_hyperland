import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import Mock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from model import Job, amount, location, short_location
from window import ProgressWindow
from samples import sample
from preferences import PROFILES
from questions import ChoiceButton

APPLICATION = QApplication.instance() or QApplication([])


class JobTests(unittest.TestCase):
    def job(self, capabilities=3, hints=None):
        return Job('/JobViewServer/job1', ':1.1', 'Dolphin', capabilities, hints)

    def test_percent_unknown_known_amounts_and_explicit_percent(self):
        job = self.job(); self.assertIsNone(job.percent)
        job.update({'processedBytes': 50, 'totalBytes': 200}); self.assertEqual(job.percent, 25)
        job.update({'percent': 42}); self.assertEqual(job.percent, 42)
        job.update({'percent': 200}); self.assertEqual(job.percent, 100)
        job.update({'percent': 'invalid', 'totalBytes': -1}); self.assertEqual(job.percent, 100)

    def test_pause_and_resume_wait_for_the_application_to_acknowledge(self):
        job = self.job(); actions = []; job.requested.connect(actions.append)
        self.assertTrue(job.request('suspend')); self.assertTrue(job.running)
        self.assertEqual(job.summary(), 'Pausing…')
        self.assertFalse(job.request('suspend'))
        job.update({'suspended': True}); self.assertFalse(job.running)
        self.assertEqual(job.pending, '')
        self.assertTrue(job.request('resume')); self.assertFalse(job.running)
        job.update({'suspended': False}); self.assertTrue(job.running)
        self.assertEqual(actions, ['suspend', 'resume'])

    def test_cancel_is_sent_once_and_never_reports_success_without_completion(self):
        job = self.job(); actions = []; job.requested.connect(actions.append)
        self.assertTrue(job.request('cancel')); self.assertFalse(job.request('cancel'))
        self.assertEqual(job.summary(), 'Canceling…'); self.assertIsNone(job.result)
        job.terminate(1); self.assertEqual(job.result, 'canceled')
        self.assertEqual(actions, ['cancel'])
        job.terminate(0); self.assertEqual(job.result, 'canceled')

    def test_capabilities_and_finished_jobs_restrict_controls(self):
        for capability in (0, 1, 2):
            job = self.job(capability)
            self.assertEqual(job.request('suspend'), bool(capability & 2))
            self.assertEqual(job.request('cancel'), bool(capability & 1))
        job = self.job(); job.terminate()
        self.assertEqual(job.percent, 100)
        self.assertFalse(job.request('cancel'))
        job.update({'percent': 12}); self.assertEqual(job.percent, 100)

    def test_crashed_application_is_reported_as_failure(self):
        job = self.job(); job.disconnected()
        self.assertEqual(job.result, 'failed')
        self.assertIn('closed before', job.summary())

    def test_metadata_does_not_expose_remote_passwords(self):
        self.assertEqual(location('sftp://user:secret@host:2222/home/file.png?token=private'), 'sftp://host:2222/home/file.png')
        self.assertEqual(location('file:///tmp/photo%20%23.png'), '/tmp/photo #.png')
        self.assertEqual(short_location('/tmp/Project assets/'), 'Project assets')
        self.assertEqual(amount(1024**3), '1.0 GiB')

    def window(self, job=None):
        # Rendering expectations must not inherit the developer's saved theme.
        window = ProgressWindow(job or self.job(hints={'title': 'Copying files', 'percent': 25}),
                                options={'style': 'modern'})
        self.addCleanup(window.dismiss)
        window.show(); APPLICATION.processEvents()
        return window

    def test_window_dimensions_controls_animation_and_opaque_surface(self):
        window = self.window()
        self.assertEqual((window.width(), window.height()), (448, 168))
        self.assertTrue(window.animation.isActive()); self.assertTrue(window.pause.isVisible())
        first = window.grab().toImage()
        self.assertEqual(first.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(first.pixelColor(225, 70).alpha(), 255)
        window.phase = .35
        second = window.grab().toImage()
        self.assertNotEqual(first, second)
        window.job.update({'suspended': True}); self.assertFalse(window.animation.isActive())
        window.job.update({'suspended': False}); self.assertTrue(window.animation.isActive())
        window.hide(); self.assertFalse(window.animation.isActive())

    def test_close_requests_cancel_without_disappearing_and_error_remains_readable(self):
        job = self.job(); window = self.window(job)
        window.close(); self.assertTrue(window.isVisible()); self.assertEqual(job.pending, 'cancel')
        job.terminate(2, 'Permission denied')
        self.assertTrue(window.isVisible()); self.assertTrue(window.details.isVisible())
        self.assertFalse(window.dismiss_timer.isActive())
        window.close(); self.assertTrue(window.closed)

    def test_unsupported_pause_is_hidden_and_uncancelable_close_is_ignored(self):
        window = self.window(self.job(0))
        self.assertFalse(window.pause.isVisible()); self.assertFalse(window.cancel.isEnabled())
        window.close(); self.assertTrue(window.isVisible()); self.assertIsNone(window.job.result)

    def test_plain_left_press_requests_native_system_move_without_super(self):
        window = self.window()
        handle = Mock(); handle.startSystemMove.return_value = True
        window.windowHandle = lambda: handle
        event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(100, 15), QPointF(100, 15),
                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mousePressEvent(event)
        handle.startSystemMove.assert_called_once()
        self.assertTrue(event.isAccepted())

    def test_questions_expand_in_every_style_and_collapse_after_a_real_button_click(self):
        for style in PROFILES:
            with self.subTest(style=style):
                job = sample()
                window = ProgressWindow(job, options={'style': style})
                window.show(); APPLICATION.processEvents()
                width, height, pause_y = window.width(), window.height(), window.pause.y()
                answers = []; job.answered.connect(answers.append)
                job.ask({'kind': 'conflicts', 'source': '/Source/a', 'destination': '/Target/a', 'replace_allowed': True})
                QTest.qWait(230)
                self.assertGreater(window.height(), height)
                self.assertEqual(window.width(), width)
                self.assertEqual(window.pause.y(), pause_y)
                self.assertFalse(window.pause.isEnabled())
                self.assertFalse(job.running)
                buttons = window.question_panel.findChildren(ChoiceButton)
                self.assertEqual([b.property('choice') for b in buttons], ['replace', 'skip', 'individual'])
                QTest.mouseClick(buttons[1], Qt.MouseButton.LeftButton)
                self.assertEqual(answers, [{'choice': 'skip', 'all': False}])
                QTest.qWait(230)
                self.assertEqual(window.height(), height)
                self.assertFalse(window.question_scroll.isVisible())
                self.assertTrue(job.running)
                window.dismiss(); APPLICATION.processEvents()

    def test_invalid_answers_never_authorize_overwrite_and_cancel_releases_question(self):
        job = self.job(); answers = []; job.answered.connect(answers.append)
        job.ask({'kind': 'file', 'destination': '/Target/folder', 'replace_allowed': False})
        self.assertFalse(job.answer('replace', True))
        self.assertFalse(job.answer('copy'))
        self.assertIsNotNone(job.question)
        self.assertFalse(job.request('suspend'))
        job.request('cancel')
        self.assertIsNone(job.question)
        self.assertEqual(answers, [{'choice': 'cancel', 'all': False}])

    def test_individual_apply_all_and_simultaneous_questions_remain_independent(self):
        first, second = self.job(), self.job()
        answers = []; first.answered.connect(answers.append)
        first.ask({'kind': 'file', 'destination': '/Target/a', 'replace_allowed': True})
        second.ask({'kind': 'duplicate', 'destination': '/Other'})
        window = self.window(first)
        window.question_panel.apply_all.setChecked(True)
        window.question_panel.findChildren(ChoiceButton)[0].click()
        self.assertEqual(answers, [{'choice': 'replace', 'all': True}])
        self.assertEqual(second.question['kind'], 'duplicate')
        second.terminate(2, 'Client disconnected')
        self.assertIsNone(second.question)

    def test_preview_questions_use_selected_style_without_mutating_preferences(self):
        window = ProgressWindow(sample(state='conflicts'), options={'style': 'breakpoint'}, preview=True, embedded=True)
        self.addCleanup(window.dismiss)
        self.assertEqual(window.design, 'breakpoint')
        self.assertGreater(window.height(), window.base_height)
        self.assertEqual(len(window.question_panel.findChildren(ChoiceButton)), 3)


if __name__ == '__main__': unittest.main()
