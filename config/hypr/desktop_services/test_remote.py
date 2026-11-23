import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import remote


class RemoteTests(unittest.TestCase):
    def test_status_distinguishes_listener_connections_and_unrelated_processes(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0)); server.listen()
            owned = dict(pid=os.getpid(), port=server.getsockname()[1])
            self.assertEqual(remote.listener_status(owned), dict(listening=True, connections=0))
            with socket.create_connection(server.getsockname()) as client:
                peer, _ = server.accept()
                with peer:
                    self.assertEqual(remote.listener_status(owned), dict(listening=True, connections=1))
            self.assertEqual(remote.listener_status(dict(owned, pid=999999999)), dict(listening=False, connections=0))
        self.assertEqual(remote.listener_status(owned), dict(listening=False, connections=0))

    def test_secrets_are_private_and_not_in_preferences(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'remote'
            remote.save(remote.DEFAULTS,'private-example-password',folder)
            self.assertNotIn('password',json.loads((folder/'settings.json').read_text()))
            self.assertEqual((folder/'password').stat().st_mode & 0o777,0o600)
            self.assertEqual(folder.stat().st_mode & 0o777,0o700)
            remote.save({**remote.DEFAULTS,'port':5991},directory=folder)
            self.assertEqual((folder/'password').read_text(),'private-example-password')

    def test_config_cannot_disable_authentication_or_inject_lines(self):
        for field,value in [('username','guest\nenable_auth=false'),('output','DP-1\n'),('address','0.0.0.0\n')]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                remote.normalize({**remote.DEFAULTS,field:value})
        with self.assertRaises(ValueError):remote.server_config(remote.DEFAULTS,'abc\nrelax_encryption=true',Path('/tmp/test'))
        config=remote.server_config(remote.DEFAULTS,'private-example-password',Path('/tmp/test'))
        self.assertIn('enable_auth=true\n',config)
        self.assertIn('relax_encryption=false\n',config)
        self.assertIn('allow_broken_crypto=false\n',config)

    def test_reused_pid_cannot_be_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            (folder/'process.json').write_text(json.dumps({'pid':os.getpid(),'start':'not-this-process'}))
            with patch.object(remote.os,'kill') as kill:
                remote.stop(folder)
                kill.assert_not_called()

    def test_opening_settings_does_not_enable_hosting(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings=remote.preferences(Path(temporary))
            self.assertFalse(settings['autostart']);self.assertFalse(settings['control'])
            self.assertEqual(settings['address'],'127.0.0.1')

    def test_disconnected_output_refuses_before_starting_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            remote.save({**remote.DEFAULTS,'output':'DP-404'},'private-example-password',folder)
            with patch.object(remote.shutil,'which',return_value='/usr/bin/wayvnc'),patch.object(remote,'monitors',return_value=[{'name':'eDP-1'}]),patch.object(remote.subprocess,'Popen') as launch:
                with self.assertRaisesRegex(RuntimeError,'disconnected'):remote.start(folder)
                launch.assert_not_called()
