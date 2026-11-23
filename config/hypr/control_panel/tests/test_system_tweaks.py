"""Transactions run against a synthetic machine; never change the host."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('system_tweaks', Path(__file__).parents[1]/'system_tweaks.py')
tweaks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tweaks)


class Services:
    def __init__(self):
        self.calls = []
        self.units = {u: dict(Id=u, LoadState='loaded', ActiveState='inactive', UnitFileState='disabled') for u in tweaks.UNITS}
        self.units[tweaks.UNIT]['LoadState'] = 'not-found'
        self.units[tweaks.UNIT]['UnitFileState'] = ''
        self.units['tmp.mount']['UnitFileState'] = 'static'
        self.fail = None

    def __call__(self, args):
        self.calls.append(args)
        if self.fail and self.fail(args):
            self.fail = None
            raise RuntimeError('Injected service failure')
        if args[1] == 'show':
            return '\n\n'.join('\n'.join(k+'='+v for k, v in unit.items()) for unit in self.units.values())
        action = args[1]
        if args[-1] in self.units:
            unit = self.units[args[-1]]
            if action in ('enable', 'disable', 'mask', 'unmask'):
                unit.update(LoadState='loaded', UnitFileState={'enable': 'enabled', 'disable': 'disabled', 'mask': 'masked', 'unmask': 'disabled'}[action])
            if '--now' in args or action in ('start', 'stop'):
                unit['ActiveState'] = 'active' if action in ('enable', 'start') else 'inactive'
        return ''


@pytest.fixture
def machine(tmp_path):
    def put(name, data):
        path = tmp_path/name.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path
    for n in (0, 1):
        base = f'/sys/devices/system/cpu/cpufreq/policy{n}/'
        for key, value in {'scaling_available_governors': 'powersave performance', 'scaling_governor': 'powersave',
                           'energy_performance_available_preferences': 'performance balance_performance balance_power power',
                           'energy_performance_preference': 'balance_performance'}.items():
            put(base+key, value)
    put('/sys/devices/system/cpu/cpufreq/boost', '1')
    put('/sys/kernel/mm/transparent_hugepage/enabled', 'always [madvise] never')
    for name, rotating in [('nvme0n1', '0'), ('sda', '1')]:
        put(f'/sys/block/{name}/queue/scheduler', '[none] mq-deadline bfq')
        put(f'/sys/block/{name}/queue/rotational', rotating)
    for kind, key in tweaks.SYSCTLS.items():
        put('/proc/sys/'+key.replace('.', '/'), '1')
    for key, value in {'vm.dirty_ratio': '20', 'vm.dirty_bytes': '0', 'vm.dirty_background_ratio': '10',
                       'vm.dirty_background_bytes': '0', 'vm.swappiness': '60',
                       'net.ipv4.tcp_congestion_control': 'cubic', 'net.ipv4.tcp_available_congestion_control': 'reno cubic',
                       'net.ipv6.conf.default.disable_ipv6': '0', 'net.core.wmem_max': '4194304',
                       'net.ipv4.tcp_rmem': '4096\t131072\t4194304', 'net.ipv4.tcp_wmem': '4096\t16384\t4194304',
                       'kernel.core_pattern': '|/usr/lib/systemd/systemd-coredump'}.items():
        put('/proc/sys/'+key.replace('.', '/'), value)
    put('/proc/swaps', 'Filename Type Size Used Priority\n/dev/zram0 partition 4096 0 100\n')
    put('/proc/mounts', 'proc /proc proc rw,relatime 0 0\ntmpfs /tmp tmpfs rw,nosuid,nodev 0 0\n')
    put('/etc/fstab', '# Keep this comment\nUUID=abc / ext4 defaults 0 1\n')
    put('/etc/pacman.conf', '# User preferences\n[options]\nParallelDownloads = 5\nColor\n# Custom\n[core]\nInclude = /etc/pacman.d/mirrorlist\n')
    put('/usr/lib/systemd/system-generators/zram-generator', '')
    put('/usr/lib/systemd/system/fstrim.timer', '[Timer]\nOnCalendar=weekly\n')
    services = Services()
    engine = tweaks.Engine(tmp_path, services)
    engine.put, engine.service_stub = put, services
    return engine


def apply(machine, kind, value):
    return machine.apply(kind, value, machine.state()[1])


def restore(machine, kind):
    return machine.restore(kind, machine.state()[1])


def test_governor_survives_boot_without_cpupower(machine):
    apply(machine, 'cpu_governor', 'performance')
    assert machine.service_stub.units[tweaks.UNIT]['UnitFileState'] == 'enabled'
    assert '/usr/local/lib/hyperfusion/tweaks-runtime.py' in machine.read(tweaks.SERVICE)
    for policy in tweaks.runtime.policies(machine.root):
        assert (policy/'scaling_governor').read_text().strip() == 'performance'
        (policy/'scaling_governor').write_text('powersave')
    tweaks.runtime.boot(machine.root)
    assert {tweaks.runtime.read(p/'scaling_governor') for p in tweaks.runtime.policies(machine.root)} == {'performance'}
    assert machine.path(tweaks.BOOT).read_text() == Path(tweaks.runtime.__file__).read_text()


def test_saved_energy_reapplied_after_leaving_performance(machine):
    apply(machine, 'cpu_energy', 'balance_power')
    apply(machine, 'cpu_governor', 'performance')
    for p in tweaks.runtime.policies(machine.root):
        (p/'energy_performance_preference').write_text('performance')
    apply(machine, 'cpu_governor', 'powersave')
    assert machine.current('cpu_energy', {}) == 'balance_power'


@pytest.mark.parametrize('kind,value', [('cpu_governor', 'ondemand'), ('cpu_governor', 'performance; rm'),
                                       ('cpu_energy', 'bad'), ('swappiness', '-1'), ('swappiness', '201'),
                                       ('ptrace', '4'), ('ptrace', '0\n1'), ('not_a_setting', '1')])
def test_rejects_unsupported_values_without_files(machine, kind, value):
    with pytest.raises(ValueError):
        apply(machine, kind, value)
    assert not machine.path(tweaks.STATE).exists()


def test_governors_intersect_all_cpu_policies(machine):
    machine.put('/sys/devices/system/cpu/cpufreq/policy1/scaling_available_governors', 'powersave')
    assert [c['value'] for c in machine.choices('cpu_governor')] == ['powersave']


def test_ptrace_is_persistent_and_keeps_old_config(machine):
    old = machine.put('/etc/sysctl.d/10-ptrace.conf', 'kernel.yama.ptrace_scope = 1\n')
    result = apply(machine, 'ptrace', '0')
    assert not result['restart']
    assert machine.read('/proc/sys/kernel/yama/ptrace_scope') == '0'
    assert 'kernel.yama.ptrace_scope = 0' in machine.read('/etc/sysctl.d/zz-hyperfusion-ptrace.conf')
    assert old.read_text() == 'kernel.yama.ptrace_scope = 1\n'
    restore(machine, 'ptrace')
    assert machine.read('/proc/sys/kernel/yama/ptrace_scope') == '1'
    assert not machine.path('/etc/sysctl.d/zz-hyperfusion-ptrace.conf').exists()


@pytest.mark.parametrize('current,requested', [('1', '3'), ('3', '0'), ('3', '1'), ('3', '3')])
def test_irreversible_ptrace_mode_is_only_scheduled(machine, current, requested):
    machine.put('/proc/sys/kernel/yama/ptrace_scope', current)
    assert apply(machine, 'ptrace', requested)['restart']
    assert machine.read('/proc/sys/kernel/yama/ptrace_scope') == current
    assert machine.state()[0]['settings']['ptrace'] == requested


def test_sysctl_conflict_preflight_and_directory_precedence(machine):
    machine.put('/usr/lib/sysctl.d/zzz-policy.conf', 'kernel.yama.ptrace_scope = 2\n')
    with pytest.raises(ValueError, match='later sysctl'):
        apply(machine, 'ptrace', '0')
    assert not machine.path(tweaks.STATE).exists()
    machine.put('/etc/sysctl.d/zzz-policy.conf', '# Vendor config masked\n')
    apply(machine, 'ptrace', '0')


def test_atomic_rollback_on_partial_kernel_failure(machine, monkeypatch):
    before = {str(p): p.read_bytes() for p in machine.path('/proc/sys').rglob('*') if p.is_file()}
    original = tweaks.runtime.write_verified
    failed = False
    def write(path, value):
        nonlocal failed
        if path.name == 'wmem_max' and not failed:
            failed = True
            raise OSError('Injected kernel failure')
        original(path, value)
    monkeypatch.setattr(tweaks.runtime, 'write_verified', write)
    with pytest.raises(OSError):
        apply(machine, 'tcp_buffers', '64')
    assert not machine.path(tweaks.STATE).exists()
    assert not machine.path('/etc/sysctl.d/zz-hyperfusion-tcp_buffers.conf').exists()
    for name, previous in before.items():
        assert Path(name).read_text().split() == previous.decode().split()


def test_boot_service_failure_rolls_back_files_and_all_policies(machine):
    machine.service_stub.fail = lambda args: args[1] == 'enable'
    with pytest.raises(RuntimeError, match='Injected'):
        apply(machine, 'cpu_governor', 'performance')
    assert machine.current('cpu_governor', {}) == 'powersave'
    assert not machine.path(tweaks.STATE).exists()
    assert not machine.path(tweaks.SERVICE).exists()
    assert not machine.path(tweaks.BOOT).exists()


def test_failed_restore_rolls_back_to_current_and_keeps_backup(machine, monkeypatch):
    apply(machine, 'ptrace', '0')
    state = machine.path(tweaks.STATE).read_bytes()
    original = tweaks.runtime.write_verified
    failed = False
    def write(path, value):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError('Restore failed')
        original(path, value)
    monkeypatch.setattr(tweaks.runtime, 'write_verified', write)
    with pytest.raises(OSError, match='Restore failed'):
        restore(machine, 'ptrace')
    assert machine.path(tweaks.STATE).read_bytes() == state
    assert machine.read('/proc/sys/kernel/yama/ptrace_scope') == '0'
    assert ' = 0' in machine.read('/etc/sysctl.d/zz-hyperfusion-ptrace.conf')
    assert machine.path(tweaks.BACKUPS+'/ptrace.json').exists()


def test_restoring_one_choice_preserves_other_saved_choices(machine):
    apply(machine, 'ptrace', '0'); apply(machine, 'swappiness', '80')
    restore(machine, 'ptrace')
    assert machine.state()[0]['settings'] == {'swappiness': '80'}


def test_restore_refuses_to_clobber_subsequent_manual_edit(machine):
    apply(machine, 'ptrace', '0')
    machine.put('/etc/sysctl.d/zz-hyperfusion-ptrace.conf', '# important manual change\n')
    with pytest.raises(ValueError, match='overwrite other edits'):
        restore(machine, 'ptrace')


def test_stale_editor_revision_is_rejected(machine):
    revision = machine.state()[1]
    apply(machine, 'ptrace', '0')
    with pytest.raises(ValueError, match='changed elsewhere'):
        machine.apply('swappiness', '80', revision)


@pytest.mark.parametrize('kind,value', [('zram', '50'), ('zram', 'off'), ('tmpfs', 'on'), ('tmpfs', 'off'), ('hidepid', '2')])
def test_mount_and_swap_changes_wait_for_reboot(machine, kind, value):
    before = machine.read('/proc/mounts'), machine.read('/proc/swaps')
    assert apply(machine, kind, value)['restart']
    assert (machine.read('/proc/mounts'), machine.read('/proc/swaps')) == before
    assert not any('swapoff' in a or 'remount' in a or 'stop' in a for a in machine.service_stub.calls)
    assert 'UUID=abc / ext4 defaults 0 1' in machine.read('/etc/fstab')


def test_mount_configuration_preserves_options_and_rejects_duplicates():
    text = '# comment\nproc /proc proc defaults,gid=123,hidepid=1 0 0\n'
    result = tweaks.mount_config(text, '/proc', 'proc', 'proc', {'hidepid': '2'})
    assert 'defaults,gid=123,hidepid=2' in result and '# comment' in result
    with pytest.raises(ValueError, match='Multiple'):
        tweaks.mount_config(text+text, '/proc', 'proc', 'proc', {'hidepid': '0'})


def test_pacman_edits_preserve_repo_sections_and_comments(machine):
    apply(machine, 'pacman_appearance', 'candy')
    apply(machine, 'pacman_downloads', '8')
    text = machine.path('/etc/pacman.conf').read_text()
    assert text.count('ParallelDownloads = 8') == 1 and 'ILoveCandy' in text
    assert '[core]\nInclude = /etc/pacman.d/mirrorlist' in text and '# Custom' in text
    apply(machine, 'pacman_appearance', 'plain')
    assert 'Color' not in machine.read('/etc/pacman.conf')
    assert 'ParallelDownloads = 8' in machine.read('/etc/pacman.conf')


def test_later_systemd_dropin_is_not_silently_overridden(machine):
    machine.put('/etc/systemd/journald.conf.d/zzz-local.conf', '[Journal]\nSystemMaxUse=64M\n')
    with pytest.raises(ValueError, match='later journald'):
        apply(machine, 'journal_limit', '512')
    assert not machine.path(tweaks.STATE).exists()


def test_dirty_bytes_restored_last_when_originally_active(machine, monkeypatch):
    machine.put('/proc/sys/vm/dirty_ratio', '0')
    machine.put('/proc/sys/vm/dirty_bytes', '104857600')
    original = tweaks.runtime.write_verified
    def emulate_kernel(path, value):
        original(path, value)
        if path.name == 'dirty_ratio': (path.parent/'dirty_bytes').write_text('0')
        if path.name == 'dirty_bytes': (path.parent/'dirty_ratio').write_text('0')
    monkeypatch.setattr(tweaks.runtime, 'write_verified', emulate_kernel)
    apply(machine, 'dirty_ratio', '30')
    restore(machine, 'dirty_ratio')
    assert machine.read('/proc/sys/vm/dirty_bytes') == '104857600'
    assert machine.read('/proc/sys/vm/dirty_ratio') == '0'


def test_systemd_and_scalar_settings_persist(machine):
    for kind, value in [('core_dumps', 'off'), ('journal_limit', '256'), ('trim', 'on'), ('tcp_fastopen', '3'),
                        ('dmesg', '0'), ('inotify_watches', '1048576'), ('inotify_instances', '2048'), ('ipv6', 'on')]:
        apply(machine, kind, value)
        assert machine.state()[0]['settings'][kind] == value
    assert machine.current('core_dumps', {}) == 'off'
    assert machine.current('journal_limit', {}) == '256'
    assert machine.service_stub.units['fstrim.timer']['UnitFileState'] == 'enabled'


def test_backup_access_is_private(machine):
    apply(machine, 'ptrace', '0')
    assert machine.path(tweaks.BACKUPS).stat().st_mode & 0o777 == 0o700
    assert machine.path(tweaks.BACKUPS+'/ptrace.json').stat().st_mode & 0o777 == 0o600


def test_symlink_configuration_is_never_replaced(machine):
    target = machine.put('/etc/real.conf', 'preserve me')
    path = machine.path('/etc/sysctl.d/zz-hyperfusion-ptrace.conf')
    path.parent.mkdir(parents=True)
    path.symlink_to(target)
    with pytest.raises(ValueError, match='symbolic link'):
        apply(machine, 'ptrace', '0')
    assert target.read_text() == 'preserve me'


def test_kernel_readback_accepts_whitespace_normalization(tmp_path):
    # Real sysctl arrays are tab separated, even when written with spaces.
    class KernelFile:
        name = 'tcp_rmem'
        def write_text(self, text): self.text = text.replace(' ', '\t')
        def read_text(self): return self.text
    tweaks.runtime.write_verified(KernelFile(), '4096 131072 67108864')


def test_service_that_did_not_stay_enabled_is_not_reported_as_success(machine):
    runner = machine.run
    def ignore_enable(args):
        return '' if args[1:2] == ['enable'] else runner(args)
    machine.run = ignore_enable
    with pytest.raises(RuntimeError, match='verify the persistent service state'):
        apply(machine, 'cpu_governor', 'performance')
    assert machine.current('cpu_governor', {}) == 'powersave'
    assert not machine.path(tweaks.STATE).exists()


def test_cpu_driver_side_effects_are_included_in_restore(machine, monkeypatch):
    original = tweaks.runtime.write_verified
    def driver(path, value):
        original(path, value)
        if path.name == 'scaling_governor' and value == 'performance':
            (path.parent/'energy_performance_preference').write_text('performance')
    monkeypatch.setattr(tweaks.runtime, 'write_verified', driver)
    apply(machine, 'cpu_governor', 'performance')
    assert machine.current('cpu_energy', {}) == 'performance'
    restore(machine, 'cpu_governor')
    assert machine.current('cpu_governor', {}) == 'powersave'
    assert machine.current('cpu_energy', {}) == 'balance_performance'


@pytest.mark.parametrize('config', ['zram-fraction=0.5', 'max-zram-size=4096'])
def test_legacy_zram_overrides_require_migration(machine, config):
    machine.put('/etc/systemd/zram-generator.conf', '[zram0]\n'+config+'\n')
    with pytest.raises(ValueError, match='Legacy'):
        apply(machine, 'zram', '50')
    assert not machine.path(tweaks.STATE).exists()


def test_persistence_only_restore_after_ptrace_mode3_boot(machine):
    apply(machine, 'ptrace', '3')
    machine.put('/proc/sys/kernel/yama/ptrace_scope', '3')
    assert restore(machine, 'ptrace')['restart']
    assert machine.read('/proc/sys/kernel/yama/ptrace_scope') == '3'
    assert not machine.path('/etc/sysctl.d/zz-hyperfusion-ptrace.conf').exists()


@pytest.mark.parametrize('option', ['0', 'false', 'off', 'no'])
def test_zram_boot_command_line_override_is_not_ignored(machine, option):
    machine.put('/proc/cmdline', 'quiet systemd.zram='+option)
    with pytest.raises(ValueError, match='boot command line disables'):
        apply(machine, 'zram', '50')
    assert not machine.path(tweaks.STATE).exists()


def test_swap_setting_does_not_change_zram_filesystem(machine):
    machine.put('/etc/systemd/zram-generator.conf', '[zram0]\nmount-point=/var/tmp\n')
    with pytest.raises(ValueError, match='filesystem, not swap'):
        apply(machine, 'zram', 'off')


def test_requested_zram_capacity_is_not_blocked_by_an_old_ram_ceiling(machine):
    machine.put('/etc/systemd/zram-generator.conf', '[zram0]\nhost-memory-limit=4096\ncompression-algorithm=zstd\n')
    apply(machine, 'zram', '50')
    effective = machine.systemd_options('zram-generator', 'zram0')
    assert effective['host-memory-limit'] == 'none'
    assert effective['compression-algorithm'] == 'zstd'


def test_status_reports_conflicts_and_external_changes(machine, monkeypatch):
    monkeypatch.setattr(tweaks, 'desktop_status', lambda row: row)
    apply(machine, 'ptrace', '0')
    machine.put('/etc/sysctl.d/zzz-policy.conf', 'kernel.yama.ptrace_scope = 2\n')
    rows = {r['id']: r for r in machine.status()['settings']}
    assert 'later config overrides' in rows['ptrace']['note']
    machine.put('/etc/sysctl.d/zz-hyperfusion-ptrace.conf', '# changed externally')
    rows = {r['id']: r for r in machine.status()['settings']}
    assert 'since changed' in rows['ptrace']['note']


def test_cpu_policy_masks_competing_daemon_and_restores_after_undo(machine):
    manager='power-profiles-daemon.service'
    machine.service_stub.units[manager].update(ActiveState='active',UnitFileState='enabled')
    apply(machine,'cpu_governor','performance')
    assert machine.service_stub.units[manager]['UnitFileState']=='masked'
    assert ['systemctl','stop',manager] in machine.service_stub.calls
    assert 'After=suspend.target' in machine.read(tweaks.RESUME)
    assert machine.service_stub.units[tweaks.RESUME_UNIT]['UnitFileState']=='enabled'
    restore(machine,'cpu_governor')
    assert machine.service_stub.units[manager]['UnitFileState']=='enabled'
    assert ['systemctl','start',manager] in machine.service_stub.calls


def test_charge_limit_survives_resume_and_refuses_conflicting_threshold(machine):
    machine.put('/sys/class/power_supply/BAT0/type','Battery')
    machine.put('/sys/class/power_supply/BAT0/charge_control_end_threshold','100')
    machine.put('/sys/class/power_supply/BAT0/charge_control_start_threshold','40')
    apply(machine,'battery_limit','80')
    machine.put('/sys/class/power_supply/BAT0/charge_control_end_threshold','100')
    tweaks.runtime.boot(machine.root)
    assert machine.read('/sys/class/power_supply/BAT0/charge_control_end_threshold')=='80'
    machine.put('/sys/class/power_supply/BAT0/charge_control_start_threshold','90')
    with pytest.raises(ValueError,match='start threshold'):apply(machine,'battery_limit','80')


def test_restoring_one_cpu_choice_keeps_other_saved_choices_in_control(machine):
    manager='power-profiles-daemon.service'
    machine.service_stub.units[manager].update(ActiveState='active',UnitFileState='enabled')
    apply(machine,'cpu_governor','powersave')
    apply(machine,'cpu_energy','balance_power')
    restore(machine,'cpu_governor')
    assert machine.service_stub.units[manager]['UnitFileState']=='masked'
    restore(machine,'cpu_energy')
    assert machine.service_stub.units[manager]['UnitFileState']=='enabled'
