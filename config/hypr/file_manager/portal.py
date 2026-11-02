#!/usr/bin/env python3
"""Hyprland-owned XDG FileChooser backend. Never opens or writes file content."""
import json
import os
from pathlib import Path
import signal
import re
import socket
import sys

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]
NAME = 'org.freedesktop.impl.portal.desktop.fusion'
INTERFACE = 'org.freedesktop.impl.portal.FileChooser'
PATH = '/org/freedesktop/portal/desktop'
XML = '''<node><interface name="org.freedesktop.impl.portal.FileChooser">
<property name="version" type="u" access="read"/>
%s
</interface></node>''' % ''.join('''<method name="%s">
<arg name="handle" type="o" direction="in"/><arg name="app_id" type="s" direction="in"/>
<arg name="parent_window" type="s" direction="in"/><arg name="title" type="s" direction="in"/>
<arg name="options" type="a{sv}" direction="in"/>
<arg name="response" type="u" direction="out"/><arg name="results" type="a{sv}" direction="out"/>
</method>''' % method for method in ('OpenFile', 'SaveFile', 'SaveFiles'))
REQUEST = Gio.DBusNodeInfo.new_for_xml('''<node><interface name="org.freedesktop.impl.portal.Request">
<method name="Close"/></interface></node>''').interfaces[0]


def path_bytes(value):
    if not isinstance(value, (bytes, bytearray, list, tuple)):
        return ''
    return os.fsdecode(bytes(value).split(b'\0', 1)[0])


def picker_request(method, app_id, parent, title, options):
    request = {key: options[key] for key in ('accept_label', 'multiple', 'directory', 'filters',
               'current_filter', 'choices', 'current_name') if key in options}
    request.update(method=method, app_id=app_id, title=title, parent_window=parent)
    for key in ('current_folder', 'current_file'):
        if key in options: request[key] = path_bytes(options[key])
    if 'files' in options: request['files'] = [path_bytes(value) for value in options['files']]
    return request


def portal_result(result):
    # Validate the subprocess boundary before constructing typed D-Bus values.
    if result.get('response') != 0: return (1, {})
    uris = result.get('uris', [])
    if not uris or not all(isinstance(uri, str) and uri.startswith('file:///') for uri in uris):
        raise ValueError('Picker returned invalid local file URIs')
    values = {'uris': GLib.Variant('as', uris), 'writable': GLib.Variant('b', True)}
    if 'choices' in result: values['choices'] = GLib.Variant('a(ss)', result['choices'])
    if 'current_filter' in result: values['current_filter'] = GLib.Variant('(sa(us))', tuple(result['current_filter']))
    return 0, values


class Backend:
    def __init__(self, connection, command=None):
        self.connection = connection
        self.command = command or [sys.executable, str(ROOT/'file_manager/launch.py'), '--picker']
        self.pending = {}
        self.object = connection.register_object(PATH, Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0],
            self.call, lambda *_: GLib.Variant('u', 4), None)
        self.owner_watch = connection.signal_subscribe('org.freedesktop.DBus', 'org.freedesktop.DBus',
            'NameOwnerChanged', '/org/freedesktop/DBus', None, Gio.DBusSignalFlags.NONE, self.owner_changed)

    def reply(self, handle, response=1, results=None):
        pending = self.pending.pop(handle, None)
        if pending is None: return
        self.connection.unregister_object(pending['object'])
        pending['invocation'].return_value(GLib.Variant('(ua{sv})', (response, results or {})))

    def cancel(self, handle):
        pending = self.pending.get(handle)
        if pending:
            # Only the child belonging to this request; no broad process kill.
            pending['process'].force_exit()
            self.reply(handle)

    def owner_changed(self, _bus, _sender, _path, _interface, _signal, parameters):
        name, old, new = parameters.unpack()
        if old and not new:
            for handle, pending in list(self.pending.items()):
                if pending['sender'] == name: self.cancel(handle)

    def application_identity(self, app_id, handle):
        if app_id: return app_id
        # Unsandboxed callers often have an empty portal app ID. The standard
        # request path carries their unique bus name; resolve its executable so
        # Chrome's geometry does not overwrite Firefox's. Only its hash is saved.
        parts = handle.split('/')
        if len(parts) > 6 and re.fullmatch(r'[0-9]+(?:_[0-9]+)+', parts[6]):
            try:
                sender = ':' + parts[6].replace('_', '.')
                pid = self.connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                    'org.freedesktop.DBus', 'GetConnectionUnixProcessID', GLib.Variant('(s)', (sender,)),
                    GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
                return os.readlink(f'/proc/{pid}/exe')
            except (GLib.Error, OSError): pass
        return 'unsandboxed'

    def call(self, _bus, sender, _path, _interface, method, parameters, invocation):
        handle, app_id, parent, title, options = parameters.unpack()
        if handle in self.pending or len(self.pending) >= 16:
            invocation.return_dbus_error('org.freedesktop.portal.Error.Failed', 'Too many active file requests.')
            return
        try:
            request = picker_request(method, self.application_identity(app_id, handle), parent, title, options)
            encoded = json.dumps(request, ensure_ascii=True) + '\n'
            if len(encoded) > 1024*1024: raise ValueError('File request is too large')
            launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE)
            launcher.setenv('XETAL_FILE_PICKER', '1', True)
            process = launcher.spawnv(self.command)
            def close(_bus, caller, _path, _interface, _method, _parameters, call):
                if caller != sender:
                    call.return_dbus_error('org.freedesktop.portal.Error.NotAllowed', 'Request belongs to another caller.')
                    return
                self.cancel(handle)
                call.return_value(GLib.Variant('()', ()))
            registration = self.connection.register_object(handle, REQUEST, close, None, None)
            self.pending[handle] = dict(process=process, invocation=invocation, object=registration, sender=sender)
            def completed(child, task):
                try:
                    _success, stdout, _stderr = child.communicate_utf8_finish(task)
                    if handle not in self.pending: return
                    if not child.get_successful(): raise ValueError('Picker exited before completing the request')
                    result = json.loads(stdout)
                    self.reply(handle, *portal_result(result))
                except (GLib.Error, ValueError, TypeError, KeyError) as error:
                    print('Fusion file chooser: '+str(error), file=sys.stderr, flush=True)
                    self.reply(handle, 2)
            process.communicate_utf8_async(encoded, None, completed)
        except (GLib.Error, ValueError, TypeError) as error:
            invocation.return_dbus_error('org.freedesktop.portal.Error.Failed', str(error))

    def stop(self):
        for handle in list(self.pending): self.cancel(handle)
        self.connection.signal_unsubscribe(self.owner_watch)
        self.connection.unregister_object(self.object)


def main():
    signature, runtime = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'), os.environ.get('XDG_RUNTIME_DIR')
    if not signature or not runtime: return 1
    # An open compositor event stream ends on logout even if socket files remain.
    events = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    events.connect(str(Path(runtime)/'hypr'/signature/'.socket2.sock'))
    loop = GLib.MainLoop()
    backend = None
    def acquired(connection, _name):
        nonlocal backend
        backend = Backend(connection)
    owner = Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE,
                            None, acquired, lambda *_: loop.quit())
    def session_event(_fd, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR) or not events.recv(65536):
            loop.quit(); return False
        return True
    GLib.io_add_watch(events.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, session_event)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, number, lambda: (loop.quit(), False)[1])
    try: loop.run()
    finally:
        if backend: backend.stop()
        Gio.bus_unown_name(owner)
        events.close()
    return 0


if __name__ == '__main__': raise SystemExit(main())
