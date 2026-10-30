"""A theme-colored terminal welcome using Fastfetch's structured system data."""
from __future__ import annotations
import argparse
import copy
import fcntl
import getpass
import html
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'theme'))
import runtime

FIELDS = {'os': 'OS', 'kernel': 'Kernel', 'uptime': 'Uptime', 'cpu': 'CPU', 'gpu': 'GPU',
          'memory': 'Memory', 'disk': 'Disk', 'shell': 'Shell', 'terminal': 'Terminal',
          'wm': 'Desktop', 'packages': 'Packages'}
DEFAULTS = {'version': 1, 'enabled': True, 'logo': 'arch', 'show_user': True, 'show_palette': True,
            'fields': list(FIELDS)}
ARCH = [
    '              /\\              ',
    '             /██\\             ',
    '            /████\\            ',
    '           /██████\\           ',
    '          /████████\\          ',
    '         /██████████\\         ',
    '        /████████████\\        ',
    '       /██████  ██████\\       ',
    '      /██████    ██████\\      ',
    '     /██████      ██████\\     ',
    '    /██████        ██████\\    ',
    '   /██████          ██████\\   ',
    '  /█████              █████\\  ',
    ' /███                    ███\\ ',
    '/██                        ██\\',
]
FUSION = ['       ╱╲        ╱╲       ', '      ╱██╲      ╱██╲      ', '     ╱████╲    ╱████╲     ',
          '     ╲█████╲  ╱█████╱     ', '      ╲█████╳█████╱      ', '       ╲█████████╱       ',
          '        ╲███████╱        ', '        ╱███████╲        ', '       ╱█████████╲       ',
          '      ╱█████╳█████╲      ', '     ╱█████╱  ╲█████╲     ', '     ╲████╱    ╲████╱     ',
          '      ╲██╱      ╲██╱      ', '       ╲╱        ╲╱       ']


def validate(value):
    if not isinstance(value, dict) or value.get('version') != 1: raise ValueError('Unsupported terminal settings.')
    result = copy.deepcopy(DEFAULTS)
    for key in ('enabled', 'show_user', 'show_palette'):
        if type(value.get(key, result[key])) is not bool: raise ValueError('Invalid ' + key + ' option.')
        result[key] = value.get(key, result[key])
    if value.get('logo', 'arch') not in ('arch', 'fusion', 'none'): raise ValueError('Choose a supported logo.')
    result['logo'] = value.get('logo', 'arch')
    fields = value.get('fields', list(FIELDS))
    if not isinstance(fields, list) or any(not isinstance(f, str) or f not in FIELDS for f in fields) or len(fields) != len(set(fields)):
        raise ValueError('Invalid information fields.')
    result['fields'] = fields
    return result


def load(path=None):
    path = path or ROOT / 'settings.json'
    return validate(json.loads(path.read_text())) if path.exists() else copy.deepcopy(DEFAULTS)


def save(value, path=None, expected=None):
    path = path or ROOT / 'settings.json'
    value = validate(value); path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if expected is not None and load(path)!=expected:raise ValueError('Terminal choices changed elsewhere. Reload before saving.')
        temporary = path.with_suffix('.tmp'); temporary.write_text(json.dumps(value, indent=2) + '\n')
        os.replace(temporary, path)


def clean(value):
    # Do not let device/host names inject terminal escape sequences or markup.
    value=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(value))
    return ''.join(c for c in value if c.isprintable())[:180]


