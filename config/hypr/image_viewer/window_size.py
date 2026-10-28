"""Remember normal window sizes by screen resolution and scale, never position."""
from dataclasses import dataclass
import json
import os
import subprocess

from PyQt6.QtCore import QEvent, QObject, QRect, QSettings, QSize, QTimer
from PyQt6.QtWidgets import QApplication

DEFAULT = QSize(1080, 760)
MINIMUM = QSize(580, 400)
EDGE = 12


def hypr_query(command):
    if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return []
    try:
        result = subprocess.run(['hyprctl', '-j', command], capture_output=True,
                                text=True, check=True, timeout=1)
        value = json.loads(result.stdout)
        return value if isinstance(value, list) else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def monitors():
    return hypr_query('monitors')


def center(area, size):
    client = next((c for c in hypr_query('clients') if c.get('pid') == os.getpid()
                   and c.get('class') == 'xetal-image-viewer' and c.get('floating')
                   and not c.get('fullscreen')), None)
    if client:
        x = area.x() + round((area.width() - size.width()) / 2)
        y = area.y() + round((area.height() - size.height()) / 2)
        try:
            subprocess.run(['hyprctl', 'dispatch', 'movewindowpixel',
                            f'exact {x} {y},address:{client["address"]}'],
                           capture_output=True, timeout=1)
        except (OSError, subprocess.SubprocessError):
            pass


@dataclass
class Display:
    key: str
    area: QRect

    @classmethod
    def for_screen(cls, screen, outputs):
        output = next((m for m in outputs if m.get('name') == screen.name()), None)
        if output:
            # Wayland's QScreen.availableGeometry() includes layer-shell bars.
            # Hyprland reports their reserved area in logical pixels.
            scale = output.get('scale', 1) or 1
            width, height = output['width'], output['height']
            if output.get('transform', 0) % 2:
                width, height = height, width
            left, top, right, bottom = output.get('reserved', [0, 0, 0, 0])
            area = QRect(output['x'] + left, output['y'] + top,
                         max(1, round(width / scale) - left - right),
                         max(1, round(height / scale) - top - bottom))
        else:
            scale = screen.devicePixelRatio()
            size = screen.geometry().size()
            width, height = round(size.width() * scale), round(size.height() * scale)
            area = screen.availableGeometry()
        return cls(f'{width}x{height}@{scale:g}', area)

    def maximum(self):
        return QSize(max(1, self.area.width() - EDGE * 2), max(1, self.area.height() - EDGE * 2))

    def fit(self, size):
        return size.expandedTo(MINIMUM).boundedTo(self.maximum())


def launch_screen(screens, outputs):
    focused = next((m.get('name') for m in outputs if m.get('focused')), None)
    return next((s for s in screens if s.name() == focused), QApplication.primaryScreen())


def valid(size):
    return isinstance(size, QSize) and 0 < size.width() <= 32768 and 0 < size.height() <= 32768


class Store:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else QSettings('Xetal', 'Images')

    def load(self, display):
        self.settings.sync()
        value = self.settings.value('sizes/' + display.key)
        if not valid(value):
            # Migrate the older, single size once. New resolutions then get
            # their own default instead of borrowing a large screen's size.
            legacy = self.settings.value('size')
            if valid(legacy) and not any(k.startswith('sizes/') for k in self.settings.allKeys()):
                value = legacy
                self.save(display, value)
                self.settings.remove('size')
                self.settings.sync()
            else:
                value = DEFAULT
        return display.fit(value)

    def save(self, display, size):
        if valid(size):
            self.settings.setValue('sizes/' + display.key, size)
            self.settings.sync()


class Memory(QObject):
    def __init__(self, window, store=None, query=monitors):
        super().__init__(window)
        self.window, self.store, self.query = window, store or Store(), query
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.save)
        self.changing = False
        self.connected = False
        self.ready = False
        self.startup = QTimer(self)
        self.startup.setSingleShot(True)
        self.startup.setInterval(150)
        self.startup.timeout.connect(self.mapped)
        self.screen = None
        outputs = query()
        screen = launch_screen(QApplication.screens(), outputs)
        self.display = Display.for_screen(screen, outputs)
        window.setScreen(screen)
        self.resize(self.store.load(self.display))
        self.last_normal = window.size()
        window.installEventFilter(self)

    def resize(self, size):
        self.changing = True
        try:
            self.window.setMinimumSize(MINIMUM.boundedTo(self.display.maximum()))
            self.window.resize(self.display.fit(size))
        finally:
            self.changing = False

    def connect_screen(self, screen):
        if self.screen is screen:
            return
        if self.screen:
            for signal in (self.screen.geometryChanged, self.screen.availableGeometryChanged):
                try:
                    signal.disconnect(self.refresh)
                except (RuntimeError, TypeError):  # A disconnected output may already be deleted.
                    pass
        self.screen = screen
        if screen:
            screen.geometryChanged.connect(self.refresh)
            screen.availableGeometryChanged.connect(self.refresh)

    def refresh(self, *args):
        screen = self.window.screen()
        if not screen:
            return
        if not self.ready:
            # During Wayland mapping Qt can briefly announce the primary
            # screen. Never save that transient screen as a user's preference.
            self.startup.start()
            return
        display = Display.for_screen(screen, self.query())
        if display != self.display:
            self.timer.stop()
            self.store.save(self.display, self.last_normal)
            self.display = display
            if not self.window.isFullScreen() and not self.window.isMaximized():
                # Moving an open viewer preserves its size, limited to the new
                # display. The preference belongs to that resolution from now on.
                self.resize(self.window.size())
                self.last_normal = self.window.size()
        self.connect_screen(screen)

    def mapped(self):
        if not self.window.isVisible():
            return
        if not self.window.windowHandle().isExposed():
            self.startup.start()
            return
        self.display = Display.for_screen(self.window.screen(), self.query())
        size = self.store.load(self.display)
        if not self.window.isFullScreen() and not self.window.isMaximized():
            changed = self.window.size() != size
            self.resize(size)
            if changed:
                center(self.display.area, self.window.size())
        self.last_normal = self.window.size()
        self.connect_screen(self.window.screen())
        self.ready = True

    def save(self):
        if not self.ready:
            return
        if self.window.isFullScreen() or self.window.isMaximized():
            size = self.window.normalGeometry().size()
        else:
            size = self.window.size()
        self.store.save(self.display, size)
        self.last_normal = size

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Show and not self.connected:
            self.connected = True
            self.window.windowHandle().screenChanged.connect(self.refresh)
            self.refresh()
        elif kind == QEvent.Type.Resize and self.ready and not self.changing:
            if not self.window.isFullScreen() and not self.window.isMaximized():
                self.last_normal = self.window.size()
                self.timer.start()
        elif kind == QEvent.Type.Close:
            self.startup.stop()
            self.timer.stop()
            self.save()
        return False
