#!/usr/bin/env python3
"""Run an approved Virtual GPU guest with narrowly bounded host file access.

The frozen supervisor prepares the selected module, memory and tap. QEMU gets
only the approved component snapshot, this run's sockets and user-accessible VM
files, in a private mount/PID namespace with no Linux capabilities. Its monitor
therefore cannot open the host's root filesystem or load arbitrary host code.
"""
import contextlib
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'backend/lib'))
from launch_policy import desktop_user, user_file, device_file
from virtual_runtime import Runtime, log, stop_child


def file_paths(argv):
    """Find file-valued structured and legacy QEMU arguments, preserving spaces."""
    result = set()
    def collect(value):
        if isinstance(value, dict):
            for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
        elif isinstance(value, str) and value.startswith('/'):
            result.add(value)
    for argument in argv:
        try:
            collect(json.loads(argument))
            continue
        except (ValueError, TypeError): pass
        if argument.startswith('/'):
            result.add(argument)
        else:
            # QEMU escapes commas by doubling them. Restore them after split.
            raw = argument.replace(',,', '\0')
            for match in re.finditer(r'(?:^|[,=])(/[^,]+)', raw):
                result.add(match.group(1).replace('\0', ','))
    return result


def sandbox_command(plan, argv, descriptors):
    snapshot, workdir = Path(plan['approved_snapshot']), Path(plan['workdir'])
    command = ['/usr/bin/bwrap', '--unshare-user', '--disable-userns', '--unshare-pid', '--unshare-ipc', '--unshare-uts',
        '--unshare-cgroup-try', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
        '--ro-bind', '/usr', '/usr',
        '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run',
        '--dir', '/etc', '--ro-bind', str(snapshot), str(snapshot),
        '--bind', str(workdir), str(workdir), '--dev-bind', '/dev/kvm', '/dev/kvm',
        '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
        '--setenv', 'LANG', 'C.UTF-8', '--chdir', '/tmp']
    for directory in ('/bin', '/sbin', '/lib', '/lib64'):
        source = Path(directory)
        if source.is_symlink(): command += ['--symlink', os.readlink(source), directory]
        elif source.is_dir(): command += ['--ro-bind', directory, directory]
    for name in ('resolv.conf', 'hosts', 'nsswitch.conf', 'ld.so.cache', 'localtime'):
        path = Path('/etc')/name
        if path.exists(): command += ['--ro-bind', str(path), str(path)]
    endpoint = os.environ.get('XETAL_KVM_LAUNCH_SOCKET')
    if endpoint:
        command += ['--ro-bind', str(Path(endpoint).parent), str(Path(endpoint).parent),
                    '--setenv', 'XETAL_KVM_LAUNCH_SOCKET', endpoint]
    for path in sorted(file_paths(argv)):
        candidate = Path(path)
        if candidate.is_relative_to(snapshot) or candidate.is_relative_to(workdir): continue
        if candidate.is_relative_to('/usr') or path in ('/dev/null', '/dev/random', '/dev/urandom'): continue
        disk = next((record for record in plan.get('approved_disks', []) if record['path'] == path), None)
        if disk:
            fd = device_file(disk); descriptors.append(fd)
            command += ['--dev-bind', f'/proc/self/fd/{fd}', path]
            continue
        if any(candidate.is_relative_to(prefix) for prefix in ('/proc', '/sys', '/dev', '/etc', '/run')):
            raise ValueError('This VM path requires ordinary administrator authentication: '+path)
        try:
            fd = user_file(path, plan['uid'], writable=True)
            option = '--bind'
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EPERM, errno.EROFS): raise
            fd = user_file(path, plan['uid'])
            option = '--ro-bind'
        descriptors.append(fd)
        # The source is a held descriptor opened with the desktop account's
        # permissions. Swapping a symlink cannot substitute a root-only file.
        command += [option, f'/proc/self/fd/{fd}', path]
    return command + ['--', *argv]


