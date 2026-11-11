"""Attention drawer interaction, stable rows and worker decision semantics."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from model import Job
from preferences import PROFILES
from window import ProgressWindow
from placement import Placement, anchored_geometry

APP = QApplication.instance() or QApplication([])


def issue(identifier=1, **changes):
    row = dict(id=identifier, version=1, name='win10.xml', source='/Mounted/Private/win10.xml',
               destination='/Home/Files/win10.xml', status='pending', statusText='Needs a choice',
               resultText='Permission denied', detail='Permission denied',
               details='Needs a choice\nIssue: Permission denied\n\nFrom: /Mounted/Private/win10.xml\nTo: /Home/Files/win10.xml\nStage: Copying',
               category='copy:permission', retry_allowed=True, replace_allowed=False)
    row.update(changes); return row


class QueueTests(unittest.TestCase):
    def window(self, style='modern'):
        job = Job('/job/1', ':1.1', 'Fusion Files', 3, {'title': 'Copying files', 'totalsKnown': True,
                  'processedFiles': 40, 'totalFiles': 100, 'phase': 'Copying', 'percent': 40})
        window = ProgressWindow(job, options={'style': style})
        self.addCleanup(window.dismiss)
        window.show(); APP.processEvents(); return window

    def populate(self, window, rows=None, **state):
        window.job.update_queue({'rows': rows or [issue()], 'state': dict(
            heading='Items needing attention', summary='Other files keep copying; retries run after this pass.',
            journal='/fixture/journal.sqlite', **state)})
        return window.queue_panel

    def test_unfolds_downward_without_changing_card_width_or_controls(self):
        window = self.window(); window.move(50, 12)
        width, height, position, pause = window.width(), window.height(), window.pos(), window.pause.geometry()
        panel = self.populate(window)
        self.assertTrue(window.expansion.state() == window.expansion.State.Running)
        QTest.qWait(240)
        self.assertEqual(window.width(), width)
        self.assertGreater(window.height(), height)
        self.assertEqual(window.pos(), position)
        self.assertEqual(window.pause.geometry(), pause)
        self.assertEqual(panel.window(), window)
        self.assertEqual(panel.model.columnCount(), 3)
        self.assertTrue(window.job.running)
        self.assertTrue(window.pause.isEnabled())
        self.assertFalse(window.job.question)
        panel.hide_button.click(); QTest.qWait(240)
        self.assertEqual(window.height(), height)
        self.assertFalse(window.queue_scroll.isVisible())
        self.assertTrue(window.job.running)
        window.review.click(); QTest.qWait(240)
        self.assertTrue(window.queue_scroll.isVisible())

    def test_each_theme_retains_its_width_and_scrolls_to_fit_screen(self):
        for style in PROFILES:
            with self.subTest(style=style):
                window = self.window(style)
                width, height = window.width(), window.base_height
                window.options['animation']['enabled'] = False
                self.populate(window, access='authorized', accessText='Administrator access is active for this transfer.')
                APP.processEvents()
                self.assertEqual(window.width(), width)
                self.assertEqual(window.base_height, height)
                self.assertLessEqual(window.height(), window.screen().availableGeometry().height()-24)
                self.assertGreater(window.height(), height)
                self.assertEqual(window.queue_panel.table.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.assertFalse(window.queue_panel.isWindow())
                window.dismiss()

    def test_multiple_selection_targets_only_unfinished_rows_with_versions(self):
        window = self.window(); panel = self.populate(window, [issue(), issue(2, status='resolved', statusText='Copied successfully'), issue(3)])
        decisions = []; window.job.queue_decision.connect(decisions.append)
        panel.table.selectAll(); panel.similar.setChecked(True); panel.buttons['skip'].click()
        self.assertEqual(decisions, [{'ids': [1, 3], 'versions': {'1': 1, '3': 1}, 'choice': 'skip', 'all': True}])
        self.assertTrue(window.job.running); self.assertIsNone(window.job.result)

    def test_sorting_and_incremental_updates_preserve_selection_and_success_details(self):
        window = self.window(); panel = self.populate(window, [issue(), issue(2, name='a.txt')])
        panel.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        panel.table.selectRow(1)
        self.assertEqual(panel.selected()[0]['id'], 1)
        window.job.update_queue({'rows': [issue(status='resolved', statusText='Copied successfully',
                                               resultText='Completed after retry', details='Copied successfully\nOriginal issue: Permission denied')]})
        self.assertEqual(panel.selected()[0]['id'], 1)
        self.assertIn('Copied successfully', panel.detail.toPlainText())
        self.assertFalse(panel.buttons['skip'].isEnabled())
        self.assertFalse(panel.buttons['retry'].isEnabled())

    def test_requested_choice_is_visible_until_worker_confirmation_even_when_paused(self):
        window=self.window();panel=self.populate(window)
        window.job.update({'suspended':True})
        decisions=[];window.job.queue_decision.connect(decisions.append)
        panel.buttons['skip'].click()
        self.assertEqual(panel.model.index(0,1).data(),'Skip requested…')
        self.assertIn('paused',panel.detail.toPlainText())
        self.assertEqual(window.job.queue_rows[1]['status'],'pending') # no invented success
        self.assertFalse(panel.buttons['skip'].isEnabled())
        panel.buttons['skip'].click();self.assertEqual(len(decisions),1)
        window.job.update_queue({'rows':[issue(status='skipped',statusText='Skipped',resultText='Original kept',details='Skip accepted. Original kept.')]})
        self.assertEqual(panel.model.index(0,1).data(),'Skipped')
        self.assertIn('Skip accepted',panel.detail.toPlainText())
        self.assertIsNotNone(panel.model.index(0,1).data(Qt.ItemDataRole.DecorationRole))
        self.assertFalse(panel.model.requests)

    def test_requested_revision_can_be_replaced_or_rejected_without_hiding_the_new_issue(self):
        window=self.window();panel=self.populate(window)
        panel.buttons['retry'].click()
        window.job.update_queue({'rows':[issue(version=2)]})
        self.assertTrue(panel.buttons['skip'].isEnabled())
        self.assertEqual(panel.model.index(0,1).data(),'Needs a choice')
        panel.buttons['skip'].click()
        window.job.update_queue({'rows':[issue(version=2,decisionRejected=True)]})
        self.assertTrue(panel.buttons['skip'].isEnabled())
        self.assertFalse(panel.model.requests)

    def test_immediate_worker_reply_replaces_request_without_a_stuck_spinner(self):
        window=self.window();panel=self.populate(window)
        window.job.queue_decision.connect(lambda _:window.job.update_queue({'rows':[
            issue(status='skipped',statusText='Skipped',details='Original kept')]}))
        panel.buttons['skip'].click()
        self.assertEqual(panel.model.index(0,1).data(),'Skipped')
        self.assertFalse(panel.model.requests)

    def test_full_paths_remain_searchable_even_without_path_columns(self):
        panel = self.populate(self.window(), [issue(), issue(2, source='/Other/file.txt', details='Other file', name='file.txt')])
        panel.filter.setText('/Mounted/Private')
        self.assertEqual(panel.proxy.rowCount(), 1)
        self.assertEqual(panel.proxy.index(0, 0).data(), 'win10.xml')
        panel.filter.setText('no matching row')
        self.assertEqual(panel.proxy.rowCount(), 0)
        self.assertFalse(panel.buttons['skip'].isEnabled())

    def test_authorization_retries_and_unsupported_items_keep_existing_rules(self):
        window = self.window(); panel = self.populate(window)
        decisions = []; window.job.queue_decision.connect(decisions.append)
        panel.buttons['authorize'].click()
        self.assertEqual(decisions[-1]['choice'], 'authorize')
        window.job.update_queue({'rows': [issue(status='authorizing', statusText='Awaiting authorization')],
                                 'state': {'access': 'authorizing', 'accessText': 'Complete the system authentication prompt.'}})
        self.assertFalse(panel.buttons['authorize'].isEnabled())
        window.job.update_queue({'rows': [issue(version=2)], 'state': {'access': 'authorized', 'accessText': 'Administrator access is active.'}})
        self.assertEqual(panel.buttons['authorize'].text(), 'Retry as administrator')
        panel.buttons['authorize'].click(); self.assertEqual(decisions[-1]['versions'], {'1': 2})
        window.job.update_queue({'rows': [issue(version=3, category='copy:named pipe', retry_allowed=False)]})
        self.assertFalse(panel.buttons['retry'].isEnabled())
        self.assertFalse(panel.buttons['authorize'].isEnabled())
        self.assertTrue(panel.buttons['skip'].isEnabled())

    def test_replace_requires_confirmation_and_rejects_changed_revision(self):
        window = self.window(); panel = self.populate(window, [issue(category='copy:exists', replace_allowed=True)])
        decisions = []; window.job.queue_decision.connect(decisions.append)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No): panel.buttons['replace'].click()
        self.assertEqual(decisions, [])
        def change_during_confirmation(*_):
            window.job.update_queue({'rows': [issue(version=2, category='copy:exists', replace_allowed=True)]})
            return QMessageBox.StandardButton.Yes
        with patch.object(QMessageBox, 'question', side_effect=change_during_confirmation): panel.buttons['replace'].click()
        self.assertEqual(decisions, [])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes): panel.buttons['replace'].click()
        self.assertEqual(decisions[0]['versions'], {'1': 2})

    def test_finished_queue_stays_available_and_never_sends_more_decisions(self):
        window = self.window(); panel = self.populate(window)
        window.job.update_queue({'rows': [issue(status='resolved', statusText='Copied successfully')],
                                 'state': {'done': True, 'heading': 'Transfer complete', 'summary': '1 file copied'}})
        window.job.terminate()
        self.assertEqual(panel.heading.text(), 'Transfer complete')
        self.assertFalse(window.dismiss_timer.isActive())
        self.assertTrue(window.review.isVisible())
        self.assertFalse(panel.buttons['retry'].isEnabled())
        self.assertFalse(panel.cancel.isEnabled())
        self.assertTrue(panel.save.isEnabled())
        self.assertFalse(window.job.decide_queue([1], 'skip'))
        panel.hide_button.click(); QTest.qWait(240)
        window.review.click(); QTest.qWait(240)
        self.assertTrue(window.queue_scroll.isVisible())

    def test_escape_collapses_without_cancel_and_separate_jobs_stay_independent(self):
        first, second = self.window(), self.window()
        one, two = self.populate(first), self.populate(second)
        decisions = []; second.job.queue_decision.connect(decisions.append)
        QTest.keyClick(first, Qt.Key.Key_Escape); QTest.qWait(240)
        self.assertFalse(first.queue_open); self.assertEqual(first.job.pending, '')
        self.assertTrue(second.queue_open)
        one.buttons['skip'].click()
        self.assertEqual(decisions, [])
        self.assertEqual(second.job.queue_rows[1]['status'], 'pending')

    def test_blocking_question_temporarily_uses_drawer_without_losing_queue(self):
        window = self.window(); panel = self.populate(window)
        window.job.ask({'kind': 'duplicate', 'source': '/a', 'destination': '/a'})
        self.assertFalse(window.queue_scroll.isVisible())
        self.assertTrue(window.question_scroll.isVisible())
        window.job.answer('copy'); QTest.qWait(240)
        self.assertTrue(window.queue_scroll.isVisible())
        self.assertEqual(window.queue_panel, panel)
        self.assertTrue(window.job.running)


class PlacementTests(unittest.TestCase):
    def test_anchor_retains_top_left_and_clamps_only_when_drawer_would_go_offscreen(self):
        monitor = dict(x=1920, y=0, width=2560, height=1440, scale=1, reserved=[0,32,0,0])
        self.assertEqual(anchored_geometry({'at':[2300,200]}, monitor, 448, 816), (2300,200,816))
        self.assertEqual(anchored_geometry({'at':[2300,1000]}, monitor, 448, 816), (2300,624,816))
        rotated = dict(x=-1080, y=0, width=1920, height=1080, scale=1.5, transform=1, reserved=[0,30,0,20])
        self.assertEqual(anchored_geometry({'at':[-1100,100]}, rotated, 448, 2000), (-1080,46,1214))

    def placement(self):
        window = ProgressWindow(Job('/fixture', ':fixture', 'Files', 3), preview=True)
        self.addCleanup(window.dismiss)
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR':'/fixture', 'HYPRLAND_INSTANCE_SIGNATURE':'test'}):
            return Placement(window)

    def test_only_exact_window_and_process_can_be_addressed(self):
        placement = self.placement()
        ours = dict(pid=os.getpid(), mapped=True, floating=True, address='0x123', stableId=9,
                    initialTitle=placement.binding_title)
        other = dict(ours, pid=os.getpid()+1)
        self.assertEqual(placement.match([other, ours]), ours)
        placement.address, placement.stable_id = '0x123', 9
        self.assertIsNone(placement.match([dict(ours, stableId=10)]))
        self.assertIsNone(placement.match([dict(ours, address='0x456')]))
        self.assertIsNone(placement.match([dict(ours, floating=False)]))
        placement.address = None; placement.binding_title = ''
        self.assertIsNone(placement.match([dict(ours, title='')]))

    def test_async_resize_coalesces_frames_and_never_moves_a_sibling(self):
        placement = self.placement(); placement.address = '0x123'; placement.stable_id = 9
        placement.anchor = (200, 100)
        calls = []
        placement.request = lambda command, callback: calls.append((command, callback))
        with patch.dict(os.environ, {'XETAL_HYPRLAND_LUA':'0'}):
            placement.resize(448, 300); placement.resize(448, 500); placement.resize(448, 816)
            self.assertEqual(len(calls), 1)
            self.assertIn('exact 200 100,address:0x123', calls[0][0])
            calls[0][1](b'ok')
            self.assertEqual(len(calls), 2)
            self.assertIn('exact 448 816,address:0x123', calls[1][0])
            placement.release(); calls[1][1](b'ok')
            self.assertEqual(len(calls), 2)

    def test_compositor_failure_falls_back_without_blocking_the_transfer(self):
        placement = self.placement(); completed = []
        placement.request = lambda command, callback: callback(None)
        placement.prepare(816, completed.append); QTest.qWait(10)
        self.assertEqual(completed, [816]); self.assertIsNone(placement.anchor)


if __name__ == '__main__': unittest.main()