def system_data():
    values = {}
    try:
        result = subprocess.run(['fastfetch', '--format', 'json', '--structure',
            'OS:Kernel:Uptime:CPU:GPU:Memory:Disk:Shell:Terminal:WM:Packages'],
            text=True, capture_output=True, timeout=3)
        data = json.loads(result.stdout)
        values = {item['type']: item['result'] for item in data if isinstance(item, dict) and 'result' in item}
    except (OSError, ValueError, TypeError, subprocess.SubprocessError): pass
    def field(kind, key, fallback='Unknown'):
        item = values.get(kind, {})
        return item.get(key, fallback) if isinstance(item, dict) else fallback
    memory = values.get('Memory', {}); disk = values.get('Disk', [])
    root_disk = next((d for d in disk if d.get('mountpoint') == '/'), {})
    size = root_disk.get('bytes', {})
    seconds = int(field('Uptime', 'uptime', 0)) // 1000
    days, seconds = divmod(seconds, 86400); hours, seconds = divmod(seconds, 3600)
    gpu = values.get('GPU', [])
    if not isinstance(gpu, list): gpu = []
    result = {
        'os': field('OS', 'prettyName', platform.system()), 'kernel': field('Kernel', 'release', platform.release()),
        'uptime': (f'{days}d ' if days else '') + f'{hours}h {seconds // 60:02d}m',
        'cpu': field('CPU', 'cpu'), 'gpu': ', '.join(g.get('name', '') for g in gpu),
        'memory': f"{memory.get('used', 0) / 2**30:.1f} / {memory.get('total', 0) / 2**30:.1f} GiB",
        'disk': f"{size.get('free', 0) / 2**30:.0f} GiB free / {size.get('total', 0) / 2**30:.0f} GiB",
        'shell': Path(os.environ.get('SHELL', '/bin/sh')).name,
        'terminal': 'Kitty' if os.environ.get('XETAL_FUSION_TERMINAL') or not sys.stdin.isatty() else field('Terminal', 'prettyName', 'Kitty'),
        'wm': field('WM', 'prettyName', 'Hyprland') + ' · ' + field('WM', 'protocolName', 'Wayland'),
        'packages': str(field('Packages', 'all', '—')),
    }
    return {key: clean(value) for key, value in result.items()}


def blend(a, b, fraction):
    left = tuple(int(a[i:i+2], 16) for i in (1, 3, 5)); right = tuple(int(b[i:i+2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x + (y - x) * fraction):02x}' for x, y in zip(left, right))


def rows(settings, data, width=110):
    colors = runtime.colors(); accent = colors['Accent']; text = colors['Text']; muted = colors['PlaceholderText']
    logo = ARCH if settings['logo'] == 'arch' else FUSION if settings['logo'] == 'fusion' else []
    # Narrow terminals retain readable values; no wrapping across the logo.
    if width < 72: logo = []
    logo_width = max(map(len, logo), default=0)
    content = [[('HYPER FUSION', accent), ('  /  ' + runtime.DESIGNS[runtime.design()], muted)]]
    if settings['show_user']: content.append([(clean(getpass.getuser() + '@' + socket.gethostname()), text)])
    content.append([('─' * min(38, max(8, width - logo_width - 8)), muted)])
    for key in settings['fields']:
        content.append([(FIELDS[key].ljust(9), accent), (data.get(key, '—'), text)])
    if settings['show_palette']:
        content += [[], [('●  ', blend(accent, text, i / 6)) for i in range(7)]]
    result = []
    height = max(len(logo), len(content))
    for i in range(height):
        line = []
        if logo:
            line.append(((logo[i] if i < len(logo) else '').ljust(logo_width) + '    ',
                         blend(accent, text, .45 * i / max(1, height - 1))))
        line += content[i] if i < len(content) else []
        remaining = max(1, width - 2); clipped = []
        for value, color in line:
            value = value[:remaining]; clipped.append((value, color)); remaining -= len(value)
            if remaining <= 0: break
        result.append(clipped)
    return result


def render(settings, data, *, width=110, markup=False, colored=True):
    result = []
    for line in rows(settings, data, width):
        if markup:
            result.append(''.join(f'<span style="color:{color}">{html.escape(text)}</span>' for text, color in line))
        elif colored:
            result.append(''.join('\x1b[38;2;' + ';'.join(str(int(color[i:i+2], 16)) for i in (1, 3, 5)) + 'm' + text for text, color in line) + '\x1b[0m')
        else: result.append(''.join(text for text, _ in line))
    return '<pre style="font-family:monospace">' + '\n'.join(result) + '</pre>' if markup else '\n'.join(result)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--force', action='store_true'); parser.add_argument('--plain', action='store_true')
    args = parser.parse_args()
    try: settings = load()
    except (OSError, ValueError): settings = copy.deepcopy(DEFAULTS)
    if not settings['enabled'] and not args.force: return 0
    print('\n' + render(settings, system_data(), width=shutil.get_terminal_size((110, 24)).columns,
                        colored=not args.plain and sys.stdout.isatty()) + '\n')
    return 0


if __name__ == '__main__': raise SystemExit(main())
