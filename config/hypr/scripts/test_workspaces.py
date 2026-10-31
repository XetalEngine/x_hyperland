"""Workspace removal guards and transaction rollback; no real session changes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('remove_workspace', Path(__file__).with_name('remove-workspace.py'))
remove = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remove)


def snapshot(occupied=False, active=5):
    return ([{'id':2,'name':'2','monitor':'DP-1','windows':1},
             {'id':5,'name':'5','monitor':'DP-1','windows':int(occupied),'ispersistent':True},
             {'id':3,'name':'3','monitor':'DP-2','windows':0}],
            [{'workspace':{'id':5}}] if occupied else [],
            [{'name':'DP-1','activeWorkspace':{'id':active}}])


class RemovalTests(unittest.TestCase):
    def setUp(self):
        environment=patch.dict('os.environ', {'HYPRLAND_INSTANCE_SIGNATURE':'test-no-live-session'})
        environment.start();self.addCleanup(environment.stop)

    def test_active_empty_chooses_same_display_and_inactive_never_switches(self):
        target, fallback = remove.removal_target(5,'DP-1',*snapshot())
        self.assertEqual(fallback['id'],2)
        target, fallback = remove.removal_target(5,'DP-1',*snapshot(active=2))
        self.assertIsNone(fallback)

    def test_occupied_hidden_clients_wrong_monitor_and_last_are_guarded(self):
        with self.assertRaisesRegex(ValueError,'open windows'):
            remove.removal_target(5,'DP-1',*snapshot(True))
        workspaces, clients, monitors = snapshot()
        clients.append({'workspace':{'id':5},'mapped':False})
        with self.assertRaisesRegex(ValueError,'open windows'):
            remove.removal_target(5,'DP-1',workspaces,clients,monitors)
        with self.assertRaisesRegex(ValueError,'changed'):
            remove.removal_target(5,'DP-2',*snapshot())
        with self.assertRaisesRegex(ValueError,'at least one'):
            remove.removal_target(5,'DP-1',workspaces[1:],[],monitors)
        with self.assertRaisesRegex(ValueError,'numbered'):
            remove.removal_target(-98,'DP-1',*snapshot())

    def test_remove_only_persistence_and_keep_comments_unrelated_rules(self):
        before = '# personal\nworkspace = 2, monitor:DP-1, persistent:true\nworkspace = 5, monitor:DP-1, persistent:true # my note\n'
        after = remove.removal_config(before,5)
        self.assertEqual(after,'# personal\nworkspace = 2, monitor:DP-1, persistent:true\n# my note\n')
        mixed = 'workspace = 5, monitor:DP-1, gapsout:20, persistent:true # keep\n'
        after = remove.removal_config(mixed,5)
        self.assertIn('monitor:DP-1, gapsout:20, persistent:false # keep',after)
        self.assertEqual(remove.removal_config('# untouched\n',5),'# untouched\nworkspace = 5, persistent:false\n')

    def transaction(self, states, ctl=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        store = Mock(state=Path(temporary.name))
        before = '# Workspaces\nworkspace = 5, monitor:DP-1, persistent:true\n'
        store.load.return_value=(before,'before')
        store.save.return_value='after'
        patches = [patch.object(remove.settings,'Store',return_value=store),
                   patch.object(remove,'monitor_at',return_value='DP-1'),
                   patch.object(remove,'snapshot',side_effect=states),
                   patch.object(remove.settings,'ctl',side_effect=ctl)]
        for p in patches:
            p.start();self.addCleanup(p.stop)
        return store,before

    def test_window_arriving_during_validation_is_rejected_before_save(self):
        store,_=self.transaction([snapshot(),snapshot(True)])
        with self.assertRaisesRegex(ValueError,'open windows'):remove.remove(5,1,1)
        store.check.assert_called_once();store.save.assert_not_called()

    def test_window_arriving_during_reload_restores_persistence(self):
        store,before=self.transaction([snapshot(),snapshot(),snapshot(True)])
        with self.assertRaisesRegex(ValueError,'open windows'):remove.remove(5,1,1)
        self.assertEqual(store.save.call_count,2)
        self.assertEqual(store.save.call_args.args,(before,'after'))

    def test_success_uses_existing_same_monitor_workspace_without_window_dispatch(self):
        ready=snapshot();ready[0][1]['ispersistent']=False
        commands=[]
        def ctl(*args):
            commands.append(args)
            return 'ok\nok' if args[0]=='--batch' else json.dumps([ready[0][0]])
        store,_=self.transaction([snapshot(),snapshot(),ready],ctl)
        self.assertEqual(remove.remove(5,1,1),5)
        self.assertEqual(commands[0],('--batch','dispatch focusmonitor DP-1; dispatch workspace 2'))
        store.save.assert_called_once()

    def test_inactive_workspace_disappearing_on_reload_does_not_change_focus(self):
        gone=snapshot(active=2);gone[0].pop(1)
        store,_=self.transaction([snapshot(active=2),snapshot(active=2),gone])
        self.assertEqual(remove.remove(5,1,1),5)
        remove.settings.ctl.assert_not_called()

    def test_switch_failure_restores_saved_configuration(self):
        ready=snapshot();ready[0][1]['ispersistent']=False
        store,before=self.transaction([snapshot(),snapshot(),ready],lambda *args:'error')
        with self.assertRaisesRegex(ValueError,'error'):remove.remove(5,1,1)
        self.assertEqual(store.save.call_args.args,(before,'after'))


if __name__ == '__main__':unittest.main()
