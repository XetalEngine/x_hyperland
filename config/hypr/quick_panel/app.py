#!/usr/bin/env python3
"""Compact, session-owned clock and power dashboards anchored to the taskbar."""
from __future__ import annotations
import argparse
import fcntl
from collections import deque
from datetime import date, datetime
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import (Qt, QEvent, QObject, QPointF, QRectF, QSize, QTimer, QRunnable,
                         QThreadPool, pyqtSignal, QSignalBlocker, QUrl)
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtNetwork import QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QPushButton, QToolButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QSlider, QMessageBox, QSizePolicy)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'theme')); sys.path.append(str(ROOT / 'launcher'))
import runtime
from identity import Avatar
from activation import BarActivation
from outside_click import CLICK_EVENT,check_pointer
import wheel_guard
import model
from protocol import Request
from placement import prepare


class Signals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)


class Work(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.signals = Signals()

    def run(self):
        try: self.signals.result.emit(self.fn())
        except Exception as error: self.signals.error.emit(str(error))


def async_run(fn, success, error):
    task = Work(fn); task.signals.result.connect(success); task.signals.error.connect(error)
    QThreadPool.globalInstance().start(task)


def label(text='', name='', center=False):
    control = QLabel(text); control.setObjectName(name); control.setTextFormat(Qt.TextFormat.PlainText)
    if center: control.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return control


def button(text, title, callback):
    control = QPushButton(text); control.setToolTip(title); control.setAccessibleName(title)
    control.setCursor(Qt.CursorShape.PointingHandCursor); control.clicked.connect(callback)
    return control


def card():
    frame = QFrame(); frame.setObjectName('card'); layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12); layout.setSpacing(8)
    return frame, layout


