#!/usr/bin/env python3
"""Check native FileManager1 routing on a private D-Bus session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from gi.repository import Gio, GLib


def check(binary):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    def owns_name():
        return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'NameHasOwner',
            GLib.Variant('(s)', ('org.freedesktop.FileManager1',)),
            GLib.VariantType.new('(b)'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
    if owns_name():
        raise RuntimeError('Run this check on a fresh private D-Bus session.')
    with tempfile.TemporaryDirectory(prefix='fusion-folder-routing-') as directory:
        root = Path(directory)
        (root/'scripts').mkdir()
        (root/'choice').write_text('Fusion Files')
        handler = root/'scripts/file-manager.sh'
        handler.write_text('''#!/usr/bin/python3
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with (root/'calls.jsonl').open('a') as log:
    log.write(json.dumps(dict(choice=(root/'choice').read_text(),arguments=sys.argv[1:]))+'\\n')
''')
        handler.chmod(0o700)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
                   XETAL_FILES_ROOT=str(root))
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','XDG_RUNTIME_DIR'):
            path = root/key.lower(); path.mkdir(mode=0o700); env[key] = str(path)
        process = subprocess.Popen([str(binary), '--service'], env=env)
        try:
            deadline = time.monotonic()+5
            while not owns_name():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('The native folder service did not start.')
                time.sleep(.025)
            uri = (root/'screen # 100% $(literal).png').as_uri()
            def invoke(method, urls):
                bus.call_sync('org.freedesktop.FileManager1', '/org/freedesktop/FileManager1',
                    'org.freedesktop.FileManager1', method, GLib.Variant('(ass)', (urls, '')),
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
            invoke('ShowItems', [uri, 'relative-path-is-not-a-uri'])
            assert calls(1)==[dict(choice='Fusion Files',arguments=['--select',uri])]
            (root/'choice').write_text('Another file manager')
            invoke('ShowFolders', [root.as_uri(), 'smb://server/share/folder%20name'])
            assert calls(2)[-1]==dict(choice='Another file manager',
                arguments=[root.as_uri(),'smb://server/share/folder%20name'])
            print('PASS: native ShowItems preserves selection/literal URIs; ShowFolders resolves the current handler on every request.')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()


if __name__ == '__main__':
    check(Path(sys.argv[1]).resolve())
