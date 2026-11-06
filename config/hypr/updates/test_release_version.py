"""Release labels follow exact commits through check, install and rollback."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import github
import release_version
import service
import update_engine as engine

OLD, NEW = '1'*40, '2'*40


class ReleaseVersionTests(unittest.TestCase):
    def test_api_uses_exact_commit_and_reuses_cached_label(self):
        contents = {'type':'file','encoding':'base64',
                    'content':base64.b64encode(b'0.0.0.200-alpha\n').decode()}
        responses = [([{'sha':NEW,'commit':{'message':'Release'}}],'etag'),
                     ({'status':'ahead'},''),(contents,'')]
        with patch.object(github,'request',side_effect=responses) as request:
            value = github.latest(OLD)
        self.assertEqual(value['release_version'],'0.0.0.200-alpha')
        self.assertEqual(request.call_args.args[0],'/contents/config/hypr/VERSION?ref='+NEW)
        with patch.object(github,'request',return_value=(None,'etag')) as request:
            self.assertEqual(github.latest(OLD,value)['release_version'],'0.0.0.200-alpha')
        request.assert_called_once()

    def test_old_or_unavailable_version_does_not_block_commit_updates(self):
        result = {'sha':NEW,'base':OLD,'relation':'ahead'}
        with patch.object(github,'request',side_effect=HTTPError('fixture',404,'missing',{},None)):
            self.assertEqual(github.with_version(result,{})['release_version'],'')
        for error in (OSError('offline'),github.RetryLater('busy',123)):
            with patch.object(github,'request',side_effect=error):
                self.assertEqual(github.with_version(result,{}),result)

    def test_bad_labels_never_become_display_markup(self):
        for invalid in ('<b>installed</b>','1.2.3','0.0.0.01-alpha',None,'x'*81):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):release_version.parse(invalid)
                self.assertEqual(release_version.label(invalid,OLD),OLD[:8])

    def test_versions_are_installed_restored_and_read_from_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);live=root/'live';live.mkdir()
            incoming=root/'incoming';incoming.mkdir();stage=root/'stage';state=root/'state'
            (live/'VERSION').write_text('0.0.0.199-alpha\n')
            engine.write_json(live/engine.META,engine.metadata(live,OLD))
            (incoming/'VERSION').write_text('0.0.0.200-alpha\n')
            expected=engine.merge_profile(live,incoming,stage,NEW)
            plan=engine.prepare_plan(live,stage,expected,NEW)
            backup=engine.apply_plan(live,stage,plan,state)
            self.assertEqual(engine.installed(live)['release_version'],'0.0.0.200-alpha')
            self.assertEqual(service.status(state,live)['current_version'],'0.0.0.200-alpha')
            rollback=engine.rollback_plan(live,backup)
            self.assertEqual(rollback['release_version'],'0.0.0.199-alpha')
            engine.apply_plan(live,backup/'files',rollback,state)
            self.assertEqual(service.status(state,live)['current_version'],'0.0.0.199-alpha')

    def test_check_keeps_version_labels_separate_from_ancestry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);live=root/'live';live.mkdir();state=root/'state'
            (live/'VERSION').write_text('0.0.0.200-alpha\n')
            engine.write_json(live/engine.META,engine.metadata(live,OLD))
            latest={'sha':NEW,'base':OLD,'relation':'behind','message':'Old branch',
                    'release_version':'0.0.0.999-alpha'}
            with patch.object(github,'latest',return_value=latest):value=service.check(live,state)
            self.assertEqual(value['current_version'],'0.0.0.200-alpha')
            self.assertEqual(value['latest_version'],'0.0.0.999-alpha')
            self.assertEqual(value['phase'],'current')
            self.assertEqual(service.badge(value)['text'],'')


if __name__=='__main__':unittest.main()
