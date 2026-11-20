"""Complete, bounded-to-the-installed-version notes without network access."""
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import github

OLD = 'a'*40


def entry(index, message=None):
    return {'sha': f'{index:040x}', 'commit': {
        'message': message or f'Change {index}\n\nFull details for change {index}.',
        'committer': {'date': '2026-11-19T20:30:00Z'},
    }}


def page(entries, total=None):
    return {'status':'ahead', 'commits':entries, 'total_commits':len(entries) if total is None else total}


class CommitNotesTests(unittest.TestCase):
    def setUp(self):
        version = patch.object(github, 'with_version', side_effect=lambda value, previous: value)
        version.start(); self.addCleanup(version.stop)

    def test_all_pages_and_full_messages_are_kept_in_newest_first_order(self):
        commits = [entry(i) for i in range(1, 306)]
        commits[0]['commit']['message'] = 'First missed change\n\n'+('Long description.\n'*400)+'Final paragraph.'
        head = commits[-1]['sha']
        replies = [([commits[-1]], 'head-etag')]
        replies.extend((page(commits[i:i+100], len(commits)), '') for i in range(0, len(commits), 100))
        with patch.object(github, 'request', side_effect=replies) as request:
            value = github.latest(OLD)
        self.assertTrue(value['notes_complete'])
        self.assertEqual([item['sha'] for item in value['commits']], [item['sha'] for item in reversed(commits)])
        self.assertEqual(value['commits'][-1]['message'], commits[0]['commit']['message'])
        self.assertNotIn(OLD, [item['sha'] for item in value['commits']])
        self.assertEqual([call.args[0] for call in request.call_args_list[1:]],
                         [f'/compare/{OLD}...{head}?per_page=100&page={i}' for i in range(1, 5)])

    def test_legacy_cache_is_refreshed_even_when_the_head_returns_304(self):
        commit = entry(3)
        previous = {'base':OLD, 'sha':commit['sha'], 'relation':'ahead', 'etag':'same', 'message':'Only the last title'}
        with patch.object(github, 'request', side_effect=[(None, 'same'), (page([entry(1), entry(2), commit]), '')]) as request:
            value = github.latest(OLD, previous)
        self.assertEqual(len(value['commits']), 3)
        self.assertTrue(value['notes_complete'])
        self.assertEqual(request.call_count, 2)
        self.assertNotIn('commits', previous)
        with patch.object(github, 'request', return_value=(None, 'same')) as request:
            self.assertEqual(github.latest(OLD, value)['commits'], value['commits'])
        request.assert_called_once()

    def test_notes_are_recomputed_when_the_installed_version_moves_forward(self):
        commits = [entry(i) for i in range(1, 4)]
        with patch.object(github, 'request', side_effect=[([commits[-1]], 'same'), (page(commits), '')]):
            previous = github.latest(OLD)
        installed = commits[1]['sha']
        with patch.object(github, 'request', side_effect=[(None, 'same'), (page([commits[-1]]), '')]) as request:
            value = github.latest(installed, previous)
        self.assertEqual([item['sha'] for item in value['commits']], [commits[-1]['sha']])
        self.assertEqual(value['base'], installed)
        self.assertIn('/compare/'+installed+'...', request.call_args.args[0])
        self.assertEqual(len(previous['commits']), 3)

    def test_new_head_invalidates_previously_complete_notes(self):
        previous = {'base':OLD, 'sha':entry(1)['sha'], 'relation':'ahead', 'message':'Old head',
                    'notes_complete':True, 'commits':[{'sha':entry(1)['sha'], 'message':'Old head'}]}
        with patch.object(github, 'request', side_effect=[([entry(2)], 'new'), (page([entry(1), entry(2)]), '')]):
            value = github.latest(OLD, previous)
        self.assertEqual([item['sha'] for item in value['commits']], [entry(2)['sha'], entry(1)['sha']])

    def test_failed_page_does_not_claim_partial_notes_are_complete_or_block_a_verified_update(self):
        first = [entry(i) for i in range(1, 101)]
        for failure in (HTTPError('fixture', 503, 'Unavailable', {}, None),
                        github.RetryLater('Busy', 9999999999),
                        (page(first, 101), ''), (page([], 101), '')):
            with self.subTest(failure=str(failure)):
                with patch.object(github, 'request', side_effect=[([entry(101)], 'head'), (page(first, 101), ''), failure]):
                    value = github.latest(OLD)
                self.assertEqual(value['relation'], 'ahead')
                self.assertFalse(value['notes_complete'])
                self.assertEqual(value['commits'], [])
                self.assertIn('Check now', value['notes_error'])

    def test_identical_or_non_update_history_never_reuses_old_range_notes(self):
        previous = {'base':OLD, 'sha':entry(2)['sha'], 'relation':'ahead', 'message':'Latest change',
                    'notes_complete':True, 'commits':[{'sha':entry(2)['sha'], 'message':'Latest change'}]}
        with patch.object(github, 'request', return_value=(None, 'same')) as request:
            value = github.latest(entry(2)['sha'], previous)
        self.assertEqual(value['relation'], 'identical')
        self.assertEqual(value['commits'], [])
        request.assert_called_once()
        for relation in ('behind', 'diverged'):
            with patch.object(github, 'request', side_effect=[(None, 'same'), ({'status':relation}, '')]):
                value = github.latest('b'*40, previous)
            self.assertEqual(value['commits'], [])
            self.assertEqual(value['relation'], relation)


if __name__ == '__main__': unittest.main()