def host_threads(qmp, child_pid):
    """Translate namespace thread IDs only for our own QEMU child."""
    peer, _, _ = struct.unpack('3i', qmp.sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    ancestor = peer
    while ancestor != child_pid and ancestor > 1:
        # /proc/stat's command may itself contain spaces and parentheses.
        ancestor = int(Path(f'/proc/{ancestor}/stat').read_text().rsplit(')', 1)[1].split()[1])
    if ancestor != child_pid:
        raise RuntimeError('The VM monitor belongs to another process.')
    mapping = {}
    for task in Path(f'/proc/{peer}/task').iterdir():
        for line in (task/'status').read_text().splitlines():
            if line.startswith('NSpid:'):
                mapping[int(line.split()[-1])] = int(task.name)
    return peer, mapping


class ApprovedRuntime(Runtime):
    def firmware_display(self):
        display = self.plan.get('firmware_display')
        if not display: return
        # Snapshot firmware code is read-only; writable NVRAM is a user file.
        import ovmf_display
        with desktop_user(self.plan['uid']):
            ovmf_display.apply_resolution(display['path'], display['width'], display['height'],
                self.guest_directory/'firmware-before-display.fd')

    def tpm(self):
        tpm = self.plan.get('tpm')
        if not tpm: return
        old = tpm['sock']
        tpm['sock'] = str(self.guest_directory/'tpm.sock')
        self.plan['argv'] = [arg.replace(old, tpm['sock']) for arg in self.plan['argv']]
        state = tpm['state']
        if ',' in state: raise ValueError('TPM state paths containing commas are unsupported.')
        # No privileged process opens or repairs caller-writable TPM state.
        with desktop_user(self.plan['uid']):
            if not list(Path(state).glob('tpm*-*.permall')):
                raise RuntimeError('The desktop account cannot read this VM\'s existing TPM state.')
        child = subprocess.Popen([tpm['binary'], 'socket', '--tpm2', '--tpmstate',
            f'dir={state},mode=0600,lock', '--ctrl', f'type=unixio,path={tpm["sock"]},mode=0600', '--terminate'],
            user=self.plan['uid'], group=self.plan['gid'], extra_groups=[], stdin=subprocess.DEVNULL)
        self.defer(stop_child, child)
        import time
        for _ in range(100):
            if child.poll() is not None: raise RuntimeError('swtpm stopped; see the launch log.')
            if Path(tpm['sock']).is_socket(): return
            time.sleep(.1)
        raise RuntimeError('swtpm did not create its control socket.')

    def spawn_guest(self):
        argv = list(self.plan['argv'])
        descriptors = []
        try:
            if self.plan.get('tap'):
                # Pass an already opened tap. QEMU never receives NET_ADMIN or
                # access to /dev/net/tun inside its restricted filesystem.
                fd = os.open('/dev/net/tun', os.O_RDWR | os.O_CLOEXEC)
                descriptors.append(fd)
                fcntl.ioctl(fd, 0x400454ca, struct.pack('16sH', self.plan['tap']['name'].encode(), 0x0002 | 0x1000))
                index = argv.index('-netdev') + 1
                net = json.loads(argv[index])
                for key in ('ifname', 'script', 'downscript', 'vhostfd', 'vhostfds'):
                    net.pop(key, None)
                if net.get('vhost') in (True, 'on', 'yes'):
                    vhost = os.open('/dev/vhost-net', os.O_RDWR | os.O_CLOEXEC)
                    descriptors.append(vhost); net['vhostfd'] = str(vhost)
                net['fd'] = str(fd)
                argv[index] = json.dumps(net)
            command = sandbox_command(self.plan, argv, descriptors)
            return subprocess.Popen(command, stdin=subprocess.DEVNULL, pass_fds=tuple(descriptors))
        finally:
            for fd in descriptors: os.close(fd)

    def apply_pinning(self, qmp):
        peer, mapping = host_threads(qmp, self.child.pid)
        class Monitor:
            def execute(self, command):
                result = qmp.execute(command)
                if command in ('query-cpus-fast', 'query-iothreads'):
                    result = [dict(item, **{'thread-id':mapping[item['thread-id']]}) for item in result]
                return result
        # The generic supervisor also pins non-vCPU emulator threads. Use the
        # verified host PID, never a namespace PID supplied by a monitor client.
        child = self.child
        from types import SimpleNamespace
        self.child = SimpleNamespace(pid=peer)
        try: super().apply_pinning(Monitor())
        finally: self.child = child

    def run(self):
        self.guest_directory = self.directory/'guest'
        self.guest_directory.mkdir(mode=0o700)
        os.chown(self.guest_directory, self.plan['uid'], self.plan['gid'])
        return super().run()


def main():
    plan = json.loads(Path(sys.argv[1]).read_text())
    if not Path(plan['approved_snapshot']).is_relative_to('/var/lib/hyperfusion-kvm-launch'):
        raise RuntimeError('Invalid approved VM snapshot.')
    def interrupted(*_): raise InterruptedError('VM service stopped.')
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    return ApprovedRuntime(plan).run()


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
