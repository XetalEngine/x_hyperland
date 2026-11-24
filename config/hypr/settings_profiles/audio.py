"""Record live device selection, channel volumes and mute without numeric IDs."""
import json
import subprocess


def run(args):
    result = subprocess.run(['pactl', *args], capture_output=True, text=True, timeout=10)
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'The audio service is unavailable.')
    return result.stdout.strip()


def capture(command=run):
    result = {'version': 1, 'devices': []}
    for kind in ('sink', 'source'):
        result['default_' + kind] = command(['get-default-' + kind])
        for device in json.loads(command(['--format=json', 'list', kind + 's'])):
            result['devices'].append({'kind': kind, 'name': device['name'], 'mute': device['mute'],
                'volume': [v['value'] for v in device['volume'].values()]})
    return validate(result)


def validate(value):
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('devices'), list) or len(value['devices']) > 256:
        raise ValueError('Invalid audio settings.')
    for name in ('default_sink', 'default_source'):
        if not isinstance(value.get(name), str) or len(value[name]) > 1024 or value[name].startswith('-'): raise ValueError('Invalid default audio device.')
    for d in value['devices']:
        if (d.get('kind') not in ('sink', 'source') or not isinstance(d.get('name'), str) or d['name'].startswith('-')
                or len(d['name']) > 1024 or type(d.get('mute')) is not bool or not isinstance(d.get('volume'), list)
                or not 1 <= len(d['volume']) <= 64 or any(type(v) is not int or not 0 <= v <= 655360 for v in d['volume'])):
            raise ValueError('Invalid saved audio device.')
    return value


def restore(value, command=run):
    validate(value)
    for kind in ('sink', 'source'):
        known = {d['name'] for d in json.loads(command(['--format=json', 'list', kind + 's']))}
        if value['default_' + kind] in known: command(['set-default-' + kind, value['default_' + kind]])
        for device in value['devices']:
            if device['kind'] != kind or device['name'] not in known: continue
            command(['set-' + kind + '-volume', device['name'], *map(str, device['volume'])])
            command(['set-' + kind + '-mute', device['name'], '1' if device['mute'] else '0'])
