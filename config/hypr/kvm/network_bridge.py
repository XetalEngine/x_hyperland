"""Create a VM bridge without discarding the host's working Ethernet profile.

Only the --create entry point changes networking. It runs after an explicit UI
click and authentication. NetworkManager owns the rollback timer, so recovery
does not depend on this process surviving a lost connection or application exit.
See https://www.networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html
"""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import time
import uuid

NM = 'org.freedesktop.NetworkManager'
ROOT = '/org/freedesktop/NetworkManager'
SETTINGS = ROOT + '/Settings'
DEVICE = NM + '.Device'
ACTIVE = NM + '.Connection.Active'
CONNECTION = NM + '.Settings.Connection'
NAT_HELP = 'Use NAT networking instead, or connect a wired Ethernet adapter and retry.'


def value(settings, group, key, default=None):
    item = settings.get(group, {}).get(key)
    return item.unpack() if item is not None else default


class NetworkManager:
    """Small synchronous D-Bus adapter; all calls run in the existing job worker."""
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    def call(self, path, interface, method, signature=None, *args):
        return self.bus.call_sync(NM, path, interface, method,
            self.GLib.Variant(signature, args) if signature else None, None,
            self.Gio.DBusCallFlags.NONE, 15000, None)

    def props(self, path, interface):
        return self.call(path, 'org.freedesktop.DBus.Properties', 'GetAll', '(s)', interface).unpack()[0]

    def settings(self, path):
        # Preserve the exact D-Bus types of addresses, routes, DNS and options.
        groups = self.call(path, CONNECTION, 'GetSettings').get_child_value(0)
        result = {}
        for index in range(groups.n_children()):
            entry = groups.get_child_value(index)
            props = entry.get_child_value(1)
            result[entry.get_child_value(0).get_string()] = {
                props.get_child_value(i).get_child_value(0).get_string():
                props.get_child_value(i).get_child_value(1).get_variant()
                for i in range(props.n_children())}
        return result

    def devices(self):
        result = []
        for path in self.call(ROOT, NM, 'GetDevices').unpack()[0]:
            device = self.props(path, DEVICE)
            device['path'] = path
            device['physical'] = (Path('/sys/class/net') / device['Interface'] / 'device').exists()
            active = device.get('ActiveConnection', '/')
            device['active'] = self.props(active, ACTIVE) if active != '/' else {}
            if device['active']:
                device['settings'] = self.settings(device['active']['Connection'])
            result.append(device)
        return result

    def profiles(self):
        return [self.settings(path) for path in
                self.call(SETTINGS, NM + '.Settings', 'ListConnections').unpack()[0]]

    def checkpoint(self, device):
        # Disconnect newly created devices on automatic rollback. Do not use
        # DELETE_NEW_CONNECTIONS: another application might create a profile.
        return self.call(ROOT, NM, 'CheckpointCreate', '(aouu)', [device], 150, 4).unpack()[0]

    def add(self, settings):
        return self.call(SETTINGS, NM + '.Settings', 'AddConnectionUnsaved',
                         '(a{sa{sv}})', settings).unpack()[0]

    def activate(self, profile, device='/'):
        return self.call(ROOT, NM, 'ActivateConnection', '(ooo)', profile, device, '/').unpack()[0]

    def ready(self, bridge_active, port_active, original):
        bridge = self.props(bridge_active, ACTIVE)
        port = self.props(port_active, ACTIVE)
        if bridge.get('State') == 4 or port.get('State') == 4:
            raise RuntimeError('NetworkManager could not activate the bridge or its Ethernet port.')
        if bridge.get('State') != 2 or port.get('State') != 2:
            return False
        for family in (4, 6):
            if original['active'].get('Default' if family == 4 else 'Default6') and not bridge.get('Default' if family == 4 else 'Default6'):
                return False
            if original['active'].get(f'Ip{family}Config', '/') != '/':
                path = bridge.get(f'Ip{family}Config', '/')
                if path == '/' or not self.props(path, NM + f'.IP{family}Config').get('AddressData'):
                    return False
        return True

    def save(self, path, settings):
        self.call(path, CONNECTION, 'Update', '(a{sa{sv}})', settings)

    def delete(self, path):
        self.call(path, CONNECTION, 'Delete')

    def rollback(self, checkpoint):
        result = self.call(ROOT, NM, 'CheckpointRollback', '(o)', checkpoint).unpack()[0]
        if any(code != 0 for code in result.values()):
            raise RuntimeError('NetworkManager reported an incomplete rollback.')

    def commit(self, checkpoint):
        self.call(ROOT, NM, 'CheckpointDestroy', '(o)', checkpoint)


def detect(name, nm):
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_.-]{0,14}', name) or name == 'lo':
        raise ValueError('Use an interface name such as br0 (at most 15 letters, digits, dots, underscores or hyphens).')
    devices = nm.devices()
    for device in devices:
        if device['Interface'] == name:
            if device['DeviceType'] == 13 and device.get('State') == 100:
                return {'existing': True, 'name': name, 'device': device}
            raise RuntimeError(f'{name} already exists but is not an active bridge. Review it in Control Panel → Network.')
    if any(value(profile, 'connection', 'interface-name') == name for profile in nm.profiles()):
        raise RuntimeError(f'A saved profile already owns {name}. Activate it in Control Panel → Network, or choose another bridge name.')
    candidates = [d for d in devices if d['DeviceType'] == 1 and d.get('physical')
                  and d.get('Managed') and d.get('State') == 100 and d.get('active')
                  and not value(d['settings'], 'connection', 'controller')
                  and not value(d['settings'], 'connection', 'master')]
    preferred = [d for d in candidates if d['active'].get('Default') or d['active'].get('Default6')]
    if preferred:
        candidates = preferred
    if not candidates:
        raise RuntimeError('No connected, unbridged Ethernet adapter is available. Standard Wi-Fi connections cannot act as Ethernet bridge ports. ' + NAT_HELP)
    if len(candidates) != 1:
        raise RuntimeError('More than one wired connection could be used. Select the default wired connection in Control Panel → Network first. ' + NAT_HELP)
    device = candidates[0]
    unsupported = set(device['settings']) - {'connection', '802-3-ethernet', 'ipv4', 'ipv6', 'proxy', 'ethtool'}
    if unsupported:
        raise RuntimeError('This Ethernet profile uses settings requiring manual bridge setup: ' + ', '.join(sorted(unsupported)) + '. Use Control Panel → Network, or NAT networking.')
    return {'existing': False, 'name': name, 'device': device}


