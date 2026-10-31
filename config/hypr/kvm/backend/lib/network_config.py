"""Keep the network selector, launch hooks and QEMU command in agreement."""
import json
import re


def configure(cfg, mode, bridge='', ifname=''):
    if mode not in ('tap', 'user'):
        raise ValueError('Choose bridged Ethernet or NAT networking.')
    raw = str(cfg.simple.get('netdev', ''))
    try:
        previous = json.loads(raw)
    except ValueError:
        previous = dict(pair.split('=', 1) for pair in raw.split(',') if '=' in pair)
        previous['type'] = raw.split(',')[0]
    if not isinstance(previous, dict):
        previous = {}
    spec = dict(previous) if previous.get('type') == mode else {'id': previous.get('id', 'hostnet0')}
    spec['type'] = mode
    if mode == 'tap':
        ifname = ifname or cfg.network.get('ifname') or 'vm2tap0'
        for name in (bridge, ifname):
            if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_.-]{0,14}', name) or name == 'lo':
                raise ValueError('Enter a valid bridge and tap interface name (at most 15 characters).')
        for key in ('fd', 'fds'):
            spec.pop(key, None)
        spec.update(ifname=ifname, script='no', downscript='no')
    else:
        bridge = ifname = ''
    cfg.simple['netdev'] = json.dumps(spec, separators=(',', ':'))
    cfg.network.update(mode=mode, bridge=bridge, ifname=ifname)
