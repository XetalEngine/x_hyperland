#!/usr/bin/env python3
"""One session-owned broker keeps screenshot actions working in notification history."""
import fcntl
import html
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]


def action_command(action, path):
    path = Path(path).resolve(strict=True)
    if not path.is_file(): raise ValueError('The screenshot is no longer a file.')
    if action == 'default': return ['xdg-open', str(path)]
    if action == 'folder-open': return [str(ROOT/'scripts/dolphin.sh'), '--select', str(path)]
    raise ValueError('Unknown notification action.')


class Notifications:
    def __init__(self, bus, launch=None):
        self.bus=bus;self.files={}
        self.launch=launch or (lambda argv:subprocess.Popen(argv,start_new_session=True,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))

    def show(self, path, summary):
        path=Path(path).resolve(strict=True)
        if not path.is_file():raise ValueError('Screenshot does not exist.')
        ident=self.bus.call_sync('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
            'org.freedesktop.Notifications', 'Notify', GLib.Variant('(susssasa{sv}i)', (
                'Hyprland Screenshot', 0, 'camera-photo', str(summary), html.escape(str(path)),
                ['default', 'Open image', 'folder-open', '📂  Show in folder'],
                {'image-path': GLib.Variant('s', path.as_uri()), 'category': GLib.Variant('s', 'transfer.complete')},
                7000)), GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        self.files[ident]=path
        return ident

    def event(self, signal, values):
        ident=values[0]
        if ident not in self.files:return
        if signal=='ActionInvoked':
            try:self.launch(action_command(values[1], self.files[ident]))
            except (ValueError,OSError) as error:
                self.launch(['notify-send','-a','Hyprland Screenshot','Cannot open screenshot',str(error)])
        elif signal=='NotificationClosed' and values[1]!=1:
            # Expired banners remain actionable in notification history.
            self.files.pop(ident,None)


def send(sock_path, request):
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as client:
        client.sendto(json.dumps(request).encode(),str(sock_path))


def main():
    path=Path(sys.argv[1]).resolve(strict=True)
    request={'path':str(path),'summary':sys.argv[2]}
    runtime=Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']
    sock_path=runtime/'screenshot-actions.sock'
    try:send(sock_path,request);return
    except (FileNotFoundError,ConnectionRefusedError):pass
    with (runtime/'screenshot-actions.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            for _ in range(20):
                time.sleep(.05)
                try:send(sock_path,request);return
                except (FileNotFoundError,ConnectionRefusedError):pass
            raise RuntimeError('Screenshot actions could not connect to this session.')
        with socket.socket(socket.AF_UNIX) as session, socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as server:
            session.connect(str(runtime/'.socket2.sock'))
            sock_path.unlink(missing_ok=True);server.bind(str(sock_path));sock_path.chmod(0o600)
            bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);loop=GLib.MainLoop();notifications=Notifications(bus)
            def invoked(connection,sender,obj,interface,signal,parameters,*_):
                notifications.event(signal,parameters.unpack())
            bus.signal_subscribe('org.freedesktop.Notifications','org.freedesktop.Notifications',None,
                '/org/freedesktop/Notifications',None,Gio.DBusSignalFlags.NONE,invoked,None)
            def receive(*_):
                try:
                    message=json.loads(server.recv(65536));notifications.show(message['path'],message['summary'])
                except (OSError,ValueError,KeyError,GLib.Error) as error:print(str(error),file=sys.stderr,flush=True)
                return True
            def alive(*_):
                try:
                    if session.recv(65536):return True
                except OSError:pass
                loop.quit();return False
            GLib.io_add_watch(server.fileno(),GLib.IO_IN,receive)
            GLib.io_add_watch(session.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,alive)
            try:
                notifications.show(request['path'],request['summary']);loop.run()
            finally:sock_path.unlink(missing_ok=True)


if __name__=='__main__':main()
