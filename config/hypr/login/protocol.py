"""greetd framing and authentication state; secrets never enter logs or files.

Protocol: https://man.archlinux.org/man/greetd-ipc.7.en
"""
import json
import struct


def encode(message):
    body = json.dumps(message, ensure_ascii=False).encode('utf-8')
    return struct.pack('=I', len(body)) + body


class Decoder:
    def __init__(self): self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while len(self.buffer) >= 4:
            size, = struct.unpack('=I', self.buffer[:4])
            if size > 1024*1024: raise ValueError('Invalid greetd message length')
            if len(self.buffer) < size+4: break
            message = json.loads(self.buffer[4:size+4])
            if not isinstance(message, dict): raise ValueError('Invalid greetd message')
            del self.buffer[:size+4]
            messages.append(message)
        return messages


class Flow:
    """One request at a time, including cancellation and arbitrary PAM prompts."""
    def __init__(self, send, notify, command):
        self.send, self.notify, self.command = send, notify, command
        self.pending = None
        self.username = None
        self.active = False
        self.ready = False
        self.starting = False

    def request(self, kind, **fields):
        if self.pending: raise RuntimeError('Authentication request already pending')
        self.pending = kind
        self.send({'type': kind, **fields})

    def select(self, username):
        if self.pending or self.starting: return
        self.username, self.ready = username, False
        self.notify('busy', '')
        if self.active: self.request('cancel_session')
        else:
            self.active = True
            self.request('create_session', username=username)

    def answer(self, response):
        if self.pending or self.starting: return
        if self.ready:
            command, environment = self.command()
            self.starting = True
            self.notify('starting', '')
            self.request('start_session', cmd=command, env=environment)
        else:
            self.notify('busy', '')
            self.request('post_auth_message_response', response=response)

    def receive(self, message):
        pending, self.pending = self.pending, None
        kind = message.get('type')
        if pending == 'cancel_session' and kind in ('success', 'error'):
            # greetd 0.10 clears its configuring slot before contacting the PAM
            # worker. An exited worker can make cleanup report an error; still
            # request a fresh conversation, which must authenticate again.
            self.active = True
            self.request('create_session', username=self.username)
            return
        if kind == 'error':
            self.starting = self.ready = False
            # Keep cleanup pending: some greetd versions retain a failed slot.
            self.notify('error', ('Sign-in failed. Please try again.' if message.get('error_type') == 'auth_error'
                                  else str(message.get('description', 'Sign-in is unavailable.'))[:240]))
            return
        if kind == 'auth_message':
            prompt = str(message.get('auth_message', ''))[:240]
            style = message.get('auth_message_type')
            if style in ('info', 'error'):
                self.notify('message', prompt)
                self.request('post_auth_message_response')
            elif style in ('secret', 'visible'):
                self.notify(style, prompt)
            else:
                self.notify('fatal', 'The sign-in service sent an unsupported question.')
        elif kind == 'success' and pending == 'start_session':
            self.notify('launched', '')
        elif kind == 'success' and pending in ('create_session', 'post_auth_message_response'):
            self.ready = True
            self.notify('ready', '')
        else:
            self.notify('fatal', 'The sign-in service sent an unexpected response.')
