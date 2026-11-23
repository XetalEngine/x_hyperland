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


def block_descriptors(plan, argv, descriptors):
    """Give QEMU approved disk handles without reopening private host paths.

    The guest retains no capabilities. Its root in a new user namespace cannot
    reopen another UID's 0600 files, even when those files are bind mounted.
    QEMU fdsets duplicate already-authorized descriptors instead.
    """
    inputs = {}
    def remember(path, direct=False, readonly=False):
        if isinstance(path, str) and path.startswith('/'):
            modes = inputs.setdefault(path, set())
            modes.add((False, direct))
            if not readonly: modes.add((True, direct))
    def collect(value):
        if isinstance(value, dict):
            if value.get('driver') in ('file', 'host_device'):
                remember(value.get('filename'), value.get('cache', {}).get('direct') is True,
                         value.get('read-only') is True)
            for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
    for index, option in enumerate(argv[:-1]):
        value = argv[index+1]
        if option == '-blockdev': collect(json.loads(value))
        elif option == '-drive':
            fields = dict(part.split('=', 1) for part in value.replace(',,', '\0').split(',') if '=' in part)
            remember(fields.get('file', '').replace('\0', ','), fields.get('cache') in ('none', 'directsync'),
                     fields.get('readonly') in ('on', 'yes', 'true'))
        elif option in ('-hda', '-hdb', '-hdc', '-hdd', '-fda', '-fdb', '-pflash', '-cdrom'):
            remember(value, readonly=option == '-cdrom')
    sets = [int(m.group(1)) for i, arg in enumerate(argv[:-1]) if arg == '-add-fd'
            for m in [re.search(r'(?:^|,)set=(\d+)(?:,|$)', argv[i+1])] if m]
    next_set = max(sets, default=-1) + 1
    replacements, additions = {}, []
    for path, modes in sorted(inputs.items()):
        if any(Path(path).is_relative_to(plan[key]) for key in ('approved_snapshot', 'workdir')): continue
        disk = next((item for item in plan.get('approved_disks', []) if item['path'] == path), None)
        if not disk and any(Path(path).is_relative_to(prefix) for prefix in ('/proc', '/sys', '/dev', '/etc', '/run')):
            raise ValueError('This VM path requires ordinary administrator authentication: '+path)
        identity = None
        for writable, direct in sorted(modes):
            try:
                fd = (device_file(disk, writable=writable, direct=direct) if disk else
                      user_file(path, plan['uid'], writable=writable, direct=direct))
            except OSError as error:
                if writable and error.errno in (errno.EACCES, errno.EPERM, errno.EROFS): continue
                raise
            descriptors.append(fd)
            info = os.fstat(fd); current = (info.st_dev, info.st_ino, info.st_rdev)
            if identity is not None and current != identity:
                raise RuntimeError('A VM file changed while opening it. Launch again: '+path)
            identity = current
            additions += ['-add-fd', f'fd={fd},set={next_set}']
        replacements[path] = f'/dev/fdset/{next_set}'; next_set += 1
    def replace(value):
        if isinstance(value, dict): return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list): return [replace(item) for item in value]
        return replacements.get(value, value) if isinstance(value, str) else value
    rewritten = list(argv)
    for index, option in enumerate(argv[:-1]):
        value = argv[index+1]
        if option == '-blockdev': rewritten[index+1] = json.dumps(replace(json.loads(value)))
        elif option == '-drive':
            fields = value.replace(',,', '\0').split(',')
            rewritten[index+1] = ','.join('file='+replacements.get(part[5:].replace('\0', ','), part[5:].replace('\0', ',')).replace(',', ',,')
                if part.startswith('file=') else part.replace('\0', ',,') for part in fields)
        elif option in ('-hda', '-hdb', '-hdc', '-hdd', '-fda', '-fdb', '-pflash', '-cdrom'):
            rewritten[index+1] = replacements.get(value, value)
    return [rewritten[0], *additions, *rewritten[1:]]


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
        if candidate.is_relative_to('/usr') or candidate.is_relative_to('/dev/fdset') or path in ('/dev/null', '/dev/random', '/dev/urandom'): continue
        disk = next((record for record in plan.get('approved_disks', []) if record['path'] == path), None)
        if disk:
            raise ValueError('Approved physical disks must use a QEMU block device: '+path)
        if any(candidate.is_relative_to(prefix) for prefix in ('/proc', '/sys', '/dev', '/etc', '/run')):
            raise ValueError('This VM path requires ordinary administrator authentication: '+path)
        fd = user_file(path, plan['uid'])
        descriptors.append(fd)
        if os.fstat(fd).st_size > 64*1024*1024:
            raise ValueError('Large VM inputs must use a QEMU block device: '+path)
        # ACPI/SMBIOS and other small inputs become read-only private copies.
        # Read their held descriptors directly, without resolving /proc links
        # through a user-owned 0700 directory in the new user namespace.
        command += ['--perms', '0444', '--ro-bind-data', str(fd), path]
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
            if self.plan.get('tpm'):
                endpoint = self.plan['tpm']['sock']
                for index, option in enumerate(argv[:-1]):
                    if option != '-chardev': continue
                    fields = argv[index+1].replace(',,', '\0').split(',')
                    if 'path='+endpoint.replace(',', '\0') not in fields: continue
                    # The socket lives in a user-owned directory. Connect as
                    # that user so replacing it cannot delegate root's socket
                    # credentials or access to a privileged host service.
                    with desktop_user(self.plan['uid']):
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                            connection.connect(endpoint)
                            fd = connection.detach()
                    descriptors.append(fd)
                    argv[index+1] = ','.join(f'fd={fd}' if part.startswith('path=') else part.replace('\0', ',,') for part in fields)
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
            argv = block_descriptors(self.plan, argv, descriptors)
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
