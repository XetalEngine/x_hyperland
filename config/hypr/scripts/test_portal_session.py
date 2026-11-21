import importlib.util
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('portal_session', Path(__file__).with_name('portal-session.py'))
portal = importlib.util.module_from_spec(spec); spec.loader.exec_module(portal)


class PortalSessionTests(unittest.TestCase):
    def setUp(self):
        self.environment = dict(XDG_RUNTIME_DIR='/run/user/1000', WAYLAND_DISPLAY='wayland-1',
            DISPLAY=':0', HYPRLAND_INSTANCE_SIGNATURE='current-session', XDG_CURRENT_DESKTOP='Hyprland')
        self.front = self.info(portal.FRONT)
        self.backend = self.info(portal.BACK, 2345)
        self.caps = {'version': 6, 'sources': 7}

    def info(self, name, pid=1234, **values):
        return dict(pid=pid, uid=os.getuid(), exe=portal.EXECUTABLES[name], started='100',
            environment={**self.environment, **values})

    def test_boot_tty_portal_and_matching_session_are_distinguished(self):
        before = self.info(portal.FRONT, **{k:'' for k in portal.ENV_KEYS if k!='XDG_RUNTIME_DIR'})
        self.assertEqual(portal.disposition(before, portal.FRONT, self.environment), 'unbound')
        self.assertEqual(portal.disposition(self.front, portal.FRONT, self.environment), 'current')

    def test_other_desktops_users_unknown_processes_and_live_sessions_are_preserved(self):
        other = [None, {**self.front, 'uid':os.getuid()+1}, {**self.front, 'exe':'unrelated'},
            self.info(portal.FRONT, XDG_CURRENT_DESKTOP='KDE'),
            self.info(portal.FRONT, WAYLAND_DISPLAY='wayland-2'),
            self.info(portal.FRONT, HYPRLAND_INSTANCE_SIGNATURE='another-session')]
        with patch.object(portal, 'compositor_alive', return_value=True):
            for value in other:
                self.assertEqual(portal.disposition(value, portal.FRONT, self.environment), 'external')

    def test_only_proven_dead_hyprland_session_can_be_repaired(self):
        info = self.info(portal.BACK, HYPRLAND_INSTANCE_SIGNATURE='old-session')
        with patch.object(portal, 'compositor_alive', return_value=False) as alive:
            self.assertEqual(portal.disposition(info, portal.BACK, self.environment), 'stale')
            alive.assert_called_once_with('/run/user/1000', 'old-session')
        self.assertTrue(portal.compositor_alive('/run/user/1000', '../invalid'))

    def test_process_identity_reads_current_process_without_exposing_other_environment(self):
        info = portal.process_info(os.getpid())
        self.assertEqual(info['pid'], os.getpid()); self.assertEqual(info['uid'], os.getuid())
        self.assertEqual(set(info['environment']), set(portal.ENV_KEYS))
        self.assertTrue(info['started'])

    def test_missing_bus_owner_does_not_activate_service(self):
        with patch.object(portal, 'run', return_value=Mock(returncode=1, stdout='', stderr='org.freedesktop.DBus.Error.NameHasNoOwner')) as run:
            self.assertIsNone(portal.owner_pid(portal.FRONT))
        self.assertIn('org.freedesktop.DBus.GetConnectionUnixProcessID', run.call_args.args[0])

    def test_capabilities_require_monitor_capture_and_uint32_properties(self):
        with patch.object(portal, 'run', return_value=Mock(returncode=0, stdout='(<uint32 7>,)\n')):
            self.assertEqual(portal.property_uint(portal.FRONT, 'interface', 'AvailableSourceTypes'), 7)
        with patch.object(portal, 'owner_pid', return_value=1234), patch.object(portal, 'property_uint', side_effect=[6,2]):
            self.assertIsNone(portal.capabilities(portal.FRONT))
        with patch.object(portal, 'owner_pid', return_value=None), patch.object(portal, 'property_uint') as query:
            self.assertIsNone(portal.capabilities(portal.FRONT)); query.assert_not_called()

    def test_activation_environment_is_checked_without_importing_variables(self):
        output='\n'.join(k+'='+v for k,v in self.environment.items())
        with patch.object(portal, 'run', return_value=Mock(returncode=0, stdout=output)) as run:
            self.assertTrue(portal.activation_ready(self.environment))
            self.assertFalse(portal.activation_ready({**self.environment, 'WAYLAND_DISPLAY':'wayland-2'}))
        for call in run.call_args_list:
            self.assertEqual(call.args[0], ['systemctl','--user','show-environment'])

    def test_healthy_portals_are_untouched(self):
        with patch.object(portal, 'inspect_owner', side_effect=[(self.front,'current'),(self.backend,'current')]), \
             patch.object(portal, 'capabilities', return_value=self.caps), patch.object(portal, 'start_service') as start:
            self.assertEqual(portal.ensure(self.environment)['changes'], [])
        start.assert_not_called()

    def test_foreign_portal_does_not_start_or_restart_any_service(self):
        with patch.object(portal, 'inspect_owner', side_effect=[(self.front,'external'),(None,'absent')]), \
             patch.object(portal, 'start_service') as start, patch.object(portal, 'activation_ready') as environment:
            self.assertEqual(portal.ensure(self.environment)['status'], 'external')
        start.assert_not_called(); environment.assert_not_called()

    def test_backend_is_ready_before_restarting_tty_frontend(self):
        calls=[]
        def start(name, previous, environment):
            calls.append(name);return {'unit':portal.UNITS[name]}
        def capabilities(name):
            self.assertIn(portal.BACK, calls)
            return self.caps
        with patch.object(portal, 'inspect_owner', side_effect=[(self.front,'unbound'),(None,'absent'),
                (self.backend,'current'),(self.front,'current')]), \
             patch.object(portal, 'activation_ready', return_value=True), \
             patch.object(portal, 'capabilities', side_effect=capabilities), patch.object(portal, 'start_service', side_effect=start):
            result=portal.ensure(self.environment)
        self.assertEqual(calls, [portal.BACK,portal.FRONT]); self.assertEqual(result['status'], 'ready')

    def test_changed_owner_or_service_process_is_never_restarted(self):
        with patch.object(portal, 'activation_ready', return_value=True), \
             patch.object(portal, 'owner_pid', return_value=9999), patch.object(portal, 'run') as run:
            with self.assertRaisesRegex(RuntimeError,'owner changed'):portal.start_service(portal.FRONT,self.front,self.environment)
        run.assert_not_called()
        with patch.object(portal, 'activation_ready', return_value=True), patch.object(portal, 'owner_pid', return_value=1234), \
             patch.object(portal, 'run', return_value=Mock(returncode=0,stdout='5678\n')) as run:
            with self.assertRaisesRegex(RuntimeError,'expected service'):portal.start_service(portal.FRONT,self.front,self.environment)
        self.assertEqual(run.call_count,1)

    def test_pid_reuse_is_rejected_before_restart(self):
        with patch.object(portal, 'activation_ready', return_value=True), patch.object(portal, 'owner_pid', return_value=1234), \
             patch.object(portal, 'process_info', return_value={**self.front,'started':'new-process'}), \
             patch.object(portal, 'run', return_value=Mock(returncode=0,stdout='1234\n')) as run:
            with self.assertRaisesRegex(RuntimeError,'process changed'):portal.start_service(portal.FRONT,self.front,self.environment)
        self.assertEqual(run.call_count,1)

    def test_restart_targets_only_the_verified_unit(self):
        with patch.object(portal, 'activation_ready', return_value=True), patch.object(portal, 'owner_pid', return_value=1234), \
             patch.object(portal, 'process_info', return_value=self.front), \
             patch.object(portal, 'run', side_effect=[Mock(returncode=0,stdout='1234\n'),Mock(returncode=0)]) as run:
            portal.start_service(portal.FRONT,self.front,self.environment)
        self.assertEqual(run.call_args.args[0], ['systemctl','--user','restart','xdg-desktop-portal.service'])

    def test_startup_check_precedes_apps_and_preserves_service_configuration(self):
        source=Path(__file__).with_name('session.sh').read_text()
        self.assertLess(source.index('file_manager/portal.py'),source.index('scripts/portal-session.py'))
        self.assertLess(source.index('scripts/portal-session.py'),source.index('control_panel/startup.py'))


if __name__ == '__main__':unittest.main()
