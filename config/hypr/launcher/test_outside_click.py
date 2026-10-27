import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtTest import QTest

from outside_click import check_pointer, outside_menu


class PointerGeometryTests(unittest.TestCase):
    def reply(self, cursor, **changes):
        menu = {'pid': 42, 'title': 'Xetal applications', 'mapped': True,
                'hidden': False, 'at': [4504, 52], 'size': [1140, 720]}
        menu.update(changes)
        # Hyprland batches return consecutive JSON documents, not one array.
        return (json.dumps(cursor) + '\n\n' + json.dumps([menu])).encode()

    def test_global_geometry_on_third_monitor(self):
        self.assertFalse(outside_menu(self.reply({'x': 4600, 'y': 80}), 42))
        self.assertTrue(outside_menu(self.reply({'x': 6000, 'y': 1000}), 42))
        self.assertTrue(outside_menu(self.reply({'x': 80, 'y': 80}), 42))

    def test_edges_and_negative_monitor_coordinates(self):
        self.assertFalse(outside_menu(self.reply({'x': 4504, 'y': 52}), 42))
        self.assertTrue(outside_menu(self.reply({'x': 5644, 'y': 52}), 42))
        self.assertTrue(outside_menu(self.reply({'x': 4504, 'y': 772}), 42))
        self.assertFalse(outside_menu(self.reply({'x': -1400, 'y': -100}, at=[-1500, -300]), 42))

    def test_missing_or_invalid_window_cannot_close_menu(self):
        self.assertIsNone(outside_menu(self.reply({'x': 0, 'y': 0}), 99))
        self.assertIsNone(outside_menu(self.reply({'x': 0, 'y': 0}, hidden=True), 42))
        self.assertIsNone(outside_menu(self.reply({'x': 0, 'y': 0}, mapped=False), 42))
        self.assertIsNone(outside_menu(self.reply({'x': 0, 'y': 0}, size=[0, 0]), 42))

    def test_bad_ipc_reply_is_ignored(self):
        for payload in (b'', b'ok', b'{}\n[]', b'{}\n{}', b'{}\n[{"pid":42}]', b'\xff'):
            with self.subTest(payload=payload):
                self.assertIsNone(outside_menu(payload, 42))


class PointerIpcTests(unittest.TestCase):
    def test_native_socket_reply_and_disconnect(self):
        qt = QCoreApplication.instance() or QCoreApplication([])
        with tempfile.TemporaryDirectory() as root:
            instance = Path(root) / 'hypr' / 'test'
            instance.mkdir(parents=True)
            server = QLocalServer()
            self.assertTrue(server.listen(str(instance / '.socket.sock')), server.errorString())
            peers, requests, answers = [], [], []

            def connected():
                peer = server.nextPendingConnection()
                peers.append(peer)

                def receive():
                    requests.append(bytes(peer.readAll()))
                    payload = PointerGeometryTests().reply({'x': 6000, 'y': 1000}, pid=os.getpid())
                    peer.write(payload)
                    peer.disconnectFromServer()

                peer.readyRead.connect(receive)

            server.newConnection.connect(connected)
            with patch.dict(os.environ, XDG_RUNTIME_DIR=root, HYPRLAND_INSTANCE_SIGNATURE='test'):
                check_pointer(qt, answers.append)
                for _ in range(100):
                    if answers:
                        break
                    QTest.qWait(10)
            self.assertEqual(requests, [b'[[BATCH]]j/cursorpos;j/clients'])
            self.assertEqual(answers, [True])
            server.close()
            for peer in peers:
                peer.deleteLater()
            qt.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
