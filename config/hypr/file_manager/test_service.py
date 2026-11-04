#!/usr/bin/env python3
"""Check native FileManager1 routing on a private D-Bus session."""
import json
import hashlib
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
        deadline = time.monotonic()+8
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.025)
        raise RuntimeError(description)
    if owns_name():
        raise RuntimeError('Run this check on a fresh private D-Bus session.')
    with tempfile.TemporaryDirectory(prefix='fusion-folder-routing-') as directory:
        root = Path(directory)
        (root/'scripts').mkdir()
        (root/'file_manager').mkdir()
        (root/'commands').mkdir()
        (root/'file_manager/automount.json').write_text(json.dumps(dict(version=1, volumes={
            'fixture-usb': dict(filesystem='ext4', enabled=True, revision=1)})))
        def inventory(sequence):
            (root/'inventory.json').write_text(json.dumps(dict(blockdevices=[dict(
                path='/dev/fixture', type='disk', tran='usb', **{'disk-seq': sequence},
                children=[dict(path='/dev/fixture1', type='part', fstype='ext4', uuid='fixture-usb')])]
                if sequence else [])))
        inventory(1)
        for command_name, script in {
            'lsblk': "print((root/'inventory.json').read_text())\n",
            'udisksctl': "with (root/'mounts.jsonl').open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\n",
        }.items():
            command = root/'commands'/command_name
            command.write_text('#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\n'
                               'root=Path(__file__).resolve().parents[1]\n' + script)
            command.chmod(0o700)
        def mounts():
            try:
                return [json.loads(line) for line in (root/'mounts.jsonl').read_text().splitlines()]
            except (FileNotFoundError, ValueError):
                return []
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
        files_handler = root/'scripts/files.sh'
        files_handler.write_text(handler.read_text().replace("'calls.jsonl'", "'desktop-calls.jsonl'"))
        files_handler.chmod(0o700)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
                   XETAL_FILES_ROOT=str(root), HYPRLAND_INSTANCE_SIGNATURE='fixture',
                   PATH=str(root/'commands')+os.pathsep+os.environ['PATH'],
                   XDG_ACTIVATION_TOKEN='stale-token', DESKTOP_STARTUP_ID='stale-startup')
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','XDG_RUNTIME_DIR'):
            path = root/key.lower(); path.mkdir(mode=0o700); env[key] = str(path)
        instance = Path(env['XDG_RUNTIME_DIR'])/'hypr/fixture'
        instance.mkdir(parents=True)
        control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        control.bind(str(instance/'.socket.sock'))
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
            wait_for(lambda: len(mounts())==1, 'Auto mount did not run with all Files windows closed.')
            assert mounts()[0]==['mount', '-b', '/dev/disk/by-uuid/fixture-usb']
            desktop_name = 'org.xetal.FusionFiles.Desktop.s'+hashlib.sha256(b'fixture').hexdigest()[:24]
            def desktop(method, signature, arguments):
                return bus.call_sync(desktop_name, '/org/xetal/FusionFiles/Desktop',
                    'org.xetal.FusionFiles.Desktop1', method, GLib.Variant(signature, arguments),
                    GLib.VariantType.new('(b)'), Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            source = root/'Desktop'; source.mkdir()
            target = root/'Target'; target.mkdir()
            filename = 'notes # 100% café.txt'
            (source/filename).write_text('desktop transfer fixture')
            assert desktop('Transfer', '(assb)', ([(source/filename).as_uri()], target.as_uri(), True))
            wait_for(lambda: (target/filename).exists(), 'Desktop copy did not reach the Files transfer engine.')
            assert (source/filename).read_text() == (target/filename).read_text()
            moved = root/'Moved'; moved.mkdir()
            assert desktop('Transfer', '(assb)', ([(target/filename).as_uri()], moved.as_uri(), False))
            wait_for(lambda: (moved/filename).exists() and not (target/filename).exists(), 'Desktop move did not complete.')
            assert not desktop('Transfer', '(assb)', (['not-a-uri'], target.as_uri(), False))
            assert desktop('Open', '(asb)', ([source.as_uri()], False))
            wait_for(lambda: (root/'desktop-calls.jsonl').exists(), 'Desktop folder did not launch Fusion Files.')
            opened = json.loads((root/'desktop-calls.jsonl').read_text().splitlines()[0])
            assert opened['arguments'] == ['--external', '--new-window', source.as_uri()]
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
            assert calls(1)==[dict(choice='Fusion Files',arguments=['--external','--select',uri],
                                   token='request-token',startup='request-token')]
            (root/'choice').write_text('Another file manager')
            invoke('ShowFolders', [root.as_uri(), 'smb://server/share/folder%20name'])
            assert calls(2)[-1]==dict(choice='Another file manager',
                arguments=['--external',root.as_uri(),'smb://server/share/folder%20name'], token='', startup='')
            duplicate, duplicate_connection = start()
            assert duplicate.wait(timeout=5)==0
            assert owner_pid()==process.pid
            duplicate_connection.close()
            logout(process, connection)
            wait_for(lambda: not owns_name(), 'Logout did not release the folder service.')
            assert not dbus('NameHasOwner', '(s)', (desktop_name,), '(b)')

            # Do not steal an existing manager's protected name or open a window
            # because registration failed. Queue, then take over when it exits.
            assert dbus('RequestName', '(su)', (name, 4), '(u)')==1
            process, connection = start()
            wait_for(lambda: len(dbus('ListQueuedOwners', '(s)', (name,), '(as)'))==2,
                     'The resident service did not wait for the existing owner.')
            assert owner_pid()==os.getpid() and process.poll() is None
            dbus('ReleaseName', '(s)', (name,), '(u)')
            wait_for(lambda: owner_pid()==process.pid, 'The queued service did not acquire the name.')
            assert len(mounts())==1, 'Restarting the router must not repeat a mount attempt.'
            invoke('ShowItems', [uri])
            assert calls(3)[-1]['arguments']==['--external','--select',uri]
            logout(process, connection)
            wait_for(lambda: not owns_name(), 'The queued service survived logout.')

            # Ordinary Fusion windows allow the resident service to replace
            # their temporary registration without closing any windows.
            assert dbus('RequestName', '(su)', (name, 1 | 4), '(u)')==1
            process, connection = start()
            wait_for(lambda: owner_pid()==process.pid, 'The temporary registration was not replaced.')
            dbus('ReleaseName', '(s)', (name,), '(u)')
            inventory(2)
            wait_for(lambda: len(mounts())==2, 'A USB reconnect did not mount in the background.')
            logout(process, connection)
            wait_for(lambda: not owns_name(), 'The replacement service survived logout.')
            inventory(3)
            assert len(mounts())==2
            outside = dict(env); outside.pop('HYPRLAND_INSTANCE_SIGNATURE')
            assert subprocess.run([str(binary), '--service'], env=outside, timeout=5).returncode==1
            assert not owns_name()
            print('PASS: routing, desktop copy/move, floating folder requests, single-instance ownership, background Auto mount, USB reconnects, restart suppression and logout.')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
            for connection in connections: connection.close()
            listener.close()
            control.close()


if __name__ == '__main__':
    check(Path(sys.argv[1]).resolve())