def bridge_profiles(plan):
    from gi.repository import GLib
    V = GLib.Variant
    source = plan['device']['settings']; name = plan['name']
    original = source['connection']; interface = plan['device']['Interface']
    priority = min(999, value(source, 'connection', 'autoconnect-priority', 0) + 1)
    bridge_id, port_id = str(uuid.uuid4()), str(uuid.uuid4())
    connection = {k: original[k] for k in ('permissions', 'zone', 'metered', 'mdns', 'llmnr', 'dns-over-tls', 'secondaries') if k in original}
    connection.update({'id': V('s', 'Xetal KVM ' + name), 'uuid': V('s', bridge_id),
        'type': V('s', 'bridge'), 'interface-name': V('s', name),
        'autoconnect': V('b', False), 'autoconnect-priority': V('i', priority),
        'autoconnect-slaves': V('i', 1),
        'stable-id': original.get('stable-id', original['uuid'])})
    bridge = {k: dict(source[k]) for k in ('ipv4', 'ipv6', 'proxy') if k in source}
    bridge['connection'] = connection
    bridge['bridge'] = {'stp': V('b', False)}
    mac = plan['device'].get('HwAddress', '')
    if re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', mac):
        bridge['bridge']['mac-address'] = V('ay', bytes.fromhex(mac.replace(':', '')))
    if plan['device'].get('Mtu'):
        bridge['802-3-ethernet'] = {'mtu': V('u', plan['device']['Mtu'])}
    port = {k: dict(source[k]) for k in ('802-3-ethernet', 'ethtool') if k in source}
    port['connection'] = {'id': V('s', f'Xetal KVM {name} · {interface}'),
        'uuid': V('s', port_id), 'type': V('s', '802-3-ethernet'),
        'interface-name': V('s', interface), 'master': V('s', bridge_id),
        'slave-type': V('s', 'bridge'), 'autoconnect': V('b', False),
        'autoconnect-priority': V('i', priority)}
    if 'permissions' in original:
        port['connection']['permissions'] = original['permissions']
    port['bridge-port'] = {}
    return bridge, port


def create_bridge(name, nm=None, timeout=90):
    nm = nm or NetworkManager()
    plan = detect(name, nm)
    device = plan['device']
    if plan['existing']:
        return {'bridge': name, 'message': f'Existing bridge {name} selected.'}
    bridge, port = bridge_profiles(plan)
    checkpoint = nm.checkpoint(device['path'])  # refuse any mutation without recovery
    created = []
    try:
        bridge_path = nm.add(bridge); created.append(bridge_path)
        port_path = nm.add(port); created.append(port_path)
        bridge_active = nm.activate(bridge_path)
        port_active = nm.activate(port_path, device['path'])
        deadline = time.monotonic() + timeout
        while not nm.ready(bridge_active, port_active, device):
            if time.monotonic() >= deadline:
                raise RuntimeError('The bridge did not recover the host IP addresses and routes in time.')
            time.sleep(.25)
        from gi.repository import GLib
        for path, settings in ((bridge_path, bridge), (port_path, port)):
            settings['connection']['autoconnect'] = GLib.Variant('b', True)
            nm.save(path, settings)
        nm.commit(checkpoint)
    except Exception as error:
        cleanup = []
        for path in reversed(created):
            try: nm.delete(path)
            except Exception as failed: cleanup.append(str(failed))
        try:
            nm.rollback(checkpoint)
            recovery = 'NetworkManager accepted recovery of the original Ethernet connection.'
        except Exception as failed:
            cleanup.append(str(failed))
            recovery = ('Automatic recovery could not be confirmed. Your original Ethernet profile is preserved; '
                        'reconnect it in Control Panel → Network.')
        raise RuntimeError(f'Bridge setup failed: {error}\n\n{recovery}' +
                           ('\nRecovery details: ' + '; '.join(cleanup) if cleanup else '')) from error
    return {'bridge': name, 'interface': device['Interface'],
            'message': f'Bridge {name} created on {device["Interface"]} and selected. The original Ethernet profile is preserved.'}


def request(name):
    """Called in a GUI worker. Reject unsuitable connections before prompting."""
    plan = detect(name, NetworkManager())
    if plan['existing']:
        return {'bridge': name, 'message': f'Existing bridge {name} selected.'}
    from uiutil import sudo_command
    command, environment, available = sudo_command(
        [sys.executable, '-E', '-s', str(Path(__file__).resolve()), '--create', name],
        'KVM Settings: create the VM network bridge')
    if not available:
        raise RuntimeError('Administrator authentication is unavailable. Open Control Panel → Network to create a bridge.')
    result = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=200)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Bridge creation was cancelled.')
    return json.loads(result.stdout)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] != '--create' or os.geteuid() != 0:
            raise ValueError('Create a bridge from KVM Settings with administrator authentication.')
        print(json.dumps(create_bridge(sys.argv[2])))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
