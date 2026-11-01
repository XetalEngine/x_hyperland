#!/usr/bin/env python3
"""Session-owned actions for saved screenshots and screen recordings."""
import argparse
import fcntl
import html
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]


def action_command(action, path, kind='screenshot'):
    path = Path(path).resolve(strict=True)
    if not path.is_file(): raise ValueError('The saved file is no longer available.')
    if action == 'folder-open' or (action == 'default' and kind == 'recording'):
        return [str(ROOT/'scripts/files.sh'), '--select', str(path)]
    if action == 'default' and kind == 'screenshot':
        return [str(ROOT/'scripts/image-viewer.sh'), '--', str(path)]
    raise ValueError('Unknown notification action.')


class Notifications:
    def __init__(self, bus, launch=None):
        self.bus=bus;self.files={}
        self.launch=launch or (lambda argv:subprocess.Popen(argv,start_new_session=True,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))

    def show(self, path, summary, kind='screenshot', body=None):
        if kind not in ('screenshot', 'recording'): raise ValueError('Unknown capture type.')
        path=Path(path).resolve(strict=True)
        if not path.is_file():raise ValueError('Saved file does not exist.')
        recording = kind == 'recording'
        app = 'Hyper Fusion Recorder' if recording else 'Hyprland Screenshot'
        hints = {'category': GLib.Variant('s', 'transfer.complete')}
        if not recording: hints['image-path'] = GLib.Variant('s', path.as_uri())
        ident=self.bus.call_sync('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
            'org.freedesktop.Notifications', 'Notify', GLib.Variant('(susssasa{sv}i)', (
                app, 0, 'media-record' if recording else 'camera-photo', str(summary),
                html.escape(str(path) if body is None else str(body)),
                ['default', 'Show in folder' if recording else 'Open image', 'folder-open', '📂  Show in folder'],
                hints,
                7000)), GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        self.files[ident]=(path,kind)
        return ident

    def event(self, signal, values):
        ident=values[0]
        if ident not in self.files:return
        if signal=='ActionInvoked':
            path,kind=self.files[ident]
            try:self.launch(action_command(values[1], path, kind))
            except (ValueError,OSError) as error:
                app='Hyper Fusion Recorder' if kind=='recording' else 'Hyprland Screenshot'
                self.launch(['notify-send','-a',app,'Cannot open '+kind,str(error)])
        elif signal=='NotificationClosed' and values[1]!=1:
            # Expired banners remain actionable in notification history.
            self.files.pop(ident,None)


def send(sock_path, request):
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as client:
        client.sendto(json.dumps(request).encode(),str(sock_path))


def main():
    parser=argparse.ArgumentParser(description='Saved capture notification actions')
    parser.add_argument('path');parser.add_argument('summary')
    parser.add_argument('--recording',action='store_true');parser.add_argument('--body')
    args=parser.parse_args()
    path=Path(args.path).resolve(strict=True)
    request={'path':str(path),'summary':args.summary,
             'kind':'recording' if args.recording else 'screenshot','body':args.body}
    runtime=Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/os.environ['HYPRLAND_INSTANCE_SIGNATURE']
    # A new endpoint lets an older screenshot-only broker keep handling its
    # existing notifications until logout when updating a running session.
    sock_path=runtime/'capture-actions.sock'
    try:send(sock_path,request);return
    except (FileNotFoundError,ConnectionRefusedError):pass
    with (runtime/'capture-actions.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            for _ in range(20):
                time.sleep(.05)
                try:send(sock_path,request);return
                except (FileNotFoundError,ConnectionRefusedError):pass
            raise RuntimeError('Capture actions could not connect to this session.')
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
                    message=json.loads(server.recv(65536));notifications.show(**message)
                except (OSError,ValueError,TypeError,KeyError,GLib.Error) as error:print(str(error),flush=True)
                return True
            def alive(*_):
                try:
                    if session.recv(65536):return True
                except OSError:pass
                loop.quit();return False
            GLib.io_add_watch(server.fileno(),GLib.IO_IN,receive)
            GLib.io_add_watch(session.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,alive)
            try:
                notifications.show(**request);loop.run()
            finally:sock_path.unlink(missing_ok=True)


if __name__=='__main__':main()
