#!/usr/bin/env python3
"""Read-only discovery and authenticated, persistent System Tweaks transactions."""
import base64
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import stat
import subprocess
import sys
import tempfile


def sibling(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = sibling('tweaks_runtime')
catalog = sibling('tweaks_catalog')
STATE = '/etc/hyperfusion/system-tweaks.json'
BACKUPS = '/var/lib/hyperfusion-system-tweaks'
SERVICE = '/etc/systemd/system/hyperfusion-system-tweaks.service'
BOOT = '/usr/local/lib/hyperfusion/tweaks-runtime.py'
UNIT = 'hyperfusion-system-tweaks.service'
RESUME_UNIT = 'hyperfusion-system-tweaks-resume.service'
RESUME = '/etc/systemd/system/' + RESUME_UNIT
POWER_MANAGERS = ('power-profiles-daemon.service', 'tlp.service', 'tuned.service', 'auto-cpufreq.service', 'cpupower.service')
UNITS = (UNIT, 'fstrim.timer', 'tmp.mount', *POWER_MANAGERS, RESUME_UNIT)
SYSCTLS = {
    'gaming': 'vm.max_map_count', 'swappiness': 'vm.swappiness', 'cache_pressure': 'vm.vfs_cache_pressure',
    'dirty_ratio': 'vm.dirty_ratio', 'dirty_background': 'vm.dirty_background_ratio',
    'nmi_watchdog': 'kernel.nmi_watchdog', 'ptrace': 'kernel.yama.ptrace_scope', 'dmesg': 'kernel.dmesg_restrict',
    'ipv6': 'net.ipv6.conf.all.disable_ipv6', 'tcp_congestion': 'net.ipv4.tcp_congestion_control',
    'tcp_fastopen': 'net.ipv4.tcp_fastopen', 'tcp_buffers': 'net.core.rmem_max',
    'inotify_watches': 'fs.inotify.max_user_watches', 'inotify_instances': 'fs.inotify.max_user_instances',
}


def command(args):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
    if result.returncode and not (args[:2] == ['systemctl', 'show'] and 'Id=' in result.stdout):
        raise RuntimeError((result.stderr or result.stdout).strip() or 'Command failed: ' + ' '.join(args))
    return result.stdout.strip()


def fingerprint(data):
    return hashlib.sha256(data or b'').hexdigest()


def ini_options(text, section):
    result, active = {}, False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            active = line == '[' + section + ']'
        elif active and line and not line.startswith(('#', ';')) and '=' in line:
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def update_options(text, changes, section=None):
    """Edit just the requested directives; preserve other sections and comments."""
    output, pending, active = [], dict(changes), section is None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if active:
                output.extend(k + (' = ' + str(v) if v is not True else '') for k, v in pending.items() if v is not None)
                pending.clear()
            active = stripped == '[' + section + ']' if section else True
        key = re.split(r'\s*=\s*|\s+', stripped, maxsplit=1)[0]
        if active and key in changes and not stripped.startswith(('#', ';')):
            if key in pending:
                value = pending.pop(key)
                if value is not None:
                    output.append(key + (' = ' + str(value) if value is not True else ''))
            continue
        output.append(line)
    if pending:
        if section and not active:
            output.append('[' + section + ']')
        output.extend(k + (' = ' + str(v) if v is not True else '') for k, v in pending.items() if v is not None)
    return '\n'.join(output).rstrip() + '\n'


def mount_config(text, target, source, fstype, changes, remove=False):
    result, found = [], False
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith('#') or len(fields) < 4 or fields[1] != target:
            result.append(line)
            continue
        if found:
            raise ValueError(f'Multiple {target} entries exist in /etc/fstab. Resolve them in System Configuration first.')
        found = True
        if fields[2] != fstype:
            raise ValueError(f'{target} already uses another filesystem. Review its mount configuration first.')
        if remove:
            continue
        opts = [x for x in fields[3].split(',') if x.split('=')[0] not in changes]
        opts.extend(k + ('=' + v if v else '') for k, v in changes.items())
        fields[3] = ','.join(opts)
        result.append('\t'.join(fields))
    if not found and not remove:
        opts = ','.join(k + ('=' + v if v else '') for k, v in changes.items())
        result.append(f'{source}\t{target}\t{fstype}\t{opts}\t0\t0')
    return '\n'.join(result).rstrip() + '\n'


class Engine:
    # root/run injection exists only for isolated unit tests, never as CLI flags
    # or environment overrides in an authenticated operation.
    def __init__(self, root=Path('/'), run=command):
        self.root, self.run = Path(root), run

    def path(self, name):
        return self.root / name.lstrip('/')

    def read(self, name):
        return runtime.read(self.path(name))

    def sysfile(self, key):
        return self.path('/proc/sys/' + key.replace('.', '/'))

    def state(self):
        path = self.path(STATE)
        raw = path.read_bytes() if path.exists() else b''
        state = json.loads(raw) if raw else {'version': 1, 'settings': {}, 'backups': []}
        if (not isinstance(state, dict) or state.get('version') != 1 or
                not isinstance(state.get('settings'), dict) or
                not all(k in catalog.BY_ID and isinstance(v, str) for k, v in state['settings'].items()) or
                not isinstance(state.get('backups', []), list)):
            raise ValueError('Unsupported saved System Tweaks settings.')
        return state, fingerprint(raw)

    def services(self):
        try:
            text = self.run(['systemctl', 'show', *UNITS, '--property=Id,LoadState,ActiveState,UnitFileState'])
            result = {}
            for block in text.split('\n\n'):
                fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
                if fields.get('Id'):
                    result[fields['Id']] = fields
            return result
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return {}

    def choices(self, kind):
        if kind in runtime.RUNTIME_IDS:
            labels = {'auto': 'Auto · match each drive', 'on': 'Enabled', 'off': 'Disabled',
                      'balance_performance': 'Balance performance', 'balance_power': 'Balance power',
                      'power': 'Power saving', 'performance': 'Performance', 'powersave': 'Powersave',
                      'madvise': 'Applications opt in (madvise)', 'always': 'Always', 'never': 'Never'}
            return [catalog.choice(v, labels.get(v, v.replace('_', ' ').capitalize())) for v in runtime.available(kind, self.root)]
        if kind == 'tcp_congestion':
            return [catalog.choice(v, v.upper()) for v in self.read('/proc/sys/net/ipv4/tcp_available_congestion_control').split()]
        return copy.deepcopy(catalog.BY_ID[kind].get('choices', []))

    def systemd_options(self, name, section, proposed=None):
        directories = ['/usr/lib/systemd', '/usr/local/lib/systemd', '/run/systemd', '/etc/systemd']
        result = {}
        for directory in reversed(directories):
            path = self.path(directory + '/' + name + '.conf')
            if path.exists():
                result = ini_options(runtime.read(path), section)
                break
        files = {}
        for directory in directories:
            files.update({p.name: runtime.read(p) for p in self.path(directory + '/' + name + '.conf.d').glob('*.conf')})
        if proposed is not None:
            files['zz-hyperfusion.conf'] = proposed
        for _, content in sorted(files.items()):
            result.update(ini_options(content, section))
        return result

    def dropin(self, name, section, changes):
        content = '[' + section + ']\n' + ''.join(k + '=' + v + '\n' for k, v in changes.items())
        effective = self.systemd_options(name, section, content)
        if any(effective.get(k) != v for k, v in changes.items()):
            raise ValueError('A later ' + name + ' drop-in overrides this choice. Review /etc/systemd/' + name + '.conf.d first.')
        return {'/etc/systemd/' + name + '.conf.d/zz-hyperfusion.conf': content}

    def validate(self, kind, value):
        if kind not in catalog.BY_ID or kind == 'hidden_files':
            raise ValueError('Unsupported system setting.')
        if not isinstance(value, str):
            raise ValueError('Invalid setting value.')
        row = catalog.BY_ID[kind]
        if 'minimum' in row:
            if not re.fullmatch(r'[0-9]+', value) or not row['minimum'] <= int(value) <= row['maximum']:
                raise ValueError(f"Choose a value from {row['minimum']} to {row['maximum']}.")
        elif value not in [c['value'] for c in self.choices(kind)]:
            raise ValueError('This choice is not available on this system.')

    def current(self, kind, services):
        if kind in runtime.RUNTIME_IDS:
            options = runtime.available(kind, self.root)
            if not options:
                return ''
            if kind == 'cpu_boost':
                path, inverted = runtime.boost_file(self.root)
                return 'on' if (runtime.read(path) == '1') != inverted else 'off'
            if kind == 'battery_limit':
                return ', '.join(runtime.read(p/'charge_control_end_threshold') for p in runtime.batteries(self.root))
            if kind in ('cpu_governor', 'cpu_energy'):
                name = 'scaling_governor' if kind == 'cpu_governor' else 'energy_performance_preference'
                values = {runtime.read(p/name) for p in runtime.policies(self.root)}
            elif kind == 'thp':
                values = {runtime.selected(self.read('/sys/kernel/mm/transparent_hugepage/enabled'))}
            else:
                values = {runtime.selected(runtime.read(p/'queue/scheduler')) for p in runtime.disks(self.root)}
            return next(iter(values)) if len(values) == 1 else 'Mixed: ' + ', '.join(sorted(values))
        if kind in SYSCTLS:
            value = runtime.read(self.sysfile(SYSCTLS[kind]))
            if kind == 'ipv6':
                return {'0': 'on', '1': 'off'}.get(value, '')
            if kind == 'nmi_watchdog':
                return {'0': 'off', '1': 'on'}.get(value, '')
            if kind == 'tcp_buffers':
                return str(int(value)//(1024**2)) if value.isdigit() else ''
            return value
        if kind == 'trim':
            state = services.get('fstrim.timer', {}).get('UnitFileState', '')
            return 'on' if state == 'enabled' else 'off' if state in ('disabled', 'masked') else ''
        if kind in ('tmpfs', 'hidepid'):
            for line in self.read('/proc/mounts').splitlines():
                fields = line.split()
                if len(fields) >= 4 and fields[1] == ('/tmp' if kind == 'tmpfs' else '/proc'):
                    if kind == 'tmpfs':
                        return 'on' if fields[2] == 'tmpfs' else 'off'
                    opts = dict(x.split('=', 1) for x in fields[3].split(',') if '=' in x)
                    return {'invisible': '2', 'noaccess': '1'}.get(opts.get('hidepid'), opts.get('hidepid', '0'))
            return 'off' if kind == 'tmpfs' else ''
        if kind == 'zram':
            return 'Active' if any(line.split()[0] == '/dev/zram0' for line in self.read('/proc/swaps').splitlines()[1:] if line.split()) else 'off'
        if kind == 'core_dumps':
            options = self.systemd_options('coredump', 'Coredump')
            if options.get('Storage') == 'none' and options.get('ProcessSizeMax') == '0':
                return 'off'
            return 'on' if options.get('Storage', 'external') != 'none' else 'Processing only'
        if kind == 'journal_limit':
            options = self.systemd_options('journald', 'Journal')
            value = options.get('SystemMaxUse', '')
            return value[:-1] if re.fullmatch(r'[0-9]+M', value) else value or 'Automatic'
        if kind.startswith('pacman_'):
            options = {}
            section = ''
            for line in self.read('/etc/pacman.conf').splitlines():
                line = line.strip()
                if line.startswith('['):
                    section = line
                elif section == '[options]' and line and not line.startswith('#'):
                    key, _, val = line.partition('='); options[key.strip()] = val.strip()
            return options.get('ParallelDownloads', '1') if kind == 'pacman_downloads' else (
                'candy' if 'ILoveCandy' in options and 'Color' in options else 'color' if 'Color' in options else 'plain')
        return ''

    def status(self):
        state, revision = self.state()
        services = self.services()
        rows = []
        managers = [name.removesuffix('.service') for name in POWER_MANAGERS if services.get(name, {}).get('ActiveState') == 'active']
        for original in catalog.CATALOG:
            row = copy.deepcopy(original); kind = row['id']
            if kind == 'hidden_files':
                rows.append(desktop_status(row)); continue
            current = self.current(kind, services)
            row.update(current=current, saved=state['settings'].get(kind, ''), has_backup=kind in state.get('backups', []), supported=True)
            if 'minimum' not in row:
                row['choices'] = self.choices(kind)
                row['supported'] = bool(row['choices'])
            if kind in SYSCTLS and not self.sysfile(SYSCTLS[kind]).is_file():
                row['supported'] = False
            if kind == 'zram':
                row['supported'] = self.path('/usr/lib/systemd/system-generators/zram-generator').is_file()
            if kind == 'trim':
                row['supported'] = any(self.path(p+'/fstrim.timer').exists() for p in ['/etc/systemd/system', '/usr/lib/systemd/system'])
            if kind.startswith('pacman_'):
                row['supported'] = self.path('/etc/pacman.conf').is_file()
            if kind == 'core_dumps':
                row['supported'] = 'systemd-coredump' in self.read('/proc/sys/kernel/core_pattern')
            if not row['supported']:
                row['note'] = 'Not available with this hardware or installed system components.'
            elif managers and kind.startswith('cpu_'):
                row['note'] = 'Saving this choice lets Fusion manage power and stops: ' + ', '.join(managers) + '. Restore reinstates their previous state.'
            elif kind in runtime.RUNTIME_IDS and row['saved'] and services.get(UNIT, {}).get('UnitFileState') != 'enabled':
                row['note'] = 'Saved, but the boot service is not confirmed enabled. Save & apply again to repair it.'
            if kind == 'ptrace' and (current == '3' or row['saved'] == '3'):
                row['restart'] = True
            if row['saved'] and kind in SYSCTLS:
                expected = self.sysctl_values(kind, row['saved'])
                conflicts = self.sysctl_conflicts(kind, expected)
                if conflicts:
                    row['note'] = 'A later config overrides this saved choice: ' + ', '.join(conflicts)
            for name, expected in state.get('files', {}).get(kind, {}).items():
                if name in ('/etc/fstab', '/etc/pacman.conf'):
                    continue  # Shared files also contain unrelated settings.
                path = self.path(name)
                if not path.is_file() or fingerprint(path.read_bytes()) != expected:
                    row['note'] = 'Saved configuration has since changed. Review it before saving again: ' + name
                    break
            rows.append(row)
        return {'version': 1, 'revision': revision, 'settings': rows}

    def sysctl_values(self, kind, value):
        key = SYSCTLS[kind]
        if kind == 'ipv6':
            return {key: '0' if value == 'on' else '1', 'net.ipv6.conf.default.disable_ipv6': '0' if value == 'on' else '1'}
        if kind == 'nmi_watchdog':
            return {key: '1' if value == 'on' else '0'}
        if kind == 'tcp_buffers':
            size = str(int(value)*1024**2)
            return {'net.core.rmem_max': size, 'net.core.wmem_max': size,
                    'net.ipv4.tcp_rmem': '4096 131072 ' + size, 'net.ipv4.tcp_wmem': '4096 16384 ' + size}
        if kind == 'dirty_ratio':
            return {'vm.dirty_bytes': '0', key: value}
        if kind == 'dirty_background':
            return {'vm.dirty_background_bytes': '0', key: value}
        return {key: value}

    def sysctl_conflicts(self, kind, values):
        # systemd resolves matching basenames by directory priority, then
        # applies filenames lexically. Detect later overrides before writing.
        files = {}
        for directory in ['/usr/lib/sysctl.d', '/usr/local/lib/sysctl.d', '/run/sysctl.d', '/etc/sysctl.d']:
            files.update({p.name: p for p in self.path(directory).glob('*.conf')})
        ours = 'zz-hyperfusion-' + kind + '.conf'
        conflicts = []
        for name, path in sorted(files.items()):
            if name <= ours:
                continue
            for line in runtime.read(path).splitlines():
                line = line.strip()
                if not line or line.startswith(('#', ';')) or '=' not in line:
                    continue
                key, value = (p.strip() for p in line.split('=', 1))
                key = key.lstrip('-').replace('/', '.')
                if key in values and ' '.join(value.split()) != values[key]:
                    conflicts.append(str(path)); break
        return conflicts

    def plan(self, kind, value):
        self.validate(kind, value)
        files, writes, actions = {}, {}, []
        restart = catalog.BY_ID[kind]['restart']
        if kind in SYSCTLS:
            values = self.sysctl_values(kind, value)
            if kind == 'dirty_ratio' and int(value) <= int(self.read('/proc/sys/vm/dirty_background_ratio') or '0'):
                raise ValueError('Writeback threshold must exceed background writeback.')
            if kind == 'dirty_background' and int(value) >= int(self.read('/proc/sys/vm/dirty_ratio') or '0'):
                raise ValueError('Background writeback must be below the writeback threshold.')
            if self.sysctl_conflicts(kind, values):
                raise ValueError('A later sysctl config overrides this setting. Review: ' + ', '.join(self.sysctl_conflicts(kind, values)))
            files['/etc/sysctl.d/zz-hyperfusion-' + kind + '.conf'] = '# Managed by Hyper Fusion System Tweaks\n' + ''.join(k + ' = ' + v + '\n' for k, v in values.items())
            restart = kind == 'ptrace' and (value == '3' or self.read('/proc/sys/kernel/yama/ptrace_scope') == '3')
            if not restart:
                writes = {self.sysfile(k): v for k, v in values.items()}
                if any(not p.is_file() for p in writes):
                    raise ValueError('This kernel does not provide the selected setting.')
        elif kind in runtime.RUNTIME_IDS:
            writes = runtime.targets(kind, value, self.root)
            if kind == 'cpu_governor' and value != 'performance':
                preference = self.state()[0]['settings'].get('cpu_energy')
                if preference in runtime.available('cpu_energy', self.root):
                    writes.update({p/'energy_performance_preference': preference for p in runtime.policies(self.root)})
            files[BOOT] = Path(__file__).with_name('tweaks_runtime.py').read_text()
            files[SERVICE] = ('[Unit]\nDescription=Restore Hyper Fusion CPU, memory and disk policies\n'
                'After=systemd-modules-load.service systemd-tmpfiles-setup.service systemd-sysctl.service cpupower.service '
                'power-profiles-daemon.service tlp.service tuned.service auto-cpufreq.service\n'
                'ConditionPathExists=' + STATE + '\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I ' + BOOT + '\n'
                '[Install]\nWantedBy=multi-user.target\n')
            actions = [['systemctl', 'daemon-reload'], ['systemctl', 'enable', UNIT]]
            files[RESUME] = ('[Unit]\nDescription=Restore Hyper Fusion policies after sleep\n'
                'After=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target\n'
                'ConditionPathExists=' + STATE + '\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I ' + BOOT + '\n'
                '[Install]\nWantedBy=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target\n')
            actions.append(['systemctl', 'enable', RESUME_UNIT])
            if kind.startswith('cpu_') or kind == 'battery_limit':
                # Explicit CPU choices belong to Fusion until the user changes
                # them. Do not race another daemon on every AC or battery event.
                services = self.services()
                for manager in POWER_MANAGERS:
                    info = services.get(manager, {})
                    if info.get('LoadState') == 'loaded' and info.get('UnitFileState') not in ('masked', 'masked-runtime'):
                        actions.extend([['systemctl', 'stop', manager], ['systemctl', 'mask', manager]])
        elif kind == 'zram':
            if not self.path('/usr/lib/systemd/system-generators/zram-generator').is_file():
                raise ValueError('Install zram-generator before configuring compressed swap.')
            boot_options = dict(word.split('=', 1) for word in self.read('/proc/cmdline').split() if '=' in word)
            if value != 'off' and boot_options.get('systemd.zram', '').lower() in ('0', 'no', 'off', 'false'):
                raise ValueError('The boot command line disables zram. Review that option in the boot editor first.')
            old = self.systemd_options('zram-generator', 'zram0')
            if old.get('mount-point'):
                raise ValueError('zram0 is configured as a filesystem, not swap. Review its mount-point before changing compressed swap.')
            if any(key in old for key in ('zram-fraction', 'max-zram-size')):
                raise ValueError('Legacy zram-fraction/max-zram-size options override zram-size. Migrate those options in zram-generator.conf first.')
            files = self.dropin('zram-generator', 'zram0', {'zram-size': '0' if value == 'off' else 'ram * ' + value + ' / 100',
                                                          'host-memory-limit': 'none'})
        elif kind in ('tmpfs', 'hidepid'):
            text = self.path('/etc/fstab').read_text()
            if kind == 'hidepid':
                files['/etc/fstab'] = mount_config(text, '/proc', 'proc', 'proc', {'hidepid': value})
            else:
                files['/etc/fstab'] = mount_config(text, '/tmp', 'tmpfs', 'tmpfs', {'nosuid': '', 'nodev': '', 'mode': '1777'}, value == 'off')
                actions = [['systemctl', 'unmask' if value == 'on' else 'mask', 'tmp.mount'], ['systemctl', 'daemon-reload']]
        elif kind == 'trim':
            actions = [['systemctl', 'enable' if value == 'on' else 'disable', '--now', 'fstrim.timer']]
        elif kind == 'core_dumps':
            if 'systemd-coredump' not in self.read('/proc/sys/kernel/core_pattern'):
                raise ValueError('This setting requires the systemd crash dump collector.')
            files = self.dropin('coredump', 'Coredump', {'Storage': 'external' if value == 'on' else 'none',
                                                       'ProcessSizeMax': '32G' if value == 'on' else '0'})
            if self.path('/usr/lib/systemd/system/systemd-coredumpd.service').is_file():
                actions = [['systemctl', 'try-reload-or-restart', 'systemd-coredumpd.service']]
        elif kind == 'journal_limit':
            files = self.dropin('journald', 'Journal', {'SystemMaxUse': value+'M', 'RuntimeMaxUse': value+'M'})
            actions = [['systemctl', 'restart', 'systemd-journald.service']]
        elif kind.startswith('pacman_'):
            changes = {'ParallelDownloads': value} if kind == 'pacman_downloads' else {
                'Color': True if value != 'plain' else None, 'ILoveCandy': True if value == 'candy' else None}
            files['/etc/pacman.conf'] = update_options(self.path('/etc/pacman.conf').read_text(), changes, 'options')
        else:
            raise ValueError('Unsupported setting.')
        return files, writes, actions, restart

    def snapshot(self, name):
        path = self.path(name)
        if path.is_symlink():
            raise ValueError('Configuration is a symbolic link; review it before applying: ' + name)
        if not path.exists():
            return None
        if not path.is_file():
            raise ValueError('Expected a regular configuration file: ' + name)
        return {'data': base64.b64encode(path.read_bytes()).decode(), 'mode': stat.S_IMODE(path.stat().st_mode)}

    def atomic(self, name, content, mode=0o644):
        path = self.path(name)
        if path.is_symlink():
            raise ValueError('Refusing to replace a symbolic link: ' + name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            path.unlink(missing_ok=True); return
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, delete=False) as stream:
            temp = Path(stream.name)
            try:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
                temp.chmod(mode); temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)

    def restore_file(self, name, snapshot):
        self.atomic(name, base64.b64decode(snapshot['data']) if snapshot else None,
                    snapshot['mode'] if snapshot else 0o644)

    def restore_services(self, services):
        if not services:
            return
        self.run(['systemctl', 'daemon-reload'])
        for unit, previous in services.items():
            state = previous.get('UnitFileState')
            if state == 'masked':
                self.run(['systemctl', 'mask', unit])
            elif state in ('enabled', 'disabled', 'static', '', 'enabled-runtime', 'masked-runtime'):
                self.run(['systemctl', 'unmask', unit])
                if state in ('enabled-runtime', 'masked-runtime'):
                    self.run(['systemctl', 'disable', unit])
                    self.run(['systemctl', '--runtime', 'enable' if state == 'enabled-runtime' else 'mask', unit])
                elif state != 'static' and previous.get('LoadState') != 'not-found':
                    self.run(['systemctl', 'enable' if state == 'enabled' else 'disable', unit])
            if unit == 'fstrim.timer' or unit in POWER_MANAGERS:
                self.run(['systemctl', 'start' if previous.get('ActiveState') == 'active' else 'stop', unit])

    def runtime_snapshot(self, writes, kind):
        paths = list(writes)
        # A governor change can also change EPP inside the CPU driver.
        if kind == 'cpu_governor':
            paths += [p/'energy_performance_preference' for p in runtime.policies(self.root)
                      if (p/'energy_performance_preference').is_file()]
        return {str(p.relative_to(self.root)): runtime.selected(runtime.read(p)) for p in paths}

    def restore_runtime(self, values):
        # Writing a ratio resets its bytes override and vice versa. Restore
        # the active bytes override last when it was nonzero.
        ordered = sorted(values, key=lambda n: n.endswith(('/dirty_bytes', '/dirty_background_bytes')) and values[n] != '0')
        for name in ordered:
            runtime.write_verified(self.path(name), values[name])

    def rollback(self, files, values, services, kind):
        errors = []
        def attempt(fn):
            try:
                fn()
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                errors.append(str(error))
        for unit in (UNIT, RESUME_UNIT):
            if unit in services and services[unit].get('LoadState') == 'not-found':
                attempt(lambda u=unit: self.run(['systemctl', 'disable', u]))
        for name, previous in files.items():
            attempt(lambda n=name, p=previous: self.restore_file(n, p))
        attempt(lambda: self.restore_runtime(values))
        attempt(lambda: self.restore_services(services))
        if kind == 'journal_limit':
            attempt(lambda: self.run(['systemctl', 'restart', 'systemd-journald.service']))
        if kind == 'core_dumps' and self.path('/usr/lib/systemd/system/systemd-coredumpd.service').is_file():
            attempt(lambda: self.run(['systemctl', 'try-reload-or-restart', 'systemd-coredumpd.service']))
        return errors

    def verify_services(self, kind, value):
        if kind not in runtime.RUNTIME_IDS and kind not in ('trim', 'tmpfs'):
            return
        unit = UNIT if kind in runtime.RUNTIME_IDS else 'fstrim.timer' if kind == 'trim' else 'tmp.mount'
        info = self.services().get(unit, {})
        state = info.get('UnitFileState', '')
        if kind in runtime.RUNTIME_IDS or (kind == 'trim' and value == 'on'):
            valid = state == 'enabled'
        elif kind == 'trim':
            valid = state == 'disabled'
        elif value == 'on':
            valid = state not in ('masked', 'masked-runtime', '')
        else:
            valid = state == 'masked'
        if not valid:
            raise RuntimeError('Could not verify the persistent service state for ' + unit + '.')

    def apply(self, kind, value, revision):
        state, current_revision = self.state()
        if revision != current_revision:
            raise ValueError('Saved settings changed elsewhere. Refresh status before applying.')
        files, writes, actions, restart = self.plan(kind, value)
        if any(not p.is_file() for p in writes):
            raise ValueError('A required kernel setting is unavailable.')
        before_runtime = self.runtime_snapshot(writes, kind)
        before_files = {name: self.snapshot(name) for name in files}
        before_state = self.snapshot(STATE)
        touched_units = [u for u in UNITS if any(u in cmd for cmd in actions)]
        unit_state = self.services() if touched_units else {}
        if any(u not in unit_state for u in touched_units):
            raise RuntimeError('Could not read system service state. No settings were changed.')
        previous_units = {u: unit_state[u] for u in touched_units}
        new_state = copy.deepcopy(state)
        if kind.startswith('cpu_') or kind == 'battery_limit':
            new_state.setdefault('power_services', {u: unit_state[u] for u in POWER_MANAGERS if u in previous_units})
        new_state['settings'][kind] = value
        new_state['backups'] = sorted(set(state.get('backups', [])) | {kind})
        new_state.setdefault('files', {})[kind] = {n: fingerprint(v.encode()) for n, v in files.items() if n not in (BOOT, SERVICE, RESUME)}
        try:
            for name, content in files.items():
                self.atomic(name, content.encode(), before_files[name]['mode'] if before_files[name] else 0o644)
            self.atomic(STATE, (json.dumps(new_state, indent=2) + '\n').encode())
            for path, content in writes.items():
                runtime.write_verified(path, content)
            for args in actions:
                self.run(args)
            if kind.startswith('cpu_') or kind == 'battery_limit':
                for path, content in writes.items():
                    runtime.write_verified(path, content)
            self.verify_services(kind, value)
            backup = {'version': 1, 'kind': kind, 'previous': state['settings'].get(kind),
                      'previous_files': state.get('files', {}).get(kind, {}),
                      'files': {n: v for n, v in before_files.items() if n not in (BOOT, SERVICE, RESUME)},
                      'after': {n: fingerprint(self.path(n).read_bytes()) for n in files if n not in (BOOT, SERVICE, RESUME)},
                      'runtime': before_runtime, 'services': previous_units, 'restart': restart}
            self.path(BACKUPS).mkdir(parents=True, exist_ok=True, mode=0o700)
            self.atomic(BACKUPS + '/' + kind + '.json', json.dumps(backup).encode(), 0o600)
        except Exception as error:
            rollback_errors = self.rollback({**before_files, STATE: before_state}, before_runtime, previous_units, kind)
            if rollback_errors:
                raise RuntimeError(str(error) + ' Some earlier settings could not be restored: ' + '; '.join(rollback_errors)) from error
            raise
        return {'ok': True, 'message': 'Saved permanently. Takes effect after reboot.' if restart else 'Saved permanently and applied.', 'restart': restart}

    def restore(self, kind, revision):
        if kind not in catalog.BY_ID or kind == 'hidden_files':
            raise ValueError('Unsupported setting.')
        state, actual = self.state()
        if revision != actual:
            raise ValueError('Saved settings changed elsewhere. Refresh before restoring.')
        path = self.path(BACKUPS + '/' + kind + '.json')
        backup = json.loads(path.read_text())
        if backup.get('version') != 1 or backup.get('kind') != kind:
            raise ValueError('Invalid settings backup.')
        for name, expected in backup['after'].items():
            if fingerprint(self.path(name).read_bytes()) != expected:
                raise ValueError('Configuration changed after this backup. Restore would overwrite other edits: ' + name)
        needs_restart = backup['restart'] or (kind == 'ptrace' and self.read('/proc/sys/kernel/yama/ptrace_scope') == '3')
        before_files = {name: self.snapshot(name) for name in backup['files']}
        before_files[STATE] = self.snapshot(STATE)
        values = {} if needs_restart else backup['runtime']
        before_runtime = {name: runtime.selected(runtime.read(self.path(name))) for name in values}
        services = {k: v for k, v in backup['services'].items() if k not in (UNIT, RESUME_UNIT)}
        if backup['previous'] is None:
            state['settings'].pop(kind, None)
        else:
            state['settings'][kind] = backup['previous']
        if kind.startswith('cpu_') or kind == 'battery_limit':
            services = {k:v for k,v in services.items() if k not in POWER_MANAGERS}
            if not any(k.startswith('cpu_') or k == 'battery_limit' for k in state['settings']):
                services.update(state.pop('power_services', {}))
        now_services = self.services() if services else {}
        if any(k not in now_services for k in services):
            raise RuntimeError('Could not read system service state. No settings were changed.')
        before_services = {k: now_services[k] for k in services}
        state['backups'] = [v for v in state.get('backups', []) if v != kind]
        state.setdefault('files', {})[kind] = backup.get('previous_files', {})
        try:
            for name, saved in backup['files'].items():
                self.restore_file(name, saved)
            self.restore_runtime(values)
            self.restore_services(services)
            if kind == 'journal_limit':
                self.run(['systemctl', 'restart', 'systemd-journald.service'])
            if kind == 'core_dumps' and self.path('/usr/lib/systemd/system/systemd-coredumpd.service').is_file():
                self.run(['systemctl', 'try-reload-or-restart', 'systemd-coredumpd.service'])
            self.atomic(STATE, (json.dumps(state, indent=2) + '\n').encode())
            path.unlink()
        except Exception as error:
            errors = self.rollback(before_files, before_runtime, before_services, kind)
            if errors:
                raise RuntimeError(str(error) + ' Some settings could not be restored: ' + '; '.join(errors)) from error
            raise
        return {'ok': True, 'restart': needs_restart, 'message': 'Previous settings restored.' + (' Reboot to apply.' if needs_restart else '')}


def desktop_status(row):
    from PyQt6.QtCore import QSettings
    path = Path(__file__).resolve().parents[1]/'file_manager/state/settings.ini'
    value = QSettings(str(path), QSettings.Format.IniFormat).value('hidden', False, type=bool)
    row.update(current='on' if value else 'off', saved='on' if value else 'off', supported=True, has_backup=False)
    return row


def desktop_apply(value):
    if value not in ('on', 'off'):
        raise ValueError('Choose Enabled or Disabled.')
    from PyQt6.QtCore import QSettings
    path = Path(__file__).resolve().parents[1]/'file_manager/state/settings.ini'
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.setValue('hidden', value == 'on'); settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError('Could not save Fusion Files preferences.')
    return {'ok': True, 'message': 'Saved for future Fusion Files windows. Existing per-folder choices are preserved.'}


def check_client():
    poll = select.poll(); poll.register(0, select.POLLHUP | select.POLLERR)
    if poll.poll(0):
        raise RuntimeError('Control Panel closed before authentication completed.')


def main(args):
    engine = Engine()
    if args == ['status']:
        return engine.status()
    if len(args) != 4 or args[0] not in ('apply', '--apply', 'restore', '--restore'):
        raise ValueError('Use status, or apply/restore SETTING VALUE REVISION.')
    action, kind, value, revision = args
    if kind not in catalog.BY_ID:
        raise ValueError('Unknown setting.')
    if kind == 'hidden_files' and action == 'apply':
        return desktop_apply(value)
    if action in ('apply', 'restore'):
        os.execv('/usr/bin/pkexec', ['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/python3', '-I',
                 str(Path(__file__).resolve()), '--' + action, kind, value, revision])
    if os.geteuid() != 0:
        raise PermissionError('Administrator authentication is required.')
    fd = os.open('/run/hyperfusion-system-tweaks.lock', os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another System Tweaks change is still running.') from error
        check_client()
        return engine.apply(kind, value, revision) if action == '--apply' else engine.restore(kind, revision)


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise RuntimeError('The operation was interrupted.')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        print(json.dumps(main(sys.argv[1:])), flush=True)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}), flush=True)
        raise SystemExit(1)
