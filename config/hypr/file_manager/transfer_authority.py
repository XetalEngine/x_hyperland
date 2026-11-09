#!/usr/bin/env python3
"""Job-scoped authenticated file access, reached only after EACCES/EPERM.

The GUI launches this helper through pkexec. Its private socket belongs to the
requesting account; it can only operate inside that job's immutable path scope.
Descriptors are passed back to the ordinary worker. EOF ends authorization.
"""
from __future__ import annotations
import array
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transfer_io import FileOps


def send(connection, value, fd=None):
    data = json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()
    control = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))]
    header = struct.pack('!Q', len(data))
    if connection.sendmsg([header], control) != len(header):
        raise ConnectionError('Incomplete transfer message.')
    connection.sendall(data)


def receive(connection):
    header, ancillary, flags, _ = connection.recvmsg(8, socket.CMSG_SPACE(array.array('i').itemsize),
                                                     socket.MSG_WAITALL | socket.MSG_CMSG_CLOEXEC)
    if not header: raise EOFError()
    fds = []
    for level, kind, raw in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            values = array.array('i'); values.frombytes(raw[:len(raw) - len(raw) % values.itemsize]); fds.extend(values)
    try:
        if len(header) != 8 or flags & socket.MSG_CTRUNC or len(fds) > 1:
            raise ConnectionError('Incomplete transfer message.')
        length = struct.unpack('!Q', header)[0]
        data = bytearray()
        while len(data) < length:
            piece = connection.recv(min(65536, length-len(data)))
            if not piece: raise EOFError()
            data.extend(piece)
        return json.loads(data), fds[0] if fds else None
    except BaseException:
        for fd in fds: os.close(fd)
        raise


def serve(connection, ops):
    while True:
        try: request, unwanted = receive(connection)
        except (EOFError, ConnectionError): return
        if unwanted is not None:
            os.close(unwanted)
            raise ValueError('Unexpected descriptor in a file-access request.')
        fd = None
        try:
            value, fd = ops.execute(request['action'], request['args'])
            send(connection, {'ok': True, 'value': value}, fd)
        except OSError as error:
            send(connection, {'ok': False, 'errno': error.errno, 'error': str(error)})
        except (ValueError, KeyError, TypeError) as error:
            send(connection, {'ok': False, 'error': str(error)})
        finally:
            if fd is not None: os.close(fd)


def main():
    if os.geteuid() != 0: raise PermissionError('Administrator authorization is required.')
    uid = int(os.environ.get('PKEXEC_UID', '0'))
    if uid <= 0: raise PermissionError('The requesting account could not be verified.')
    account = pwd.getpwuid(uid)
    request = json.load(sys.stdin)
    endpoint = request['socket']
    parent = os.lstat(os.path.dirname(endpoint))
    entry = os.lstat(endpoint)
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != uid or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != uid):
        raise PermissionError('The transfer channel is not private to the requesting account.')
    ops = FileOps(request['sources'], request['destination'], request.get('moving', False),
                  uid=uid, gid=account.pw_gid, undo=request.get('undo', False))
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(endpoint)
        _, peer_uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if peer_uid != uid: raise PermissionError('The transfer owner changed.')
        send(connection, {'token': request['token']})
        serve(connection, ops)


if __name__ == '__main__':
    try: main()
    except (EOFError, BrokenPipeError, ConnectionResetError): pass
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
