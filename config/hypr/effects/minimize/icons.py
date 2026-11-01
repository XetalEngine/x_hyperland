#!/usr/bin/env python3
"""Resolve installed app icons outside the compositor; cache per login only."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PyQt6.QtCore import QStandardPaths, QTimer
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtNetwork import QLocalSocket
from gi.repository import Gio

ROOT = Path(__file__).resolve().parents[2]


def configure_icon_paths():
    # Offscreen Qt has no desktop platform theme and otherwise only searches
    # embedded resources. Include the actual XDG icon themes and pixmaps.
    locations = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.GenericDataLocation)
    paths = [str(Path.home()/'.icons'), *(str(Path(path)/'icons') for path in locations), *QIcon.themeSearchPaths()]
    QIcon.setThemeSearchPaths(list(dict.fromkeys(paths)))
    fallback = [*(str(Path(path)/'pixmaps') for path in locations), *QIcon.fallbackSearchPaths()]
    QIcon.setFallbackSearchPaths(list(dict.fromkeys(fallback)))


def key(name):
    # Same FNV-1a encoding as native/icons.hpp. ASCII normalization is explicit.
    value = 14695981039346656037
    for byte in name.encode('utf-8'):
        if 65 <= byte <= 90:
            byte += 32
        value = ((value ^ byte) * 1099511628211) & 0xffffffffffffffff
    return f'{value:016x}.png'


def app_aliases(info):
    result = {(info.get_id() or '').removesuffix('.desktop'), info.get_executable() or ''}
    if hasattr(info, 'get_startup_wm_class'):
        result.add(info.get_startup_wm_class() or '')
    return {Path(name).name.casefold() for name in result if name}


def resolve(name, applications):
    for candidate in (name, name.lower(), name.replace(' ', '-').lower()):
        icon = QIcon.fromTheme(candidate)
        if not icon.isNull():
            return icon
    for info in applications:
        if name.casefold().removesuffix('.desktop') not in app_aliases(info):
            continue
        source = info.get_icon()
        if isinstance(source, Gio.FileIcon):
            icon = QIcon(source.get_file().get_path())
            if not icon.isNull():return icon
        if isinstance(source, Gio.ThemedIcon):
            for candidate in source.get_names():
                icon = QIcon.fromTheme(candidate)
                if not icon.isNull():return icon
    # A generic executable icon is not an app icon: let the native preview win.
    return QIcon()


def save(directory, name, icon):
    if not name or icon.isNull():return False
    picture = icon.pixmap(256, 256)
    if picture.isNull():return False
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.icon-', suffix='.png', dir=directory)
    os.close(fd)
    try:
        if not picture.save(temporary, 'PNG'):return False
        os.replace(temporary, directory/key(name))
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


class Cache:
    def __init__(self, directory):
        self.directory = directory
        self.applications = []
        self.known = set()
        self.stamp = None
        self.refresh()

    def refresh(self):
        try:
            theme = json.loads((ROOT/'theme/state.json').read_text())
        except (OSError, ValueError):theme = {}
        style = 'Papirus-Light' if theme.get('mode') == 'light' else 'Papirus-Dark'
        QIcon.setThemeName(style); QIcon.setFallbackThemeName('hicolor')
        self.applications = Gio.AppInfo.get_all()
        stamp = (style, tuple((info.get_id(), info.get_icon().to_string() if info.get_icon() else '') for info in self.applications))
        if stamp != self.stamp:
            self.known.clear(); self.stamp = stamp
        try:
            result = subprocess.run(['hyprctl', '-j', 'clients'], capture_output=True, text=True, timeout=4)
            clients = json.loads(result.stdout) if result.returncode == 0 else []
        except (OSError, ValueError, subprocess.TimeoutExpired):clients = []
        for client in clients:
            for name in (client.get('class'), client.get('initialClass')):
                if name and name not in self.known:
                    if not save(self.directory, name, resolve(name, self.applications)):
                        (self.directory/key(name)).unlink(missing_ok=True)
                    self.known.add(name)


def main():
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not signature or '/' in signature or not os.environ.get('XDG_RUNTIME_DIR'):
        return 1
    instance = Path(os.environ['XDG_RUNTIME_DIR'])/'hypr'/signature
    if not (instance/'.socket2.sock').is_socket():return 1
    directory = instance/'xetal-minimize-icons'
    directory.mkdir(mode=0o700, exist_ok=True)
    session_lock = (directory/'.lock').open('a')
    try:fcntl.flock(session_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:return 0
    app = QGuiApplication([sys.argv[0]])
    app.setApplicationName('Fusion minimize icons')
    configure_icon_paths()
    cache = Cache(directory)
    debounce = QTimer(); debounce.setSingleShot(True); debounce.setInterval(120)
    debounce.timeout.connect(cache.refresh)
    connection = QLocalSocket()
    connection.disconnected.connect(app.quit)
    connection.errorOccurred.connect(app.quit)
    buffer = bytearray()
    def events():
        buffer.extend(bytes(connection.readAll()))
        while b'\n' in buffer:
            line, _, rest = buffer.partition(b'\n'); buffer[:] = rest
            if line.startswith((b'openwindow>>', b'windowtitle>>', b'windowtitlev2>>')):
                debounce.start()
    connection.readyRead.connect(events)
    connection.connectToServer(str(instance/'.socket2.sock'))
    # Also detect installed/uninstalled apps and palette changes.
    timer = QTimer(); timer.setInterval(15000); timer.timeout.connect(cache.refresh); timer.start()
    return app.exec()


if __name__ == '__main__':raise SystemExit(main())
