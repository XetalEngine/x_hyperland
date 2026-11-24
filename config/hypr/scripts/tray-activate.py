#!/usr/bin/env python3
"""Reveal a tray application's own window without moving it or toggling it off.

Called only for a left click by the Waybar GTK extension. Exit 2 leaves the
click to Waybar (unknown items and menu-only applets). No background focus rule
or application launch command is installed.
"""
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tray_window_activation', ROOT/'activate-window.py')
window_activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(window_activation)
from floating import Hypr, runtime, descendant, process_stamp


@dataclass(frozen=True)
class Item:
    owner: str
    path: str
    pid: int
    stamp: str
    menu_only: bool


class TrayBus:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(self, owner, path, interface, method, signature, args):
        return self.bus.call_sync(owner, path, interface, method,
            self.GLib.Variant(signature, args), None,
            self.Gio.DBusCallFlags.NO_AUTO_START, 800, None).unpack()

    def owner(self, name):
        return self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'GetNameOwner', '(s)', (name,))[0]

    def property(self, owner, path, name, default=None):
        try:
            return self.call(owner, path, 'org.freedesktop.DBus.Properties', 'Get',
                '(ss)', ('org.kde.StatusNotifierItem', name))[0]
        except self.GLib.Error:
            return default

    def resolve(self, hint):
        # A menu attached to the clicked GTK widget provides the exact D-Bus
        # endpoint. Match its menu path as well: one process can own many items.
        name, menu = hint.get('bus', ''), hint.get('menu', '')
        tooltip = hint.get('tooltip', '').strip().split('\n')[0]
        if not name and not tooltip: return None
        owner = self.owner(name) if name else ''
        registered = self.call('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
            'org.freedesktop.DBus.Properties', 'Get', '(ss)',
            ('org.kde.StatusNotifierWatcher', 'RegisteredStatusNotifierItems'))[0]
        matches = set()
        for entry in registered[:128]:
            service, slash, rest = entry.partition('/')
            path = '/'+rest if slash else '/StatusNotifierItem'
            try: candidate = self.owner(service)
            except self.GLib.Error: continue  # The app may exit during the click.
            if owner:
                if candidate != owner or self.property(candidate, path, 'Menu') != menu: continue
            else:
                # Menu-less items have no GTK endpoint. Use an exact, unique
                # displayed title, then verify the actual D-Bus process below.
                title = self.property(candidate, path, 'Title', '')
                if not title:
                    tooltip_value = self.property(candidate, path, 'ToolTip', ())
                    if isinstance(tooltip_value, (tuple, list)) and len(tooltip_value) == 4:
                        title = tooltip_value[2]
                if not title or title != tooltip: continue
            matches.add((candidate, path))
        if len(matches) != 1: return None
        owner, path = next(iter(matches))
        pid = self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'GetConnectionUnixProcessID', '(s)', (owner,))[0]
        stamp = process_stamp(pid)
        if not stamp: return None
        return Item(owner, path, pid, stamp, self.property(owner, path, 'ItemIsMenu', True) is not False)

    def activate(self, item, x, y):
        self.call(item.owner, item.path, 'org.kde.StatusNotifierItem', 'Activate', '(ii)', (x, y))


def choose_window(clients, item):
    if process_stamp(item.pid) != item.stamp: return None
    owned = [w for w in clients if w.get('mapped') and w.get('address') and
             (w.get('pid') == item.pid or descendant(w.get('pid', 0), (item.pid, item.stamp)))]
    # Hyprland reports zero for the most recently focused window and -1 for
    # windows which have never been focused. Titles/classes are not ownership.
    def recent(window):
        value = window.get('focusHistoryID', -1)
        return (value if isinstance(value, int) and value >= 0 else 1_000_000, window['address'])
    return min(owned, key=recent) if owned else None


def reveal(hypr, bus, hint, *, wait_seconds=2):
    item = bus.resolve(hint)
    if item is None: return False
    window = choose_window(hypr.query('clients'), item)
    if window:
        # focuswindow already handles the monitor/workspace and the minimize
        # restore hook. Never send movetoworkspace or an app's hide/show toggle.
        try: window_activation.activate(hypr, window['address'])
        except (OSError, ValueError, KeyError) as error:
            print('Tray focus: '+str(error), file=sys.stderr)
        return True
    if item.menu_only or process_stamp(item.pid) != item.stamp: return False
    try:
        bus.activate(item, hint.get('x', 0), hint.get('y', 0))
        # Only the application can recreate a closed window. Focus that newly
        # mapped window where it chose to appear; never start a duplicate process.
        deadline = time.monotonic()+wait_seconds
        while time.monotonic() < deadline and process_stamp(item.pid) == item.stamp:
            window = choose_window(hypr.query('clients'), item)
            if window:
                window_activation.activate(hypr, window['address'])
                break
            time.sleep(.05)
    except Exception as error:
        # Even a timeout can mean the app processed Activate. Replaying a
        # second click could immediately close the window we just opened.
        print('Tray activation: '+str(error), file=sys.stderr)
    return True  # Activate was delivered. Do not replay it and toggle twice.


def main():
    try:
        hint = json.loads(sys.stdin.read(8193))
        if not isinstance(hint, dict): return 2
        for key in ('bus', 'menu', 'tooltip'):
            if not isinstance(hint.get(key, ''), str) or len(hint.get(key, '')) > 2048: return 2
        for key in ('x', 'y'):
            if type(hint.get(key, 0)) is not int or not -(2**31) <= hint.get(key, 0) < 2**31: return 2
        return 0 if reveal(Hypr(runtime()), TrayBus(), hint) else 2
    except Exception as error:
        print('Tray activation: '+str(error), file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
