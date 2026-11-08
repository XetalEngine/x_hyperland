"""Offline update fixtures. No user settings, network requests or live reloads."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_engine as engine
import github
import service

OLD = '1'*40
NEW = '2'*40


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xetal-update-test-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.live = self.root/'live'; self.live.mkdir()
        self.state = self.root/'state'; self.upstream = self.root/'incoming'; self.stage = self.root/'stage'
        (self.live/'code.py').write_text('old code\n')
        (self.live/'theme').mkdir()
        (self.live/'theme/state.json').write_text(json.dumps({'theme': 'raw', 'apps': ['echo'], 'modules': ['apps','keys','pins']}))
        engine.write_json(self.live/engine.META, engine.metadata(self.live, OLD))
        shutil.copytree(self.live, self.upstream); (self.upstream/engine.META).unlink()

    def prepare(self):
        expected = engine.merge_profile(self.live, self.upstream, self.stage, NEW)
        return engine.prepare_plan(self.live, self.stage, expected, NEW)

    def pending(self, revision=NEW, **options):
        stage = self.state/'prepared'
        stage.mkdir(parents=True, exist_ok=True)
        engine.write_json(stage/'plan.json', {'version':1, 'revision':revision})
        value = {'revision':revision, 'stage':str(stage), 'automatic':True, **options}
        engine.write_json(self.state/'pending.json', value)
        return value

    def test_status_reuses_inventory_but_tracks_atomic_registration_changes(self):
        with patch.object(engine, 'installed', wraps=engine.installed) as inspect:
            for _ in range(5):
                self.assertEqual(service.status(self.state, self.live)['current'], OLD)
            self.assertEqual(inspect.call_count, 1)
            value = engine.json_file(self.live/engine.META)
            value.update(revision=NEW, release_version='0.0.0.300-alpha')
            engine.write_json(self.live/engine.META, value)
            fresh = service.status(self.state, self.live)
            self.assertEqual(fresh['current'], NEW)
            self.assertEqual(fresh['current_version'], '0.0.0.300-alpha')
            self.assertEqual(inspect.call_count, 2)

    def test_cached_status_does_not_skip_transaction_path_validation(self):
        engine.installed_identity(self.live)
        (self.live/'code.py').unlink()
        (self.live/'code.py').symlink_to(self.upstream/'code.py')
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            engine.installed(self.live)

    def test_status_identity_tracks_in_place_changes_and_missing_registration(self):
        self.assertEqual(engine.installed_identity(self.live)['revision'], OLD)
        value = engine.json_file(self.live/engine.META)
        value['revision'] = NEW
        (self.live/engine.META).write_text(json.dumps(value))
        self.assertEqual(engine.installed_identity(self.live)['revision'], NEW)
        (self.live/engine.META).unlink()
        with self.assertRaises(FileNotFoundError):
            engine.installed_identity(self.live)

    def test_local_registration_preserves_preferences_and_backs_up_stale_tracking(self):
        (self.upstream/'code.py').write_text('new code\n')
        self.prepare()
        shutil.copyfile(self.stage/'code.py', self.live/'code.py')
        preference = self.live/'theme/state.json'
        preference.write_text('{"theme":"hollowgrove","my-choice":true}\n')
        (self.live/'personal.txt').write_text('keep me')
        self.pending()
        service.publish(self.state, phase='ready', current=OLD, latest=NEW, prepared=NEW,
                        github={'base':OLD,'relation':'ahead'})
        before = {path:path.read_bytes() for path in
                  (self.live/engine.META, self.state/'pending.json', self.state/'status.json')}
        result = engine.register_deployment(self.live, self.stage, self.state)
        self.assertEqual(engine.installed(self.live)['revision'], NEW)
        self.assertEqual(preference.read_text(), '{"theme":"hollowgrove","my-choice":true}\n')
        self.assertEqual((self.live/'personal.txt').read_text(), 'keep me')
        self.assertEqual(engine.installed(self.live)['files']['theme/state.json'],
                         engine.installed(self.stage)['files']['theme/state.json'])
        self.assertFalse((self.state/'pending.json').exists())
        self.assertEqual(service.badge(service.status(self.state, self.live))['text'], '')
        for path, data in before.items():
            self.assertEqual((Path(result['backup'])/path.name).read_bytes(), data)

    def test_local_registration_rejects_partial_delivery_and_changed_reference(self):
        (self.upstream/'code.py').write_text('new code\n')
        self.prepare()
        before = (self.live/engine.META).read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            engine.register_deployment(self.live, self.stage, self.state)
        self.assertEqual((self.live/engine.META).read_bytes(), before)
        shutil.copyfile(self.stage/'code.py', self.live/'code.py')
        (self.stage/'code.py').write_text('modified reference\n')
        with self.assertRaisesRegex(RuntimeError, 'reference changed'):
            engine.register_deployment(self.live, self.stage, self.state)
        self.assertEqual((self.live/engine.META).read_bytes(), before)

    def test_local_registration_preserves_runtime_rollback_and_other_pending_releases(self):
        self.prepare()
        for revision, options in ((NEW, {'runtime_setup':True}), (NEW, {'rollback':True}), ('3'*40, {})):
            with self.subTest(revision=revision, options=options):
                self.pending(revision, **options)
                before = (self.state/'pending.json').read_bytes()
                engine.register_deployment(self.live, self.stage, self.state)
                self.assertEqual((self.state/'pending.json').read_bytes(), before)

    def test_local_registration_requires_working_executable_permissions(self):
        helper = self.upstream/'helper.sh'
        helper.write_text('#!/bin/sh\nexit 0\n'); helper.chmod(0o755)
        self.prepare()
        shutil.copyfile(helper, self.live/'helper.sh'); (self.live/'helper.sh').chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            engine.register_deployment(self.live, self.stage, self.state)
        # Private owner-only executables are valid; world-read permission is not required.
        (self.live/'helper.sh').chmod(0o700)
        engine.register_deployment(self.live, self.stage, self.state)
        self.assertEqual(engine.installed(self.live)['revision'], NEW)

    def test_local_registration_restores_tracking_if_status_write_fails(self):
        self.prepare(); self.pending()
        service.publish(self.state, phase='ready', current=OLD, latest=NEW)
        before = {path:path.read_bytes() for path in
                  (self.live/engine.META, self.state/'pending.json', self.state/'status.json')}
        actual = engine.write_json
        def failing(path, value):
            if path == self.state/'status.json': raise OSError('disk failed')
            return actual(path, value)
        with patch.object(engine, 'write_json', side_effect=failing):
            with self.assertRaisesRegex(OSError, 'disk failed'):
                engine.register_deployment(self.live, self.stage, self.state)
        for path, data in before.items(): self.assertEqual(path.read_bytes(), data)

    def test_updates_code_and_keeps_personal_preferences_and_unmanaged_files(self):
        (self.upstream/'code.py').write_text('new code\n')
        (self.live/'theme/state.json').write_text(json.dumps({'theme':'breakpoint','apps':['echo','mine'],'modules':['apps','keys','pins','mine']}))
        (self.upstream/'theme/state.json').write_text(json.dumps({'theme':'modern','apps':['echo','new'],'modules':['apps','keys','updates','pins'],'extra':True}))
        (self.live/'my-wallpaper.png').write_bytes(b'private artwork')
        plan = self.prepare(); backup = engine.apply_plan(self.live, self.stage, plan, self.state)
        values = json.loads((self.live/'theme/state.json').read_text())
        self.assertEqual(values['theme'], 'breakpoint'); self.assertEqual(values['apps'], ['echo','new','mine'])
        self.assertEqual(values['modules'], ['apps','keys','updates','pins','mine']); self.assertTrue(values['extra'])
        self.assertEqual((self.live/'code.py').read_text(), 'new code\n')
        self.assertEqual((self.live/'my-wallpaper.png').read_bytes(), b'private artwork')
        self.assertEqual((backup/'files/code.py').read_text(), 'old code\n')
        self.assertEqual(engine.installed(self.live)['revision'], NEW)

    def test_control_panel_binary_is_updated_without_cmake_cache_or_personal_state(self):
        settings=self.live/'control_panel/state/prefs.ini'
        settings.parent.mkdir(parents=True);settings.write_text('personal setting')
        expected=engine.merge_profile(self.live,self.upstream,self.stage,NEW)
        output=self.stage/'control_panel/.build';output.mkdir(parents=True)
        (output/'xetal-control-panel').write_bytes(b'new native program')
        (output/'xetal-control-panel').chmod(0o755)
        (output/'CMakeCache.txt').write_text('temporary build paths')
        plan=engine.prepare_plan(self.live,self.stage,expected,NEW)
        self.assertIn('control_panel/.build/xetal-control-panel',plan['changes'])
        self.assertNotIn('control_panel/.build/CMakeCache.txt',plan['changes'])
        engine.apply_plan(self.live,self.stage,plan,self.state)
        self.assertEqual(settings.read_text(),'personal setting')
        self.assertEqual((self.live/'control_panel/.build/xetal-control-panel').read_bytes(),b'new native program')

    def test_generated_badge_css_does_not_conflict_with_a_personal_palette(self):
        (self.live/'waybar').mkdir()
        path=self.live/'waybar/updates.css';path.write_text('color: blue;\nold selector\n')
        engine.write_json(self.live/engine.META,engine.metadata(self.live,OLD))
        path.write_text('color: cyan;\nold selector\n')
        (self.upstream/'waybar').mkdir()
        (self.upstream/'waybar/updates.css').write_text('color: orange;\nnew selector\n')
        self.prepare()
        # update.py regenerates this from the merged palette after compilation.
        self.assertEqual((self.stage/'waybar/updates.css').read_bytes(),path.read_bytes())

    def test_overlapping_code_edit_is_replaced_with_backup(self):
        (self.live/'code.py').write_text('my code\n'); (self.upstream/'code.py').write_text('new code\n')
        plan = self.prepare()
        self.assertEqual((self.live/'code.py').read_text(), 'my code\n')
        self.assertEqual(engine.installed(self.live)['revision'], OLD)
        backup = engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual((self.live/'code.py').read_text(), 'new code\n')
        self.assertEqual((backup/'files/code.py').read_text(), 'my code\n')

    def test_nonoverlapping_personal_configuration_edit_merges(self):
        original = ''.join(f'line {i}\n' for i in range(40))
        (self.live/'hyprland.conf').write_text(original)
        engine.write_json(self.live/engine.META, engine.metadata(self.live, OLD))
        (self.live/'hyprland.conf').write_text(original.replace('line 2\n','local monitor\n'))
        (self.upstream/'hyprland.conf').write_text(original.replace('line 35\n','new functionality\n'))
        plan = self.prepare(); engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertIn('local monitor', (self.live/'hyprland.conf').read_text())
        self.assertIn('new functionality', (self.live/'hyprland.conf').read_text())

    def test_edits_after_preparation_prevent_activation(self):
        (self.upstream/'code.py').write_text('new code\n'); plan = self.prepare()
        (self.live/'theme/state.json').write_text('{"theme":"my-new-theme"}')
        with self.assertRaisesRegex(RuntimeError, 'changed after'): engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual((self.live/'code.py').read_text(), 'old code\n')

    def test_integrity_failure_prevents_activation(self):
        (self.upstream/'code.py').write_text('new code\n'); plan = self.prepare()
        (self.stage/'code.py').write_text('damaged download\n')
        with self.assertRaisesRegex(RuntimeError, 'integrity'): engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual(engine.installed(self.live)['revision'], OLD)

    def test_symlinks_and_traversal_cannot_write_outside_profile(self):
        other = self.root/'other'; other.mkdir(); (other/'keep').write_text('unchanged')
        (self.live/'escape').symlink_to(other, target_is_directory=True)
        for relative in ('../other/keep', '/etc/passwd', 'escape/keep'):
            with self.assertRaises(ValueError): engine.location(self.live, relative)
        self.assertEqual((other/'keep').read_text(), 'unchanged')

    def test_disk_failure_rolls_back_all_written_files(self):
        (self.upstream/'code.py').write_text('new code\n'); plan = self.prepare(); actual = engine.atomic
        def failing(path, data, mode=0o600):
            if path == self.live/'code.py' and data == b'new code\n': raise OSError('disk failed')
            return actual(path, data, mode)
        with patch.object(engine, 'atomic', side_effect=failing):
            with self.assertRaisesRegex(OSError, 'disk failed'): engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertEqual(engine.installed(self.live)['revision'], OLD)
        self.assertFalse((self.state/'transaction.json').exists())

    def test_process_death_recovers_on_next_start(self):
        (self.upstream/'code.py').write_text('new code\n'); plan = self.prepare(); plan_path = self.root/'plan.json'; engine.write_json(plan_path, plan)
        script = '''import os,sys,json
from pathlib import Path
import update_engine as e
live,stage,state,plan=map(Path,sys.argv[1:]); actual=e.atomic
def abrupt(path,data,mode=0o600):
 actual(path,data,mode)
 if path==live/'code.py':os._exit(19)
e.atomic=abrupt
e.apply_plan(live,stage,json.loads(plan.read_text()),state)
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.live), str(self.stage), str(self.state), str(plan_path)],
                                env={**os.environ, 'PYTHONPATH': str(Path(engine.__file__).parent)})
        self.assertEqual(result.returncode, 19); self.assertTrue((self.state/'transaction.json').exists())
        engine.recover(self.live, self.state)
        self.assertEqual((self.live/'code.py').read_text(), 'old code\n'); self.assertEqual(engine.installed(self.live)['revision'], OLD)

    def test_rollback_restores_files_but_refuses_to_clobber_later_edits(self):
        (self.upstream/'code.py').write_text('new code\n'); (self.upstream/'new.py').write_text('new helper\n')
        plan = self.prepare(); backup = engine.apply_plan(self.live, self.stage, plan, self.state)
        rollback = engine.rollback_plan(self.live, backup)
        (self.live/'code.py').write_text('later personal edit\n')
        with self.assertRaises(RuntimeError): engine.check_plan(self.live, backup/'files', rollback)
        (self.live/'code.py').write_text('new code\n')
        engine.apply_plan(self.live, backup/'files', rollback, self.state)
        self.assertFalse((self.live/'new.py').exists()); self.assertEqual(engine.installed(self.live)['revision'], OLD)

    def test_completed_transaction_recovers_rollback_pointer(self):
        (self.upstream/'code.py').write_text('new code\n'); plan = self.prepare()
        backup = engine.apply_plan(self.live, self.stage, plan, self.state)
        (self.state/'last-backup.json').unlink()
        engine.write_json(self.state/'transaction.json', {'backup':str(backup)})
        engine.recover(self.live,self.state)
        self.assertEqual(engine.json_file(self.state/'last-backup.json')['backup'],str(backup))
        self.assertEqual(engine.installed(self.live)['revision'],NEW)

    def test_removed_application_file_is_retired_even_when_edited(self):
        (self.upstream/'code.py').unlink(); (self.live/'code.py').write_text('keep my version\n')
        plan = self.prepare(); backup = engine.apply_plan(self.live, self.stage, plan, self.state)
        self.assertFalse((self.live/'code.py').exists())
        self.assertEqual((backup/'files/code.py').read_text(), 'keep my version\n')

    def test_api_checks_new_commit_and_does_not_autodowngrade(self):
        for relation in ('ahead', 'behind', 'diverged'):
            responses = [([{'sha': NEW, 'commit': {'message':'Release'}}], 'etag'), ({'status':relation}, ''), (None, '')]
            with patch.object(github, 'request', side_effect=responses): result = service.check(self.live, self.state)
            self.assertEqual(result['phase'], 'available' if relation == 'ahead' else 'current')
            (self.state/'status.json').unlink()

    def test_conditional_api_check_and_rate_limit_keep_cached_release(self):
        previous = {'sha': NEW, 'base':OLD, 'etag':'same', 'relation':'ahead', 'message':'Release', 'release_version':''}
        with patch.object(github, 'request', return_value=(None, 'same')) as call:
            self.assertEqual(github.latest(OLD, previous)['sha'], NEW); self.assertEqual(call.call_count, 1)
        service.publish(self.state, phase='available', latest=NEW, github=previous)
        with patch.object(github, 'latest', side_effect=github.RetryLater('rate limited', time.time()+120)) as call:
            service.check(self.live, self.state); value = service.check(self.live, self.state)
            self.assertEqual(call.call_count, 1); self.assertEqual(value['latest'], NEW)

    def test_paused_auto_update_does_not_activate_and_requests_are_consumed_once(self):
        engine.write_json(self.state/'pending.json', {'automatic':True})
        engine.write_json(self.state/'settings.json', {'automatic':False})
        self.assertFalse(service.activate(self.live, self.state))
        service.request('check', self.state); self.assertEqual(service.take_request(self.state), 'check')
        self.assertIsNone(service.take_request(self.state))

    def test_explicit_restart_enables_pending_update_without_enabling_automatic_updates(self):
        from types import SimpleNamespace
        (self.upstream/'code.py').write_text('new code\n')
        plan = self.prepare(); staged = self.state/'prepared'; shutil.copytree(self.stage, staged)
        engine.write_json(staged/'plan.json', plan)
        engine.write_json(self.state/'pending.json', {'revision':NEW, 'stage':str(staged), 'automatic':True})
        engine.write_json(self.state/'settings.json', {'automatic':False})
        service.publish(self.state, phase='ready', current=OLD, latest=NEW, prepared=NEW)
        self.assertFalse(service.activate(self.live, self.state))
        service.prepare_restart(self.live, self.state)
        self.assertFalse(service.preferences(self.state)['automatic'])
        self.assertFalse(engine.json_file(self.state/'pending.json')['automatic'])
        compatibility = SimpleNamespace(candidate=lambda *args: staged/'hyprland.conf')
        with patch.dict(sys.modules, {'hypr_compat':compatibility}), \
             patch.object(service.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'config ok','')):
            self.assertTrue(service.activate(self.live, self.state))
        self.assertEqual((self.live/'code.py').read_text(), 'new code\n')

    def test_incomplete_update_never_becomes_restartable(self):
        pending = {'revision': NEW, 'stage': str(self.stage), 'automatic':True}
        engine.write_json(self.state/'pending.json', pending)
        for phase in ('available', 'checking', 'preparing', 'attention', 'runtime-required'):
            service.publish(self.state, phase=phase, current=OLD, latest=NEW)
            with self.subTest(phase=phase), self.assertRaisesRegex(RuntimeError, 'not ready'):
                service.prepare_restart(self.live, self.state)
        self.assertEqual(engine.json_file(self.state/'pending.json'), pending)

    def test_installed_update_requests_restart_only_in_its_original_session(self):
        service.publish(self.state, phase='current', current=OLD, latest=OLD,
                        restart_revision=OLD, restart_session='test-session')
        with patch.dict(os.environ, {'HYPRLAND_INSTANCE_SIGNATURE':'test-session'}):
            value = service.status(self.state, self.live)
            self.assertTrue(service.restart_ready(value))
            self.assertEqual(value['message'], service.READY_MESSAGE)
            self.assertEqual(service.badge(value)['text'], '↻ RESTART')
            service.prepare_restart(self.live, self.state)
            with patch.object(github, 'latest', return_value={'sha':OLD, 'relation':'identical', 'message':'Current'}):
                self.assertTrue(service.restart_ready(service.check(self.live, self.state)))
        with patch.dict(os.environ, {'HYPRLAND_INSTANCE_SIGNATURE':'next-login'}):
            value = service.status(self.state, self.live)
            self.assertFalse(service.restart_ready(value))
            self.assertEqual(service.badge(value)['text'], '')

    def test_manual_update_is_not_consumed_by_a_due_background_check(self):
        service.publish(self.state, phase='available', current=OLD, latest=NEW, github={'relation':'ahead'})
        service.request('prepare', self.state)
        with patch.object(service, 'STATE', self.state), patch.object(service, 'ROOT', self.live), \
             patch.dict(os.environ, {'HYPRLAND_INSTANCE_SIGNATURE':'test-session', 'XDG_RUNTIME_DIR':str(self.root)}), \
             patch.object(service.random, 'uniform', return_value=0), \
             patch.object(service.socket, 'socket') as socket_factory, \
             patch.object(service.select, 'select') as select_socket, \
             patch.object(service.subprocess, 'Popen') as popen, patch.object(service, 'stop_worker'):
            session = socket_factory.return_value.__enter__.return_value
            session.recv.return_value = b''
            select_socket.side_effect = [([], [], []), ([session], [], [])]
            service.serve()
        popen.assert_called_once()
        self.assertIn('--worker', popen.call_args.args[0])
        self.assertIn('--manual', popen.call_args.args[0])
        self.assertNotIn('--check', popen.call_args.args[0])

    def test_status_escapes_remote_markup(self):
        badge = service.badge({'phase':'available','message':'<b>not markup</b>'})
        self.assertEqual(badge['text'], '↻ UPDATE'); self.assertNotIn('<b>', badge['tooltip'])

    def test_cached_ancestry_for_another_install_cannot_show_an_update_badge(self):
        service.publish(self.state,phase='available',current=OLD,latest=NEW,
                        github={'sha':NEW,'base':'3'*40,'relation':'ahead'})
        value=service.status(self.state,self.live)
        self.assertEqual(service.badge(value)['text'],'')
        self.assertEqual(value['github']['relation'],'unknown')

    def test_public_api_missing_local_commit_keeps_development_build_unadvertised(self):
        from urllib.error import HTTPError
        responses=[([{'sha':NEW,'commit':{'message':'Published release'}}],'etag'),
                   HTTPError('https://example.invalid/compare',404,'Not Found',{},None), (None,'')]
        with patch.object(github,'request',side_effect=responses):
            result=service.check(self.live,self.state)
        self.assertEqual(result['github']['relation'],'unknown')
        self.assertEqual(service.badge(result)['text'],'')

    def test_runtime_mismatch_cannot_activate_prepared_desktop(self):
        (self.upstream/'runtime').mkdir()
        shutil.copyfile(service.ROOT/'runtime/manifest.json',self.upstream/'runtime/manifest.json')
        shutil.copyfile(service.ROOT/'runtime/fedora-44.json',self.upstream/'runtime/fedora-44.json')
        shutil.copyfile(service.ROOT/'runtime/debian-13.json',self.upstream/'runtime/debian-13.json')
        plan=self.prepare()
        staged=self.state/'prepared';shutil.copytree(self.stage,staged)
        engine.write_json(staged/'plan.json',plan)
        engine.write_json(self.state/'pending.json',{'revision':NEW,'stage':str(staged),'automatic':True})
        with patch.object(service.runtime_policy,'installed',return_value={'version':'0.57.0','commit':'a'*40}):
            self.assertFalse(service.activate(self.live,self.state))
        self.assertEqual(engine.installed(self.live)['revision'],OLD)
        self.assertEqual((self.live/'code.py').read_text(),'old code\n')
        self.assertEqual(service.status(self.state,self.live)['phase'],'runtime-required')
        self.assertEqual(engine.json_file(self.state/'runtime-required.json')['revision'],NEW)

    def test_current_source_with_wrong_system_compositor_offers_repair(self):
        (self.live/'runtime').mkdir()
        shutil.copyfile(service.ROOT/'runtime/manifest.json',self.live/'runtime/manifest.json')
        shutil.copyfile(service.ROOT/'runtime/fedora-44.json',self.live/'runtime/fedora-44.json')
        shutil.copyfile(service.ROOT/'runtime/debian-13.json',self.live/'runtime/debian-13.json')
        latest={'sha':OLD,'base':OLD,'relation':'identical','message':'Current desktop'}
        with patch.object(github,'latest',return_value=latest), \
             patch.object(service.runtime_policy,'installed',return_value={'version':'0.57.0','commit':'a'*40}):
            value=service.check(self.live,self.state)
        self.assertEqual(value['phase'],'runtime-required')
        self.assertEqual(service.status(self.state,self.live)['phase'],'runtime-required')
        self.assertEqual(service.badge(value)['text'],'↻ SETUP REQUIRED')

    def test_same_revision_setup_can_activate_components_rebuilt_for_correct_runtime(self):
        from types import SimpleNamespace
        (self.upstream/'runtime').mkdir()
        shutil.copyfile(service.ROOT/'runtime/manifest.json',self.upstream/'runtime/manifest.json')
        shutil.copyfile(service.ROOT/'runtime/fedora-44.json',self.upstream/'runtime/fedora-44.json')
        shutil.copyfile(service.ROOT/'runtime/debian-13.json',self.upstream/'runtime/debian-13.json')
        (self.upstream/'code.py').write_text('rebuilt for the matching compositor\n')
        expected=engine.merge_profile(self.live,self.upstream,self.stage,OLD)
        plan=engine.prepare_plan(self.live,self.stage,expected,OLD,automatic=False)
        staged=self.state/'prepared';shutil.copytree(self.stage,staged)
        engine.write_json(staged/'plan.json',plan)
        engine.write_json(self.state/'pending.json',{'revision':OLD,'stage':str(staged),
                                                   'automatic':False,'runtime_setup':True})
        compatibility=SimpleNamespace(candidate=lambda *args: staged/'hyprland.conf')
        with patch.dict(sys.modules,{'hypr_compat':compatibility}), \
             patch.object(service.runtime_policy,'problem',return_value=''), \
             patch.object(service.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'config ok','')):
            self.assertTrue(service.activate(self.live,self.state))
        self.assertEqual((self.live/'code.py').read_text(),'rebuilt for the matching compositor\n')
        self.assertEqual(engine.installed(self.live)['revision'],OLD)
        service.request('setup',self.state)
        self.assertEqual(service.take_request(self.state),'setup')

    def test_newer_release_supersedes_ready_status_without_claiming_it_was_built(self):
        pending='3'*40
        self.pending(pending)
        latest={'sha':NEW,'base':OLD,'relation':'ahead','message':'New release'}
        with patch.object(github,'latest',return_value=latest): value=service.check(self.live,self.state)
        self.assertEqual(value['phase'],'available');self.assertEqual(value['prepared'],pending)
        self.assertIn(pending[:8],service.badge(value)['tooltip'])
        self.assertEqual(engine.json_file(self.state/'pending.json')['revision'],pending)

    def test_already_installed_pending_release_never_shows_update_ready(self):
        self.pending(OLD)
        service.publish(self.state, phase='ready', current=NEW, latest=OLD, prepared=OLD,
                        github={'base':NEW,'relation':'ahead'})
        value = service.status(self.state, self.live)
        self.assertEqual(value['phase'], 'current')
        self.assertEqual(value['prepared'], '')
        self.assertEqual(service.badge(value)['text'], '')
        with patch.object(github, 'latest', return_value={'sha':OLD,'base':OLD,'relation':'identical','message':'Current'}):
            checked = service.check(self.live, self.state)
        self.assertEqual(checked['phase'], 'current')
        self.assertEqual(checked['prepared'], '')
        self.assertFalse(service.restart_ready(checked, engine.json_file(self.state/'pending.json')))

    def test_old_pending_release_is_not_ready_when_local_build_is_ahead(self):
        self.pending(NEW)
        latest = {'sha':NEW,'base':OLD,'relation':'behind','message':'Older release'}
        service.publish(self.state, phase='ready', current=OLD, latest=NEW, prepared=NEW, github=latest)
        self.assertEqual(service.status(self.state, self.live)['phase'], 'current')
        with patch.object(github, 'latest', return_value=latest): value = service.check(self.live, self.state)
        self.assertEqual(value['phase'], 'current')
        self.assertEqual(service.badge(value)['text'], '')

    def test_missing_or_invalid_prepared_package_remains_available_instead_of_ready(self):
        for damage in ('stage', 'plan', 'revision', 'json', 'outside'):
            with self.subTest(damage=damage):
                pending = self.pending(); stage = Path(pending['stage'])
                if damage == 'stage': shutil.rmtree(stage)
                elif damage == 'plan': (stage/'plan.json').unlink()
                elif damage == 'revision': engine.write_json(stage/'plan.json', {'revision':'3'*40})
                elif damage == 'json': (self.state/'pending.json').write_text('{broken')
                else:
                    outside = self.root/'outside'; outside.mkdir()
                    engine.write_json(outside/'plan.json', {'revision':NEW})
                    engine.write_json(self.state/'pending.json', {**pending, 'stage':str(outside)})
                latest = {'sha':NEW,'base':OLD,'relation':'ahead','message':'New release'}
                service.publish(self.state, phase='ready', current=OLD, latest=NEW, prepared=NEW, github=latest)
                value = service.status(self.state, self.live)
                self.assertEqual(value['phase'], 'available')
                self.assertEqual(value['prepared'], '')
                self.assertEqual(service.badge(value)['text'], '↻ UPDATE')
                with patch.object(github, 'latest', return_value=latest): checked = service.check(self.live, self.state)
                self.assertEqual(checked['phase'], 'available')

    def test_ready_requires_a_valid_package_but_preserves_same_revision_runtime_repair(self):
        for target, options in ((NEW, {}), (OLD, {'runtime_setup':True})):
            with self.subTest(target=target):
                pending = self.pending(target, **options)
                latest = {'sha':target,'base':OLD,'relation':'identical' if target == OLD else 'ahead','message':'Release'}
                service.publish(self.state, phase='ready', current=OLD, latest=target, prepared=target, github=latest)
                value = service.status(self.state, self.live)
                self.assertEqual(value['phase'], 'ready')
                self.assertTrue(service.restart_ready(value, pending))
                with patch.object(github, 'latest', return_value=latest): checked = service.check(self.live, self.state)
                self.assertEqual(checked['phase'], 'ready')
                self.assertEqual(service.badge(checked)['text'], '✓ UPDATE READY')

    def test_development_install_supersedes_cached_update_failure(self):
        service.publish(self.state, phase='attention', current=NEW, latest=OLD,
                        failed_revision=OLD, github={'relation':'ahead'}, message='Old failure')
        value=service.status(self.state,self.live)
        self.assertEqual(value['phase'],'current')
        self.assertEqual(value['failed_revision'],'')
        self.assertEqual(service.badge(value)['text'],'')
        with patch.object(github,'latest',return_value={'sha':OLD,'relation':'identical','message':'Current'}):
            value=service.check(self.live,self.state)
        self.assertEqual(value['phase'],'current')
        self.assertEqual(value['failed_revision'],'')

    def test_badge_is_hidden_until_an_update_exists(self):
        for value in ({}, {'phase':'current'}, {'phase':'checking'},
                      {'phase':'attention','message':'Network unavailable'},
                      {'phase':'current','current':NEW,'latest':OLD,'github':{'relation':'behind'}},
                      {'phase':'attention','current':NEW,'latest':NEW,'github':{'relation':'identical'}}):
            with self.subTest(value=value):
                self.assertEqual(service.badge(value)['text'], '')

    def test_status_keeps_active_check_and_handles_unregistered_profile(self):
        service.publish(self.state, phase='checking', current=OLD, latest=OLD,
                        message='Checking GitHub…')
        value=service.status(self.state,self.live)
        self.assertEqual(value['phase'],'checking')
        self.assertEqual(value['message'],'Checking GitHub…')
        service.publish(self.state, phase='preparing', message='Updating…')
        value=service.status(self.state,self.live)
        self.assertEqual(value['phase'],'preparing')
        self.assertEqual(value['message'],'Updating…')
        (self.live/engine.META).unlink()
        self.assertEqual(service.status(self.state,self.live),value)

    def test_badge_keeps_update_progress_and_actionable_failures_visible(self):
        for phase in ('available','preparing','ready','attention'):
            with self.subTest(phase=phase):
                value = {'phase':phase,'current':OLD,'latest':NEW,'github':{'relation':'ahead'}}
                self.assertTrue(service.badge(value)['text'])
        self.assertIn('ROLLBACK', service.badge({'phase':'rollback'})['text'])

    def test_bar_choice_hides_only_ready_and_restart_notices(self):
        options = self.live/'waybar/options.json'
        engine.write_json(options, {'version':1, 'position':'bottom', 'hidden':['cpu','custom/updates#ready']})
        service.publish(self.state, phase='ready', current=OLD, latest=NEW)
        engine.write_json(self.state/'settings.json', {'automatic':True, 'interval':900})
        before = {p:p.read_bytes() for p in (options,self.state/'status.json',self.state/'settings.json')}
        self.assertEqual(service.badge({'phase':'ready'},self.live)['text'],'')
        with patch.dict(os.environ, {'HYPRLAND_INSTANCE_SIGNATURE':'this-session'}):
            value = {'phase':'current', 'current':NEW, 'restart_revision':NEW, 'restart_session':'this-session'}
            self.assertEqual(service.badge(value,self.live)['text'],'')
            engine.write_json(options, {'version':1, 'hidden':['cpu']})
            self.assertEqual(service.badge(value,self.live)['text'],'↻ RESTART')
        engine.atomic(options,before[options])
        for phase in ('available','preparing','attention','runtime-required','rollback'):
            with self.subTest(phase=phase):
                value = {'phase':phase,'current':OLD,'latest':NEW,'github':{'relation':'ahead'}}
                self.assertTrue(service.badge(value,self.live)['text'])
        for path, data in before.items(): self.assertEqual(path.read_bytes(),data)
        engine.write_json(options, {'version':1, 'hidden':['cpu']})
        self.assertEqual(service.badge({'phase':'ready'},self.live)['text'],'✓ UPDATE READY')

    def test_missing_or_invalid_bar_choices_keep_ready_notice_visible(self):
        options = self.live/'waybar/options.json'
        self.assertEqual(service.badge({'phase':'ready'},self.live)['text'],'✓ UPDATE READY')
        options.parent.mkdir()
        for contents in ('{','null','[]','{"version":2,"hidden":["custom/updates#ready"]}',
                         '{"version":1,"hidden":"custom/updates#ready"}'):
            with self.subTest(contents=contents):
                options.write_text(contents)
                self.assertEqual(service.badge({'phase':'ready'},self.live)['text'],'✓ UPDATE READY')

    def test_download_checkout_is_exact_and_keeps_developer_clone_untouched(self):
        repository = self.root/'repo'; repository.mkdir()
        subprocess.run(['git','init','-q',str(repository)], check=True)
        (repository/'source.py').write_text('released\n')
        subprocess.run(['git','-C',str(repository),'add','.'], check=True)
        subprocess.run(['git','-C',str(repository),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','release'], check=True)
        commit = subprocess.check_output(['git','-C',str(repository),'rev-parse','HEAD'], text=True).strip()
        (repository/'source.py').write_text('uncommitted developer work\n')
        with patch.object(github, 'REPOSITORY', str(repository)):
            copied = github.source(commit, self.root/'cache', self.root/'download')
        self.assertEqual((copied/'source.py').read_text(), 'released\n')
        self.assertEqual(subprocess.check_output(['git','-C',str(copied),'rev-parse','HEAD'],text=True).strip(), commit)
        self.assertEqual((repository/'source.py').read_text(), 'uncommitted developer work\n')

    def test_preparation_failure_keeps_installer_reason_instead_of_raw_command(self):
        self.state.mkdir()
        with patch.object(service, 'STATE', self.state), patch.object(service.os, 'nice'), \
             patch.object(service.github, 'source', return_value=self.root/'source'), \
             patch.object(service.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run:
            self.assertEqual(service.worker(NEW, manual=True), 1)
        self.assertNotIn('check', run.call_args.kwargs)
        with patch.object(sys, 'argv', ['service.py', '--worker', NEW]), \
             patch.object(service, 'worker', return_value=1), patch.object(service, 'publish') as publish:
            self.assertEqual(service.main(), 1)
            publish.assert_not_called()


if __name__ == '__main__': unittest.main()
