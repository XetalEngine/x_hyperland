#!/usr/bin/env python3
"""Check native FileManager1 routing on a private D-Bus session."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from gi.repository import Gio, GLib


def check(binary):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    name = 'org.freedesktop.FileManager1'
    def dbus(method, signature, arguments, reply):
        return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', method, GLib.Variant(signature, arguments),
            GLib.VariantType.new(reply), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
    def owns_name():
        return dbus('NameHasOwner', '(s)', (name,), '(b)')
    def owner_pid():
        return dbus('GetConnectionUnixProcessID', '(s)', (name,), '(u)') if owns_name() else None
    def wait_for(predicate, description):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.025)
        raise RuntimeError(description)
    if owns_name():
        raise RuntimeError('Run this check on a fresh private D-Bus session.')
    with tempfile.TemporaryDirectory(prefix='fusion-folder-routing-') as directory:
        root = Path(directory)
        (root/'scripts').mkdir()
        (root/'choice').write_text('Fusion Files')
        handler = root/'scripts/file-manager.sh'
        handler.write_text('''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with (root/'calls.jsonl').open('a') as log:
    log.write(json.dumps(dict(choice=(root/'choice').read_text(),arguments=sys.argv[1:],
        token=os.environ.get('XDG_ACTIVATION_TOKEN',''),startup=os.environ.get('DESKTOP_STARTUP_ID','')))+'\\n')
''')
        handler.chmod(0o700)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
                   XETAL_FILES_ROOT=str(root), HYPRLAND_INSTANCE_SIGNATURE='fixture',
                   XDG_ACTIVATION_TOKEN='stale-token', DESKTOP_STARTUP_ID='stale-startup')
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','XDG_RUNTIME_DIR'):
            path = root/key.lower(); path.mkdir(mode=0o700); env[key] = str(path)
        instance = Path(env['XDG_RUNTIME_DIR'])/'hypr/fixture'
        instance.mkdir(parents=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(instance/'.socket2.sock'))
        listener.listen(8); listener.settimeout(5)
        processes, connections = [], []
        def start():
            process = subprocess.Popen([str(binary), '--service'], env=env)
            processes.append(process)
            connection, _ = listener.accept(); connections.append(connection)
            return process, connection
        def logout(process, connection):
            connection.shutdown(socket.SHUT_RDWR); connection.close()
            assert process.wait(timeout=5) == 0
        process, connection = start()
        try:
            wait_for(lambda: owner_pid()==process.pid, 'The native folder service did not start.')
            uri = (root/'screen # 100% $(literal).png').as_uri()
            def invoke(method, urls, token=''):
                bus.call_sync(name, '/org/freedesktop/FileManager1',
                    name, method, GLib.Variant('(ass)', (urls, token)),
                    None, Gio.DBusCallFlags.NONE, 3000, None)
            def calls(count):
                deadline = time.monotonic()+5
                while time.monotonic()<deadline:
                    try:
                        rows = [json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
                    except (FileNotFoundError, ValueError):
                        rows = []
                    if len(rows)==count:
                        return rows
                    time.sleep(.025)
                raise RuntimeError('Folder request did not reach the selected handler.')
            invoke('ShowItems', [uri, 'relative-path-is-not-a-uri'], 'request-token')
            assert calls(1)==[dict(choice='Fusion Files',arguments=['--select',uri],
                                   token='request-token',startup='request-token')]
            (root/'choice').write_text('Another file manager')
            invoke('ShowFolders', [root.as_uri(), 'smb://server/share/folder%20name'])
            assert calls(2)[-1]==dict(choice='Another file manager',
                arguments=[root.as_uri(),'smb://server/share/folder%20name'], token='', startup='')
            duplicate, duplicate_connection = start()
            assert duplicate.wait(timeout=5)==0
            assert owner_pid()==process.pid
            duplicate_connection.close()
            logout(process, connection)
            wait_for(lambda: not owns_name(), 'Logout did not release the folder service.')

            # Do not steal an existing manager's protected name or open a window
            # because registration failed. Queue, then take over when it exits.
            assert dbus('RequestName', '(su)', (name, 4), '(u)')==1
            process, connection = start()
            wait_for(lambda: len(dbus('ListQueuedOwners', '(s)', (name,), '(as)'))==2,
                     'The resident service did not wait for the existing owner.')
            assert owner_pid()==os.getpid() and process.poll() is None
            dbus('ReleaseName', '(s)', (name,), '(u)')
            wait_for(lambda: owner_pid()==process.pid, 'The queued service did not acquire the name.')
            invoke('ShowItems', [uri])
            assert calls(3)[-1]['arguments']==['--select',uri]
            logout(process, connection)
            wait_for(lambda: not owns_name(), 'The queued service survived logout.')

            # Ordinary Fusion windows allow the resident service to replace
            # their temporary registration without closing any windows.
            assert dbus('RequestName', '(su)', (name, 1 | 4), '(u)')==1
            process, connection = start()
            wait_for(lambda: owner_pid()==process.pid, 'The temporary registration was not replaced.')
            dbus('ReleaseName', '(s)', (name,), '(u)')
            logout(process, connection)
            wait_for(lambda: not owns_name(), 'The replacement service survived logout.')
            outside = dict(env); outside.pop('HYPRLAND_INSTANCE_SIGNATURE')
            assert subprocess.run([str(binary), '--service'], env=outside, timeout=5).returncode==1
            assert not owns_name()
            print('PASS: selection, literal URIs, live default changes, activation tokens, single-instance service, ownership conflicts, replacement and logout.')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
            for connection in connections: connection.close()
            listener.close()


if __name__ == '__main__':
    check(Path(sys.argv[1]).resolve())
