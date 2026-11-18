"""Allowlisted CPU/memory/disk policies, shared by the editor and boot service."""
import json
from pathlib import Path
import re
import sys

RUNTIME_IDS = ('cpu_governor', 'cpu_energy', 'cpu_boost', 'thp', 'io_scheduler')


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def policies(root=Path('/')):
    return sorted((root/'sys/devices/system/cpu/cpufreq').glob('policy[0-9]*'))


def disks(root=Path('/')):
    return [p for p in sorted((root/'sys/block').glob('*'))
            if re.fullmatch(r'(nvme\d+n\d+|sd[a-z]+|vd[a-z]+|mmcblk\d+)', p.name)
            and (p/'queue/scheduler').is_file()]


def available(kind, root=Path('/')):
    if kind in ('cpu_governor', 'cpu_energy'):
        name = 'scaling_available_governors' if kind == 'cpu_governor' else 'energy_performance_available_preferences'
        sets = [set(read(p/name).split()) for p in policies(root)]
        return sorted(set.intersection(*sets) - {'custom'}) if sets else []
    if kind == 'cpu_boost':
        return ['off', 'on'] if boost_file(root)[0].is_file() else []
    if kind == 'thp':
        return read(root/'sys/kernel/mm/transparent_hugepage/enabled').replace('[', '').replace(']', '').split()
    if kind == 'io_scheduler':
        sets = [set(read(p/'queue/scheduler').replace('[', '').replace(']', '').split()) for p in disks(root)]
        return ['auto', *sorted(set.intersection(*sets))] if sets else []
    return []


def boost_file(root):
    intel = root/'sys/devices/system/cpu/intel_pstate/no_turbo'
    return (intel, True) if intel.is_file() else (root/'sys/devices/system/cpu/cpufreq/boost', False)


def targets(kind, value, root=Path('/')):
    if kind not in RUNTIME_IDS or value not in available(kind, root):
        raise ValueError('This choice is not supported by the current hardware or driver.')
    if kind == 'cpu_governor':
        return {p/'scaling_governor': value for p in policies(root)}
    if kind == 'cpu_energy':
        if value != 'performance' and any(read(p/'scaling_governor') == 'performance' for p in policies(root)):
            raise ValueError('The performance governor controls energy preference. Select powersave before changing this preference.')
        return {p/'energy_performance_preference': value for p in policies(root)}
    if kind == 'cpu_boost':
        path, inverted = boost_file(root)
        return {path: str(int((value == 'on') != inverted))}
    if kind == 'thp':
        return {root/'sys/kernel/mm/transparent_hugepage/enabled': value}
    result = {}
    for disk in disks(root):
        options = read(disk/'queue/scheduler').replace('[', '').replace(']', '').split()
        preference = (('bfq', 'mq-deadline', 'none') if read(disk/'queue/rotational') == '1'
                      else ('none', 'mq-deadline') if disk.name.startswith('nvme') else ('mq-deadline', 'none'))
        selected = next((s for s in preference if s in options), options[0]) if value == 'auto' else value
        result[disk/'queue/scheduler'] = selected
    return result


def selected(text):
    match = re.search(r'\[([^]]+)\]', text)
    return match[1] if match else text


def write_verified(path, value):
    path.write_text(value + '\n')
    if ' '.join(selected(read(path)).split()) != ' '.join(value.split()):
        raise RuntimeError(f'The kernel did not accept {path.name} = {value}.')


def boot(root=Path('/')):
    state = json.loads((root/'etc/hyperfusion/system-tweaks.json').read_text())
    failures = []
    for kind in RUNTIME_IDS:
        value = state.get('settings', {}).get(kind)
        if value is None:
            continue
        # The performance governor owns EPP. Retain the saved preference for
        # when the governor is changed back, without failing the boot service.
        if kind == 'cpu_energy' and any(read(p/'scaling_governor') == 'performance' for p in policies(root)):
            continue
        try:
            for path, content in targets(kind, value, root).items():
                write_verified(path, content)
        except (OSError, ValueError, RuntimeError) as error:
            failures.append(f'{kind}: {error}')
    if failures:
        raise RuntimeError('\n'.join(failures))


if __name__ == '__main__':
    try:
        boot()
    except (OSError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
