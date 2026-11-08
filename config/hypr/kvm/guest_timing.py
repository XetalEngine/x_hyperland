#!/usr/bin/env python3
"""Apply the loaded custom module's CPU timing setting after Windows boots."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time

import module_state


def guest_state(path, expected_name):
    """Bounded, read-only QMP handshake with the selected KVM guest."""
    deadline = time.monotonic() + 10
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        try:
            client.connect(str(path))
        except FileNotFoundError:
            return 'shut off'
        with client.makefile('rb') as stream:
            def receive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('QMP did not respond within 10 seconds')
                client.settimeout(remaining)
                line = stream.readline(65537)
                if not line or len(line) > 65536 or not line.endswith(b'\n'):
                    raise ValueError('QMP closed or returned an incomplete/oversized reply')
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError('Invalid QMP reply')
                return message

            if 'QMP' not in receive():
                raise ValueError('The socket did not provide a QMP greeting')

            def query(command):
                request_id = 'guest-timing-' + command
                client.sendall(json.dumps({'execute': command, 'id': request_id}).encode() + b'\n')
                while True:
                    reply = receive()
                    if 'event' in reply or reply.get('id') != request_id:
                        continue
                    if 'error' in reply:
                        raise ValueError(f'QMP {command} failed: {reply["error"]}')
                    result = reply.get('return')
                    if not isinstance(result, dict):
                        raise ValueError(f'Invalid QMP {command} result')
                    return result

            query('qmp_capabilities')
            name = query('query-name').get('name')
            if name != expected_name:
                raise ValueError(f'QMP guest is {name!r}, expected {expected_name!r}')
            if query('query-kvm').get('enabled') is not True:
                raise ValueError('The selected guest is not using KVM acceleration')
            status = query('query-status')
            state = status.get('status')
            if not isinstance(state, str) or not state:
                raise ValueError('QMP did not return a guest state')
            if state == 'running' and status.get('running') is not True:
                raise ValueError('QMP did not confirm that the guest CPUs are running')
            return state


def apply(action, qmp, domain):
    if action not in ('on', 'off'):
        raise ValueError('Choose CPUID interception on or off')
    if os.geteuid() != 0:
        raise RuntimeError('Run the host helper with sudo; enter your Linux administrator password when prompted.')
    module_state.verified()
    if action == 'off':
        state = guest_state(qmp, domain)
        if state != 'running':
            raise RuntimeError(f'{domain} is {state}; boot Windows to its desktop before running this helper.')
    # Recheck after talking to QMP before touching a module-global parameter.
    module_state.verified()
    parameter = module_state.SYS_MODULE/'kvm_amd/parameters/intercept_cpuid'
    expected = ('Y', '1') if action == 'on' else ('N', '0')
    if parameter.read_text().strip() not in expected:
        parameter.write_text(expected[1]+'\n')
    if parameter.read_text().strip() not in expected:
        raise RuntimeError('The kernel did not retain the requested CPUID setting.')
    if action == 'off':
        print('CPU timing enabled: CPUID interception is OFF; guest CPUID executes directly.')
        print('Before restarting Windows within this VM, run this BAT with the on argument.')
    else:
        print('CPUID interception is ON; ready for the next Windows boot.')
    print('Scope: all AMD KVM guests on this host.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--cpuid', choices=('on', 'off'), default='off')
    actions.add_argument('--status', action='store_true')
    parser.add_argument('--qmp', required=True, type=Path)
    parser.add_argument('--domain', default='win10')
    args = parser.parse_args(argv)
    if not args.qmp.is_absolute() or not args.domain:
        raise ValueError('Choose an absolute QMP socket path and a guest name.')
    if args.status:
        record = module_state.verified()
        print('Verified custom KVM modules: '+record['kernel'])
        print('Guest: '+args.domain+' ('+guest_state(args.qmp, args.domain)+')')
        parameter = module_state.SYS_MODULE/'kvm_amd/parameters/intercept_cpuid'
        print('CPUID interception: '+parameter.read_text().strip()+' (Y/1 = intercepted, N/0 = native)')
    else:
        apply(args.cpuid, args.qmp, args.domain)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print('KVM CPU timing: '+str(error), file=sys.stderr)
        sys.exit(1)
