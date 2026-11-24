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
add_spec = importlib.util.spec_from_file_location('new_workspace', Path(__file__).with_name('new-workspace.py'))
add = importlib.util.module_from_spec(add_spec)
add_spec.loader.exec_module(add)
import workspace


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

    def test_hyprland_057_named_and_special_workspaces_have_no_numeric_id(self):
        workspaces,clients,monitors=snapshot()
        workspaces.insert(0,{'name':'special:xetal-startup','type':'special','monitor':'DP-1','windows':4})
        workspaces.append({'name':'Research','type':'named','monitor':'DP-1','windows':1})
        target,fallback=remove.removal_target(5,'DP-1',workspaces,clients,monitors)
        self.assertEqual(target['id'],5);self.assertEqual(fallback['id'],2)
        self.assertEqual(add.next_id(workspaces,''),1)
        with patch.object(workspace,'cube_faces',return_value={2,5,6,7}):
            self.assertEqual(workspace.monitor_faces(workspaces,'DP-1'),[2,5])

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

    def test_cube_minimum_rejects_removal_without_writing(self):
        store,_=self.transaction([snapshot()])
        with patch.object(workspace,'monitor_faces',return_value=[2,5,6,7]):
            with self.assertRaisesRegex(ValueError,'at least 4'):remove.remove(5,1,1)
        store.save.assert_not_called()

    def test_cube_removal_pins_remaining_sides_and_releases_runtime_owner(self):
        gone=snapshot(active=2);gone[0].pop(1)
        commands=[]
        def ctl(*args):commands.append(args);return 'ok'
        store,_=self.transaction([snapshot(),snapshot(),gone],ctl)
        with patch.object(workspace,'monitor_faces',return_value=[2,5,6,7,8]):
            self.assertEqual(remove.remove(5,1,1),5)
        content=store.save.call_args.args[0]
        for n in (2,6,7,8):self.assertIn(f'workspace = {n}, monitor:DP-1, persistent:true',content)
        self.assertIn('workspace = 5, persistent:false',content)
        self.assertEqual(commands,[('dispatch','xetalcube:reload')])

    def test_cube_rule_failure_rolls_back(self):
        store,before=self.transaction([snapshot(),snapshot()],lambda *args:'Cannot reload cube')
        with patch.object(workspace,'monitor_faces',return_value=[2,5,6,7,8]):
            with self.assertRaisesRegex(ValueError,'Cannot reload cube'):remove.remove(5,1,1)
        self.assertEqual(store.save.call_args.args,(before,'after'))

    def test_cube_addition_limit_and_saved_sides(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Mock(state=Path(temp));store.load.return_value=('# Workspaces\n','token');store.main.read_text.return_value=''
            state=[{'id':n,'monitor':'DP-1'} for n in range(1,5)]
            def ctl(*args):
                if args==('-j','workspaces'):return json.dumps(state)
                if args==('-j','workspacerules'):return '[]'
                return 'ok\nok'
            with patch.object(add.settings,'Store',return_value=store),patch.object(add,'monitor_at',return_value='DP-1'), \
                 patch.object(add.settings,'monitors',return_value=[]),patch.object(add.settings,'ctl',side_effect=ctl), \
                 patch.object(workspace,'monitor_faces',return_value=[1,2,3,4]) as faces:
                self.assertEqual(add.create(1,1),(5,'DP-1'))
                content=store.save.call_args.args[0]
                for n in range(1,6):self.assertIn(f'workspace = {n}, monitor:DP-1, persistent:true',content)
                store.save.reset_mock();faces.return_value=list(range(1,11))
                with self.assertRaisesRegex(ValueError,'up to 10'):add.create(1,1)
                store.save.assert_not_called()


if __name__ == '__main__':unittest.main()
