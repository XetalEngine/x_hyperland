import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('notification_session', Path(__file__).with_name('notification-session.py'))
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class NotificationOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.environment = {'HYPRLAND_INSTANCE_SIGNATURE': 'our-login',
                            'WAYLAND_DISPLAY': 'wayland-1', 'XDG_RUNTIME_DIR': '/run/user/1000'}
        self.info = {'pid': 4321, 'uid': os.getuid(), 'command': ['/usr/bin/swaync'],
                     'environment': dict(self.environment), 'started': '12345'}

    def test_only_same_user_swaync_on_same_hyprland_instance_can_be_replaced(self):
        self.assertTrue(session.same_session(self.info, self.environment))
        for change in ({'uid': os.getuid()+1}, {'command': ['plasmashell']},
                       {'environment': {}}, *({'environment': {**self.environment, key: 'other'}}
                         for key in self.environment)):
            with self.subTest(change=change):
                self.assertFalse(session.same_session({**self.info, **change}, self.environment))

    def test_both_config_and_style_must_match_the_fusion_profile(self):
        root = Path('/profile')
        self.assertFalse(session.uses_profile(self.info, root))
        for args in (['-c', '/profile/swaync/config.json', '-s', '/profile/swaync/style.css'],
                     ['--config=/profile/swaync/config.json', '--style=/profile/swaync/style.css']):
            self.assertTrue(session.uses_profile({**self.info, 'command': ['swaync', *args]}, root))
        self.assertFalse(session.uses_profile({**self.info, 'command': ['swaync', '-c', '/profile/swaync/config.json']}, root))

    def test_bus_owner_query_does_not_activate_notification_service(self):
        with patch.object(session.subprocess, 'run', return_value=Mock(returncode=0, stdout='(uint32 4321,)\n', stderr='')) as run:
            self.assertEqual(session.owner_pid(), 4321)
        self.assertIn('org.freedesktop.DBus.GetConnectionUnixProcessID', run.call_args.args[0])
        with patch.object(session.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='org.freedesktop.DBus.Error.NameHasNoOwner')):
            self.assertIsNone(session.owner_pid())
        with patch.object(session.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='Bus disconnected')):
            with self.assertRaises(RuntimeError): session.owner_pid()

    def test_stops_only_the_matching_activation_without_changing_unit_configuration(self):
        activation = Mock()
        with patch.object(session, 'process_info', return_value=self.info), \
             patch.object(session.subprocess, 'run', side_effect=[Mock(returncode=0, stdout='4321\n'), Mock(returncode=0)]) as run, \
             patch.object(session.os, 'pidfd_open') as kill:
            session.retire_default(self.info, self.environment, activation)
        self.assertEqual(run.call_args_list[1].args[0], ['systemctl', '--user', 'stop', 'swaync.service'])
        activation.acquire.assert_called_once_with()
        kill.assert_not_called()

    def test_changed_or_foreign_process_is_never_stopped(self):
        with patch.object(session, 'process_info', return_value={**self.info, 'started': 'new-process'}), \
             patch.object(session.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError): session.retire_default(self.info, self.environment)
        run.assert_not_called()

    def test_failed_service_stop_does_not_kill_and_trigger_its_restart_policy(self):
        with patch.object(session, 'process_info', return_value=self.info), \
             patch.object(session.subprocess, 'run', side_effect=[Mock(returncode=0, stdout='4321\n'),
                  subprocess.CalledProcessError(1, ['systemctl'])]), patch.object(session.os, 'pidfd_open') as kill:
            with self.assertRaises(subprocess.CalledProcessError): session.retire_default(self.info, self.environment)
        kill.assert_not_called()


class ActivationPauseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-activation-test-')
        self.addCleanup(temporary.cleanup)
        self.pause = session.ActivationPause(temporary.name)
        self.pause.path.parent.mkdir(parents=True)

    def test_runtime_block_is_removed_after_handover(self):
        with patch.object(session.subprocess, 'run') as run:
            self.pause.acquire()
            self.assertEqual(self.pause.path.readlink(), Path('/dev/null'))
            self.pause.release()
        self.assertFalse(self.pause.path.is_symlink())
        self.assertEqual(run.call_count, 2)

    def test_existing_mask_is_preserved(self):
        self.pause.path.symlink_to('/dev/null')
        with patch.object(session.subprocess, 'run') as run:
            self.pause.acquire(); self.pause.release()
        self.assertEqual(self.pause.path.readlink(), Path('/dev/null'))
        run.assert_not_called()

    def test_existing_override_is_never_replaced(self):
        self.pause.path.write_text('user override')
        with patch.object(session.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError): self.pause.acquire()
            self.pause.release()
        self.assertEqual(self.pause.path.read_text(), 'user override')
        run.assert_not_called()

    def test_failed_reload_can_still_restore_the_runtime_unit(self):
        with patch.object(session.subprocess, 'run', side_effect=[subprocess.CalledProcessError(1, ['systemctl']), Mock()]) as run:
            with self.assertRaises(subprocess.CalledProcessError): self.pause.acquire()
            self.pause.release()
        self.assertFalse(self.pause.path.is_symlink())
        self.assertEqual(run.call_count, 2)


class NotificationSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-notifications-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(self.root/'.socket2.sock')); self.server.listen(); self.server.settimeout(3)
        self.addCleanup(self.server.close)

    def test_other_desktop_is_preserved_without_starting_a_competing_daemon(self):
        with patch.object(session, 'owner_pid', return_value=99), \
             patch.object(session, 'process_info', return_value=None), \
             patch.object(session.subprocess, 'Popen') as launch:
            self.assertEqual(session.serve(self.root, self.root, {}), 0)
        launch.assert_not_called()
        self.assertEqual(json.loads((self.root/'notifications-ready.json').read_text())['status'], 'external')

    def test_live_child_is_ready_only_after_both_names_and_stops_when_compositor_closes(self):
        processes = []
        original = subprocess.Popen
        commands = []
        queried = []
        def launch(command, **kwargs):
            commands.append(command)
            process = original([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
            processes.append(process)
            self.addCleanup(session.stop, process)
            return process
        def owner(name=session.NOTIFICATIONS):
            queried.append(name)
            return processes[-1].pid if processes else None
        def compositor():
            connection, _ = self.server.accept()
            try:
                deadline = time.monotonic()+3
                while time.monotonic() < deadline:
                    try:
                        if json.loads((self.root/'notifications-ready.json').read_text())['status'] == 'ready':
                            break
                    except (OSError, ValueError): pass
                    time.sleep(.01)
            finally: connection.close()
        peer = threading.Thread(target=compositor)
        peer.start()
        with patch.object(session, 'owner_pid', side_effect=owner), patch.object(session.subprocess, 'Popen', side_effect=launch):
            self.assertEqual(session.serve(self.root, self.root, dict(os.environ)), 0)
        peer.join(4)
        self.assertFalse(peer.is_alive())
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())
        self.assertIn(session.CONTROL, queried)
        self.assertEqual(commands[0], ['swaync', '--config', str(self.root/'swaync/config.json'), '--style', str(self.root/'swaync/style.css')])
        self.assertEqual(json.loads((self.root/'notifications-ready.json').read_text())['status'], 'ready')

    def test_session_waits_for_notifications_before_any_bar_or_startup_clients(self):
        source = Path(__file__).with_name('session.sh').read_text()
        ready = source.index('notification-session.py" --wait-ready')
        for client in ('effects/burn/controller.py', 'updates/service.py" --serve',
                       'control_panel/startup.py', 'waybar-session.py'):
            self.assertLess(ready, source.index(client), client)


if __name__ == '__main__':
    unittest.main()
