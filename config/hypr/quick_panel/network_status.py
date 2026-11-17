"""Shared, read-only network snapshot for the taskbar and its connection panel."""
from concurrent.futures import ThreadPoolExecutor
import html
import json
import os
import re
import subprocess

WIFI = '󰤨'
LAN = '󰈀'
WIFI_IDLE = '󰤭'
WIFI_OFF = '󰖪'
OFFLINE = '󰈂'


def read(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=3,
                                env={**os.environ, 'LC_ALL': 'C', 'NO_COLOR': '1'})
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def fields(line):
    """nmcli terse output escapes colons and backslashes in connection names."""
    result, value, escaped = [], [], False
    for character in line:
        if escaped:
            value.append(character); escaped = False
        elif character == '\\':
            escaped = True
        elif character == ':':
            result.append(''.join(value)); value = []
        else:
            value.append(character)
    if escaped: value.append('\\')
    return result + [''.join(value)]


def summarize(raw):
    general = fields(raw.get('general') or '') + [''] * 4
    devices = []
    for line in (raw.get('devices') or '').splitlines():
        values = fields(line)
        if len(values) == 4:
            name, kind, state, connection = values
            devices.append(dict(name=name, kind=kind, state=state,
                                connection='' if connection == '--' else connection,
                                connected=state.startswith('connected')))
    wifi = [d for d in devices if d['kind'] in ('wifi', '802-11-wireless')]
    wired = [d for d in devices if d['kind'] in ('ethernet', '802-3-ethernet')]
    for group in (wifi, wired): group.sort(key=lambda d: not d['connected'])
    # Prefer the actual physical default route. Ignore VPN/tunnel routes so
    # enabling a VPN never turns a Wi-Fi indicator into an Ethernet indicator.
    active = None
    for family in ('ipv4', 'ipv6'):
        try: routes = json.loads(raw.get(family) or '[]')
        except (ValueError, TypeError): routes = []
        if not isinstance(routes, list): routes = []
        routes = [r for r in routes if isinstance(r, dict) and isinstance(r.get('metric', 0), (int, float))]
        for route in sorted(routes, key=lambda r: r.get('metric', 0)):
            active = next((d for d in wired + wifi if d['connected'] and d['name'] == route.get('dev')), None)
            if not active:
                bridge = next((d for d in devices if d['kind'] in ('bridge', 'bond') and d['connected'] and d['name'] == route.get('dev')), None)
                if bridge: active = next((d for d in wired if d['connected']), None)
            if active: break
        if active: break
    active = active or next((d for d in wired + wifi if d['connected']), None)
    radio = general[2] == 'enabled'
    kind = 'wifi' if active in wifi else 'lan' if active else 'offline'
    icon = WIFI if kind == 'wifi' else LAN if kind == 'lan' else WIFI_IDLE if wifi and radio else WIFI_OFF if wifi else OFFLINE
    connectivity = general[1]
    internet = {'full': 'Internet connected', 'limited': 'Limited internet access',
                'portal': 'Network sign-in required', 'none': 'No internet connection',
                'unknown': 'Internet status unknown'}.get(connectivity, 'Network status unavailable')
    vpn = []
    for line in (raw.get('connections') or '').splitlines():
        values = fields(line)
        if len(values) == 2 and values[0] in ('vpn', 'wireguard', 'tun'):
            vpn.append(values[1])
    for d in devices:
        if d['kind'] in ('wireguard', 'tun') and d['connected']:
            name = d['connection'] or d['name']
            if name not in vpn: vpn.append(name)
    controller = raw.get('bluetooth') or ''
    bluetooth = dict(available=bool(re.search(r'^Controller ', controller, re.M)),
                     enabled=bool(re.search(r'^\s*Powered:\s*yes\s*$', controller, re.M)), devices=[])
    for line in (raw.get('bluetooth_devices') or '').splitlines():
        match = re.match(r'^Device [0-9A-Fa-f:]+ (.+)$', line)
        if match: bluetooth['devices'].append(match[1])
    return dict(available=raw.get('general') is not None, connectivity=connectivity,
                internet=internet, kind=kind, icon=icon, active=active,
                wifi=dict(available=bool(wifi), enabled=radio, hardware=general[3] == 'enabled', devices=wifi),
                lan=dict(available=bool(wired), devices=wired), vpn=vpn, bluetooth=bluetooth)


def snapshot(details=True):
    queries = {
        'general': ['nmcli', '-t', '-f', 'STATE,CONNECTIVITY,WIFI,WIFI-HW', 'general', 'status'],
        'devices': ['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'],
        'ipv4': ['ip', '-j', '-4', 'route', 'show', 'default'],
        'ipv6': ['ip', '-j', '-6', 'route', 'show', 'default'],
    }
    if details:
        queries.update(connections=['nmcli', '-t', '-f', 'TYPE,NAME', 'connection', 'show', '--active'],
                       bluetooth=['bluetoothctl', '--timeout', '2', 'show'],
                       bluetooth_devices=['bluetoothctl', '--timeout', '2', 'devices', 'Connected'])
    with ThreadPoolExecutor(max_workers=len(queries)) as workers:
        raw = dict(zip(queries, workers.map(read, queries.values())))
    return summarize(raw)


def bar_status(data):
    active = data['active']
    connection = ('Wi-Fi' if data['kind'] == 'wifi' else 'Ethernet') + ': ' + (active['connection'] or active['name']) if active else 'No active connection'
    return {'text': data['icon'], 'class': [data['kind'], 'online' if data['connectivity'] == 'full' else 'offline'],
            'tooltip': html.escape(connection + '\n' + data['internet']) + '\nClick for Internet, LAN, Wi-Fi, VPN &amp; Bluetooth'}


def set_radio(kind, enabled):
    """Only explicit UI actions change a radio; reading status never does."""
    state = 'on' if enabled else 'off'
    if kind == 'wifi': argv = ['nmcli', '--wait', '5', 'radio', 'wifi', state]
    elif kind == 'bluetooth': argv = ['bluetoothctl', '--timeout', '5', 'power', state]
    else: raise ValueError('Unknown radio')
    result = subprocess.run(argv, capture_output=True, text=True, timeout=7,
                            env={**os.environ, 'LC_ALL': 'C', 'NO_COLOR': '1'})
    if result.returncode or (kind == 'bluetooth' and 'succeeded' not in result.stdout.lower()):
        raise RuntimeError((result.stderr or result.stdout).strip() or 'Could not change the radio. Open Settings for details.')
