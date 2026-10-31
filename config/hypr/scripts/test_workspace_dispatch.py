import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import workspace

class DispatchTests(unittest.TestCase):
    def test_native_shortcuts_keep_action_and_monitor_resolution_in_compositor(self):
        run=Mock(return_value=SimpleNamespace(returncode=0,stdout='ok',stderr=''))
        workspace.dispatch('move','4',run)
        run.assert_called_once_with(['hyprctl','dispatch','xetalcube:workspace','move 4'],capture_output=True,text=True)
    def test_unsupported_adapter_preserves_global_workspace_ten(self):
        run=Mock(side_effect=[SimpleNamespace(returncode=1,stdout='Invalid dispatcher',stderr=''),SimpleNamespace(returncode=0,stdout='ok',stderr='')])
        workspace.dispatch('switch','10',run)
        self.assertEqual(run.call_args.args[0],['hyprctl','dispatch','workspace','10'])
    def test_failed_native_command_is_not_dispatched_twice(self):
        run=Mock(return_value=SimpleNamespace(returncode=1,stdout='Session has ended',stderr=''))
        with self.assertRaises(RuntimeError):workspace.dispatch('switch','1',run)
        self.assertEqual(run.call_count,1)
    def test_only_current_instance_can_lock_add_and_remove_buttons(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'XDG_RUNTIME_DIR':d,'HYPRLAND_INSTANCE_SIGNATURE':'our-test'}):
            path=Path(d)/'hypr/our-test/xetal-cube-faces';path.parent.mkdir(parents=True)
            path.write_text('enabled\n7 1\n');self.assertTrue(workspace.cube_enabled())
            path.write_text('disabled\n');self.assertFalse(workspace.cube_enabled())
            with patch.dict(os.environ,{'HYPRLAND_INSTANCE_SIGNATURE':'other-session'}):self.assertFalse(workspace.cube_enabled())

if __name__=='__main__':unittest.main()
