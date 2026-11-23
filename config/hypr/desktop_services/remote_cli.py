#!/usr/bin/env python3
"""Private JSON bridge for Control Panel's native RDP/VNC hosting tab."""
import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_services import remote
from desktop_services.common import install_packages, monitors

ACTIONS = frozenset(('refresh', 'status', 'save', 'start', 'stop', 'install'))
MAX_REQUEST = 16384


def snapshot():
    return dict(status=remote.status(), has_password=(remote.DIRECTORY/'password').is_file(),
                components={name: bool(remote.executable(name)) for name in ('vnc', 'rdp')})


def execute(action, request):
    if action not in ACTIONS:
        raise ValueError('Unknown remote desktop action.')
    if not isinstance(request, dict):
        raise ValueError('Invalid remote desktop request.')
    if action in ('save', 'start'):
        values, password = request.get('values'), request.get('password', '')
        if not isinstance(values, dict) or not isinstance(password, str):
            raise ValueError('Invalid remote desktop settings.')
        remote.save(values, password)
        if action == 'start':
            remote.start()
    elif action == 'stop':
        remote.stop()
    elif action == 'install':
        protocol = request.get('protocol')
        if protocol == 'vnc':
            install_packages(['wayvnc'])
        elif protocol == 'rdp':
            # Keep build progress off the JSON channel, including child output.
            result = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('build.py')), 'hypr-rdp'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=1800)
            if result.returncode:
                raise RuntimeError('RDP component could not be built.\n' + result.stderr[-3000:])
        else:
            raise ValueError('Choose VNC or RDP.')
    result = snapshot()
    if action == 'refresh':
        result.update(preferences=remote.preferences(), monitors=monitors(), addresses=remote.addresses())
    return result


def redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, '[hidden]')
        return value
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    return value


def main():
    request = {}
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ACTIONS:
            raise ValueError('Unknown remote desktop action.')
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError('Remote desktop request is too large.')
        request = json.loads(raw or b'{}')
        result = dict(ok=True, **execute(sys.argv[1], request))
    except Exception as error:
        result = dict(ok=False, error=str(error))
        try:
            result.update(snapshot())
        except Exception:
            pass
    secrets = [request.get('password', '')] if isinstance(request, dict) and isinstance(request.get('password', ''), str) else []
    try:
        secrets.append((remote.DIRECTORY/'password').read_text())
    except OSError:
        pass
    print(json.dumps(redact(result, secrets)), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