class Grip(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove(); event.accept()
        else: super().mousePressEvent(event)


class ClockPage(QWidget):
    def __init__(self, open_calendar):
        super().__init__(); self.selected = date.today(); self.year, self.month = self.selected.year, self.selected.month
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(10)
        clock, clock_layout = card(); self.time = label('', 'clock', True); self.today_label = label('', 'muted', True)
        clock_layout.addWidget(self.time); clock_layout.addWidget(self.today_label); layout.addWidget(clock)
        month, month_layout = card(); controls = QHBoxLayout(); controls.setSpacing(3)
        controls.addWidget(button('‹', 'Previous month', lambda: self.shift(-1)))
        self.month_label = label('', 'section', True); controls.addWidget(self.month_label, 1)
        controls.addWidget(button('›', 'Next month', lambda: self.shift(1)))
        controls.addSpacing(12); controls.addWidget(button('‹', 'Previous year', lambda: self.shift(-12)))
        self.year_label = label('', 'section', True); controls.addWidget(self.year_label)
        controls.addWidget(button('›', 'Next year', lambda: self.shift(12))); month_layout.addLayout(controls)
        grid = QGridLayout(); grid.setSpacing(3); self.days = []
        for i, day in enumerate(('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')):
            grid.addWidget(label(day, 'weekday', True), 0, i)
        for i in range(42):
            control = button('', '', lambda _, index=i: self.select(index)); control.setObjectName('day')
            control.setMinimumSize(28, 28); self.days.append(control); grid.addWidget(control, i // 7 + 1, i % 7)
        month_layout.addLayout(grid); layout.addWidget(month)
        self.selected_label = label('', 'muted', True); layout.addWidget(self.selected_label)
        actions = QHBoxLayout(); actions.addWidget(button('Today', 'Jump to today', self.today)); actions.addStretch()
        actions.addWidget(button('Full calendar ↗', 'Open the full calendar in Fusion Settings', open_calendar))
        layout.addLayout(actions); layout.addStretch(); self.tick(); self.refresh_month()

    def tick(self):
        now = datetime.now().astimezone(); self.time.setText(now.strftime('%H:%M:%S'))
        self.today_label.setText(now.strftime('%A, %d %B %Y  ·  %Z'))
        if getattr(self, 'last_date', None) != now.date(): self.last_date = now.date(); self.refresh_month()

    def shift(self, delta):
        self.year, self.month = model.shift_month(self.year, self.month, delta); self.refresh_month()

    def today(self):
        self.selected = date.today(); self.year, self.month = self.selected.year, self.selected.month; self.refresh_month()

    def select(self, index):
        self.selected = self.dates[index]; self.year, self.month = self.selected.year, self.selected.month; self.refresh_month()

    def refresh_month(self):
        self.month_label.setText(date(self.year, self.month, 1).strftime('%B')); self.year_label.setText(str(self.year))
        self.dates = model.month_days(self.year, self.month)
        for control, day in zip(self.days, self.dates):
            control.setText(str(day.day)); control.setToolTip(day.strftime('%A, %d %B %Y'))
            control.setAccessibleName(control.toolTip()); control.setProperty('outside', day.month != self.month)
            control.setProperty('selected', day == self.selected); control.setProperty('today', day == date.today())
            control.style().unpolish(control); control.style().polish(control)
        self.selected_label.setText(self.selected.strftime('%A, %d %B %Y'))


class Gauge(QWidget):
    def __init__(self, title):
        super().__init__(); self.title = title; self.value = 0; self.setMinimumSize(90, 105)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); colors = runtime.colors()
        circle = QRectF((self.width() - 60) / 2, 6, 60, 60)
        p.setPen(QPen(QColor(colors['Mid']), 5)); p.drawArc(circle, 90 * 16, -360 * 16)
        p.setPen(QPen(QColor(colors['Accent']), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(circle, 90 * 16, round(-360 * 16 * self.value / 100))
        p.setPen(QColor(colors['Text'])); p.setFont(QFont('JetBrains Mono', 13, QFont.Weight.Bold))
        p.drawText(circle, Qt.AlignmentFlag.AlignCenter, f'{self.value:.0f}%')
        p.setPen(QColor(colors['PlaceholderText'])); p.setFont(QFont(runtime.ui_font(), 10))
        p.drawText(QRectF(0, 77, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self.title)


class TemperatureGraph(QWidget):
    def __init__(self):
        super().__init__(); self.values = deque(maxlen=90); self.setMinimumHeight(80)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); colors = runtime.colors()
        box = QRectF(self.rect()).adjusted(2, 5, -2, -5); p.setPen(QPen(QColor(colors['Mid']), 1))
        for fraction in (.25, .5, .75):
            y = box.top() + box.height() * fraction; p.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
        if not self.values:
            p.setPen(QColor(colors['PlaceholderText'])); p.drawText(box, Qt.AlignmentFlag.AlignCenter, 'Waiting for temperature samples'); return
        points = [QPointF(box.left() + i * box.width() / 89, box.bottom() - min(110, max(0, n)) / 110 * box.height()) for i, n in enumerate(self.values)]
        path = QPainterPath(points[0])
        for point in points[1:]: path.lineTo(point)
        fill = QPainterPath(path); fill.lineTo(points[-1].x(), box.bottom()); fill.lineTo(points[0].x(), box.bottom()); fill.closeSubpath()
        color = QColor(colors['Accent']); color.setAlpha(30); p.fillPath(fill, color)
        p.setPen(QPen(QColor(colors['Accent']), 2)); p.drawPath(path)


class PowerPage(QWidget):
    def __init__(self, owner):
        super().__init__(); self.owner = owner; self.busy = False; self.data = {}; self.art_url = ''; self.art_reply = None
        self.network = QNetworkAccessManager(self)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(9)
        profile, box = card(); row = QHBoxLayout(); self.avatar = Avatar(70); row.addWidget(self.avatar)
        info = QVBoxLayout(); info.setSpacing(4); info.addWidget(label(getpass.getuser(), 'username'))
        self.uptime = label('Your session', 'muted'); info.addWidget(self.uptime); row.addLayout(info, 1); box.addLayout(row)
        controls = QHBoxLayout(); controls.setSpacing(7)
        for glyph, key, title in [('⏻', 'poweroff', 'Power off'), ('↻', 'reboot', 'Restart'), ('⇥', 'logout', 'Log out'), ('⌑', 'lock', 'Lock screen'), ('☾', 'suspend', 'Suspend')]:
            control = button(glyph, title, lambda _, k=key, t=title: self.power(k, t)); control.setObjectName('powerAction'); controls.addWidget(control)
        box.addLayout(controls); layout.addWidget(profile)
        battery, box = card(); row = QHBoxLayout(); self.battery_icon = label('▰', 'battery'); row.addWidget(self.battery_icon)
        info = QVBoxLayout(); self.battery_title = label('Power', 'section'); self.battery_detail = label('', 'muted')
        info.addWidget(self.battery_title); info.addWidget(self.battery_detail); row.addLayout(info, 1); box.addLayout(row); layout.addWidget(battery)
        metrics, box = card(); row = QHBoxLayout(); self.gauges = {}
        for key, title in [('cpu', 'CPU'), ('memory', 'RAM'), ('disk', 'DISK')]:
            self.gauges[key] = Gauge(title); row.addWidget(self.gauges[key], 1)
        box.addLayout(row); layout.addWidget(metrics)
        levels, box = card(); self.sliders = {}; self.readouts = {}; self.pending = {}
        for key, glyph, title in [('audio', '♪', 'Volume'), ('backlight', '☀', 'Brightness')]:
            row = QHBoxLayout(); symbol = button(glyph, 'Mute / unmute' if key == 'audio' else title, self.mute if key == 'audio' else lambda: None)
            symbol.setFixedWidth(28); row.addWidget(symbol)
            slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(0, 100); slider.setAccessibleName(title); slider.setEnabled(False)
            slider.valueChanged.connect(lambda value, k=key: self.queue_level(k, value)); self.sliders[key] = slider; row.addWidget(slider, 1)
            value = label('—', 'muted'); value.setFixedWidth(42); value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.readouts[key] = value; row.addWidget(value); box.addLayout(row)
        self.level_timer = QTimer(self); self.level_timer.setSingleShot(True); self.level_timer.timeout.connect(self.apply_levels)
        layout.addWidget(levels)
        temperatures, box = card(); row = QHBoxLayout(); row.addWidget(label('Core temperature', 'section'), 1)
        self.temperature = label('—', 'accent'); row.addWidget(self.temperature); box.addLayout(row)
        self.graph = TemperatureGraph(); box.addWidget(self.graph); self.sensors = label('', 'muted'); self.sensors.setWordWrap(True); box.addWidget(self.sensors)
        layout.addWidget(temperatures)
        media, box = card(); row = QHBoxLayout(); self.art = label('♫', 'art', True); self.art.setFixedSize(62, 62); row.addWidget(self.art)
        info = QVBoxLayout(); self.song = label('Nothing playing', 'section'); self.artist = label('Open your music or video player', 'muted')
        for control in (self.song, self.artist): control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(self.song); info.addWidget(self.artist); row.addLayout(info, 1); box.addLayout(row)
        self.progress = QSlider(Qt.Orientation.Horizontal); self.progress.setRange(0, 1000); self.progress.setEnabled(False)
        self.progress.setAccessibleName('Playback position'); self.progress.sliderReleased.connect(self.seek); box.addWidget(self.progress)
        times = QHBoxLayout(); self.elapsed = label('0:00', 'muted'); self.length = label('0:00', 'muted')
        times.addWidget(self.elapsed); times.addStretch(); times.addWidget(self.length); box.addLayout(times)
        controls = QHBoxLayout(); controls.addStretch(); self.media_buttons = []
        for glyph, action, title in [('◀', 'previous', 'Previous track'), ('▶', 'play-pause', 'Play / pause'), ('■', 'stop', 'Stop'), ('▶▏', 'next', 'Next track')]:
            control = button(glyph, title, lambda _, a=action: self.media_action(a)); control.setFixedWidth(45); control.setEnabled(False)
            if action == 'play-pause': self.play = control
            controls.addWidget(control); self.media_buttons.append(control)
        controls.addStretch(); box.addLayout(controls); layout.addWidget(media)
        self.status = label('', 'muted'); self.status.setWordWrap(True); self.status.hide(); layout.addWidget(self.status)
        layout.addStretch()

    def refresh(self):
        if self.busy or not self.isVisible(): return
        self.busy = True; async_run(model.snapshot, self.loaded, self.failed)

    def failed(self, message):
        self.busy = False; self.status.setText(message[:250]); self.status.show()

    def loaded(self, data):
        self.busy = False; self.data = data; self.uptime.setText('Up ' + data['uptime']); self.avatar.refresh()
        battery = data['battery']; self.battery_title.setText(f"{battery['title']}  {battery['percent']}%")
        self.battery_detail.setText(battery['detail']); self.battery_icon.setText('▰' if battery['percent'] >= 50 else '▱')
        for key, gauge in self.gauges.items(): gauge.value = data[key]; gauge.update()
        self.gauges['memory'].setToolTip(data['memory_detail']); self.gauges['disk'].setToolTip(data['disk_detail'])
        for key, slider in self.sliders.items():
            value = data[key]; slider.setEnabled(bool(value))
            slider.setToolTip('Volume' if key == 'audio' else 'Display brightness' if value else 'No adjustable backlight on this display')
            if value and not slider.isSliderDown() and key not in self.pending:
                with QSignalBlocker(slider): slider.setValue(value['percent'])
                self.readouts[key].setText('Mute' if value.get('muted') else str(value['percent']) + '%')
        sensors = data['temperatures']
        if sensors:
            temperature = max(value for _, value in sensors); self.temperature.setText(f'{temperature:.0f} °C')
            self.graph.values.append(temperature); self.graph.update()
            self.sensors.setText('   ·   '.join(f'{name}: {value:.0f}°' for name, value in sensors[:6]))
            self.sensors.setToolTip('\n'.join(f'{name}: {value:.1f} °C' for name, value in sensors))
        else: self.temperature.setText('—'); self.sensors.setText('No CPU temperature sensor reported')
        media = data['media']; self.song.setText(media['title'] if media else 'Nothing playing')
        self.song.setToolTip(self.song.text()); self.artist.setText(media['artist'] if media else 'Open your music or video player')
        self.artist.setToolTip(self.artist.text()); self.play.setText('Ⅱ' if media and media['status'] == 'Playing' else '▶')
        for control in self.media_buttons: control.setEnabled(bool(media))
        length = media['length'] if media else 0; position = media['position'] if media else 0
        self.progress.setEnabled(length > 0)
        if not self.progress.isSliderDown():
            with QSignalBlocker(self.progress): self.progress.setValue(round(min(1, position / length) * 1000) if length else 0)
        stamp = lambda value: f'{int(value) // 60}:{int(value) % 60:02d}'
        self.elapsed.setText(stamp(position)); self.length.setText(stamp(length)); self.set_art(media['art'] if media else '')

    def set_art(self, url):
        if url == self.art_url: return
        self.art_url = url; self.art.setPixmap(QPixmap()); self.art.setText('♫')
        if self.art_reply is not None: self.art_reply.abort(); self.art_reply = None
        parsed = urlparse(url)
        if parsed.scheme == 'file' and parsed.netloc in ('', 'localhost'):
            path = Path(unquote(parsed.path))
            try:
                if path.stat().st_size <= 4_000_000: self.show_art(path.read_bytes())
            except OSError: pass
        elif parsed.scheme in ('https', 'http'):
            request = QNetworkRequest(QUrl(url)); request.setTransferTimeout(2500)
            reply = self.network.get(request); self.art_reply = reply
            reply.downloadProgress.connect(lambda received, total: reply.abort() if max(received, total) > 4_000_000 else None)
            def finished():
                if self.art_reply is reply:
                    if reply.error().value == 0: self.show_art(bytes(reply.readAll()))
                    self.art_reply = None
                reply.deleteLater()
            reply.finished.connect(finished)

    def show_art(self, data):
        image = QPixmap()
        if image.loadFromData(data): self.art.setPixmap(image.scaled(62, 62, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def execute(self, args):
        def run():
            result = subprocess.run(args, capture_output=True, text=True, timeout=5)
            if result.returncode: raise RuntimeError((result.stderr or result.stdout or 'Command unavailable').strip())
        async_run(run, lambda _: self.refresh(), self.failed)

    def queue_level(self, key, value):
        self.pending[key] = value; self.readouts[key].setText(str(value) + '%'); self.level_timer.start(140)

    def apply_levels(self):
        pending, self.pending = self.pending, {}
        for key, value in pending.items():
            if key == 'audio': self.execute(['wpctl', 'set-volume', '-l', '1', '@DEFAULT_AUDIO_SINK@', f'{value}%'])
            elif self.data.get('backlight'): self.execute(['brightnessctl', '--device=' + self.data['backlight']['device'], 'set', f'{max(1, value)}%'])

    def mute(self):
        if self.data.get('audio'): self.execute(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'])

    def media_action(self, action):
        media = self.data.get('media')
        if media: self.execute(['playerctl', '--player=' + media['player'], action])

    def seek(self):
        media = self.data.get('media')
        if media and media['length'] > 0:
            self.execute(['playerctl', '--player=' + media['player'], 'position', str(media['length'] * self.progress.value() / 1000)])

    def power(self, key, title):
        actions = {'poweroff': ['systemctl', 'poweroff'], 'reboot': ['systemctl', 'reboot'],
                   'logout': ['hyprctl', 'dispatch', 'exit'], 'suspend': ['systemctl', 'suspend'],
                   'lock': ['hyprlock', '--config', str(ROOT / 'hyprlock.conf')]}
        if key == 'lock':
            self.owner.hide(); subprocess.Popen(actions[key], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); return
        self.owner.modal = True
        try:
            confirmed = QMessageBox.question(self, title, title + ' this session now?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if confirmed == QMessageBox.StandardButton.Yes: self.execute(actions[key])
        finally: self.owner.modal = False


class Popup(QWidget):
    def __init__(self, kind='clock', preview=False):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName('quickPanel'); self.setWindowTitle('Hyper Fusion quick panel'); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.preview = preview; self.kind = kind; self.modal = False; self.armed = False; self.dismissed_at = 0
        self.generation=0;self.opened_at=0
        root = QVBoxLayout(self); root.setContentsMargins(12, 8, 12, 12); root.setSpacing(5)
        grip = Grip(); header = QHBoxLayout(grip); header.setContentsMargins(3, 0, 0, 0)
        self.caption = label('', 'eyebrow'); self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); header.addWidget(self.caption, 1)
        close = button('×', 'Close popup', self.hide); close.setFixedSize(28, 28); header.addWidget(close); root.addWidget(grip)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); root.addWidget(self.scroll, 1)
        self.pages = {'clock': ClockPage(self.open_calendar), 'power': PowerPage(self)}
        self.clock_timer = QTimer(self); self.clock_timer.setInterval(1000); self.clock_timer.timeout.connect(self.pages['clock'].tick)
        self.power_timer = QTimer(self); self.power_timer.setInterval(2000); self.power_timer.timeout.connect(self.pages['power'].refresh)
        self.change_kind(kind); self.refresh_style(); QApplication.instance().hypr_theme.changed.connect(self.refresh_style)

    def refresh_style(self):
        c = runtime.colors(); radius = 5 if runtime.widget_design() == 'binaryknife' else 19 if runtime.layout()=='sidebar' else 14
        self.setStyleSheet(f'''
            QWidget {{background:transparent; color:{c['Text']}; font-family:"{runtime.ui_font()}"; font-size:12px;}}
            QWidget#quickPanel, QScrollArea, QScrollArea > QWidget > QWidget {{background:transparent;}}
            QFrame#card {{background:{c['Window']}; border:1px solid {c['Mid']}; border-radius:{radius}px;}}
            QLabel {{border:none; background:transparent;}}
            QLabel#muted {{color:{c['PlaceholderText']}; font-size:11px;}}
            QLabel#section {{font-weight:600;}}
            QLabel#eyebrow {{font-family:"JetBrains Mono"; color:{c['Accent']}; font-size:10px; letter-spacing:2px;}}
            QLabel#clock {{font-family:"JetBrains Mono"; color:{c['Accent']}; font-size:41px; font-weight:600; letter-spacing:1px;}}
            QLabel#username {{color:{c['Accent']}; font-size:23px; font-weight:600;}}
            QLabel#accent, QLabel#weekday {{color:{c['Accent']};}}
            QLabel#battery, QLabel#art {{font-size:32px; color:{c['Accent']};}}
            QPushButton {{background:{c['Button']}; border:1px solid transparent; border-radius:{max(3,radius-5)}px; padding:5px 7px; min-width:0; min-height:0;}}
            QPushButton:hover, QPushButton:focus {{background:{c['Highlight']}; border-color:{c['Accent']};}}
            QPushButton:disabled {{color:{c['Disabled']};}}
            QPushButton#powerAction {{font-size:20px; color:{c['Accent']}; padding:2px 8px;}}
            QPushButton#day {{background:transparent; padding:2px;}}
            QPushButton#day[outside="true"] {{color:{c['Disabled']};}}
            QPushButton#day[today="true"] {{border-color:{c['Accent']};}}
            QPushButton#day[selected="true"] {{background:{c['Highlight']}; color:{c['HighlightedText']};}}
            QPushButton#day:hover {{background:{c['Button']}; border-color:{c['Accent']};}}
            QSlider::groove:horizontal {{height:5px; background:{c['Mid']}; border-radius:2px;}}
            QSlider::sub-page:horizontal {{background:{c['Accent']}; border-radius:2px;}}
            QSlider::handle:horizontal {{background:{c['Accent']}; width:10px; margin:-4px 0; border-radius:5px;}}
            QSlider:disabled::sub-page:horizontal {{background:{c['Mid']};}}
            QScrollBar:vertical {{background:transparent; width:5px; margin:0;}}
            QScrollBar::handle:vertical {{background:{c['Mid']}; min-height:24px; border-radius:2px;}}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
        '''); self.pages['clock'].refresh_month(); self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); c = runtime.colors()
        fill = QColor(c['Base']); fill.setAlpha(247); p.setBrush(fill)
        border = QColor(c['Accent']); border.setAlpha(145); p.setPen(QPen(border, 1))
        radius = 5 if runtime.widget_design() == 'binaryknife' else 19 if runtime.layout()=='sidebar' else 16
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), radius, radius)

    def change_kind(self, kind):
        previous = self.scroll.takeWidget()
        if previous: previous.hide(); previous.setParent(self)
        self.kind = kind; self.scroll.setWidget(self.pages[kind]); self.pages[kind].show()
        self.caption.setText('LOCAL TIME' if kind == 'clock' else 'YOUR SESSION')

    def present(self, request):
        kind = request.get('kind', 'clock')
        if kind not in self.pages: return
        if self.isVisible() and self.kind == kind: self.hide(); return
        if kind == self.kind and time.monotonic() - self.dismissed_at < .25: return
        try:
            if self.preview:
                size = int(request['width']), int(request['height'])
            else:
                if 'monitor' not in request:
                    monitors = json.loads(model.command(['hyprctl', '-j', 'monitors']))
                    cursor = json.loads(model.command(['hyprctl', '-j', 'cursorpos']))
                    options = json.loads((ROOT / 'waybar/options.json').read_text())
                    request = dict(request, **model.placement(model.monitor_at(monitors, cursor), kind, options.get('position', 'top')))
                size = prepare(request)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            print(error, file=sys.stderr)
            return
        # A different page/output needs a fresh map so its static geometry rules
        # apply again. Unmapping also lets the compositor take the Burn snapshot.
        if self.isVisible(): self.hide()
        self.generation+=1;self.opened_at=time.monotonic()
        self.change_kind(kind); self.armed = False
        self.resize(*size)
        self.show(); self.raise_(); self.activateWindow()
        if not self.preview:
            self.activation = BarActivation(self); self.activation.start()
        self.clock_timer.start() if kind == 'clock' else self.clock_timer.stop()
        self.power_timer.start() if kind == 'power' else self.power_timer.stop()
        if kind == 'power': self.pages['power'].refresh()

    def dismissal_protected(self): return self.modal or QApplication.activeModalWidget() is not None

    def event(self, event):
        if event.type() == QEvent.Type.WindowActivate: self.armed = True
        return super().event(event)

    def compositor_events(self,connection):
        while connection.canReadLine():
            event=bytes(connection.readLine()).strip()
            if not self.isVisible() or self.dismissal_protected() or time.monotonic()-self.opened_at<.2:continue
            if event==CLICK_EVENT:
                generation=self.generation
                def checked(outside,generation=generation):
                    if outside is True and generation==self.generation and self.isVisible() and not self.dismissal_protected():
                        self.hide();self.dismissed_at=time.monotonic()
                check_pointer(self,checked,'Hyper Fusion quick panel')
            elif event.startswith(b'workspace>>'):self.hide()

    def hideEvent(self, event):
        self.generation+=1;self.clock_timer.stop(); self.power_timer.stop(); super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.hide()
        else: super().keyPressEvent(event)

    def open_calendar(self):
        self.hide(); subprocess.Popen([str(ROOT / 'scripts/control-center.sh'), '--tab', 'calendar'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--kind', choices=['clock', 'power'], default='clock')
    parser.add_argument('--request', default='{}'); parser.add_argument('--preview'); parser.add_argument('--design', choices=list(runtime.DESIGNS))
    args = parser.parse_args()
    if args.design and args.preview: runtime.design = lambda: args.design
    app = QApplication(sys.argv[:1]); app.setApplicationName('fusion-quick-panel'); app.setDesktopFileName('fusion-quick-panel')
    app.setQuitOnLastWindowClosed(False); runtime.install(app); wheel_guard.install(app)
    request = json.loads(args.request); request['kind'] = args.kind
    request.setdefault('width', 370 if args.kind == 'clock' else 420); request.setdefault('height', 440 if args.kind == 'clock' else 835)
    server = QLocalServer(app)
    if not args.preview:
        signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'); directory = os.environ.get('XDG_RUNTIME_DIR')
        if not signature or not directory: return 1
        instance = Path(directory) / 'hypr' / signature; address = str(instance / 'fusion-quick-panel.sock')
        start_lock=(instance/'fusion-quick-panel.lock').open('a');fcntl.flock(start_lock,fcntl.LOCK_EX)
        peer = QLocalSocket(); peer.connectToServer(address)
        if peer.waitForConnected(150):
            peer.write(json.dumps(request).encode() + b'\n'); peer.waitForBytesWritten(300); return 0
        QLocalServer.removeServer(address)
        if not server.listen(address): return 1
        start_lock.close()
        lifetime = QLocalSocket(app); lifetime.connectToServer(str(instance / '.socket2.sock'))
        lifetime.disconnected.connect(app.quit)
    window = Popup(args.kind, bool(args.preview)); app.aboutToQuit.connect(window.deleteLater); window.present(request)
    if not args.preview:lifetime.readyRead.connect(lambda:window.compositor_events(lifetime))
    def incoming():
        connection = server.nextPendingConnection(); message=Request()
        def receive():
            try:
                value=message.feed(bytes(connection.readAll()))
                if value is not None:window.present(value)
            except (ValueError, TypeError, AttributeError):message.done=True
            if message.done:connection.disconnectFromServer()
        connection.readyRead.connect(receive); connection.disconnected.connect(connection.deleteLater)
        if connection.bytesAvailable(): receive()
    server.newConnection.connect(incoming)
    if args.preview: QTimer.singleShot(1800, lambda: (window.grab().save(args.preview), app.quit()))
    return app.exec()


if __name__ == '__main__': raise SystemExit(main())
