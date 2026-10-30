"""Read-only snapshots and geometry for the taskbar's compact panels."""
from __future__ import annotations
import calendar
from datetime import date, timedelta
import math
from pathlib import Path
import re
import subprocess
import time

import psutil


def command(argv, timeout=1.5):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def duration(seconds):
    minutes = max(0, int(seconds)) // 60
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return (f'{days}d ' if days else '') + f'{hours}h {minutes:02d}m'


def month_days(year, month):
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    return [start + timedelta(days=i) for i in range(42)]


def shift_month(year, month, delta):
    index = max(12, min(9999 * 12 - 1, year * 12 + month - 1 + delta))
    year, month = divmod(index, 12)
    return year, month + 1


def monitor_at(monitors, cursor):
    enabled = [m for m in monitors if not m.get('disabled') and m.get('mirrorOf', 'none') in ('none', '', None, -1)]
    for m in enabled:
        w, h = m['width'], m['height']
        if m.get('transform', 0) % 2: w, h = h, w
        scale = m.get('scale', 1) or 1
        if m['x'] <= cursor['x'] < m['x'] + w / scale and m['y'] <= cursor['y'] < m['y'] + h / scale:
            return m
    return next((m for m in enabled if m.get('focused')), enabled[0] if enabled else None)


def placement(monitor, kind, edge='top'):
    w, h = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2: w, h = h, w
    scale = monitor.get('scale', 1) or 1
    left, top, right, bottom = monitor.get('reserved', [0, 0, 0, 0])
    width = max(1, min(420 if kind == 'power' else 370, w / scale - left - right - 24))
    height = max(1, min(835 if kind == 'power' else 440, h / scale - top - bottom - 20))
    x = w / scale - right - width - 12
    y = top + 10 if edge == 'top' else h / scale - bottom - height - 10
    return {'monitor': monitor['id'], 'x': round(monitor['x'] + x), 'y': round(monitor['y'] + y),
            'relative_x': round(x), 'relative_y': round(y), 'width': round(width), 'height': round(height)}


def battery_status(battery):
    if battery is None:
        return {'present': False, 'percent': 100, 'title': 'AC power', 'detail': 'Desktop · always connected'}
    percent = max(0, min(100, round(battery.percent)))
    detail = 'Fully charged' if percent >= 99 and battery.power_plugged else 'Charging' if battery.power_plugged else 'On battery'
    if not battery.power_plugged and battery.secsleft >= 0:
        detail += ' · ' + duration(battery.secsleft) + ' remaining'
    return {'present': True, 'percent': percent, 'title': 'Battery', 'detail': detail}


def backlight(root=Path('/sys/class/backlight')):
    for device in sorted(root.glob('*')):
        try:
            maximum = int((device / 'max_brightness').read_text())
            value = int((device / 'brightness').read_text())
            if maximum > 0:
                return {'device': device.name, 'percent': max(0, min(100, round(100 * value / maximum)))}
        except (OSError, ValueError): pass
    return None


def media_snapshot():
    fields = ['playerName', 'title', 'artist', 'mpris:artUrl', 'mpris:length', 'position', 'status']
    text = command(['playerctl', 'metadata', '--format', '\x1f'.join('{{' + key + '}}' for key in fields)])
    if not text: return None
    parts = (text.split('\x1f') + [''] * 7)[:7]
    def number(value):
        try: return max(0, float(value) / 1_000_000)
        except ValueError: return 0
    return {'player': parts[0], 'title': parts[1] or 'Media player', 'artist': parts[2], 'art': parts[3],
            'length': number(parts[4]), 'position': number(parts[5]), 'status': parts[6]}


def snapshot():
    memory = psutil.virtual_memory(); disk = psutil.disk_usage(str(Path.home()))
    sensors = []
    try:
        for chip, values in psutil.sensors_temperatures().items():
            if chip not in ('coretemp', 'k10temp', 'zenpower', 'cpu_thermal', 'acpitz'): continue
            for item in values:
                if math.isfinite(item.current) and 0 < item.current < 150:
                    sensors.append((item.label or chip, item.current))
    except (AttributeError, OSError): pass
    raw = command(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
    match = re.search(r'Volume:\s*([\d.]+)', raw)
    audio = {'percent': max(0, min(100, round(float(match[1]) * 100))), 'muted': '[MUTED]' in raw} if match else None
    try: battery = psutil.sensors_battery()
    except (AttributeError, OSError): battery = None
    return {'cpu': psutil.cpu_percent(interval=.12), 'memory': memory.percent, 'disk': disk.percent,
            'memory_detail': f'{memory.used / 2**30:.1f} / {memory.total / 2**30:.1f} GiB',
            'disk_detail': f'{disk.free / 2**30:.0f} GiB free', 'uptime': duration(time.time() - psutil.boot_time()),
            'battery': battery_status(battery), 'temperatures': sensors, 'audio': audio,
            'backlight': backlight(), 'media': media_snapshot()}
