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
import unicodedata

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'theme'))
import runtime

FIELDS = {'os': 'OS', 'kernel': 'Kernel', 'uptime': 'Uptime', 'cpu': 'CPU', 'gpu': 'GPU',
          'memory': 'Memory', 'disk': 'Disk', 'shell': 'Shell', 'terminal': 'Terminal',
          'wm': 'Desktop', 'packages': 'Packages'}
DEFAULTS = {'version': 1, 'enabled': True, 'logo': 'arch', 'show_user': True, 'show_palette': True,
            'fields': list(FIELDS)}
ARCH = [
    '              ▄              ',
    '             ▟█▙             ',
    '            ▟███▙            ',
    '           ▟█████▙           ',
    '          ▟███████▙          ',
    '         ▂▔▀███████▙         ',
    '        ▟██▅▂▝▀█████▙        ',
    '       ▟█████████████▙       ',
    '      ▟██████▀▀▀██████▙      ',
    '     ▟██████▏   ▕██████▙     ',
    '    ▟███████     ███████▙    ',
    '   ▟████████     █████████▙   ',
    '  ▟██████▀▀       ▀▀██████▙  ',
    ' ▟███▀▀               ▀▀███▙ ',
    '▟▀▀                       ▀▀▙',
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
    if value.get('logo', 'arch') not in ('arch', 'arch-ascii', 'fusion', 'none'): raise ValueError('Choose a supported logo.')
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


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in text)


def fit(text, columns):
    """Fit whole terminal cells, including wide device names and combining marks."""
    if cell_width(text) <= columns: return text
    result='';remaining=max(0,columns-1)
    for character in text:
        size=cell_width(character)
        if size>remaining:break
        result+=character;remaining-=size
    return result+'…' if columns else ''


def rows(settings, data, width=110, image_logo=None):
    colors = runtime.colors(); accent = colors['Accent']; text = colors['Text']; muted = colors['PlaceholderText']
    edge=blend(accent,colors['Window'],.60)
    logo = ARCH if settings['logo'] in ('arch', 'arch-ascii') else FUSION if settings['logo'] == 'fusion' else []
    if image_logo: logo = image_logo[0]
    # Narrow terminals retain readable values; no wrapping across the logo.
    if width < 72: logo = []
    logo_width = max(map(cell_width, logo), default=0)
    info_width=max(1,width-4-(logo_width+4 if logo else 0))
    heading=clean(getpass.getuser()+'@'+socket.gethostname()) if settings['show_user'] else 'HYPER FUSION'
    content = [[(heading, accent)], [('HYPER FUSION  ·  '+runtime.DESIGNS[runtime.design()],muted)]]
    content.append([('─' * min(42, info_width), edge)])
    for key in settings['fields']:
        content.append([(FIELDS[key].ljust(10), muted), (clean(data.get(key, '—')), text)])
    if settings['show_palette']:
        content += [[], [('▰ ', blend(accent, text, i / 9)) for i in range(7)]]
    result = []
    height = max(len(logo), len(content))
    logo_offset=max(0,(height-len(logo))//2)
    for i in range(height):
        line = [('  ',text)]
        if logo:
            index=i-logo_offset
            art=logo[index] if 0<=index<len(logo) else ''
            line.append((art+' '*(logo_width-cell_width(art))+'    ',
                         image_logo[1] if image_logo else blend(accent, text, .42*(1-i/max(1,height-1)))))
        line += content[i] if i < len(content) else []
        remaining = max(1, width - 2); clipped = []
        for value, color in line:
            value = fit(value,remaining); clipped.append((value, color)); remaining -= cell_width(value)
            if remaining <= 0: break
        result.append(clipped)
    return result


def render(settings, data, *, width=110, markup=False, colored=True, image_logo=None):
    result = []
    for line in rows(settings, data, width, image_logo):
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
    width = shutil.get_terminal_size((110, 24)).columns
    colored = not args.plain and sys.stdout.isatty()
    prefix = ''; image_logo = None
    if (colored and settings['logo'] == 'arch' and width >= 72
            and os.environ.get('TERM') == 'xterm-kitty'
            and not os.environ.get('TMUX') and not os.environ.get('STY')):
        try:
            import artwork
            prefix, lines, color = artwork.kitty_image(runtime.colors())
            image_logo = (lines, color)
        except (ImportError, OSError, ValueError):
            pass  # Keep a readable theme-colored text logo if graphics fail.
    print(prefix + '\n' + render(settings, system_data(), width=width,
                                colored=colored, image_logo=image_logo) + '\n')
    return 0


if __name__ == '__main__': raise SystemExit(main())
