"""Sign-in boundaries: framing, PAM conversations and desktop discovery."""
from pathlib import Path
import json
import struct
import tempfile
import unittest

from model import desktop_command, presentation, sessions, session_environment
from protocol import Decoder, Flow, encode


class ProtocolTests(unittest.TestCase):
    def test_fragmented_and_multiple_messages(self):
        decoder = Decoder()
        first, second = {'type': 'success'}, {'type': 'auth_message', 'auth_message': 'Password:'}
        wire = encode(first)+encode(second)
        result = []
        for byte in wire: result.extend(decoder.feed(bytes([byte])))
        self.assertEqual(result, [first, second])
        with self.assertRaises(ValueError): decoder.feed(struct.pack('=I', 2*1024*1024))

    def flow(self):
        sent, notices = [], []
        flow = Flow(sent.append, lambda *notice: notices.append(notice),
                    lambda: (['/greeter/launch.py', '--session', 'wayland:plasma.desktop'], ['XDG_CURRENT_DESKTOP=KDE']))
        return flow, sent, notices

    def test_desktop_starts_only_after_pam_success_and_start_acknowledgement(self):
        flow, sent, notices = self.flow()
        flow.select('alice')
        self.assertEqual(sent[-1], {'type': 'create_session', 'username': 'alice'})
        flow.receive({'type': 'auth_message', 'auth_message_type': 'secret', 'auth_message': 'Password:'})
        self.assertEqual(notices[-1], ('secret', 'Password:'))
        flow.answer('test-password')
        self.assertFalse(any(m['type'] == 'start_session' for m in sent))
        flow.receive({'type': 'success'})
        self.assertEqual(notices[-1][0], 'ready')
        flow.answer('')
        self.assertEqual(sent[-1]['type'], 'start_session')
        self.assertEqual(sent[-1]['env'], ['XDG_CURRENT_DESKTOP=KDE'])
        self.assertNotEqual(notices[-1][0], 'launched')
        flow.receive({'type': 'success'})
        self.assertEqual(notices[-1][0], 'launched')
        self.assertNotIn('test-password', repr(notices))

    def test_retry_cancels_failed_pam_and_account_switch_creates_new_identity(self):
        flow, sent, notices = self.flow()
        flow.select('alice'); flow.receive({'type': 'error', 'error_type': 'auth_error'})
        flow.select('bob')
        self.assertEqual(sent[-1]['type'], 'cancel_session')
        self.assertFalse(any(m.get('username') == 'bob' for m in sent))
        flow.receive({'type': 'success'})
        self.assertEqual(sent[-1], {'type': 'create_session', 'username': 'bob'})
        self.assertFalse(any(m['type'] == 'start_session' for m in sent))

    def test_visible_and_multiple_secret_prompts_and_information(self):
        flow, sent, notices = self.flow()
        flow.select('alice')
        flow.receive({'type': 'auth_message', 'auth_message_type': 'info', 'auth_message': 'Use your security token'})
        self.assertEqual(sent[-1], {'type': 'post_auth_message_response'})
        flow.receive({'type': 'auth_message', 'auth_message_type': 'visible', 'auth_message': 'Login name:'})
        self.assertEqual(notices[-1][0], 'visible')
        flow.answer('alice')
        flow.receive({'type': 'auth_message', 'auth_message_type': 'secret', 'auth_message': 'Verification code:'})
        self.assertEqual(notices[-1], ('secret', 'Verification code:'))
        flow.answer('123456')
        flow.receive({'type': 'error', 'error_type': 'auth_error'})
        self.assertEqual(notices[-1][0], 'error')
        self.assertFalse(any(m['type'] == 'start_session' for m in sent))


class DesktopTests(unittest.TestCase):
    def test_malformed_public_artwork_cannot_break_login_or_read_arbitrary_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = root/'12345'; folder.mkdir()
            (folder/'profile.json').write_text(json.dumps({'design': [], 'avatar': '../../private.png', 'wallpaper': None}))
            result = presentation({'username': 'fixture-nobody', 'uid': 12345}, root)
            self.assertEqual(result['design'], 'modern')
            self.assertIsNone(result['avatar']); self.assertIsNone(result['wallpaper'])

    def test_plasma_and_xfce_and_missing_or_hidden_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); wayland = root/'wayland'; x11 = root/'x11'
            wayland.mkdir(); x11.mkdir()
            (wayland/'plasma.desktop').write_text('[Desktop Entry]\nName=Plasma\nDesktopNames=KDE;\nExec=/usr/bin/startplasma-wayland\n')
            (x11/'xfce.desktop').write_text('[Desktop Entry]\nName=XFCE\nDesktopNames=XFCE\nExec=startxfce4\n')
            (x11/'hidden.desktop').write_text('[Desktop Entry]\nName=Hidden\nHidden=true\nExec=hidden\n')
            (wayland/'missing.desktop').write_text('[Desktop Entry]\nName=Missing\nTryExec=missing\nExec=program\n')
            values = sessions((('wayland', wayland), ('x11', x11)), which=lambda c: None if c == 'missing' else c)
            self.assertEqual({s.identifier for s in values}, {'wayland:plasma.desktop', 'x11:xfce.desktop'})
            plasma = next(s for s in values if s.kind == 'wayland')
            self.assertEqual(plasma.command, ('/usr/bin/startplasma-wayland',))
            self.assertIn('XDG_CURRENT_DESKTOP=KDE', session_environment(plasma))
            self.assertIn('XDG_SESSION_TYPE=x11', session_environment(next(s for s in values if s.kind == 'x11')))

    def test_desktop_exec_expands_field_codes_without_a_shell(self):
        self.assertEqual(desktop_command('program --title %c %F %%', 'My Desktop', Path('/session.desktop')),
                         ('program', '--title', 'My Desktop', '%'))
        self.assertEqual(desktop_command('program "$(touch /tmp/never-run)"', 'Name', Path('/session.desktop')),
                         ('program', '$(touch /tmp/never-run)'))
        with self.assertRaises(ValueError): desktop_command('program %Z', 'Name', Path('/session.desktop'))


if __name__ == '__main__': unittest.main()
