"""Small synchronous CDP client for the disposable local browser only."""
import base64
import hashlib
import json
import os
import socket
import struct
from urllib.parse import urlparse


class Browser:
    def __init__(self, url):
        address=urlparse(url)
        if address.scheme!='ws' or address.hostname not in ('127.0.0.1','localhost'):
            raise ValueError('Only the disposable local debugging socket is allowed')
        self.socket=socket.create_connection((address.hostname,address.port),timeout=15)
        self.buffer=bytearray();self.sequence=0
        key=base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((f'GET {address.path} HTTP/1.1\r\nHost: {address.netloc}\r\n'
            f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n').encode())
        while b'\r\n\r\n' not in self.buffer:
            block=self.socket.recv(4096)
            if not block:raise EOFError('Browser debugging handshake closed')
            self.buffer.extend(block)
        header,_,self.buffer=self.buffer.partition(b'\r\n\r\n')
        expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if not header.startswith(b'HTTP/1.1 101') or expected not in header:raise RuntimeError('Browser debugging handshake failed')

    def read(self, count):
        while len(self.buffer)<count:
            block=self.socket.recv(max(4096,count-len(self.buffer)))
            if not block:raise EOFError('Browser debugging socket closed')
            self.buffer.extend(block)
        result=bytes(self.buffer[:count]);del self.buffer[:count];return result

    def send(self, payload, opcode=1):
        mask=os.urandom(4);size=len(payload)
        header=bytes([0x80|opcode,0x80|(size if size<126 else 126 if size<65536 else 127)])
        if size>=126:header+=struct.pack('!H' if size<65536 else '!Q',size)
        self.socket.sendall(header+mask+bytes(value^mask[i%4] for i,value in enumerate(payload)))

    def receive(self):
        message=bytearray()
        while True:
            first,second=self.read(2);size=second&127
            if size>=126:size=struct.unpack('!H' if size==126 else '!Q',self.read(2 if size==126 else 8))[0]
            if size>4_000_000:raise ValueError('Unexpected debugging frame size')
            mask=self.read(4) if second&128 else None
            payload=self.read(size)
            if mask:payload=bytes(value^mask[i%4] for i,value in enumerate(payload))
            opcode=first&15
            if opcode==8:raise EOFError('Browser closed its debugger')
            if opcode==9:self.send(payload,10);continue
            if opcode not in (0,1):continue
            message.extend(payload)
            if first&128:return json.loads(message)

    def call(self, method, **params):
        self.sequence+=1
        self.send(json.dumps({'id':self.sequence,'method':method,'params':params}).encode())
        while True:
            reply=self.receive()
            if reply.get('id')!=self.sequence:continue
            if 'error' in reply:raise RuntimeError(str(reply['error']))
            return reply.get('result',{})

    def close(self):self.socket.close()
