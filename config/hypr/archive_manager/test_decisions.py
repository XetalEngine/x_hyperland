"""Archive choices are acknowledged independently of compression and pause."""
import errno
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QCoreApplication

sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import Result
from tasks import Task


class Decisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'XDG_STATE_HOME':str(self.root/'state')});env.start();self.addCleanup(env.stop)
        self.task=Task(dict(operation='compress',sources=[str(self.root/'source')],output=str(self.root/'out.7z')))
        self.task.engine_cwd=str(self.root);self.task.begin_archive_pass()
        self.events=[];self.task.message.connect(self.events.append)

    def error(self,name='private',code=errno.EACCES,stage='open'):
        return dict(event='error',path=name,code=code,stage=stage)

    def choose(self,row,choice='skip',similar=False,version=None):
        self.task.command(dict(command='issue_answer',ids=[row['id']],
            versions={str(row['id']):row['version'] if version is None else version},choice=choice,all=similar))

    def test_paused_skip_is_confirmed_without_waiting_for_the_compression_pass(self):
        error=self.error();row=self.task.archive_issue(error)
        self.task.command({'command':'pause'});self.choose(row)
        self.assertTrue(self.task.control.paused)
        self.assertEqual(self.task.archive_ids[row['id']]['status'],'skipped')
        self.assertEqual(self.events[-1]['status'],'skipped')
        self.assertIn('Skip accepted',self.events[-1]['decisionText'])
        self.assertEqual(self.events[0]['status'],'pending') # queued events are snapshots
        self.task.command({'command':'resume'})
        self.assertFalse(self.task.resolve_archive_errors(Result(1,'',[error])))
        self.assertEqual(self.task.archive_ids[row['id']]['version'],row['version'])
        history=[json.loads(line) for line in self.task.report.read_text().splitlines()]
        self.assertEqual([r['status'] for r in history if r['event']=='issue'],['pending','skipped'])

    def test_skip_similar_accepts_current_and_future_matches_only(self):
        first=self.task.archive_issue(self.error('one'))
        second=self.task.archive_issue(self.error('two'))
        different=self.task.archive_issue(self.error('missing',errno.ENOENT))
        self.choose(first,similar=True)
        later=self.task.archive_issue(self.error('three'))
        for row in (first,second,later):
            self.assertEqual(self.task.archive_ids[row['id']]['status'],'skipped')
            self.assertIn('later matching',self.task.archive_ids[row['id']]['decisionText'])
        self.assertEqual(self.task.archive_ids[different['id']]['status'],'pending')
        self.assertIn('automatically',later['decisionText'])

    def test_retry_similar_is_one_attempt_and_failed_retry_gets_a_new_revision(self):
        error=self.error('one');first=self.task.archive_issue(error)
        second=self.task.archive_issue(self.error('two'))
        self.choose(first,'retry',True)
        self.assertEqual(self.task.archive_ids[second['id']]['status'],'retry')
        later=self.task.archive_issue(self.error('three'))
        self.assertEqual(later['status'],'pending')
        self.task.begin_archive_pass()
        again=self.task.archive_issue(error)
        self.assertEqual((again['id'],again['version'],again['status']),(first['id'],2,'pending'))
        self.choose(first,similar=True) # old revision must not install a skip policy
        self.assertFalse(self.task.skip_categories)
        self.assertEqual(self.task.archive_ids[first['id']]['status'],'pending')
        self.assertTrue(self.events[-1]['decisionRejected'])
        self.choose(again)
        self.task.finish_archive_pass()
        self.assertEqual(self.task.archive_ids[second['id']]['status'],'resolved')

    def test_changed_issue_during_retry_does_not_claim_the_input_was_archived(self):
        row=self.task.archive_issue(self.error())
        self.choose(row,'retry');self.task.begin_archive_pass()
        self.task.archive_issue(self.error(code=errno.EIO,stage='read'))
        self.task.finish_archive_pass()
        state=self.task.archive_ids[row['id']]
        self.assertEqual(state['resolution'],'Retry attempted')
        self.assertIn('another issue',state['decisionText'])

    def test_cancel_and_duplicate_clicks_do_not_install_new_skip_policies(self):
        first=self.task.archive_issue(self.error('one'));self.choose(first)
        self.choose(first,similar=True)
        self.assertFalse(self.task.skip_categories)
        second=self.task.archive_issue(self.error('two'))
        self.task.command({'command':'cancel'});self.choose(second,similar=True)
        self.assertFalse(self.task.skip_categories)
        self.assertEqual(self.task.archive_ids[second['id']]['status'],'pending')


if __name__=='__main__':unittest.main()
