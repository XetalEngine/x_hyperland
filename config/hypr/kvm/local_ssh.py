"""Explicit, authenticated setup of a separate SSH endpoint for local VM access.

No host changes happen during import, preview or Copy. The managed service has
its own config/port, permits only opted-in users from private IPv4 networks, and
does not alter the administrator's existing SSH service or firewall defaults.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guest_connection import PORT, PRIVATE_NETWORKS, USER

SERVICE = 'xetal-kvm-ssh.service'
CONFIG = Path('/etc/ssh/xetal-kvm-local.conf')
UNIT = Path('/etc/systemd/system') / SERVICE
MARKER = '# Managed by HyperFusion local SSH\n'
SOURCES = ('127.0.0.0/8', *(str(network) for network in PRIVATE_NETWORKS))


def configuration(users):
    return MARKER + '# Users: ' + ' '.join(sorted(users)) + '\n' + f'''Port {PORT}
AddressFamily inet
ListenAddress 0.0.0.0
PermitRootLogin no
PermitEmptyPasswords no
PasswordAuthentication yes
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM yes
DisableForwarding yes
PermitTunnel no
X11Forwarding no
UseDNS no
LoginGraceTime 30
MaxAuthTries 3
MaxStartups 10:30:30
''' + 'AllowUsers ' + ' '.join(user + '@' + source for user in sorted(users) for source in SOURCES) + '\n'


def unit(binary):
    return MARKER + f'''[Unit]
Description=HyperFusion SSH for local networks
After=network.target

[Service]
Type=simple
ExecStartPre=/usr/bin/install -d -m 0755 /run/sshd
ExecStartPre={binary} -t -f {CONFIG}
ExecStart={binary} -D -e -f {CONFIG}
ExecReload=/bin/kill -HUP $MAINPID
KillMode=process
Restart=on-failure
RestartSec=3
IPAddressDeny=any
IPAddressAllow=localhost
''' + ''.join(f'IPAddressAllow={source}\n' for source in SOURCES[1:]) + '''
[Install]
WantedBy=multi-user.target
'''


class System:
    def run(self, args, *, check=True, timeout=30):
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout,
                                env={**os.environ, 'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL':'C'})
        if check and result.returncode:
            raise RuntimeError((result.stderr or result.stdout or 'Command failed: ' + ' '.join(args))[-3000:].strip())
        return result

    def which(self, command):
        return shutil.which(command, path='/usr/sbin:/usr/bin:/sbin:/bin')

    def active(self, service):
        return self.run(['systemctl', 'is-active', '--quiet', service], check=False).returncode == 0

    def enabled(self, service):
        return self.run(['systemctl', 'is-enabled', '--quiet', service], check=False).returncode == 0

    def ensure_server(self):
        binary = self.which('sshd')
        if binary:
            return binary
        if self.which('pacman'):
            self.run(['pacman', '-S', '--needed', '--noconfirm', 'openssh'], timeout=600)
        elif self.which('dnf'):
            self.run(['dnf', 'install', '-y', 'openssh-server'], timeout=600)
        elif self.which('apt-get'):
            # Debian's package otherwise starts the general-purpose SSH server.
            # Temporary masks cover only absent units and are removed afterward.
            masked = []
            try:
                for name in ('ssh.service', 'ssh.socket'):
                    state = self.run(['systemctl', 'show', '-p', 'LoadState', '--value', name]).stdout.strip()
                    if state != 'not-found':
                        raise RuntimeError('An existing SSH unit needs attention. Install openssh-server with your package manager, then retry.')
                    self.run(['systemctl', 'mask', '--runtime', name]); masked.append(name)
                self.run(['apt-get', 'install', '-y', 'openssh-server'], timeout=600)
            finally:
                for name in masked:
                    self.run(['systemctl', 'disable', name], check=False)
                    self.run(['systemctl', 'unmask', '--runtime', name])
        else:
            raise RuntimeError('Install the OpenSSH server with your distribution package manager, then retry.')
        binary = self.which('sshd')
        if not binary:
            raise RuntimeError('OpenSSH installation did not provide sshd.')
        return binary

    def banner(self):
        with socket.create_connection(('127.0.0.1', PORT), timeout=3) as peer:
            peer.settimeout(3)
            if not peer.recv(255).startswith(b'SSH-2.0-'):
                raise RuntimeError('The local SSH endpoint did not return an SSH greeting.')

    def port_available(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: probe.bind(('0.0.0.0', PORT))
            except OSError as error:
                raise RuntimeError(f'Port {PORT} is already in use; local SSH was not changed.') from error


def firewall_commands(system):
    """Return only missing, source-restricted rules and their exact inverse."""
    changes = []
    if system.which('firewall-cmd') and system.active('firewalld.service'):
        zones = system.run(['firewall-cmd', '--get-active-zones']).stdout.splitlines()
        zones = [line.strip() for line in zones if line and not line[0].isspace()]
        if not zones:
            zones = [system.run(['firewall-cmd', '--get-default-zone']).stdout.strip()]
        for zone in zones:
            for source in SOURCES[1:]:
                rule = f'rule family="ipv4" source address="{source}" port port="{PORT}" protocol="tcp" accept'
                for scope in ([], ['--permanent']):
                    prefix = ['firewall-cmd', *scope, '--zone='+zone]
                    if system.run([*prefix, '--query-rich-rule='+rule], check=False).returncode:
                        changes.append(([*prefix, '--add-rich-rule='+rule], [*prefix, '--remove-rich-rule='+rule]))
    if system.which('ufw'):
        status = system.run(['ufw', 'status']).stdout
        if status.startswith('Status: active'):
            # UFW treats identical rules as idempotent; only remove rules we add.
            existing = system.run(['ufw', 'show', 'added']).stdout
            for source in SOURCES[1:]:
                rule = ['allow', 'from', source, 'to', 'any', 'port', str(PORT), 'proto', 'tcp']
                if 'ufw ' + ' '.join(rule) not in existing:
                    changes.append((['ufw', *rule], ['ufw', '--force', 'delete', *rule]))
    return changes


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, pending = tempfile.mkstemp(prefix='.xetal-ssh-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.chmod(pending, 0o644)
        os.replace(pending, path)
    finally:
        if os.path.exists(pending): os.unlink(pending)


def enable(user, system=None, root=Path('/')):
    """Bounded transaction. Tests supply a temporary root and fake commands."""
    if not USER.fullmatch(user) or user == 'root':
        raise ValueError('Choose a normal Linux account for local SSH.')
    system = system or System()
    config = root / CONFIG.relative_to('/'); service = root / UNIT.relative_to('/')
    old = {}
    for path in (config, service):
        if path.is_symlink(): raise RuntimeError(f'{path} is a symlink; review it before enabling local SSH.')
        previous = path.read_text() if path.exists() else None
        if previous is not None and not previous.startswith(MARKER):
            raise RuntimeError(f'{path} is not managed by HyperFusion; it was left unchanged.')
        old[path] = previous
    users = {user}
    if old[config]:
        for line in old[config].splitlines():
            if line.startswith('# Users: '): users.update(line[9:].split())
    if any(not USER.fullmatch(name) or name == 'root' for name in users):
        raise RuntimeError('The managed SSH user list is invalid.')
    was_active = system.active(SERVICE); was_enabled = system.enabled(SERVICE)
    if not was_active:
        system.port_available()
    binary = system.ensure_server()
    system.run(['ssh-keygen', '-A'])
    changes = firewall_commands(system); applied = []
    try:
        atomic_write(config, configuration(users)); atomic_write(service, unit(binary))
        system.run(['/usr/bin/install', '-d', '-m', '0755', '/run/sshd'])
        system.run([binary, '-t', '-f', str(config)])
        for forward, inverse in changes:
            result = system.run(forward)
            # UFW may canonicalize an existing rule differently in `show added`.
            # A duplicate is not ours to remove if a later setup step fails.
            duplicate = forward[0] == 'ufw' and 'Skipping adding existing rule' in result.stdout
            if not duplicate: applied.append(inverse)
        system.run(['systemctl', 'daemon-reload'])
        system.run(['systemctl', 'enable', SERVICE])
        system.run(['systemctl', 'restart' if was_active else 'start', SERVICE])
        if not system.active(SERVICE): raise RuntimeError('The local SSH service did not start.')
        # Type=simple can become active before sshd opens its listening socket.
        import time
        for attempt in range(10):
            try: system.banner(); break
            except OSError:
                if attempt == 9: raise
                time.sleep(.15)
    except Exception as error:
        recovery = []
        for command in ([['systemctl', 'stop', SERVICE]] + list(reversed(applied)) +
                        ([['systemctl', 'disable', SERVICE]] if not was_enabled else [])):
            try: system.run(command)
            except Exception as failed: recovery.append(str(failed))
        for path, previous in old.items():
            try:
                if previous is None: path.unlink(missing_ok=True)
                else: atomic_write(path, previous)
            except OSError as failed: recovery.append(str(failed))
        for command in [['systemctl', 'daemon-reload']] + ([['systemctl', 'start', SERVICE]] if was_active else []):
            try: system.run(command)
            except Exception as failed: recovery.append(str(failed))
        raise RuntimeError(f'Local SSH setup failed: {error}' + ('\nRecovery needs attention: ' + '; '.join(recovery) if recovery else '\nPrevious SSH configuration restored.')) from error
    return {'port': PORT, 'message': f'Local SSH enabled for {user}. Click Copy, then run the script in Windows and use your Linux password.'}


def request():
    from uiutil import sudo_command
    command, environment, available = sudo_command(
        [sys.executable, '-I', str(Path(__file__).resolve()), '--enable', str(os.getuid())],
        'KVM Settings: enable SSH from local networks')
    if not available: raise RuntimeError('Administrator authentication is unavailable.')
    result = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=700)
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'Local SSH setup was cancelled.')
    return json.loads(result.stdout)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--enable', type=int, required=True)
        args = parser.parse_args()
        if os.geteuid() != 0 or args.enable <= 0 or int(os.environ.get('SUDO_UID', '-1')) != args.enable:
            raise ValueError('Enable local SSH from KVM Settings using your normal account and administrator authentication.')
        account = pwd.getpwuid(args.enable)
        fd = os.open('/run/xetal-kvm-ssh.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            print(json.dumps(enable(account.pw_name)))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
