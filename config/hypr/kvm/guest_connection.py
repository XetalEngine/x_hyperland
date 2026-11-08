"""Recipient-local guest script rendering; never writes the shipped template."""
import fcntl
import ipaddress
import os
from pathlib import Path
import pwd
import re
import socket
import struct

PORT = 2222
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
USER = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]*\$?')


def username():
    user = pwd.getpwuid(os.getuid()).pw_name
    if os.getuid() == 0 or not USER.fullmatch(user):
        raise ValueError('Open KVM Settings as your normal Linux user.')
    return user


def local_addresses():
    """Bounded kernel queries, without DNS, external connections or processes."""
    result = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for _, name in socket.if_nameindex():
            try:
                request = struct.pack('256s', name.encode()[:15])
                value = fcntl.ioctl(sock.fileno(), 0x8915, request)  # SIOCGIFADDR
                address = socket.inet_ntoa(value[20:24])
                if any(ipaddress.ip_address(address) in network for network in PRIVATE_NETWORKS):
                    result.append((name, address))
            except OSError:
                continue
    return result


def default_interface():
    try:
        routes = [line.split() for line in Path('/proc/net/route').read_text().splitlines()[1:]]
        routes = [line for line in routes if len(line) > 7 and line[1] == '00000000'
                  and int(line[3], 16) & 1]
        return min(routes, key=lambda line: int(line[6]))[0] if routes else ''
    except (OSError, ValueError):
        return ''


def host_address(config, addresses=None, default=None):
    addresses = local_addresses() if addresses is None else addresses
    network = config.get('network', {})
    preferred = (network.get('bridge', ''), default_interface() if default is None else default)
    for interface in preferred:
        for name, address in addresses:
            if name == interface and interface:
                return address
    candidates = [(name, address) for name, address in addresses
                  if not name.startswith(('lo', 'docker', 'veth', 'virbr', 'tun', 'tap', 'vm2'))]
    if len(candidates) == 1:
        return candidates[0][1]
    if network.get('mode') == 'user':
        return '10.0.2.2'  # QEMU's standard NAT host endpoint, including offline hosts.
    if not candidates:
        raise ValueError('No local IPv4 address found. Connect Ethernet/Wi-Fi or select NAT networking, then retry Copy.')
    raise ValueError('Several local networks are available. Select the VM bridge or a default network connection, then retry Copy.')


def render(text, config, *, managed, user=None, address=None):
    """Customize only our template or an explicit login placeholder in a custom file."""
    placeholder = 'set "HOST_LOGIN=YOUR_LINUX_USER@YOUR_LINUX_HOST"'
    if not managed and placeholder not in text:
        return text
    user = username() if user is None else user
    address = host_address(config) if address is None else address
    if not USER.fullmatch(user) or ipaddress.ip_address(address).version != 4:
        raise ValueError('The guest script needs a valid Linux username and IPv4 address.')
    values = {'HOST_LOGIN': user + '@' + address}
    if managed:
        tools = config.get('tools', {}); simple = config.get('simple', {})
        qmp = simple.get('qmp', '')
        if not qmp.startswith('unix:'):
            raise ValueError('Select a Unix QMP socket before copying the guest helper.')
        values.update(HOST_PORT=str(PORT), HOST_HELPER=tools.get('vmstealth_host', ''),
                      QMP_SOCKET=qmp[5:].split(',', 1)[0],
                      GUEST_NAME=simple.get('name', 'win10').split(',', 1)[0].removeprefix('guest='))
    for key, value in values.items():
        # Values cross both cmd.exe and the remote POSIX shell. The template
        # quotes paths, and rejects characters that could break either layer.
        if not value or any(c in value for c in '\r\n\0\"\'%'):
            raise ValueError(f'{key} contains an unsupported quote, percent sign or line break; use a plain path/name for the guest helper.')
        pattern = re.compile(r'^set "' + key + r'=[^\r\n]*"(?=\r?$)', re.MULTILINE)
        text, count = pattern.subn(lambda _: f'set "{key}={value}"', text)
        if count != 1:
            raise ValueError(f'The guest script needs exactly one {key} setting.')
    return text.replace('\r\n', '\n').replace('\n', '\r\n') if managed else text
